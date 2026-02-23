"""
Data models for the SMC Trading Bot.
Defines structures for candles, swings, liquidity levels,
order blocks, fair value gaps, trade setups, and positions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SwingType(Enum):
    HIGH = "high"
    LOW = "low"


class LiquidityType(Enum):
    BUY_SIDE = "buy_side"   # Above swing highs (stop losses of shorts)
    SELL_SIDE = "sell_side"  # Below swing lows (stop losses of longs)


class SweepStatus(Enum):
    PENDING = "pending"
    SWEPT = "swept"
    CONFIRMED = "confirmed"  # MSS confirmed after sweep


class SetupState(Enum):
    AWAITING_SWEEP = "awaiting_sweep"
    AWAITING_MSS = "awaiting_mss"
    AWAITING_OB_ENTRY = "awaiting_ob_entry"
    ENTRY_PENDING = "entry_pending"
    ACTIVE = "active"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TradeResult(Enum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    TIME_STOP = "time_stop"


@dataclass
class Candle:
    """Represents a single OHLC candle."""
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    index: int = 0  # Position in the data array

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def range_size(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low


@dataclass
class SwingPoint:
    """A confirmed fractal swing high or low."""
    type: SwingType
    price: float
    candle_index: int
    candle_time: datetime
    confirmed: bool = False
    confirmation_index: int = 0


@dataclass
class LiquidityLevel:
    """A price level where liquidity is expected to pool."""
    type: LiquidityType
    price: float
    source: str  # "pdh", "pdl", "swing_high", "swing_low", "equal_highs", "equal_lows"
    creation_time: datetime = None
    swept: bool = False
    sweep_time: Optional[datetime] = None
    sweep_candle_index: Optional[int] = None


@dataclass
class LiquiditySweep:
    """Record of a liquidity sweep event."""
    level: LiquidityLevel
    sweep_candle: Candle
    direction: str  # "long" (swept below, expect up) or "short" (swept above, expect down)
    sweep_low: float = 0.0  # Lowest point of sweep (for longs)
    sweep_high: float = 0.0  # Highest point of sweep (for shorts)
    mss_confirmed: bool = False
    mss_candle_index: Optional[int] = None


@dataclass
class OrderBlock:
    """An identified order block zone."""
    high: float
    low: float
    candle_index: int
    candle_time: datetime
    direction: str  # "bullish" or "bearish"
    is_valid: bool = True
    mitigated: bool = False  # Price has returned and traded through
    entry_price: float = 0.0  # Computed: OB_low + f*(OB_high - OB_low)

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2.0


@dataclass
class FairValueGap:
    """A three-candle imbalance / fair value gap."""
    high: float  # Upper boundary of the gap
    low: float   # Lower boundary of the gap
    direction: str  # "bullish" (gap up) or "bearish" (gap down)
    candle_index: int  # Index of the middle candle
    candle_time: datetime
    is_valid: bool = True
    filled: bool = False

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2.0

    @property
    def size(self) -> float:
        return abs(self.high - self.low)


@dataclass
class MarketStructureShift:
    """A market structure shift / change of character event."""
    direction: str  # "bullish" or "bearish"
    break_level: float  # The swing level that was broken
    break_candle_index: int
    break_candle_time: datetime
    displacement: bool = False  # Whether the break was with displacement
    displacement_body_size: float = 0.0


@dataclass
class DailyLevels:
    """Previous day high/low and current day levels."""
    pdh: float = 0.0  # Previous Day High
    pdl: float = 0.0  # Previous Day Low
    current_day_high: float = 0.0
    current_day_low: float = 0.0
    date: Optional[datetime] = None


@dataclass
class TradeSetup:
    """A complete trade setup from signal detection to order parameters."""
    template: str  # "reversal" or "continuation"
    direction: str  # "long" or "short"
    state: SetupState = SetupState.AWAITING_SWEEP

    # Signal components
    sweep: Optional[LiquiditySweep] = None
    mss: Optional[MarketStructureShift] = None
    order_block: Optional[OrderBlock] = None
    fvg: Optional[FairValueGap] = None

    # Order parameters
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    risk_distance: float = 0.0  # |entry - stop|
    reward_distance: float = 0.0  # |target - entry|
    r_multiple: float = 0.0  # reward / risk

    # Timing
    signal_time: Optional[datetime] = None
    signal_candle_index: int = 0
    entry_expiry_index: int = 0  # Cancel limit order after this index
    max_hold_index: int = 0  # Time stop after this index

    # Execution
    lot_size: float = 0.0
    ticket: int = 0
    fill_price: float = 0.0
    fill_time: Optional[datetime] = None

    # Management
    breakeven_moved: bool = False

    # Result
    exit_price: float = 0.0
    exit_time: Optional[datetime] = None
    result: Optional[TradeResult] = None
    realized_r: float = 0.0
    pnl: float = 0.0


@dataclass
class PerformanceMetrics:
    """Rolling performance metrics for monitoring."""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0
    time_stops: int = 0

    total_r: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy_r: float = 0.0

    max_drawdown_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    peak_equity: float = 0.0
    current_equity: float = 0.0

    rolling_win_rate: float = 0.0  # Last N trades
    rolling_expectancy: float = 0.0

    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0

    ob_fill_rate: float = 0.0  # % of OB orders that filled
    avg_entry_slippage: float = 0.0
