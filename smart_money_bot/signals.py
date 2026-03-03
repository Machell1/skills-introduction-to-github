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
    LiquidityLevel,
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
        self.max_candles_for_mss: int = config.order_block.max_mss_candles

        # Monotonic tick counter for sweep age (candle indices shift on each fetch)
        self._tick_counter: int = 0
        self._sweep_tick: dict[int, int] = {}

        # Track swept price levels to prevent duplicates from recreated objects
        self._swept_prices: set[float] = set()

    def reset(self):
        """Clear all tracked state."""
        self.active_sweeps.clear()
        self._tick_counter = 0
        self._sweep_tick.clear()

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
        self._tick_counter += 1

        # ── Step 1: Check for bias alignment if required ──────────
        # (Reversal trades against the immediate move but should align
        #  with the higher-timeframe bias for higher probability)

        # ── Step 2: Detect new liquidity sweeps ───────────────────
        current_atr = atr_values[current_index] if current_index < len(atr_values) else 0.0
        liquidity_levels = self.engine.identify_liquidity_levels(
            swings, daily_levels, current_index, current_atr=current_atr,
        )
        new_sweeps = self.engine.detect_sweep(candle, liquidity_levels, current_atr=current_atr)

        for sweep in new_sweeps:
            # Skip if this price level was already swept (prevents duplicates from recreated objects)
            price_key = round(sweep.level.price, 5)
            if price_key in self._swept_prices:
                continue

            # Inducement filter: reject shallow sweeps (override for high-quality sweeps)
            min_depth = self.config.order_block.min_sweep_depth_atr
            if current_atr > 0 and sweep.sweep_depth < min_depth * current_atr:
                if sweep.sweep_quality >= 0.80:
                    logger.info(
                        "Shallow sweep ALLOWED (high quality %.2f): depth %.2f at %.2f",
                        sweep.sweep_quality, sweep.sweep_depth, sweep.level.price,
                    )
                else:
                    logger.info(
                        "Sweep REJECTED (inducement): depth %.2f < %.2f ATR at %.2f (quality=%.2f)",
                        sweep.sweep_depth, min_depth, sweep.level.price, sweep.sweep_quality,
                    )
                    continue

            # Premium/discount filter: use sweep price, not current candle close
            # (after a sell-side sweep, price bounces up into premium before MSS confirms)
            if self.config.bias_filter.premium_discount_enabled:
                sweep_ref_price = sweep.sweep_candle.low if sweep.direction == "long" else sweep.sweep_candle.high
                zone, midpoint = self.engine.get_premium_discount_zone(swings, sweep_ref_price, current_index)
                if sweep.direction == "long" and zone == "premium":
                    logger.info("Skipping long sweep at %.2f — sweep price in premium zone", sweep.level.price)
                    continue
                if sweep.direction == "short" and zone == "discount":
                    logger.info("Skipping short sweep at %.2f — sweep price in discount zone", sweep.level.price)
                    continue

            # Optional: filter by bias alignment (allow high-quality counter-bias)
            if self.config.bias_filter.require_alignment and bias:
                is_counter_bias = (
                    (sweep.direction == "long" and bias != "bullish")
                    or (sweep.direction == "short" and bias != "bearish")
                )
                if is_counter_bias:
                    if sweep.sweep_quality >= 0.80:
                        logger.info(
                            "Counter-bias sweep ALLOWED at %.2f (quality=%.2f, bias=%s) — will require R >= %.1f",
                            sweep.level.price, sweep.sweep_quality, bias,
                            self.config.bias_filter.counter_bias_min_r,
                        )
                        sweep._counter_bias = True
                    else:
                        logger.info(
                            "Skipping %s sweep at %.2f — bias is %s (quality=%.2f < 0.80)",
                            sweep.direction, sweep.level.price, bias, sweep.sweep_quality,
                        )
                        continue

            self._swept_prices.add(price_key)
            self.active_sweeps.append(sweep)
            self._sweep_tick[id(sweep)] = self._tick_counter
            logger.info(
                "Reversal: New sweep tracked | Direction: %s | Level: %.2f (%s) | Quality: %.2f",
                sweep.direction, sweep.level.price, sweep.level.source, sweep.sweep_quality,
            )

        # ── Step 3: Check active sweeps for MSS confirmation ──────
        expired_sweeps = []
        for sweep in self.active_sweeps:
            if sweep.mss_confirmed:
                continue

            # Use monotonic tick counter for age (candle indices shift on each fetch)
            sweep_tick = self._sweep_tick.get(id(sweep), self._tick_counter)
            candles_since_sweep = self._tick_counter - sweep_tick
            if candles_since_sweep > self.max_candles_for_mss:
                expired_sweeps.append(sweep)
                logger.info(
                    "Sweep EXPIRED without MSS after %d candles: %s at %.2f",
                    candles_since_sweep, sweep.direction, sweep.level.price,
                )
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

                # ── Step 4b: Check FVG confluence ─────────────────
                fvgs = self.engine.detect_fvg(candles, max(0, ob.candle_index - 3))
                fvg = self.engine.find_nearest_fvg(fvgs, mss.direction, max(0, ob.candle_index - 2), ob.midpoint, current_index)
                if fvg:
                    logger.info(
                        "FVG CONFLUENCE | %s FVG [%.2f-%.2f] overlaps OB [%.2f-%.2f]",
                        fvg.direction, fvg.low, fvg.high, ob.low, ob.high,
                    )
                elif self.config.order_block.require_fvg_confluence:
                    logger.info(
                        "Setup REJECTED: No FVG confluence for OB [%.2f-%.2f] at index %d",
                        ob.low, ob.high, ob.candle_index,
                    )
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
                    # Enforce higher min R for counter-bias trades
                    if getattr(sweep, '_counter_bias', False):
                        min_r = self.config.bias_filter.counter_bias_min_r
                        if setup.r_multiple < min_r:
                            logger.info(
                                "Counter-bias setup REJECTED: R %.2f < min %.1fR | %s at %.2f",
                                setup.r_multiple, min_r, setup.direction, setup.entry_price,
                            )
                            continue
                        logger.info("Counter-bias setup ACCEPTED: R %.2f >= min %.1fR", setup.r_multiple, min_r)
                    setup.fvg = fvg  # Attach FVG confluence (may be None)
                    ready_setups.append(setup)

        # Clean up expired sweeps — reset swept flag so level can be re-swept
        for s in expired_sweeps:
            s.level.swept = False
            self.active_sweeps.remove(s)
            self._sweep_tick.pop(id(s), None)
            self._swept_prices.discard(round(s.level.price, 5))

        # Clean up confirmed sweeps — release swept price if no setup was produced
        confirmed = [s for s in self.active_sweeps if s.mss_confirmed]
        for s in confirmed:
            self.active_sweeps.remove(s)
            self._sweep_tick.pop(id(s), None)
            price_key = round(s.level.price, 5)
            if not any(rs.sweep is s for rs in ready_setups):
                self._swept_prices.discard(price_key)

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
            logger.info("Reversal setup rejected: ATR=0 at index %d", current_index)
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

        # Compute Fibonacci OTE entry if enabled
        if self.config.order_block.use_fibonacci_entry and mss:
            sweep_ref = sweep.sweep_low if sweep.direction == "long" else sweep.sweep_high
            fib_entry = self.engine.compute_fib_entry(ob, sweep_ref, mss.break_level)
            ob.entry_price = fib_entry
            logger.info("Fibonacci OTE entry: %.2f (OB range: %.2f-%.2f)", fib_entry, ob.low, ob.high)

        if sweep.direction == "long":
            setup.entry_price = ob.entry_price
            # Stop below the lower of (sweep low, OB low) minus ATR buffer
            reference_low = min(sweep.sweep_low, ob.low)
            setup.stop_price = reference_low - b * atr
            setup.risk_distance = setup.entry_price - setup.stop_price

            if setup.risk_distance <= 0:
                logger.warning(
                    "Invalid risk distance for long setup: entry=%.2f stop=%.2f dist=%.4f",
                    setup.entry_price, setup.stop_price, setup.risk_distance,
                )
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
                        logger.info(
                            "Long liquidity target R too small: %.2fR (min %.2fR) | target=%.2f entry=%.2f",
                            raw_r, target_cfg.liquidity_min_r, liq_target, setup.entry_price,
                        )
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
                logger.warning(
                    "Invalid risk distance for short setup: entry=%.2f stop=%.2f dist=%.4f",
                    setup.entry_price, setup.stop_price, setup.risk_distance,
                )
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
                        logger.info(
                            "Short liquidity target R too small: %.2fR (min %.2fR) | target=%.2f entry=%.2f",
                            raw_r, target_cfg.liquidity_min_r, liq_target, setup.entry_price,
                        )
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

        # Track broken swing levels to prevent duplicate BOS signals
        self._broken_levels: set[float] = set()

    def reset(self):
        """Clear tracked state."""
        self._broken_levels.clear()

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
            logger.info("Continuation skipped: no daily bias available")
            return ready_setups

        # ── Detect BOS in trend direction ─────────────────────────
        bos = self.engine.detect_bos(candle, current_index, swings, atr_values, bias)
        if bos:
            # Dedup: skip if this swing level was already broken
            level_key = round(bos.break_level, 5)
            if level_key in self._broken_levels:
                return ready_setups
            self._broken_levels.add(level_key)

            logger.info(
                "Continuation: BOS detected | Direction: %s | Break: %.2f | Body: %.2f",
                bos.direction, bos.break_level, bos.displacement_body_size,
            )

            # Find the OB before the BOS candle
            ob = self.engine.find_order_block(candles, current_index, bos.direction)
            if ob is None:
                logger.info("No OB found for continuation BOS at index %d", current_index)
                return ready_setups

            # Check FVG confluence (consistent with reversal generator)
            fvgs = self.engine.detect_fvg(candles, max(0, ob.candle_index - 3))
            fvg = self.engine.find_nearest_fvg(fvgs, bos.direction, max(0, ob.candle_index - 2), ob.midpoint, current_index)
            if fvg:
                logger.info(
                    "Continuation FVG CONFLUENCE | %s FVG [%.2f-%.2f] overlaps OB [%.2f-%.2f]",
                    fvg.direction, fvg.low, fvg.high, ob.low, ob.high,
                )
            elif self.config.order_block.require_fvg_confluence:
                logger.info(
                    "Continuation setup REJECTED: No FVG confluence for OB [%.2f-%.2f] at index %d",
                    ob.low, ob.high, ob.candle_index,
                )
                return ready_setups

            # Premium/discount zone filter
            if self.config.bias_filter.premium_discount_enabled:
                zone, _ = self.engine.get_premium_discount_zone(swings, candle.close, current_index)
                if bos.direction == "bullish" and zone == "premium":
                    logger.info("Continuation REJECTED: bullish BOS in premium zone")
                    return ready_setups
                elif bos.direction == "bearish" and zone == "discount":
                    logger.info("Continuation REJECTED: bearish BOS in discount zone")
                    return ready_setups

            # Fibonacci OTE entry
            if self.config.order_block.use_fibonacci_entry and bos:
                if bos.direction == "bullish":
                    sweep_ref = candle.low
                else:
                    sweep_ref = candle.high
                fib_entry = self.engine.compute_fib_entry(ob, sweep_ref, bos.break_level)
                ob.entry_price = fib_entry

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
                setup.fvg = fvg  # Attach FVG confluence (may be None)
                ready_setups.append(setup)

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
            logger.info("Continuation setup rejected: ATR=0 at index %d", current_index)
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
                logger.warning(
                    "Invalid risk distance for bullish continuation: entry=%.2f stop=%.2f",
                    setup.entry_price, setup.stop_price,
                )
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
                if raw_r >= self.config.continuation.min_r_multiple:
                    setup.r_multiple = min(raw_r, self.config.continuation.max_r_multiple)
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
                logger.warning(
                    "Invalid risk distance for bearish continuation: entry=%.2f stop=%.2f",
                    setup.entry_price, setup.stop_price,
                )
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
                if raw_r >= self.config.continuation.min_r_multiple:
                    setup.r_multiple = min(raw_r, self.config.continuation.max_r_multiple)
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


