"""
Signal generators for Reversal and Continuation trade templates.

Each template follows the SMC workflow:
- Reversal: Liquidity Sweep → MSS/Displacement → OB Entry → Target Opposing Liquidity
- Continuation: BOS in Trend Direction → OB Retrace Entry → Continuation Target
"""

import logging
from typing import Optional

from .config import BotConfig, TargetMode, TemplateType
from .models import (
    Candle,
    DailyLevels,
    LiquiditySweep,
    MarketStructureShift,
    OrderBlock,
    SetupState,
    SwingPoint,
    SwingType,
    TradeSetup,
)
from .smc_engine import SMCEngine

logger = logging.getLogger(__name__)


class ReversalSignalGenerator:
    """
    Reversal Template: Sweep → MSS → OB Entry → Target Opposing Liquidity

    State machine:
    1. AWAITING_SWEEP: scan for liquidity sweeps on each new candle
    2. AWAITING_MSS: after sweep, wait up to N candles for MSS/displacement
    3. AWAITING_OB_ENTRY: OB found, compute entry/stop/target, prepare limit order
    """

    def __init__(self, config: BotConfig, engine: SMCEngine):
        self.config = config
        self.engine = engine
        self.active_sweeps: list[LiquiditySweep] = []
        self.pending_setups: list[TradeSetup] = []
        self.max_candles_for_mss: int = 6  # N: max candles after sweep to confirm MSS

    def reset(self):
        """Clear all tracked state."""
        self.active_sweeps.clear()
        self.pending_setups.clear()

    def process_candle(
        self,
        candles: list[Candle],
        current_index: int,
        swings: list[SwingPoint],
        daily_levels: DailyLevels,
        atr_values: list[float],
        bias: Optional[str],
    ) -> list[TradeSetup]:
        """
        Process one new candle through the reversal template state machine.

        Returns:
            List of new TradeSetup objects ready for order placement.
        """
        ready_setups = []
        candle = candles[current_index]

        # ── Step 1: Check for bias alignment if required ──────────
        # (Reversal trades against the immediate move but should align
        #  with the higher-timeframe bias for higher probability)

        # ── Step 2: Detect new liquidity sweeps ───────────────────
        liquidity_levels = self.engine.identify_liquidity_levels(
            swings, daily_levels, current_index,
        )
        new_sweeps = self.engine.detect_sweep(candle, liquidity_levels)

        for sweep in new_sweeps:
            # Optional: filter by bias alignment
            if self.config.bias_filter.require_alignment and bias:
                if sweep.direction == "long" and bias != "bullish":
                    logger.debug("Skipping long sweep — bias is %s", bias)
                    continue
                if sweep.direction == "short" and bias != "bearish":
                    logger.debug("Skipping short sweep — bias is %s", bias)
                    continue

            self.active_sweeps.append(sweep)
            logger.info(
                "Reversal: New sweep tracked | Direction: %s | Level: %.2f (%s)",
                sweep.direction, sweep.level.price, sweep.level.source,
            )

        # ── Step 3: Check active sweeps for MSS confirmation ──────
        expired_sweeps = []
        for sweep in self.active_sweeps:
            if sweep.mss_confirmed:
                continue

            candles_since_sweep = current_index - sweep.sweep_candle.index
            if candles_since_sweep > self.max_candles_for_mss:
                expired_sweeps.append(sweep)
                logger.debug("Sweep expired without MSS: %s at %.2f", sweep.direction, sweep.level.price)
                continue

            mss = self.engine.detect_mss(candle, current_index, sweep, swings, atr_values)
            if mss:
                sweep.mss_confirmed = True
                sweep.mss_candle_index = current_index
                logger.info(
                    "Reversal: MSS CONFIRMED | Direction: %s | Break level: %.2f | Body: %.2f",
                    mss.direction, mss.break_level, mss.displacement_body_size,
                )

                # ── Step 4: Find Order Block ──────────────────────
                ob = self.engine.find_order_block(candles, current_index, mss.direction)
                if ob is None:
                    logger.warning("No OB found after MSS at index %d", current_index)
                    continue

                # ── Step 5: Build TradeSetup ──────────────────────
                setup = self._build_setup(
                    sweep=sweep,
                    mss=mss,
                    ob=ob,
                    candles=candles,
                    current_index=current_index,
                    atr_values=atr_values,
                    daily_levels=daily_levels,
                    swings=swings,
                )
                if setup:
                    ready_setups.append(setup)
                    self.pending_setups.append(setup)

        # Clean up expired sweeps
        for s in expired_sweeps:
            self.active_sweeps.remove(s)

        return ready_setups

    def _build_setup(
        self,
        sweep: LiquiditySweep,
        mss: MarketStructureShift,
        ob: OrderBlock,
        candles: list[Candle],
        current_index: int,
        atr_values: list[float],
        daily_levels: DailyLevels,
        swings: list[SwingPoint],
    ) -> Optional[TradeSetup]:
        """Compute entry, stop, target and build a complete TradeSetup."""
        atr = atr_values[current_index] if current_index < len(atr_values) else 0.0
        if atr <= 0:
            return None

        b = self.config.stop.atr_buffer_multiplier
        target_cfg = self.config.target

        setup = TradeSetup(
            template="reversal",
            direction=sweep.direction,
            state=SetupState.ENTRY_PENDING,
            sweep=sweep,
            mss=mss,
            order_block=ob,
            signal_time=candles[current_index].time,
            signal_candle_index=current_index,
            entry_expiry_index=current_index + self.config.order_block.entry_expiry_candles,
            max_hold_index=current_index + self.config.trade_mgmt.max_hold_candles,
        )

        if sweep.direction == "long":
            setup.entry_price = ob.entry_price
            # Stop below the lower of (sweep low, OB low) minus ATR buffer
            reference_low = min(sweep.sweep_low, ob.low)
            setup.stop_price = reference_low - b * atr
            setup.risk_distance = setup.entry_price - setup.stop_price

            if setup.risk_distance <= 0:
                logger.warning("Invalid risk distance for long setup")
                return None

            # Target computation
            if target_cfg.mode == TargetMode.FIXED_R:
                setup.target_price = setup.entry_price + target_cfg.fixed_r_multiple * setup.risk_distance
                setup.r_multiple = target_cfg.fixed_r_multiple
            else:
                # Liquidity target: opposing pool (PDH for a PDL sweep)
                liq_target = daily_levels.pdh
                if liq_target <= setup.entry_price:
                    # Fall back to next swing high
                    for s in reversed(swings):
                        if s.type == SwingType.HIGH and s.price > setup.entry_price:
                            liq_target = s.price
                            break

                if liq_target > setup.entry_price:
                    raw_r = (liq_target - setup.entry_price) / setup.risk_distance
                    if raw_r < target_cfg.liquidity_min_r:
                        logger.debug("Liquidity target R too small: %.2f", raw_r)
                        return None
                    capped_r = min(raw_r, target_cfg.liquidity_max_r)
                    setup.target_price = setup.entry_price + capped_r * setup.risk_distance
                    setup.r_multiple = capped_r
                else:
                    # Fall back to fixed R
                    setup.target_price = setup.entry_price + target_cfg.fixed_r_multiple * setup.risk_distance
                    setup.r_multiple = target_cfg.fixed_r_multiple

        elif sweep.direction == "short":
            setup.entry_price = ob.entry_price
            # Stop above the higher of (sweep high, OB high) plus ATR buffer
            reference_high = max(sweep.sweep_high, ob.high)
            setup.stop_price = reference_high + b * atr
            setup.risk_distance = setup.stop_price - setup.entry_price

            if setup.risk_distance <= 0:
                logger.warning("Invalid risk distance for short setup")
                return None

            # Target computation
            if target_cfg.mode == TargetMode.FIXED_R:
                setup.target_price = setup.entry_price - target_cfg.fixed_r_multiple * setup.risk_distance
                setup.r_multiple = target_cfg.fixed_r_multiple
            else:
                # Liquidity target: PDL for a PDH sweep
                liq_target = daily_levels.pdl
                if liq_target >= setup.entry_price:
                    for s in reversed(swings):
                        if s.type == SwingType.LOW and s.price < setup.entry_price:
                            liq_target = s.price
                            break

                if liq_target < setup.entry_price:
                    raw_r = (setup.entry_price - liq_target) / setup.risk_distance
                    if raw_r < target_cfg.liquidity_min_r:
                        logger.debug("Liquidity target R too small: %.2f", raw_r)
                        return None
                    capped_r = min(raw_r, target_cfg.liquidity_max_r)
                    setup.target_price = setup.entry_price - capped_r * setup.risk_distance
                    setup.r_multiple = capped_r
                else:
                    setup.target_price = setup.entry_price - target_cfg.fixed_r_multiple * setup.risk_distance
                    setup.r_multiple = target_cfg.fixed_r_multiple

        setup.reward_distance = abs(setup.target_price - setup.entry_price)

        logger.info(
            "Reversal SETUP | %s | Entry: %.2f | Stop: %.2f | Target: %.2f | R: %.2f",
            setup.direction.upper(), setup.entry_price, setup.stop_price,
            setup.target_price, setup.r_multiple,
        )
        return setup


