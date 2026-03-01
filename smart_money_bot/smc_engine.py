"""
Smart Money Concepts (SMC) Analysis Engine.

Implements:
- ATR computation
- Fractal pivot / swing detection (no lookahead)
- PDH/PDL and swing-based liquidity level identification
- Liquidity sweep detection (wick beyond + close back inside)
- Market Structure Shift (MSS) / Change of Character (CHoCH) detection
- Order Block (OB) identification
- Fair Value Gap (FVG) identification
- Daily EMA bias filter
"""

import logging
from typing import Optional

from .config import BotConfig
from .models import (
    Candle,
    DailyLevels,
    FairValueGap,
    LiquidityLevel,
    LiquiditySweep,
    LiquidityType,
    MarketStructureShift,
    OrderBlock,
    SwingPoint,
    SwingType,
)

logger = logging.getLogger(__name__)


class SMCEngine:
    """Stateless analysis engine that takes candle data and returns SMC structures."""

    def __init__(self, config: BotConfig):
        self.config = config

    # ── ATR Computation ───────────────────────────────────────────

    def compute_atr(self, candles: list[Candle], period: int = 0) -> list[float]:
        """
        Compute ATR for each candle using Wilder's smoothing.

        Returns:
            List of ATR values aligned with candle indices.
            ATR is 0.0 for the first (period - 1) candles.
        """
        if period <= 0:
            period = self.config.displacement.atr_period

        n = len(candles)
        if n < period + 1:
            return [0.0] * n

        tr_values = [0.0] * n
        for i in range(1, n):
            high_low = candles[i].high - candles[i].low
            high_prev_close = abs(candles[i].high - candles[i - 1].close)
            low_prev_close = abs(candles[i].low - candles[i - 1].close)
            tr_values[i] = max(high_low, high_prev_close, low_prev_close)

        # First TR for index 0
        tr_values[0] = candles[0].high - candles[0].low

        atr = [0.0] * n
        # Initial ATR: simple average of first `period` TR values
        atr[period - 1] = sum(tr_values[:period]) / period

        # Wilder's smoothing
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr_values[i]) / period

        return atr

    def get_current_atr(self, candles: list[Candle]) -> float:
        """Get the most recent ATR value."""
        atr_values = self.compute_atr(candles)
        if not atr_values:
            return 0.0
        # Return the last non-zero ATR
        for v in reversed(atr_values):
            if v > 0:
                return v
        return 0.0

    # ── EMA Computation ───────────────────────────────────────────

    def compute_ema(self, candles: list[Candle], period: int = 0) -> list[float]:
        """
        Compute EMA of closing prices.

        Returns:
            List of EMA values aligned with candle indices.
        """
        if period <= 0:
            period = self.config.bias_filter.ema_period

        n = len(candles)
        if n < period:
            return [0.0] * n

        ema = [0.0] * n
        # Seed with SMA
        ema[period - 1] = sum(c.close for c in candles[:period]) / period

        multiplier = 2.0 / (period + 1)
        for i in range(period, n):
            ema[i] = (candles[i].close - ema[i - 1]) * multiplier + ema[i - 1]

        return ema

    def get_daily_bias(self, daily_candles: list[Candle]) -> Optional[str]:
        """
        Determine directional bias from daily EMA.

        Returns:
            "bullish", "bearish", or None if insufficient data.
        """
        if not self.config.bias_filter.enabled:
            return None

        ema = self.compute_ema(daily_candles, self.config.bias_filter.ema_period)
        if not ema or ema[-1] == 0.0:
            return None

        last_close = daily_candles[-1].close
        last_ema = ema[-1]

        if last_close > last_ema:
            return "bullish"
        elif last_close < last_ema:
            return "bearish"
        return None

    # ── Premium / Discount Zone ────────────────────────────────────

    def get_premium_discount_zone(
        self,
        swings: list[SwingPoint],
        current_price: float,
        current_index: int,
    ) -> tuple[str, float]:
        """
        Determine whether current price is in premium, discount, or equilibrium.

        Uses the last confirmed swing high and swing low to define the range.
        - Above 50% = premium (expensive — favour shorts)
        - Below 50% = discount (cheap — favour longs)
        - Within 5% of 50% = equilibrium (neutral)

        Returns:
            (zone, midpoint) where zone is "premium", "discount", or "equilibrium"
        """
        last_high = self.get_last_swing_high(swings, current_index)
        last_low = self.get_last_swing_low(swings, current_index)

        if not last_high or not last_low or last_high.price <= last_low.price:
            return "equilibrium", current_price

        swing_range = last_high.price - last_low.price
        midpoint = last_low.price + 0.5 * swing_range
        position = (current_price - last_low.price) / swing_range

        if position > 0.55:
            return "premium", midpoint
        elif position < 0.45:
            return "discount", midpoint
        return "equilibrium", midpoint

    # ── Fibonacci OTE Entry ──────────────────────────────────────

    def compute_fib_entry(
        self,
        ob: OrderBlock,
        sweep_reference: float,
        mss_break_level: float,
    ) -> float:
        """
        Compute Optimal Trade Entry (OTE) using Fibonacci retracement.

        The OTE zone is 62-79% retracement of the impulse move.
        Default entry at 70.5% (configurable via fib_entry_level).

        For bullish: measure from sweep low to MSS break level, enter at
        fib_entry_level retracement — but clamped within the OB zone.

        For bearish: measure from sweep high to MSS break level, enter at
        fib_entry_level retracement — but clamped within the OB zone.

        Returns:
            Fibonacci-adjusted entry price (clamped to OB bounds).
        """
        if not self.config.order_block.use_fibonacci_entry:
            return ob.entry_price  # Fallback to standard fixed-fraction entry

        fib = self.config.order_block.fib_entry_level  # 0.705 default

        if ob.direction == "bullish":
            # Impulse: sweep_low → mss_break_level (upward)
            impulse_range = mss_break_level - sweep_reference
            if impulse_range <= 0:
                return ob.entry_price
            fib_price = mss_break_level - fib * impulse_range
            # Clamp within OB zone
            return max(ob.low, min(ob.high, fib_price))

        else:  # bearish
            # Impulse: sweep_high → mss_break_level (downward)
            impulse_range = sweep_reference - mss_break_level
            if impulse_range <= 0:
                return ob.entry_price
            fib_price = mss_break_level + fib * impulse_range
            # Clamp within OB zone
            return max(ob.low, min(ob.high, fib_price))

    # ── Swing Detection ───────────────────────────────────────────

    def detect_swings(self, candles: list[Candle]) -> list[SwingPoint]:
        """
        Detect fractal swing highs and lows using confirmed pivots.
        A swing high at index i is confirmed only after L future bars exist
        to the right, ensuring no lookahead bias.

        Uses swing_length L: a swing high is the maximum over
        [i-L, i+L], confirmed once bar i+L is available.
        """
        L = self.config.swing.swing_length
        n = len(candles)
        swings = []

        for i in range(L, n - L):
            # Check swing high
            is_high = True
            for j in range(i - L, i + L + 1):
                if j == i:
                    continue
                if candles[j].high >= candles[i].high:
                    is_high = False
                    break
            if is_high:
                swings.append(SwingPoint(
                    type=SwingType.HIGH,
                    price=candles[i].high,
                    candle_index=i,
                    candle_time=candles[i].time,
                    confirmed=True,
                    confirmation_index=i + L,
                ))

            # Check swing low
            is_low = True
            for j in range(i - L, i + L + 1):
                if j == i:
                    continue
                if candles[j].low <= candles[i].low:
                    is_low = False
                    break
            if is_low:
                swings.append(SwingPoint(
                    type=SwingType.LOW,
                    price=candles[i].low,
                    candle_index=i,
                    candle_time=candles[i].time,
                    confirmed=True,
                    confirmation_index=i + L,
                ))

        swings.sort(key=lambda s: s.candle_index)
        return swings

    def get_last_swing_high(self, swings: list[SwingPoint], before_index: int) -> Optional[SwingPoint]:
        """Get the most recent confirmed swing high before a given candle index."""
        candidates = [
            s for s in swings
            if s.type == SwingType.HIGH and s.confirmation_index <= before_index
        ]
        return candidates[-1] if candidates else None

    def get_last_swing_low(self, swings: list[SwingPoint], before_index: int) -> Optional[SwingPoint]:
        """Get the most recent confirmed swing low before a given candle index."""
        candidates = [
            s for s in swings
            if s.type == SwingType.LOW and s.confirmation_index <= before_index
        ]
        return candidates[-1] if candidates else None

    # ── Liquidity Level Identification ────────────────────────────

    def identify_liquidity_levels(
        self,
        swings: list[SwingPoint],
        daily_levels: DailyLevels,
        current_index: int,
        current_atr: float = 0.0,
    ) -> list[LiquidityLevel]:
        """
        Build a list of liquidity levels from:
        1. Previous Day High/Low (PDH/PDL)
        2. Recent confirmed swing highs/lows
        3. Equal highs/lows (within tolerance)
        """
        levels = []

        # PDH / PDL
        if daily_levels.pdh > 0:
            levels.append(LiquidityLevel(
                type=LiquidityType.BUY_SIDE,
                price=daily_levels.pdh,
                source="pdh",
                creation_time=daily_levels.date,
            ))
        if daily_levels.pdl > 0:
            levels.append(LiquidityLevel(
                type=LiquidityType.SELL_SIDE,
                price=daily_levels.pdl,
                source="pdl",
                creation_time=daily_levels.date,
            ))

        # Swing highs as buy-side liquidity
        confirmed_highs = [
            s for s in swings
            if s.type == SwingType.HIGH and s.confirmation_index <= current_index
        ]
        for sh in confirmed_highs[-10:]:  # Last 10 swing highs
            levels.append(LiquidityLevel(
                type=LiquidityType.BUY_SIDE,
                price=sh.price,
                source="swing_high",
                creation_time=sh.candle_time,
            ))

        # Swing lows as sell-side liquidity
        confirmed_lows = [
            s for s in swings
            if s.type == SwingType.LOW and s.confirmation_index <= current_index
        ]
        for sl in confirmed_lows[-10:]:  # Last 10 swing lows
            levels.append(LiquidityLevel(
                type=LiquidityType.SELL_SIDE,
                price=sl.price,
                source="swing_low",
                creation_time=sl.candle_time,
            ))

        # Detect equal highs (buy-side liquidity)
        # Tolerance scales with ATR (configurable), falls back to $1 for gold
        eq_tol = current_atr * self.config.order_block.equal_level_atr_fraction if current_atr > 0 else 1.0
        for i in range(len(confirmed_highs)):
            for j in range(i + 1, len(confirmed_highs)):
                if abs(confirmed_highs[i].price - confirmed_highs[j].price) < eq_tol:
                    avg_price = (confirmed_highs[i].price + confirmed_highs[j].price) / 2.0
                    levels.append(LiquidityLevel(
                        type=LiquidityType.BUY_SIDE,
                        price=avg_price,
                        source="equal_highs",
                        creation_time=confirmed_highs[j].candle_time,
                    ))

        # Detect equal lows (sell-side liquidity)
        for i in range(len(confirmed_lows)):
            for j in range(i + 1, len(confirmed_lows)):
                if abs(confirmed_lows[i].price - confirmed_lows[j].price) < eq_tol:
                    avg_price = (confirmed_lows[i].price + confirmed_lows[j].price) / 2.0
                    levels.append(LiquidityLevel(
                        type=LiquidityType.SELL_SIDE,
                        price=avg_price,
                        source="equal_lows",
                        creation_time=confirmed_lows[j].candle_time,
                    ))

        buy_side = [l for l in levels if l.type == LiquidityType.BUY_SIDE]
        sell_side = [l for l in levels if l.type == LiquidityType.SELL_SIDE]
        logger.info(
            "Liquidity levels: %d buy-side, %d sell-side (swings: %d highs, %d lows)",
            len(buy_side), len(sell_side), len(confirmed_highs), len(confirmed_lows),
        )

        return levels

    # ── Liquidity Sweep Detection ─────────────────────────────────

    def detect_sweep(
        self,
        candle: Candle,
        liquidity_levels: list[LiquidityLevel],
        current_atr: float = 0.0,
    ) -> list[LiquiditySweep]:
        """
        Check if a candle sweeps any liquidity level.
        A sweep occurs when price trades beyond a level (wick) but closes back inside.

        Sell-side sweep (bullish): candle low < level price AND candle close > level price
        Buy-side sweep (bearish): candle high > level price AND candle close < level price

        Inducement scoring: measures sweep depth vs ATR. Shallow sweeps (< min_sweep_depth_atr)
        are scored lower and can be filtered by signal generators.
        """
        sweeps = []
        min_depth_atr = self.config.order_block.min_sweep_depth_atr

        for level in liquidity_levels:
            if level.swept:
                continue

            if level.type == LiquidityType.SELL_SIDE:
                # Sell-side liquidity sweep → potential long
                if candle.low < level.price and candle.close > level.price:
                    depth = level.price - candle.low
                    depth_atr = depth / current_atr if current_atr > 0 else 1.0
                    quality = min(1.0, depth_atr / max(min_depth_atr, 0.1)) if current_atr > 0 else 1.0

                    level.swept = True
                    level.sweep_time = candle.time
                    level.sweep_candle_index = candle.index
                    sweep = LiquiditySweep(
                        level=level,
                        sweep_candle=candle,
                        direction="long",
                        sweep_low=candle.low,
                        sweep_depth=depth,
                        sweep_quality=quality,
                    )
                    sweeps.append(sweep)
                    logger.info(
                        "SELL-SIDE SWEEP at %.2f (source: %s) | Low: %.2f | Depth: %.2f (%.2f ATR) | Quality: %.2f",
                        level.price, level.source, candle.low, depth, depth_atr, quality,
                    )

            elif level.type == LiquidityType.BUY_SIDE:
                # Buy-side liquidity sweep → potential short
                if candle.high > level.price and candle.close < level.price:
                    depth = candle.high - level.price
                    depth_atr = depth / current_atr if current_atr > 0 else 1.0
                    quality = min(1.0, depth_atr / max(min_depth_atr, 0.1)) if current_atr > 0 else 1.0

                    level.swept = True
                    level.sweep_time = candle.time
                    level.sweep_candle_index = candle.index
                    sweep = LiquiditySweep(
                        level=level,
                        sweep_candle=candle,
                        direction="short",
                        sweep_high=candle.high,
                        sweep_depth=depth,
                        sweep_quality=quality,
                    )
                    sweeps.append(sweep)
                    logger.info(
                        "BUY-SIDE SWEEP at %.2f (source: %s) | High: %.2f | Depth: %.2f (%.2f ATR) | Quality: %.2f",
                        level.price, level.source, candle.high, depth, depth_atr, quality,
                    )

        return sweeps

    # ── Market Structure Shift (MSS) / CHoCH Detection ────────────

    def detect_mss(
        self,
        candle: Candle,
        candle_index: int,
        sweep: LiquiditySweep,
        swings: list[SwingPoint],
        atr_values: list[float],
    ) -> Optional[MarketStructureShift]:
        """
        After a liquidity sweep, check if the current candle confirms
        a Market Structure Shift (MSS) / Change of Character (CHoCH).

        For a bullish MSS (after sell-side sweep):
        - Candle closes above sweep candle high or above an internal swing high
        - Candle body >= k * ATR (displacement)

        For a bearish MSS (after buy-side sweep):
        - Candle closes below sweep candle low or below an internal swing low
        - Candle body >= k * ATR (displacement)
        """
        k = self.config.displacement.body_atr_multiplier
        atr = atr_values[candle_index] if candle_index < len(atr_values) else 0.0

        if atr <= 0:
            logger.info("MSS check skipped: ATR=0 at index %d", candle_index)
            return None

        body_size = candle.body_size
        is_displacement = body_size >= k * atr

        if sweep.direction == "long":
            # Bullish MSS: close above the nearest structural high
            # Use the higher of sweep candle high and last swing high
            break_level = sweep.sweep_candle.high
            last_swing_high = self.get_last_swing_high(swings, candle_index)
            if last_swing_high and last_swing_high.price > break_level:
                break_level = last_swing_high.price

            close_above = candle.close > break_level
            if close_above and is_displacement:
                return MarketStructureShift(
                    direction="bullish",
                    break_level=break_level,
                    break_candle_index=candle_index,
                    break_candle_time=candle.time,
                    displacement=True,
                    displacement_body_size=body_size,
                )
            elif close_above and not is_displacement:
                logger.info(
                    "Bullish MSS near-miss: close above %.2f but body %.2f < %.2f (%.1f×ATR)",
                    break_level, body_size, k * atr, k,
                )

        elif sweep.direction == "short":
            # Bearish MSS: close below the nearest structural low
            # Use the lower of sweep candle low and last swing low
            break_level = sweep.sweep_candle.low
            last_swing_low = self.get_last_swing_low(swings, candle_index)
            if last_swing_low and last_swing_low.price < break_level:
                break_level = last_swing_low.price

            close_below = candle.close < break_level
            if close_below and is_displacement:
                return MarketStructureShift(
                    direction="bearish",
                    break_level=break_level,
                    break_candle_index=candle_index,
                    break_candle_time=candle.time,
                    displacement=True,
                    displacement_body_size=body_size,
                )
            elif close_below and not is_displacement:
                logger.info(
                    "Bearish MSS near-miss: close below %.2f but body %.2f < %.2f (%.1f×ATR)",
                    break_level, body_size, k * atr, k,
                )

        return None

    # ── Break of Structure (BOS) for Continuation ─────────────────

    def detect_bos(
        self,
        candle: Candle,
        candle_index: int,
        swings: list[SwingPoint],
        atr_values: list[float],
        bias: Optional[str],
    ) -> Optional[MarketStructureShift]:
        """
        Detect a Break of Structure (BOS) in the direction of the trend.
        Used by the Continuation template.

        Bullish BOS: candle closes above last confirmed swing high (in bullish bias)
        Bearish BOS: candle closes below last confirmed swing low (in bearish bias)
        """
        k = self.config.displacement.body_atr_multiplier
        atr = atr_values[candle_index] if candle_index < len(atr_values) else 0.0

        if atr <= 0:
            logger.info("BOS check skipped: ATR=0 at index %d", candle_index)
            return None

        body_size = candle.body_size
        is_displacement = body_size >= k * atr

        if bias == "bullish":
            last_high = self.get_last_swing_high(swings, candle_index)
            if last_high and candle.close > last_high.price and is_displacement:
                return MarketStructureShift(
                    direction="bullish",
                    break_level=last_high.price,
                    break_candle_index=candle_index,
                    break_candle_time=candle.time,
                    displacement=is_displacement,
                    displacement_body_size=body_size,
                )
            elif last_high and candle.close > last_high.price and not is_displacement:
                logger.info(
                    "Bullish BOS near-miss: close above %.2f but body %.2f < %.2f (%.1f×ATR)",
                    last_high.price, body_size, k * atr, k,
                )

        elif bias == "bearish":
            last_low = self.get_last_swing_low(swings, candle_index)
            if last_low and candle.close < last_low.price and is_displacement:
                return MarketStructureShift(
                    direction="bearish",
                    break_level=last_low.price,
                    break_candle_index=candle_index,
                    break_candle_time=candle.time,
                    displacement=is_displacement,
                    displacement_body_size=body_size,
                )
            elif last_low and candle.close < last_low.price and not is_displacement:
                logger.info(
                    "Bearish BOS near-miss: close below %.2f but body %.2f < %.2f (%.1f×ATR)",
                    last_low.price, body_size, k * atr, k,
                )

        return None

    # ── Order Block Identification ────────────────────────────────

    def find_order_block(
        self,
        candles: list[Candle],
        displacement_candle_index: int,
        direction: str,
    ) -> Optional[OrderBlock]:
        """
        Find the order block associated with a displacement candle.

        Bullish OB: the last bearish candle before the bullish displacement candle.
        Bearish OB: the last bullish candle before the bearish displacement candle.

        The OB zone is defined by the candle's high-low range.
        """
        if displacement_candle_index < 1 or displacement_candle_index >= len(candles):
            logger.info("OB search skipped: invalid displacement index %d", displacement_candle_index)
            return None

        f = self.config.order_block.entry_fraction
        ob_lookback = self.config.order_block.ob_lookback

        min_body_ratio = self.config.order_block.min_ob_body_range_ratio

        if direction == "bullish":
            # Search backwards for the last bearish candle before displacement
            for i in range(displacement_candle_index - 1, max(0, displacement_candle_index - ob_lookback) - 1, -1):
                if candles[i].is_bearish:
                    # OB quality filter: skip doji/spinning top candles
                    if candles[i].range_size > 0 and candles[i].body_size / candles[i].range_size < min_body_ratio:
                        continue
                    ob = OrderBlock(
                        high=candles[i].high,
                        low=candles[i].low,
                        candle_index=i,
                        candle_time=candles[i].time,
                        direction="bullish",
                    )
                    ob.entry_price = ob.low + f * (ob.high - ob.low)
                    logger.info(
                        "BULLISH OB found at index %d (%d bars back) | Zone: %.2f-%.2f | Entry: %.2f",
                        i, displacement_candle_index - i, ob.low, ob.high, ob.entry_price,
                    )
                    return ob
            logger.info(
                "No bullish OB found: searched %d candles back from index %d",
                ob_lookback, displacement_candle_index,
            )

        elif direction == "bearish":
            # Search backwards for the last bullish candle before displacement
            for i in range(displacement_candle_index - 1, max(0, displacement_candle_index - ob_lookback) - 1, -1):
                if candles[i].is_bullish:
                    # OB quality filter: skip doji/spinning top candles
                    if candles[i].range_size > 0 and candles[i].body_size / candles[i].range_size < min_body_ratio:
                        continue
                    ob = OrderBlock(
                        high=candles[i].high,
                        low=candles[i].low,
                        candle_index=i,
                        candle_time=candles[i].time,
                        direction="bearish",
                    )
                    ob.entry_price = ob.high - f * (ob.high - ob.low)
                    logger.info(
                        "BEARISH OB found at index %d (%d bars back) | Zone: %.2f-%.2f | Entry: %.2f",
                        i, displacement_candle_index - i, ob.low, ob.high, ob.entry_price,
                    )
                    return ob
            logger.info(
                "No bearish OB found: searched %d candles back from index %d",
                ob_lookback, displacement_candle_index,
            )

        return None

    # ── Fair Value Gap (FVG) Identification ───────────────────────

    def detect_fvg(self, candles: list[Candle], start_index: int = 0) -> list[FairValueGap]:
        """
        Detect Fair Value Gaps (three-candle imbalances) in the candle data.

        Bullish FVG: candle[i-2].high < candle[i].low (gap between candle 1 high and candle 3 low)
        Bearish FVG: candle[i-2].low > candle[i].high
        """
        fvgs = []
        for i in range(max(2, start_index), len(candles)):
            c1 = candles[i - 2]
            c3 = candles[i]

            # Bullish FVG
            if c1.high < c3.low:
                fvgs.append(FairValueGap(
                    high=c3.low,  # Upper boundary of the gap
                    low=c1.high,  # Lower boundary of the gap
                    direction="bullish",
                    candle_index=i - 1,  # Middle candle
                    candle_time=candles[i - 1].time,
                ))

            # Bearish FVG
            if c1.low > c3.high:
                fvgs.append(FairValueGap(
                    high=c1.low,  # Upper boundary of the gap
                    low=c3.high,  # Lower boundary of the gap
                    direction="bearish",
                    candle_index=i - 1,
                    candle_time=candles[i - 1].time,
                ))

        return fvgs

    def find_nearest_fvg(
        self,
        fvgs: list[FairValueGap],
        direction: str,
        after_index: int,
        near_price: float,
        current_index: int = -1,
    ) -> Optional[FairValueGap]:
        """
        Find the nearest valid FVG in the given direction near a price level.

        FVG freshness weighting: older FVGs are penalised in the sort.
        Age thresholds (in candles): 0-5 = 100%, 6-15 = 80%, 16-30 = 60%, 30+ = 40%.
        """
        max_age = self.config.order_block.fvg_max_age_candles
        candidates = [
            f for f in fvgs
            if f.direction == direction and f.candle_index >= after_index and f.is_valid and not f.filled
            and (current_index < 0 or (current_index - f.candle_index) <= max_age)
        ]
        if not candidates:
            return None

        def freshness_weight(fvg: FairValueGap) -> float:
            if current_index < 0:
                return 1.0
            age = current_index - fvg.candle_index
            if age <= 5:
                return 1.0
            elif age <= 15:
                return 0.8
            elif age <= max_age:
                return 0.6
            return 0.4

        # Sort by proximity to near_price, penalised by staleness
        candidates.sort(key=lambda f: abs(f.midpoint - near_price) / freshness_weight(f))
        return candidates[0]
