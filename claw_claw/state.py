"""Runtime state tracking for Claw Claw."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TradeState:
    trades_today: int = 0
    last_trade_time: Optional[datetime] = None
    consecutive_losses: int = 0
    day_start_equity: Optional[float] = None
    daily_drawdown_pct: float = 0.0
    open_position_ticket: Optional[int] = None
    last_processed_candle_time: Optional[datetime] = None
    total_volume: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class PositionSnapshot:
    ticket: int
    symbol: str
    volume: float
    price_open: float
    sl: float
    tp: float
    time_open: datetime
    direction: str
    risk_amount: float


@dataclass
class MarketContext:
    symbol: str
    timeframe: int
    candles: list
    last_closed_time: datetime
    spread_points: float


@dataclass
class Proposal:
    bot_name: str
    symbol: str
    direction: str
    entry_type: str
    suggested_sl: float
    suggested_tp: float
    confidence: float
    rationale: str
