"""Claw Claw: single-file MT5 trading framework (Python 3.9)."""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import MetaTrader5 as mt5


# -----------------------------
# Utilities
# -----------------------------

REDACT_PATTERNS = [
    re.compile(r"\b\d{6,}\b"),
    re.compile(r"(?i)(password|pass|pwd|token|secret)=\S+"),
]


def redact_text(text: str, max_len: int = 500) -> str:
    redacted = text
    for pattern in REDACT_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    if len(redacted) > max_len:
        redacted = redacted[:max_len] + "..."
    return redacted


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def kill_switch_triggered(project_root: Path) -> bool:
    return (project_root / "KILL_SWITCH").exists()


def load_config(config_path: Path) -> Dict[str, Any]:
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    return {}


# -----------------------------
# Logging
# -----------------------------

class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def setup_logger(log_dir: Path, name: str, filename: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    handler = RotatingFileHandler(log_dir / filename, maxBytes=1_000_000, backupCount=5)
    formatter = RedactingFormatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


# -----------------------------
# State / Models
# -----------------------------

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


# -----------------------------
# MT5 Connection / Symbol Resolver
# -----------------------------


def initialize_mt5(
    auto_login: bool = False,
    terminal_path: Optional[str] = None,
    data_path: Optional[str] = None,
    portable: bool = False,
) -> bool:
    init_kwargs = {}
    if terminal_path:
        init_kwargs["path"] = terminal_path
    if data_path:
        init_kwargs["data_path"] = data_path
    if portable:
        init_kwargs["portable"] = True

    if not auto_login:
        return mt5.initialize(**init_kwargs)
    # WARNING: auto login reads credentials from environment variables only.
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    if not login or not password or not server:
        return False
    return mt5.initialize(login=int(login), password=password, server=server, **init_kwargs)


def connect_mt5(
    auto_login: bool = False,
    retries: int = 3,
    delay_seconds: float = 2.0,
    terminal_path: Optional[str] = None,
    data_path: Optional[str] = None,
    portable: bool = False,
) -> Tuple[bool, str]:
    last_error = None
    for attempt in range(1, retries + 1):
        if initialize_mt5(
            auto_login=auto_login,
            terminal_path=terminal_path,
            data_path=data_path,
            portable=portable,
        ) and is_connected():
            return True, "Connected to MT5."
        last_error = mt5.last_error()
        time.sleep(delay_seconds)
    return False, f"MT5 connection failed after {retries} attempts. Last error: {last_error}"


def is_connected() -> bool:
    info = mt5.terminal_info()
    return info is not None and info.connected


def is_ready() -> bool:
    info = mt5.terminal_info()
    if info is None or not info.connected:
        return False
    account = mt5.account_info()
    return account is not None


def trading_permissions() -> Tuple[bool, str]:
    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        return False, "MT5 terminal info unavailable."
    if not terminal_info.connected:
        return False, "MT5 terminal is not connected."
    if not terminal_info.trade_allowed:
        return False, "Terminal trading is disabled."
    if hasattr(terminal_info, "trade_expert") and not terminal_info.trade_expert:
        return False, "Algo trading is disabled in MT5 terminal settings."
    account = mt5.account_info()
    if account is None:
        return False, "MT5 account info unavailable."
    if not account.trade_allowed:
        return False, "Trading is disabled for the account."
    return True, "Trading permissions confirmed."


def account_equity() -> Optional[float]:
    info = mt5.account_info()
    return float(info.equity) if info else None


def resolve_symbol(preferred: str) -> Optional[str]:
    if mt5.symbol_info(preferred) is not None:
        return preferred
    symbols = mt5.symbols_get()
    if symbols is None:
        return None
    candidates = [s.name for s in symbols if "BTC" in s.name.upper() and "USD" in s.name.upper()]
    if not candidates:
        return None
    candidates.sort(key=len)
    return candidates[0]


def ensure_symbol_enabled(symbol: str) -> bool:
    info = mt5.symbol_info(symbol)
    if info is None:
        return False
    return mt5.symbol_select(symbol, True)


# -----------------------------
# Data Feed
# -----------------------------


def fetch_candles(symbol: str, timeframe: int, count: int = 200) -> List[dict]:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        return []
    return [
        {
            "time": datetime.fromtimestamp(rate["time"]),
            "open": rate["open"],
            "high": rate["high"],
            "low": rate["low"],
            "close": rate["close"],
            "tick_volume": rate["tick_volume"],
        }
        for rate in rates
    ]


# -----------------------------
# Bots + Arbiter
# -----------------------------

class BaseBot:
    @property
    def name(self) -> str:
        raise NotImplementedError

    def propose(self, market: MarketContext) -> Optional[Proposal]:
        raise NotImplementedError


class TrendBot(BaseBot):
    @property
    def name(self) -> str:
        return "TrendBot"

    def propose(self, market: MarketContext) -> Optional[Proposal]:
        candles = market.candles
        if len(candles) < 20:
            return None
        closes = [c["close"] for c in candles[-20:]]
        short = sum(closes[-5:]) / 5
        long = sum(closes) / 20
        direction = None
        if short > long * 1.001:
            direction = "buy"
        elif short < long * 0.999:
            direction = "sell"
        if direction is None:
            return None
        last_close = candles[-1]["close"]
        sl = last_close * (0.995 if direction == "buy" else 1.005)
        tp = last_close * (1.008 if direction == "buy" else 0.992)
        return Proposal(
            bot_name=self.name,
            symbol=market.symbol,
            direction=direction,
            entry_type="market",
            suggested_sl=sl,
            suggested_tp=tp,
            confidence=0.55,
            rationale="TrendBot: short vs long moving average bias.",
        )


class MeanReversionBot(BaseBot):
    @property
    def name(self) -> str:
        return "MeanReversionBot"

    def propose(self, market: MarketContext) -> Optional[Proposal]:
        candles = market.candles
        if len(candles) < 30:
            return None
        closes = [c["close"] for c in candles[-30:]]
        mean = sum(closes) / 30
        last_close = closes[-1]
        distance = (last_close - mean) / mean
        if distance > 0.002:
            direction = "sell"
        elif distance < -0.002:
            direction = "buy"
        else:
            return None
        sl = last_close * (1.004 if direction == "sell" else 0.996)
        tp = last_close * (0.996 if direction == "sell" else 1.004)
        return Proposal(
            bot_name=self.name,
            symbol=market.symbol,
            direction=direction,
            entry_type="market",
            suggested_sl=sl,
            suggested_tp=tp,
            confidence=0.52,
            rationale="MeanReversionBot: price deviation from 30-period mean.",
        )


class Arbiter:
    def __init__(self, min_confidence: float = 0.6, dominance_gap: float = 0.15) -> None:
        self.min_confidence = min_confidence
        self.dominance_gap = dominance_gap

    def select(self, proposals: List[Proposal]) -> Optional[Proposal]:
        if not proposals:
            return None
        proposals = sorted(proposals, key=lambda p: p.confidence, reverse=True)
        top = proposals[0]
        if top.confidence < self.min_confidence:
            return None
        opposing = [p for p in proposals if p.direction != top.direction]
        if opposing and opposing[0].confidence + self.dominance_gap >= top.confidence:
            return None
        return top


# -----------------------------
# Risk Manager
# -----------------------------

@dataclass
class RiskDecision:
    allowed: bool
    reasons: List[str]
    volume: float


class RiskManager:
    def __init__(self, config: dict) -> None:
        self.config = config

    def _positions_for_symbol(self, symbol: str, magic: int) -> List:
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return []
        return [p for p in positions if p.magic == magic]

    def _current_spread_points(self, symbol: str) -> Optional[float]:
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            return None
        return (tick.ask - tick.bid) / info.point

    def _daily_drawdown_pct(self, state: TradeState, equity: float) -> float:
        if state.day_start_equity is None:
            state.day_start_equity = equity
            return 0.0
        drawdown = max(0.0, (state.day_start_equity - equity) / state.day_start_equity * 100)
        state.daily_drawdown_pct = drawdown
        return drawdown

    def _cooldown_active(self, state: TradeState) -> bool:
        if not state.last_trade_time:
            return False
        cooldown = timedelta(minutes=self.config["cooldown_minutes"])
        return datetime.now() - state.last_trade_time < cooldown

    def compute_volume(self, symbol: str, equity: float, sl_price: float, entry_price: float) -> Optional[float]:
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        sl_distance = abs(entry_price - sl_price)
        if sl_distance <= 0:
            return None
        point_value = info.trade_tick_value / info.trade_tick_size
        risk_amount = equity * (self.config["risk_per_trade_pct"] / 100)
        volume = risk_amount / (sl_distance / info.point * point_value)
        if volume <= 0:
            return None
        volume = max(info.volume_min, min(volume, info.volume_max, self.config["max_volume"]))
        step = info.volume_step
        volume = round(volume / step) * step
        return float(volume)

    def evaluate(self, proposal: Proposal, state: TradeState, equity: float) -> RiskDecision:
        reasons: List[str] = []
        allowed = True

        if proposal.symbol != self.config["resolved_symbol"]:
            allowed = False
            reasons.append("Symbol mismatch.")

        positions = self._positions_for_symbol(proposal.symbol, self.config["magic"])
        if self.config["one_trade_at_a_time"] and positions:
            allowed = False
            reasons.append("Existing position open.")

        if state.trades_today >= self.config["max_trades_per_day"]:
            allowed = False
            reasons.append("Max trades per day reached.")

        if self._cooldown_active(state):
            allowed = False
            reasons.append("Cooldown active.")

        spread_points = self._current_spread_points(proposal.symbol)
        if spread_points is None or spread_points > self.config["max_spread_points"]:
            allowed = False
            reasons.append("Spread too high or unavailable.")

        drawdown = self._daily_drawdown_pct(state, equity)
        if drawdown >= self.config["max_daily_loss_pct"]:
            allowed = False
            reasons.append("Daily loss limit breached.")

        if state.consecutive_losses >= self.config["max_consecutive_losses"]:
            allowed = False
            reasons.append("Consecutive loss circuit breaker.")

        symbol_info = mt5.symbol_info(proposal.symbol)
        if symbol_info is None:
            allowed = False
            reasons.append("Symbol info unavailable.")
            return RiskDecision(allowed, reasons, 0.0)

        if proposal.suggested_sl <= 0 or proposal.suggested_tp <= 0:
            allowed = False
            reasons.append("Invalid SL/TP.")

        min_sl = self.config["min_sl_points"] * symbol_info.point
        max_sl = self.config["max_sl_points"] * symbol_info.point
        tick = mt5.symbol_info_tick(proposal.symbol)
        if tick is None:
            allowed = False
            reasons.append("Tick unavailable.")
            return RiskDecision(allowed, reasons, 0.0)
        entry_price = tick.ask if proposal.direction == "buy" else tick.bid
        sl_distance = abs(entry_price - proposal.suggested_sl)
        if sl_distance < min_sl or sl_distance > max_sl:
            allowed = False
            reasons.append("SL distance out of bounds.")

        volume = self.compute_volume(proposal.symbol, equity, proposal.suggested_sl, entry_price)
        if volume is None:
            allowed = False
            reasons.append("Volume computation failed.")
            volume = 0.0

        if state.total_volume + volume > self.config["max_total_volume"]:
            allowed = False
            reasons.append("Exposure cap reached.")

        return RiskDecision(allowed, reasons, volume)


# -----------------------------
# Execution + Monitor
# -----------------------------

class ExecutionEngine:
    def __init__(self, config: dict, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

    def send_order(self, proposal: Proposal, volume: float) -> Optional[int]:
        tick = mt5.symbol_info_tick(proposal.symbol)
        if tick is None:
            self.logger.info("Execution aborted: tick unavailable.")
            return None

        price = tick.ask if proposal.direction == "buy" else tick.bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": proposal.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if proposal.direction == "buy" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": proposal.suggested_sl,
            "tp": proposal.suggested_tp,
            "deviation": self.config["deviation_points"],
            "magic": self.config["magic"],
            "comment": self.config["comment"],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result is None:
            self.logger.info("Order send failed: no result.")
            return None
        if result.retcode == mt5.TRADE_RETCODE_REQUOTE:
            time.sleep(0.5)
            result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.info("Order failed retcode=%s", result.retcode)
            return None
        self.logger.info("Order executed ticket=%s", result.order)
        return int(result.order)


class TradeMonitor:
    def __init__(self, config: dict, project_root: Path, logger: logging.Logger) -> None:
        self.config = config
        self.project_root = project_root
        self.logger = logger

    def snapshot_position(self, symbol: str, magic: int) -> Optional[PositionSnapshot]:
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            return None
        for pos in positions:
            if pos.magic != magic:
                continue
            direction = "buy" if pos.type == mt5.POSITION_TYPE_BUY else "sell"
            return PositionSnapshot(
                ticket=pos.ticket,
                symbol=pos.symbol,
                volume=pos.volume,
                price_open=pos.price_open,
                sl=pos.sl,
                tp=pos.tp,
                time_open=datetime.fromtimestamp(pos.time),
                direction=direction,
                risk_amount=0.0,
            )
        return None

    def _close_position(self, snapshot: PositionSnapshot) -> None:
        tick = mt5.symbol_info_tick(snapshot.symbol)
        if tick is None:
            return
        price = tick.bid if snapshot.direction == "buy" else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": snapshot.symbol,
            "volume": snapshot.volume,
            "type": mt5.ORDER_TYPE_SELL if snapshot.direction == "buy" else mt5.ORDER_TYPE_BUY,
            "position": snapshot.ticket,
            "price": price,
            "deviation": self.config["deviation_points"],
            "magic": self.config["magic"],
            "comment": f"{self.config['comment']}_exit",
        }
        mt5.order_send(request)

    def monitor(self, state: TradeState, snapshot: PositionSnapshot) -> None:
        while True:
            if kill_switch_triggered(self.project_root):
                if self.config["flatten_on_kill_switch"]:
                    self.logger.info("Kill switch active: flattening position.")
                    self._close_position(snapshot)
                break

            position = self.snapshot_position(snapshot.symbol, self.config["magic"])
            if position is None:
                break

            open_duration = datetime.now() - position.time_open
            if open_duration > timedelta(minutes=self.config["max_minutes_in_trade"]):
                self.logger.info("Time-based exit triggered.")
                self._close_position(position)
                break

            tick = mt5.symbol_info_tick(position.symbol)
            if tick is None:
                time.sleep(1)
                continue

            price = tick.bid if position.direction == "buy" else tick.ask
            unrealized_points = (price - position.price_open) if position.direction == "buy" else (position.price_open - price)
            loss_points = max(0.0, -unrealized_points)
            risk_points = abs(position.price_open - position.sl)
            if risk_points > 0:
                target = risk_points * self.config["break_even_r_multiple"]
                if unrealized_points >= target:
                    desired_sl = position.price_open
                    if (position.direction == "buy" and position.sl < desired_sl) or (
                        position.direction == "sell" and position.sl > desired_sl
                    ):
                        mt5.order_send(
                            {
                                "action": mt5.TRADE_ACTION_SLTP,
                                "position": position.ticket,
                                "sl": desired_sl,
                                "tp": position.tp,
                            }
                        )
            if snapshot.risk_amount > 0:
                info = mt5.symbol_info(position.symbol)
                if info is not None:
                    point_value = info.trade_tick_value / info.trade_tick_size
                    loss_value = (loss_points / info.point) * point_value * position.volume
                    if loss_value >= (snapshot.risk_amount * (self.config["stake_loss_cut_pct"] / 100)):
                        self.logger.info("Loss exceeds stake threshold. Closing position.")
                        self._close_position(position)
                        break

            time.sleep(1)

        state.open_position_ticket = None


# -----------------------------
# Audit DB
# -----------------------------

class AuditDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    symbol TEXT,
                    bot_name TEXT,
                    direction TEXT,
                    confidence REAL,
                    rationale TEXT,
                    arbiter_decision TEXT,
                    risk_allowed INTEGER,
                    risk_reasons TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    ticket INTEGER,
                    symbol TEXT,
                    direction TEXT,
                    volume REAL,
                    entry_price REAL,
                    sl REAL,
                    tp REAL,
                    spread REAL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_time TEXT,
                    exit_time TEXT,
                    symbol TEXT,
                    direction TEXT,
                    volume REAL,
                    entry_price REAL,
                    exit_price REAL,
                    sl REAL,
                    tp REAL,
                    pnl REAL,
                    pnl_pct REAL,
                    risk_amount REAL,
                    drawdown_at_entry REAL,
                    spread_at_entry REAL,
                    bot_name TEXT,
                    rationale TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS equity_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    equity REAL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    message TEXT
                )
                """
            )
            conn.commit()

    def log_decision(self, data: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO decisions (timestamp, symbol, bot_name, direction, confidence, rationale, arbiter_decision, risk_allowed, risk_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("timestamp"),
                    data.get("symbol"),
                    data.get("bot_name"),
                    data.get("direction"),
                    data.get("confidence"),
                    data.get("rationale"),
                    data.get("arbiter_decision"),
                    int(data.get("risk_allowed", 0)),
                    data.get("risk_reasons"),
                ),
            )
            conn.commit()

    def log_order(self, data: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO orders (timestamp, ticket, symbol, direction, volume, entry_price, sl, tp, spread)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("timestamp"),
                    data.get("ticket"),
                    data.get("symbol"),
                    data.get("direction"),
                    data.get("volume"),
                    data.get("entry_price"),
                    data.get("sl"),
                    data.get("tp"),
                    data.get("spread"),
                ),
            )
            conn.commit()

    def log_trade(self, data: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (entry_time, exit_time, symbol, direction, volume, entry_price, exit_price, sl, tp, pnl, pnl_pct, risk_amount, drawdown_at_entry, spread_at_entry, bot_name, rationale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("entry_time"),
                    data.get("exit_time"),
                    data.get("symbol"),
                    data.get("direction"),
                    data.get("volume"),
                    data.get("entry_price"),
                    data.get("exit_price"),
                    data.get("sl"),
                    data.get("tp"),
                    data.get("pnl"),
                    data.get("pnl_pct"),
                    data.get("risk_amount"),
                    data.get("drawdown_at_entry"),
                    data.get("spread_at_entry"),
                    data.get("bot_name"),
                    data.get("rationale"),
                ),
            )
            conn.commit()

    def log_equity(self, timestamp: str, equity: float) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO equity_snapshots (timestamp, equity) VALUES (?, ?)",
                (timestamp, equity),
            )
            conn.commit()

    def daily_summary(self) -> str:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), SUM(pnl), AVG(pnl) FROM trades")
            count, total_pnl, avg_pnl = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM trades WHERE pnl > 0")
            wins = cursor.fetchone()[0]
            cursor.execute("SELECT AVG(pnl / risk_amount) FROM trades WHERE risk_amount > 0")
            avg_r = cursor.fetchone()[0]
            cursor.execute("SELECT equity FROM equity_snapshots ORDER BY id ASC")
            equity_rows = cursor.fetchall()

        total_pnl = total_pnl or 0.0
        avg_pnl = avg_pnl or 0.0
        avg_r = avg_r or 0.0
        win_rate = (wins / count * 100) if count else 0.0
        max_drawdown = 0.0
        peak = None
        for (equity,) in equity_rows:
            if equity is None:
                continue
            if peak is None or equity > peak:
                peak = equity
            if peak is not None:
                drawdown = (peak - equity) / peak * 100 if peak else 0.0
                max_drawdown = max(max_drawdown, drawdown)
        return (
            f"Daily summary: trades={count}, win_rate={win_rate:.1f}%, "
            f"avg_r={avg_r:.2f}, max_dd={max_drawdown:.2f}%, "
            f"avg_pnl={avg_pnl:.2f}, total_pnl={total_pnl:.2f}"
        )


# -----------------------------
# Main Loop
# -----------------------------

TIMEFRAME_MAP = {"M5": mt5.TIMEFRAME_M5}


def prompt_unlock(config: dict) -> str:
    mode = config["mode"].lower()
    if mode in {"demo", "live"}:
        phrase = input("Type the exact unlock phrase to enable demo/live mode: ").strip()
        if phrase != config["unlock_phrase"]:
            print("Unlock phrase not provided. Falling back to paper mode.")
            return "paper"
    return mode


def resolve_timeframe(config: dict) -> int:
    timeframe = config["timeframe"].upper()
    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return TIMEFRAME_MAP[timeframe]


def collect_proposals(bots: List[BaseBot], market: MarketContext) -> List[Proposal]:
    proposals: List[Proposal] = []
    for bot in bots:
        proposal = bot.propose(market)
        if proposal is not None:
            proposals.append(proposal)
    return proposals


def log_proposals(logger: logging.Logger, proposals: List[Proposal]) -> None:
    for proposal in proposals:
        logger.info("Proposal %s %s confidence=%.2f", proposal.bot_name, proposal.direction, proposal.confidence)


def update_state_on_close(state: TradeState, config: dict, audit_db: AuditDB) -> None:
    history = mt5.history_deals_get(datetime.now() - timedelta(days=1), datetime.now())
    if history is None:
        return
    relevant = [d for d in history if d.magic == config["magic"]]
    if not relevant:
        return
    last = relevant[-1]
    if last.profit < 0:
        state.consecutive_losses += 1
    else:
        state.consecutive_losses = 0
    state.realized_pnl += last.profit
    audit_db.log_trade(
        {
            "entry_time": datetime.fromtimestamp(last.time).isoformat(),
            "exit_time": datetime.fromtimestamp(last.time).isoformat(),
            "symbol": last.symbol,
            "direction": "buy" if last.type == mt5.DEAL_TYPE_BUY else "sell",
            "volume": last.volume,
            "entry_price": last.price,
            "exit_price": last.price,
            "sl": 0.0,
            "tp": 0.0,
            "pnl": last.profit,
            "pnl_pct": 0.0,
            "risk_amount": 0.0,
            "drawdown_at_entry": state.daily_drawdown_pct,
            "spread_at_entry": 0.0,
            "bot_name": "",
            "rationale": "",
        }
    )


def main() -> None:
    project_root = Path(__file__).resolve().parent
    config_path = project_root / "claw_claw" / "config.json"
    config = load_config(config_path)

    defaults = {
        "mode": "paper",
        "symbol_preferred": "BTCUSD",
        "timeframe": "M5",
        "magic": 20250101,
        "comment": "ClawClaw",
        "max_spread_points": 200.0,
        "risk_per_trade_pct": 0.25,
        "max_daily_loss_pct": 2.0,
        "max_consecutive_losses": 3,
        "max_trades_per_day": 4,
        "cooldown_minutes": 10,
        "one_trade_at_a_time": True,
        "max_minutes_in_trade": 60,
        "stake_loss_cut_pct": 10.0,
        "flatten_on_kill_switch": False,
        "min_sl_points": 200.0,
        "max_sl_points": 2000.0,
        "max_volume": 1.0,
        "max_total_volume": 1.0,
        "deviation_points": 20,
        "break_even_r_multiple": 1.5,
        "unlock_phrase": "I UNDERSTAND LIVE RISK",
        "auto_login": False,
        "connection_retries": 3,
        "connection_delay_seconds": 2.0,
        "mt5_terminal_path": "",
        "mt5_data_path": "",
        "mt5_portable": False,
    }
    for key, value in defaults.items():
        config.setdefault(key, value)

    logs_dir = project_root / "logs"
    trade_logger = setup_logger(logs_dir, "trading", "trading.log")
    audit_logger = setup_logger(logs_dir, "audit", "audit.log")

    print("Please open MetaTrader 5 and log in to Deriv. Press Enter when ready.")
    input()

    connected, message = connect_mt5(
        auto_login=bool(config.get("auto_login")),
        retries=int(config.get("connection_retries", 3)),
        delay_seconds=float(config.get("connection_delay_seconds", 2.0)),
        terminal_path=config.get("mt5_terminal_path") or None,
        data_path=config.get("mt5_data_path") or None,
        portable=bool(config.get("mt5_portable", False)),
    )
    if not connected:
        print(message)
        return

    if not is_ready():
        print("MT5 terminal is not ready (account info unavailable).")
        mt5.shutdown()
        return
    trading_ok, trading_message = trading_permissions()
    if not trading_ok:
        print(trading_message)
        mt5.shutdown()
        return

    resolved = resolve_symbol(config["symbol_preferred"])
    if resolved is None:
        print("Could not resolve BTCUSD symbol.")
        mt5.shutdown()
        return

    if not ensure_symbol_enabled(resolved):
        print("Failed to enable symbol.")
        mt5.shutdown()
        return

    config["resolved_symbol"] = resolved
    print(f"Resolved symbol: {resolved}")

    config["mode"] = prompt_unlock(config)
    print(f"Mode: {config['mode']}")

    timeframe = resolve_timeframe(config)
    bots: List[BaseBot] = [TrendBot(), MeanReversionBot()]
    arbiter = Arbiter()
    risk_manager = RiskManager(config)
    execution = ExecutionEngine(config, trade_logger)
    audit_db = AuditDB(project_root / "clawclaw.db")
    monitor = TradeMonitor(config, project_root, trade_logger)
    state = TradeState()

    while True:
        if kill_switch_triggered(project_root):
            trade_logger.info("Kill switch active: no new trades.")
            time.sleep(5)
            continue
        if not is_ready():
            trade_logger.info("MT5 not ready or disconnected; waiting.")
            time.sleep(5)
            continue
        trading_ok, trading_message = trading_permissions()
        if not trading_ok:
            trade_logger.info("MT5 trading not allowed: %s", trading_message)
            time.sleep(5)
            continue

        equity = account_equity()
        if equity is None:
            trade_logger.info("Equity unavailable.")
            time.sleep(5)
            continue
        audit_db.log_equity(utc_now().isoformat(), equity)

        candles = fetch_candles(resolved, timeframe, 200)
        if len(candles) < 3:
            time.sleep(10)
            continue

        last_closed = candles[-2]
        last_closed_time = last_closed["time"]
        if state.last_processed_candle_time == last_closed_time:
            time.sleep(5)
            continue

        tick = mt5.symbol_info_tick(resolved)
        info = mt5.symbol_info(resolved)
        if tick is None or info is None:
            time.sleep(5)
            continue

        spread_points = (tick.ask - tick.bid) / info.point
        market = MarketContext(
            symbol=resolved,
            timeframe=timeframe,
            candles=candles[:-1],
            last_closed_time=last_closed_time,
            spread_points=spread_points,
        )

        proposals = collect_proposals(bots, market)
        log_proposals(audit_logger, proposals)
        selected = arbiter.select(proposals)

        audit_db.log_decision(
            {
                "timestamp": utc_now().isoformat(),
                "symbol": resolved,
                "bot_name": selected.bot_name if selected else "",
                "direction": selected.direction if selected else "",
                "confidence": selected.confidence if selected else 0.0,
                "rationale": selected.rationale if selected else "",
                "arbiter_decision": selected.bot_name if selected else "none",
                "risk_allowed": 0,
                "risk_reasons": "",
            }
        )

        if selected is None:
            state.last_processed_candle_time = last_closed_time
            time.sleep(2)
            continue

        decision = risk_manager.evaluate(selected, state, equity)
        audit_db.log_decision(
            {
                "timestamp": utc_now().isoformat(),
                "symbol": resolved,
                "bot_name": selected.bot_name,
                "direction": selected.direction,
                "confidence": selected.confidence,
                "rationale": selected.rationale,
                "arbiter_decision": selected.bot_name,
                "risk_allowed": int(decision.allowed),
                "risk_reasons": ";".join(decision.reasons),
            }
        )

        if not decision.allowed:
            trade_logger.info("Risk veto: %s", ";".join(decision.reasons))
            state.last_processed_candle_time = last_closed_time
            time.sleep(2)
            continue

        if config["mode"] == "paper":
            trade_logger.info("Paper mode: trade not sent.")
            state.last_processed_candle_time = last_closed_time
            state.trades_today += 1
            state.last_trade_time = datetime.now()
            time.sleep(2)
            continue

        ticket = execution.send_order(selected, decision.volume)
        if ticket is not None:
            state.trades_today += 1
            state.last_trade_time = datetime.now()
            state.open_position_ticket = ticket
            state.total_volume += decision.volume
            audit_db.log_order(
                {
                    "timestamp": utc_now().isoformat(),
                    "ticket": ticket,
                    "symbol": resolved,
                    "direction": selected.direction,
                    "volume": decision.volume,
                    "entry_price": tick.ask if selected.direction == "buy" else tick.bid,
                    "sl": selected.suggested_sl,
                    "tp": selected.suggested_tp,
                    "spread": spread_points,
                }
            )

            snapshot = monitor.snapshot_position(resolved, config["magic"])
            if snapshot is not None:
                info = mt5.symbol_info(resolved)
                if info is not None:
                    point_value = info.trade_tick_value / info.trade_tick_size
                    sl_distance = abs(snapshot.price_open - snapshot.sl)
                    snapshot.risk_amount = (sl_distance / info.point) * point_value * snapshot.volume
                monitor.monitor(state, snapshot)
            else:
                trade_logger.info("Position not found after execution.")
        else:
            trade_logger.info("Order failed; backing off.")
            time.sleep(5)

        update_state_on_close(state, config, audit_db)
        print(audit_db.daily_summary())
        state.last_processed_candle_time = last_closed_time
        time.sleep(2)


if __name__ == "__main__":
    main()