# ── Timeframe multipliers for scaling H1 parameters to lower TFs ────
_TF_CANDLES_PER_H1 = {
    "M1": 60, "M5": 12, "M15": 4, "M30": 2, "H1": 1, "H4": 0.25,
}


class LowerTFSignalGenerator:
    """
    Multi-timeframe entry scanner.

    Uses H1 structure (swings, liquidity levels, daily bias) but scans
    lower-timeframe candles (M15, M30) for:
    - Sweeps invisible on H1 (intra-hour wick + recovery)
    - Faster MSS confirmation (displacement shows up sooner)
    - Tighter OB entries (smaller candle zones → better entry price)

    Produces TradeSetup objects identical to the H1 generators so the
    trade manager handles them the same way.
    """

    def __init__(self, config: BotConfig, engine: SMCEngine, timeframe: str):
        self.config = config
        self.engine = engine
        self.timeframe = timeframe
        self.active_sweeps: list[LiquiditySweep] = []

        # Scale MSS window to lower TF: more candles for the same wall-clock time
        tf_mult = _TF_CANDLES_PER_H1.get(timeframe, 1)
        self.max_candles_for_mss: int = int(config.order_block.max_mss_candles * tf_mult)

        # Last processed candle time to avoid re-processing
        self._last_candle_time = None

        # Monotonic tick counter for sweep age tracking (candle indices shift on each fetch)
        self._tick_counter: int = 0
        self._sweep_tick: dict[int, int] = {}  # sweep id(obj) → tick when detected

        # Track swept price levels to prevent duplicates from recreated objects
        self._swept_prices: set[float] = set()

    def reset(self):
        self.active_sweeps.clear()
        self._last_candle_time = None
        self._tick_counter = 0
        self._sweep_tick.clear()
        self._swept_prices.clear()

    def process_candles(
        self,
        ltf_candles: list[Candle],
        h1_swings: list[SwingPoint],
        daily_levels: DailyLevels,
        h1_atr: float,
        bias: Optional[str],
        h1_current_index: int = 0,
    ) -> list[TradeSetup]:
        """
        Scan lower-TF candles for new setups.

        Only processes candles newer than the last seen candle to avoid
        duplicate signals.

        Args:
            ltf_candles: M15 or M30 candle array.
            h1_swings: Swing points from H1 (structural context).
            daily_levels: PDH/PDL from daily.
            h1_atr: Current H1 ATR (used for stop buffer).
            bias: Daily bias string or None.
            h1_current_index: Current H1 candle index (for expiry/hold timing).
        """
        if not ltf_candles or len(ltf_candles) < 20:
            return []

        ready_setups = []
        ltf_atr_values = self.engine.compute_atr(ltf_candles)
        current_index = len(ltf_candles) - 1
        candle = ltf_candles[current_index]

        # Skip if we already processed this candle
        if self._last_candle_time and candle.time <= self._last_candle_time:
            return []
        self._last_candle_time = candle.time
        self._tick_counter += 1

        # ── Build liquidity levels from H1 structure ───────────────
        liquidity_levels = self.engine.identify_liquidity_levels(
            h1_swings, daily_levels, h1_current_index, current_atr=h1_atr,
        )

        # ── Detect sweeps on LTF candle ────────────────────────────
        new_sweeps = self.engine.detect_sweep(candle, liquidity_levels, current_atr=h1_atr)
        for sweep in new_sweeps:
            # Skip if this price level was already swept (prevents duplicates)
            price_key = round(sweep.level.price, 5)
            if price_key in self._swept_prices:
                continue

            if self.config.bias_filter.require_alignment and bias:
                is_counter_bias = (
                    (sweep.direction == "long" and bias != "bullish")
                    or (sweep.direction == "short" and bias != "bearish")
                )
                if is_counter_bias:
                    if sweep.sweep_quality >= 0.80:
                        logger.info(
                            "[%s] Counter-bias sweep ALLOWED at %.2f (quality=%.2f, bias=%s) — will require R >= %.1f",
                            self.timeframe, sweep.sweep_quality, sweep.level.price, bias,
                            self.config.bias_filter.counter_bias_min_r,
                        )
                        sweep._counter_bias = True
                    else:
                        logger.info(
                            "[%s] Skipping %s sweep at %.2f — bias is %s (quality=%.2f < 0.80)",
                            self.timeframe, sweep.direction, sweep.level.price, bias, sweep.sweep_quality,
                        )
                        continue

            self._swept_prices.add(price_key)
            self.active_sweeps.append(sweep)
            self._sweep_tick[id(sweep)] = self._tick_counter
            logger.info(
                "[%s] Sweep detected | Direction: %s | Level: %.2f (%s)",
                self.timeframe, sweep.direction, sweep.level.price, sweep.level.source,
            )

        # ── Check active sweeps for MSS on LTF ────────────────────
        ltf_swings = self.engine.detect_swings(ltf_candles)
        expired_sweeps = []

        for sweep in self.active_sweeps:
            if sweep.mss_confirmed:
                continue

            # Use monotonic tick counter for age (candle indices shift on each fetch)
            sweep_tick = self._sweep_tick.get(id(sweep), self._tick_counter)
            candles_since_sweep = self._tick_counter - sweep_tick
            if candles_since_sweep > self.max_candles_for_mss:
                expired_sweeps.append(sweep)
                logger.info(
                    "[%s] Sweep EXPIRED without MSS after %d candles: %s at %.2f",
                    self.timeframe, candles_since_sweep, sweep.direction, sweep.level.price,
                )
                continue

            # Use LTF swings for MSS break-level, LTF ATR for displacement
            mss = self.engine.detect_mss(candle, current_index, sweep, ltf_swings, ltf_atr_values)
            if mss:
                sweep.mss_confirmed = True
                sweep.mss_candle_index = current_index
                logger.info(
                    "[%s] MSS CONFIRMED | Direction: %s | Break: %.2f | Body: %.2f",
                    self.timeframe, mss.direction, mss.break_level, mss.displacement_body_size,
                )

                # Find OB on LTF candles (tighter zones)
                ob = self.engine.find_order_block(ltf_candles, current_index, mss.direction)
                if ob is None:
                    logger.info("[%s] No OB found after MSS at index %d", self.timeframe, current_index)
                    continue

                # Check FVG confluence on LTF candles
                ltf_fvgs = self.engine.detect_fvg(ltf_candles, max(0, ob.candle_index - 3))
                ltf_fvg = self.engine.find_nearest_fvg(ltf_fvgs, mss.direction, max(0, ob.candle_index - 2), ob.midpoint, current_index)
                if ltf_fvg:
                    logger.info(
                        "[%s] FVG CONFLUENCE | %s FVG [%.2f-%.2f] overlaps OB [%.2f-%.2f]",
                        self.timeframe, ltf_fvg.direction, ltf_fvg.low, ltf_fvg.high, ob.low, ob.high,
                    )
                elif self.config.order_block.require_fvg_confluence:
                    logger.info(
                        "[%s] Setup REJECTED: No FVG confluence for OB [%.2f-%.2f] at index %d",
                        self.timeframe, ob.low, ob.high, ob.candle_index,
                    )
                    continue

                # Premium/discount zone filter — use sweep price, not current candle close
                if self.config.bias_filter.premium_discount_enabled:
                    sweep_zone_price = sweep.sweep_candle.low if sweep.direction == "long" else sweep.sweep_candle.high
                    zone, _ = self.engine.get_premium_discount_zone(h1_swings, sweep_zone_price, h1_current_index)
                    if sweep.direction == "long" and zone == "premium":
                        logger.info("[%s] LTF REJECTED: long sweep in premium zone (sweep price %.2f)", self.timeframe, sweep_zone_price)
                        continue
                    elif sweep.direction == "short" and zone == "discount":
                        logger.info("[%s] LTF REJECTED: short sweep in discount zone (sweep price %.2f)", self.timeframe, sweep_zone_price)
                        continue

                # Fibonacci OTE entry
                if self.config.order_block.use_fibonacci_entry and mss:
                    sweep_ref = sweep.sweep_low if sweep.direction == "long" else sweep.sweep_high
                    fib_entry = self.engine.compute_fib_entry(ob, sweep_ref, mss.break_level)
                    ob.entry_price = fib_entry

                # Build setup using H1 ATR for stop buffer, LTF OB for entry
                setup = self._build_ltf_setup(
                    sweep=sweep,
                    mss=mss,
                    ob=ob,
                    ltf_candles=ltf_candles,
                    current_index=current_index,
                    h1_atr=h1_atr,
                    daily_levels=daily_levels,
                    h1_swings=h1_swings,
                    h1_current_index=h1_current_index,
                )
                if setup:
                    # Enforce higher min R for counter-bias trades
                    if getattr(sweep, '_counter_bias', False):
                        min_r = self.config.bias_filter.counter_bias_min_r
                        if setup.r_multiple < min_r:
                            logger.info(
                                "[%s] Counter-bias setup REJECTED: R %.2f < min %.1fR | %s at %.2f",
                                self.timeframe, setup.r_multiple, min_r, setup.direction, setup.entry_price,
                            )
                            continue
                        logger.info(
                            "[%s] Counter-bias setup ACCEPTED: R %.2f >= min %.1fR",
                            self.timeframe, setup.r_multiple, min_r,
                        )
                    ready_setups.append(setup)

        for s in expired_sweeps:
            s.level.swept = False
            self.active_sweeps.remove(s)
            self._sweep_tick.pop(id(s), None)
            self._swept_prices.discard(round(s.level.price, 5))

        # Clean up confirmed sweeps — release swept price if no setup was produced
        confirmed = [s for s in self.active_sweeps if s.mss_confirmed]
        for s in confirmed:
            self.active_sweeps.remove(s)
            self._sweep_tick.pop(id(s), None)
            price_key = round(s.level.price, 5)
            if not any(rs.sweep is s for rs in ready_setups):
                self._swept_prices.discard(price_key)

        return ready_setups

    def _build_ltf_setup(
        self,
        sweep: LiquiditySweep,
        mss: MarketStructureShift,
        ob: OrderBlock,
        ltf_candles: list[Candle],
        current_index: int,
        h1_atr: float,
        daily_levels: DailyLevels,
        h1_swings: list[SwingPoint],
        h1_current_index: int = 0,
    ) -> Optional[TradeSetup]:
        """Build a trade setup from lower-TF entry with H1 structure."""
        if h1_atr <= 0:
            logger.info("[%s] Setup rejected: H1 ATR=0", self.timeframe)
            return None

        b = self.config.stop.atr_buffer_multiplier
        target_cfg = self.config.target

        # Use H1 candle indices for expiry/hold since trade_manager monitors on H1
        setup = TradeSetup(
            template=f"reversal_{self.timeframe}",
            direction=sweep.direction,
            state=SetupState.ENTRY_PENDING,
            sweep=sweep,
            mss=mss,
            order_block=ob,
            signal_time=ltf_candles[current_index].time,
            signal_candle_index=h1_current_index,
            entry_expiry_index=h1_current_index + self.config.order_block.entry_expiry_candles,
            max_hold_index=h1_current_index + self.config.trade_mgmt.max_hold_candles,
        )

        if sweep.direction == "long":
            setup.entry_price = ob.entry_price
            reference_low = min(sweep.sweep_low, ob.low)
            # Use H1 ATR for stop buffer (structural level)
            setup.stop_price = reference_low - b * h1_atr
            setup.risk_distance = setup.entry_price - setup.stop_price

            if setup.risk_distance <= 0:
                logger.warning(
                    "[%s] Invalid risk distance for long: entry=%.2f stop=%.2f",
                    self.timeframe, setup.entry_price, setup.stop_price,
                )
                return None

            if target_cfg.mode == TargetMode.FIXED_R:
                setup.target_price = setup.entry_price + target_cfg.fixed_r_multiple * setup.risk_distance
                setup.r_multiple = target_cfg.fixed_r_multiple
            else:
                liq_target = daily_levels.pdh
                if liq_target <= setup.entry_price:
                    for s in reversed(h1_swings):
                        if s.type == SwingType.HIGH and s.price > setup.entry_price:
                            liq_target = s.price
                            break
                if liq_target > setup.entry_price:
                    raw_r = (liq_target - setup.entry_price) / setup.risk_distance
                    if raw_r < target_cfg.liquidity_min_r:
                        logger.info("[%s] Long liquidity R too small: %.2fR", self.timeframe, raw_r)
                        return None
                    capped_r = min(raw_r, target_cfg.liquidity_max_r)
                    setup.target_price = setup.entry_price + capped_r * setup.risk_distance
                    setup.r_multiple = capped_r
                else:
                    setup.target_price = setup.entry_price + target_cfg.fixed_r_multiple * setup.risk_distance
                    setup.r_multiple = target_cfg.fixed_r_multiple

        elif sweep.direction == "short":
            setup.entry_price = ob.entry_price
            reference_high = max(sweep.sweep_high, ob.high)
            setup.stop_price = reference_high + b * h1_atr
            setup.risk_distance = setup.stop_price - setup.entry_price

            if setup.risk_distance <= 0:
                logger.warning(
                    "[%s] Invalid risk distance for short: entry=%.2f stop=%.2f",
                    self.timeframe, setup.entry_price, setup.stop_price,
                )
                return None

            if target_cfg.mode == TargetMode.FIXED_R:
                setup.target_price = setup.entry_price - target_cfg.fixed_r_multiple * setup.risk_distance
                setup.r_multiple = target_cfg.fixed_r_multiple
            else:
                liq_target = daily_levels.pdl
                if liq_target >= setup.entry_price:
                    for s in reversed(h1_swings):
                        if s.type == SwingType.LOW and s.price < setup.entry_price:
                            liq_target = s.price
                            break
                if liq_target < setup.entry_price:
                    raw_r = (setup.entry_price - liq_target) / setup.risk_distance
                    if raw_r < target_cfg.liquidity_min_r:
                        logger.info("[%s] Short liquidity R too small: %.2fR", self.timeframe, raw_r)
                        return None
                    capped_r = min(raw_r, target_cfg.liquidity_max_r)
                    setup.target_price = setup.entry_price - capped_r * setup.risk_distance
                    setup.r_multiple = capped_r
                else:
                    setup.target_price = setup.entry_price - target_cfg.fixed_r_multiple * setup.risk_distance
                    setup.r_multiple = target_cfg.fixed_r_multiple

        setup.reward_distance = abs(setup.target_price - setup.entry_price)

        logger.info(
            "[%s] SETUP | %s | Entry: %.2f | Stop: %.2f | Target: %.2f | R: %.2f",
            self.timeframe, setup.direction.upper(), setup.entry_price,
            setup.stop_price, setup.target_price, setup.r_multiple,
        )
        return setup