class ContinuationSignalGenerator:
    """
    Continuation Template: BOS in Trend Direction → OB Retrace → Continuation

    Requires a daily bias filter to determine trend direction.
    """

    def __init__(self, config: BotConfig, engine: SMCEngine):
        self.config = config
        self.engine = engine
        self.active_bos: list[MarketStructureShift] = []
        self.pending_setups: list[TradeSetup] = []

    def reset(self):
        """Clear tracked state."""
        self.active_bos.clear()
        self.pending_setups.clear()

    def process_candle(
        self,
        candles: list[Candle],
        current_index: int,
        swings: list[SwingPoint],
        daily_levels: DailyLevels,
        atr_values: list[float],
        bias: Optional[str],
    ) -> list[TradeSetup]:
        """
        Process one new candle through the continuation template.

        Returns:
            List of TradeSetup objects ready for order placement.
        """
        ready_setups = []
        candle = candles[current_index]

        if bias is None:
            return ready_setups  # Continuation requires a bias

        # ── Detect BOS in trend direction ─────────────────────────
        bos = self.engine.detect_bos(candle, current_index, swings, atr_values, bias)
        if bos:
            logger.info(
                "Continuation: BOS detected | Direction: %s | Break: %.2f | Body: %.2f",
                bos.direction, bos.break_level, bos.displacement_body_size,
            )

            # Find the OB before the BOS candle
            ob = self.engine.find_order_block(candles, current_index, bos.direction)
            if ob is None:
                logger.debug("No OB found for continuation BOS at index %d", current_index)
                return ready_setups

            # Build setup
            setup = self._build_setup(
                bos=bos,
                ob=ob,
                candles=candles,
                current_index=current_index,
                atr_values=atr_values,
                daily_levels=daily_levels,
                swings=swings,
            )
            if setup:
                ready_setups.append(setup)
                self.pending_setups.append(setup)

        return ready_setups

    def _build_setup(
        self,
        bos: MarketStructureShift,
        ob: OrderBlock,
        candles: list[Candle],
        current_index: int,
        atr_values: list[float],
        daily_levels: DailyLevels,
        swings: list[SwingPoint],
    ) -> Optional[TradeSetup]:
        """Compute entry, stop, target for a continuation setup."""
        atr = atr_values[current_index] if current_index < len(atr_values) else 0.0
        if atr <= 0:
            return None

        b = self.config.stop.atr_buffer_multiplier
        r_target = self.config.continuation.fixed_r_multiple

        setup = TradeSetup(
            template="continuation",
            direction="long" if bos.direction == "bullish" else "short",
            state=SetupState.ENTRY_PENDING,
            mss=bos,
            order_block=ob,
            signal_time=candles[current_index].time,
            signal_candle_index=current_index,
            entry_expiry_index=current_index + self.config.order_block.entry_expiry_candles,
            max_hold_index=current_index + self.config.trade_mgmt.max_hold_candles,
        )

        if bos.direction == "bullish":
            setup.entry_price = ob.entry_price
            setup.stop_price = ob.low - b * atr
            setup.risk_distance = setup.entry_price - setup.stop_price

            if setup.risk_distance <= 0:
                return None

            # Continuation target: next liquidity pool or fixed R
            next_target = None
            for s in reversed(swings):
                if s.type == SwingType.HIGH and s.price > setup.entry_price:
                    next_target = s.price
                    break
            if next_target is None:
                next_target = daily_levels.pdh if daily_levels.pdh > setup.entry_price else None

            if next_target and next_target > setup.entry_price:
                raw_r = (next_target - setup.entry_price) / setup.risk_distance
                if raw_r >= 1.2:
                    setup.r_multiple = min(raw_r, 4.0)
                    setup.target_price = setup.entry_price + setup.r_multiple * setup.risk_distance
                else:
                    setup.r_multiple = r_target
                    setup.target_price = setup.entry_price + r_target * setup.risk_distance
            else:
                setup.r_multiple = r_target
                setup.target_price = setup.entry_price + r_target * setup.risk_distance

        elif bos.direction == "bearish":
            setup.entry_price = ob.entry_price
            setup.stop_price = ob.high + b * atr
            setup.risk_distance = setup.stop_price - setup.entry_price

            if setup.risk_distance <= 0:
                return None

            next_target = None
            for s in reversed(swings):
                if s.type == SwingType.LOW and s.price < setup.entry_price:
                    next_target = s.price
                    break
            if next_target is None:
                next_target = daily_levels.pdl if daily_levels.pdl < setup.entry_price else None

            if next_target and next_target < setup.entry_price:
                raw_r = (setup.entry_price - next_target) / setup.risk_distance
                if raw_r >= 1.2:
                    setup.r_multiple = min(raw_r, 4.0)
                    setup.target_price = setup.entry_price - setup.r_multiple * setup.risk_distance
                else:
                    setup.r_multiple = r_target
                    setup.target_price = setup.entry_price - r_target * setup.risk_distance
            else:
                setup.r_multiple = r_target
                setup.target_price = setup.entry_price - r_target * setup.risk_distance

        setup.reward_distance = abs(setup.target_price - setup.entry_price)

        logger.info(
            "Continuation SETUP | %s | Entry: %.2f | Stop: %.2f | Target: %.2f | R: %.2f",
            setup.direction.upper(), setup.entry_price, setup.stop_price,
            setup.target_price, setup.r_multiple,
        )
        return setup
