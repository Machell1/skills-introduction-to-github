"""
Aggressive Asian session scalping bot for XAUUSD on the 5-minute timeframe.

This bot is a conversion of the original M15 intraday swing trading bot into
a high-frequency scalper that exclusively trades during the Asian session
(00:00-06:00 UTC). It exploits the low-volatility, range-bound price action
typical of the Tokyo/Sydney hours using a confluence-based signal system that
combines RSI mean reversion, Bollinger Band bounces, EMA micro-crossovers,
session range S/R levels, MACD histogram flips, and smart money concepts
(order blocks, fair value gaps, liquidity sweeps) adapted for M5 data.

Key differences from the original swing bot:
  - M5 timeframe with 60-second evaluation cycles
  - Tight ATR x0.5 stops and ATR x0.75 take-profits
  - Up to 40 trades per day
  - 15-bar (15-minute) max holding time
  - Confluence scoring: trades require >= 2 agreeing signals
  - Strict spread filter (critical for scalping)
  - Session range detection for dynamic S/R
  - Automatic position closure at session end

Like the original, this bot is intended for educational use only. Always
backtest strategies in a demo environment before risking real money.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import ta

try:
    import MetaTrader5 as mt5
except ImportError as exc:
    raise ImportError(
        "The MetaTrader5 package is required. Install it with `pip install MetaTrader5`."
    ) from exc


# ---------------------------------------------------------------------------
# Environment and version checks
# ---------------------------------------------------------------------------


def check_python_version() -> None:
    """Warn if the running Python version is outside the tested range."""
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 9):
        print(
            f"[WARNING] Detected Python {major}.{minor}. This bot is designed for Python 3.9 or later."
        )
    elif major >= 4:
        print(
            f"[WARNING] Detected Python {major}.{minor}. Verify that all dependencies are compatible."
        )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYMBOL: str = os.environ.get("MT5_SYMBOL", "XAUUSD")
TIMEFRAME: int = mt5.TIMEFRAME_M5

# Asian session window (UTC hours)
ASIAN_SESSION_START_UTC: int = int(os.environ.get("ASIAN_SESSION_START_UTC", 0))   # 00:00 UTC
ASIAN_SESSION_END_UTC: int = int(os.environ.get("ASIAN_SESSION_END_UTC", 6))       # 06:00 UTC

# Base risk parameters
RISK_PER_TRADE: float = float(os.environ.get("RISK_PER_TRADE", 0.005))  # 0.5% per trade
MAX_DRAWDOWN_LIMIT: float = float(os.environ.get("MAX_DRAWDOWN_LIMIT", 0.15))  # 15% max drawdown

# Stop-loss and take-profit multipliers relative to ATR (tight for scalping)
STOP_MULTIPLIER: float = float(os.environ.get("STOP_MULTIPLIER", 0.5))
TP_MULTIPLIER: float = float(os.environ.get("TP_MULTIPLIER", 0.75))

# Lot size limits
MIN_LOT: float = float(os.environ.get("MIN_LOT", 0.01))
MAX_LOT: float = float(os.environ.get("MAX_LOT", 10.0))

# Sleep interval between evaluations (60 seconds for M5 scalping)
SLEEP_INTERVAL: int = int(os.environ.get("SLEEP_INTERVAL", 60))

# Trailing stop multiplier (tight for scalping)
TRAIL_MULTIPLIER: float = float(os.environ.get("TRAIL_MULTIPLIER", 0.3))

# News filter parameters
NEWS_EVENTS: str = os.environ.get("NEWS_EVENTS", "")
NEWS_BUFFER_MINUTES: int = int(os.environ.get("NEWS_BUFFER_MINUTES", 10))
NEWS_EVENTS_FILE: str = os.environ.get("NEWS_EVENTS_FILE", "")

# Drawdown management
PEAK_BALANCE: float = 0.0

# Magic number to tag bot orders
MAGIC_NUMBER: int = int(os.environ.get("MAGIC_NUMBER", 234100))

# Logging configuration
LOG_FILE: str = os.environ.get("LOG_FILE", "scalping_bot.log")

# ---------------------------------------------------------------------------
# Loss-prevention parameters (aggressive scalping)
# ---------------------------------------------------------------------------

SOFT_DAILY_RISK_LIMIT: float = float(
    os.environ.get("SOFT_DAILY_RISK_LIMIT", 0.25)
)
SOFT_RISK_FACTOR: float = float(os.environ.get("SOFT_RISK_FACTOR", 0.5))
MAX_CONSECUTIVE_LOSSES: int = int(os.environ.get("MAX_CONSECUTIVE_LOSSES", 5))
MAX_TRADES_PER_DAY: int = int(os.environ.get("MAX_TRADES_PER_DAY", 40))
VOLATILITY_THRESHOLD: float = float(os.environ.get("VOLATILITY_THRESHOLD", 1.8))
SPREAD_THRESHOLD_MULTIPLIER: float = float(os.environ.get("SPREAD_THRESHOLD_MULTIPLIER", 1.5))
MAX_EXPOSURE_LIMIT: float = float(os.environ.get("MAX_EXPOSURE_LIMIT", 0.10))
MAX_HOLDING_BARS: int = int(os.environ.get("MAX_HOLDING_BARS", 12))  # 12 bars = 60 min on M5

# ---------------------------------------------------------------------------
# Scalping signal parameters
# ---------------------------------------------------------------------------

# RSI (short window for M5)
RSI_WINDOW: int = int(os.environ.get("RSI_WINDOW", 7))
RSI_OVERSOLD: float = float(os.environ.get("RSI_OVERSOLD", 25))
RSI_OVERBOUGHT: float = float(os.environ.get("RSI_OVERBOUGHT", 75))

# Bollinger Bands (tighter for M5)
BB_WINDOW: int = int(os.environ.get("BB_WINDOW", 14))
BB_STD: float = float(os.environ.get("BB_STD", 2.0))

# EMA micro-crossover
EMA_FAST: int = int(os.environ.get("EMA_FAST", 5))
EMA_SLOW: int = int(os.environ.get("EMA_SLOW", 13))

# MACD (faster for M5)
MACD_FAST: int = int(os.environ.get("MACD_FAST", 8))
MACD_SLOW: int = int(os.environ.get("MACD_SLOW", 17))
MACD_SIGNAL: int = int(os.environ.get("MACD_SIGNAL", 9))

# ATR window
ATR_WINDOW: int = int(os.environ.get("ATR_WINDOW", 10))

# Session range proximity (fraction of price)
SESSION_RANGE_PROXIMITY: float = float(os.environ.get("SESSION_RANGE_PROXIMITY", 0.001))

# Minimum confluence score to trigger a trade
MIN_CONFLUENCE_SCORE: int = int(os.environ.get("MIN_CONFLUENCE_SCORE", 2))

# ---------------------------------------------------------------------------
# Dynamic Risk Sizing (lower per-trade risk for scalping)
# ---------------------------------------------------------------------------


def get_risk_percent_for_balance(balance: float) -> float:
    """Determine base risk percentage per trade based on account balance.

    Lower percentages than the swing bot since scalping takes many more trades.
    """
    if balance < 5_000:
        return 0.01
    if balance < 10_000:
        return 0.008
    if balance < 50_000:
        return 0.005
    if balance < 100_000:
        return 0.004
    return 0.003


# Daily counters (reset at midnight)
CURRENT_DAY: Optional[date] = None
TRADES_TODAY: int = 0


# ---------------------------------------------------------------------------
# Logger setup
# ---------------------------------------------------------------------------


def setup_logger() -> logging.Logger:
    """Configure a rotating logger for the scalping bot."""
    logger = logging.getLogger("scalping_bot")
    logger.setLevel(logging.INFO)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5_000_000, backupCount=3
    )
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


logger: logging.Logger = setup_logger()


# ---------------------------------------------------------------------------
# MT5 Connection
# ---------------------------------------------------------------------------


def connect_to_mt5(login: int, password: str, server: str) -> None:
    """Initialise and log into MetaTrader 5."""
    if not mt5.initialize():
        logger.error(f"MT5 initialisation failed: {mt5.last_error()}")
        raise SystemExit("Failed to initialise MetaTrader 5.")
    authorized = mt5.login(login=login, password=password, server=server)
    if not authorized:
        logger.error(f"MT5 login failed: {mt5.last_error()}")
        mt5.shutdown()
        raise SystemExit("Failed to log in to MetaTrader 5.")
    info = mt5.version()
    logger.info(f"Connected to MetaTrader 5 terminal version: {info}")


# ---------------------------------------------------------------------------
# Asian Session Detection
# ---------------------------------------------------------------------------


def is_within_asian_session(now_utc: datetime) -> bool:
    """Check if the current UTC time falls within the Asian session window."""
    hour = now_utc.hour
    if ASIAN_SESSION_START_UTC <= ASIAN_SESSION_END_UTC:
        return ASIAN_SESSION_START_UTC <= hour < ASIAN_SESSION_END_UTC
    # Handle wrap-around midnight (e.g., 22:00-06:00)
    return hour >= ASIAN_SESSION_START_UTC or hour < ASIAN_SESSION_END_UTC


def get_session_range(data: pd.DataFrame, now_utc: datetime) -> Dict[str, Optional[float]]:
    """Compute the high/low of the current Asian session so far.

    These levels serve as dynamic support and resistance for mean-reversion
    scalping entries. The session range is built from all M5 bars since the
    session start.

    Returns:
        A dict with 'session_high' and 'session_low', or None values if
        insufficient data is available.
    """
    session_start = now_utc.replace(
        hour=ASIAN_SESSION_START_UTC, minute=0, second=0, microsecond=0
    )
    if now_utc < session_start:
        session_start -= timedelta(days=1)

    session_bars = data[data["time"] >= session_start]
    if len(session_bars) < 5:
        return {"session_high": None, "session_low": None}

    return {
        "session_high": float(session_bars["high"].max()),
        "session_low": float(session_bars["low"].min()),
    }


# ---------------------------------------------------------------------------
# Market Data and Indicators (M5 scalping parameters)
# ---------------------------------------------------------------------------


def fetch_live_market_data(
    symbol: str, timeframe: int, bars: int = 300
) -> Optional[pd.DataFrame]:
    """Fetch recent M5 market data and compute technical indicators.

    Indicator parameters are tuned for 5-minute scalping:
      - RSI window=7 (faster reversals)
      - MACD (8, 17, 9) (quicker signals)
      - Bollinger Bands window=14
      - EMA 5 vs 13 (micro-crossover)
      - ATR window=10
    """
    try:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        if rates is None or len(rates) == 0:
            logger.error("No market data returned by MT5 API.")
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.rename(
            columns={
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "tick_volume": "tick_volume",
                "spread": "spread",
                "real_volume": "real_volume",
            },
            inplace=True,
        )
        # RSI (short window for M5)
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=RSI_WINDOW).rsi()
        # MACD (faster for M5)
        macd = ta.trend.MACD(
            df["close"],
            window_slow=MACD_SLOW,
            window_fast=MACD_FAST,
            window_sign=MACD_SIGNAL,
        )
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_diff"] = macd.macd_diff()
        # Bollinger Bands (tighter window)
        bb = ta.volatility.BollingerBands(df["close"], window=BB_WINDOW, window_dev=BB_STD)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_middle"] = bb.bollinger_mavg()
        # EMA micro-crossover pair
        df["ema_fast"] = ta.trend.EMAIndicator(df["close"], window=EMA_FAST).ema_indicator()
        df["ema_slow"] = ta.trend.EMAIndicator(df["close"], window=EMA_SLOW).ema_indicator()
        # ATR (shorter window)
        df["atr"] = ta.volatility.average_true_range(
            df["high"], df["low"], df["close"], window=ATR_WINDOW
        )
        return df
    except Exception as exc:
        logger.exception(f"Error fetching or processing market data: {exc}")
        return None


# ---------------------------------------------------------------------------
# Pattern Detection (adapted lookback for M5)
# ---------------------------------------------------------------------------


def identify_order_blocks(data: pd.DataFrame) -> List[Dict[str, float]]:
    """Identify potential order blocks (simplified logic, M5-adapted)."""
    order_blocks: List[Dict[str, float]] = []
    try:
        avg_volume = data["real_volume"].mean()
        for i in range(2, len(data)):
            volume_condition = data["real_volume"].iloc[i] > avg_volume * 1.1
            bullish_candle = data["close"].iloc[i] > data["open"].iloc[i]
            high_low_condition = data["low"].iloc[i - 1] >= data["high"].iloc[i - 2] * 0.99
            if volume_condition and bullish_candle and high_low_condition:
                order_blocks.append(
                    {"high": float(data["high"].iloc[i]), "low": float(data["low"].iloc[i])}
                )
        return order_blocks
    except KeyError as err:
        logger.error(f"Missing columns when identifying order blocks: {err}")
        return []


def detect_fvg(data: pd.DataFrame) -> List[Dict[str, float]]:
    """Detect fair value gaps (FVG) in the price series."""
    fvg_zones: List[Dict[str, float]] = []
    try:
        for i in range(1, len(data) - 1):
            if data["low"].iloc[i + 1] > data["high"].iloc[i - 1]:
                fvg_zones.append(
                    {
                        "start": float(data["high"].iloc[i - 1]),
                        "end": float(data["low"].iloc[i + 1]),
                    }
                )
        return fvg_zones
    except KeyError as err:
        logger.error(f"Missing columns when detecting FVG: {err}")
        return []


def detect_candlestick_patterns(data: pd.DataFrame) -> List[Dict[str, int]]:
    """Detect simple candlestick patterns such as engulfing patterns."""
    patterns: List[Dict[str, int]] = []
    try:
        for i in range(1, len(data)):
            open_i = float(data["open"].iloc[i])
            close_i = float(data["close"].iloc[i])
            high_i = float(data["high"].iloc[i])
            low_i = float(data["low"].iloc[i])
            prev_high = float(data["high"].iloc[i - 1])
            prev_low = float(data["low"].iloc[i - 1])
            bullish_engulf = close_i > open_i and open_i <= prev_low * 1.01
            bearish_engulf = close_i < open_i and open_i >= prev_high * 0.99
            if bullish_engulf:
                patterns.append({"type": "bullish_engulfing", "index": i})
            if bearish_engulf:
                patterns.append({"type": "bearish_engulfing", "index": i})
            body = abs(close_i - open_i)
            candle_range = high_i - low_i
            if candle_range <= 0:
                continue
            top_wick = high_i - max(open_i, close_i)
            bottom_wick = min(open_i, close_i) - low_i
            if bottom_wick >= 2 * body and bottom_wick > top_wick:
                patterns.append({"type": "pin_bar_bullish", "index": i})
            if top_wick >= 2 * body and top_wick > bottom_wick:
                patterns.append({"type": "pin_bar_bearish", "index": i})
        return patterns
    except KeyError as err:
        logger.error(f"Missing columns when detecting candlestick patterns: {err}")
        return []


def detect_liquidity_sweeps(
    data: pd.DataFrame, lookback: int = 5, margin: float = 0.001
) -> List[Dict[str, int]]:
    """Detect liquidity sweep patterns (stop hunts) over the last `lookback` bars."""
    patterns: List[Dict[str, int]] = []
    try:
        for i in range(lookback, len(data)):
            open_i = float(data["open"].iloc[i])
            close_i = float(data["close"].iloc[i])
            high_i = float(data["high"].iloc[i])
            low_i = float(data["low"].iloc[i])
            prev_high = float(data["high"].iloc[i - lookback : i].max())
            prev_low = float(data["low"].iloc[i - lookback : i].min())
            bullish_sweep = low_i < prev_low * (1 - margin) and close_i > open_i
            bearish_sweep = high_i > prev_high * (1 + margin) and close_i < open_i
            if bullish_sweep:
                patterns.append({"type": "liquidity_sweep_bullish", "index": i})
            if bearish_sweep:
                patterns.append({"type": "liquidity_sweep_bearish", "index": i})
        return patterns
    except KeyError as err:
        logger.error(f"Missing columns when detecting liquidity sweeps: {err}")
        return []


# ---------------------------------------------------------------------------
# Scalping Signal Generation (confluence-based)
# ---------------------------------------------------------------------------


def generate_scalp_signals(
    data: pd.DataFrame, session_range: Dict[str, Optional[float]]
) -> List[Dict]:
    """Generate scalping signals using a confluence scoring system.

    Each signal source contributes +1 (bullish) or -1 (bearish) to a running
    score. A trade is only considered when the absolute score reaches
    MIN_CONFLUENCE_SCORE, ensuring that at least two independent signals agree.

    Signal sources:
      1. RSI mean reversion (oversold/overbought)
      2. Bollinger Band bounce (price at band edge)
      3. EMA micro-crossover (EMA 5 vs EMA 13)
      4. Session range bounce (price near session high/low)
      5. MACD histogram flip (momentum shift)

    Returns a list of signal dicts with 'direction' and 'score'.
    """
    if data is None or len(data) < 3:
        return []

    signals: List[Dict] = []
    last = data.iloc[-1]
    prev = data.iloc[-2]

    bullish_score = 0
    bearish_score = 0
    reasons_bull: List[str] = []
    reasons_bear: List[str] = []

    # 1. RSI Mean Reversion
    rsi = last.get("rsi")
    if rsi is not None and not np.isnan(rsi):
        if rsi < RSI_OVERSOLD:
            bullish_score += 1
            reasons_bull.append("RSI_oversold")
        elif rsi > RSI_OVERBOUGHT:
            bearish_score += 1
            reasons_bear.append("RSI_overbought")

    # 2. Bollinger Band Bounce
    close = last["close"]
    bb_lower = last.get("bb_lower")
    bb_upper = last.get("bb_upper")
    prev_close = prev["close"]
    prev_bb_lower = prev.get("bb_lower")
    prev_bb_upper = prev.get("bb_upper")
    if bb_lower is not None and not np.isnan(bb_lower):
        if close <= bb_lower or (prev_close <= prev_bb_lower and close > bb_lower):
            bullish_score += 1
            reasons_bull.append("BB_lower_bounce")
    if bb_upper is not None and not np.isnan(bb_upper):
        if close >= bb_upper or (prev_close >= prev_bb_upper and close < bb_upper):
            bearish_score += 1
            reasons_bear.append("BB_upper_bounce")

    # 3. EMA Micro-Crossover
    ema_f = last.get("ema_fast")
    ema_s = last.get("ema_slow")
    prev_ema_f = prev.get("ema_fast")
    prev_ema_s = prev.get("ema_slow")
    if (
        ema_f is not None
        and ema_s is not None
        and not np.isnan(ema_f)
        and not np.isnan(ema_s)
        and prev_ema_f is not None
        and prev_ema_s is not None
        and not np.isnan(prev_ema_f)
        and not np.isnan(prev_ema_s)
    ):
        if prev_ema_f <= prev_ema_s and ema_f > ema_s:
            bullish_score += 1
            reasons_bull.append("EMA_cross_up")
        elif prev_ema_f >= prev_ema_s and ema_f < ema_s:
            bearish_score += 1
            reasons_bear.append("EMA_cross_down")

    # 4. Session Range Bounce
    session_high = session_range.get("session_high")
    session_low = session_range.get("session_low")
    if session_high is not None and session_low is not None:
        proximity = SESSION_RANGE_PROXIMITY
        if close <= session_low * (1 + proximity):
            bullish_score += 1
            reasons_bull.append("session_low_bounce")
        if close >= session_high * (1 - proximity):
            bearish_score += 1
            reasons_bear.append("session_high_bounce")

    # 5. MACD Histogram Flip
    macd_diff = last.get("macd_diff")
    prev_macd_diff = prev.get("macd_diff")
    if (
        macd_diff is not None
        and prev_macd_diff is not None
        and not np.isnan(macd_diff)
        and not np.isnan(prev_macd_diff)
    ):
        if prev_macd_diff < 0 and macd_diff >= 0:
            bullish_score += 1
            reasons_bull.append("MACD_flip_up")
        elif prev_macd_diff > 0 and macd_diff <= 0:
            bearish_score += 1
            reasons_bear.append("MACD_flip_down")

    # Evaluate confluence
    if bullish_score >= MIN_CONFLUENCE_SCORE:
        signals.append(
            {
                "direction": "buy",
                "score": bullish_score,
                "reasons": reasons_bull,
                "index": len(data) - 1,
            }
        )
    if bearish_score >= MIN_CONFLUENCE_SCORE:
        signals.append(
            {
                "direction": "sell",
                "score": bearish_score,
                "reasons": reasons_bear,
                "index": len(data) - 1,
            }
        )

    # If both buy and sell signals are present, keep only the stronger one
    if len(signals) == 2:
        if signals[0]["score"] >= signals[1]["score"]:
            signals = [signals[0]]
        else:
            signals = [signals[1]]

    return signals


# ---------------------------------------------------------------------------
# Contextual Signal Filtering
# ---------------------------------------------------------------------------


def filter_signals_by_context(
    patterns: List[Dict[str, int]],
    order_blocks: List[Dict[str, float]],
    fvg_zones: List[Dict[str, float]],
    data: pd.DataFrame,
    tolerance: float = 0.001,
) -> List[Dict[str, int]]:
    """Filter detected pattern signals by proximity to order blocks or FVG zones.

    For M5 scalping this is used as optional confluence rather than a hard gate.
    """
    if not patterns:
        return []
    filtered: List[Dict[str, int]] = []
    zones: List[Dict[str, float]] = []
    for ob in order_blocks:
        zones.append({"low": ob["low"], "high": ob["high"]})
    for fvg in fvg_zones:
        zones.append({"low": fvg["start"], "high": fvg["end"]})
    for pattern in patterns:
        i = pattern["index"]
        price = float(data["close"].iloc[i])
        for zone in zones:
            zone_low = zone["low"] * (1 - tolerance)
            zone_high = zone["high"] * (1 + tolerance)
            if zone_low <= price <= zone_high:
                filtered.append(pattern)
                break
    return filtered


# ---------------------------------------------------------------------------
# Risk Management Utilities
# ---------------------------------------------------------------------------


def calculate_lot_size(
    account_balance: float,
    risk_percent: float,
    stop_distance: float,
    symbol_info: mt5.SymbolInfo,
) -> float:
    """Calculate the appropriate lot size for a given risk percentage and stop distance."""
    if stop_distance <= 0 or account_balance <= 0 or risk_percent <= 0:
        return MIN_LOT

    contract_size = getattr(symbol_info, "trade_contract_size", None)
    if contract_size is None or contract_size <= 0:
        tick_value = getattr(symbol_info, "trade_tick_value", 0)
        tick_size = getattr(symbol_info, "trade_tick_size", 0)
        if tick_value > 0 and tick_size > 0:
            contract_size = tick_value / tick_size
        else:
            contract_size = 0
    if contract_size > 0:
        risk_per_lot = stop_distance * contract_size
    else:
        point = symbol_info.point
        tick_value = symbol_info.trade_tick_value
        if point <= 0 or tick_value <= 0:
            return MIN_LOT
        risk_per_lot = (stop_distance / point) * tick_value

    risk_amount = account_balance * risk_percent
    if risk_per_lot <= 0:
        return MIN_LOT
    lot_size = risk_amount / risk_per_lot
    lot_size = max(MIN_LOT, min(lot_size, MAX_LOT))
    return round(lot_size, 2)


def calculate_stop_levels(entry_price: float, atr: float, direction: str) -> Dict[str, float]:
    """Calculate stop-loss and take-profit levels based on ATR and direction.

    Uses tight multipliers appropriate for scalping (ATR x0.5 SL, ATR x0.75 TP).
    """
    if atr is None or np.isnan(atr) or atr <= 0:
        atr = 10 * 0.01  # default 10 pips
    stop_distance = atr * STOP_MULTIPLIER
    target_distance = atr * TP_MULTIPLIER
    if direction == "buy":
        sl = entry_price - stop_distance
        tp = entry_price + target_distance
    else:
        sl = entry_price + stop_distance
        tp = entry_price - target_distance
    return {"sl": sl, "tp": tp, "stop_distance": stop_distance}



def parse_news_events() -> List[str]:
    """Parse the NEWS_EVENTS environment variable into a list of HH:MM strings."""
    if not NEWS_EVENTS:
        return []
    return [evt.strip() for evt in NEWS_EVENTS.split(",") if evt.strip()]


def should_skip_due_to_news(now: datetime) -> bool:
    """Determine whether trading should be skipped due to a scheduled news event."""
    events = parse_news_events()
    if not events:
        return False
    buffer = timedelta(minutes=NEWS_BUFFER_MINUTES)
    for evt in events:
        try:
            hours, minutes = map(int, evt.split(":"))
            event_time = datetime(now.year, now.month, now.day, hours, minutes, tzinfo=now.tzinfo)
        except Exception:
            continue
        if abs(now - event_time) <= buffer:
            return True
    return False


def load_calendar_events(file_path: str) -> List[datetime]:
    """Load high-impact event times from a CSV/text file."""
    events: List[datetime] = []
    if not file_path or not os.path.isfile(file_path):
        return events
    try:
        with open(file_path, "r") as file_handle:
            for line in file_handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",")
                dt_str = parts[0].strip()
                try:
                    event_dt = datetime.fromisoformat(dt_str)
                    events.append(event_dt)
                except ValueError:
                    logger.warning(f"Invalid event date format in {file_path}: {dt_str}")
                    continue
        return events
    except Exception as exc:
        logger.exception(f"Failed to load calendar events from {file_path}: {exc}")
        return []


def should_skip_due_to_calendar(now: datetime, events: List[datetime]) -> bool:
    """Determine whether trading should be skipped due to calendar events."""
    buffer = timedelta(minutes=NEWS_BUFFER_MINUTES)
    for event_time in events:
        if event_time.date() != now.date():
            continue
        if abs(now - event_time) <= buffer:
            return True
    return False


def check_drawdown_limit(account_info: mt5.AccountInfo) -> bool:
    """Check whether the account has exceeded the maximum drawdown."""
    global PEAK_BALANCE
    current_balance = account_info.balance
    if PEAK_BALANCE == 0 or current_balance > PEAK_BALANCE:
        PEAK_BALANCE = current_balance
        return True
    drawdown = (PEAK_BALANCE - current_balance) / PEAK_BALANCE if PEAK_BALANCE > 0 else 0
    if drawdown > MAX_DRAWDOWN_LIMIT:
        logger.warning(
            f"Maximum drawdown exceeded: {drawdown:.2%} (limit {MAX_DRAWDOWN_LIMIT:.2%}). "
            "Pausing trading."
        )
        return False
    return True


def get_active_bot_orders(symbol: str) -> Tuple[List, List]:
    """Return active positions and pending orders for this bot based on magic number."""
    positions = mt5.positions_get(symbol=symbol) or []
    orders = mt5.orders_get(symbol=symbol) or []
    active_positions = [pos for pos in positions if pos.magic == MAGIC_NUMBER]
    active_orders = [order for order in orders if order.magic == MAGIC_NUMBER]
    return active_positions, active_orders


# ---------------------------------------------------------------------------
# Additional Loss-Prevention Utilities
# ---------------------------------------------------------------------------


def reset_daily_counters(now: datetime) -> None:
    """Reset daily counters at midnight based on current date."""
    global CURRENT_DAY, TRADES_TODAY
    today = now.date()
    if CURRENT_DAY is None or today != CURRENT_DAY:
        CURRENT_DAY = today
        TRADES_TODAY = 0


def get_consecutive_losses(symbol: str) -> int:
    """Count consecutive losing trades within the current day."""
    now = datetime.now()
    start_of_day = datetime(now.year, now.month, now.day)
    deals = mt5.history_deals_get(start_of_day, now, group=symbol)
    if deals is None:
        return 0
    try:
        deals_list = sorted(list(deals), key=lambda deal: deal.time)
    except Exception:
        return 0
    loss_streak = 0
    for deal in reversed(deals_list):
        if getattr(deal, "magic", None) != MAGIC_NUMBER:
            continue
        if hasattr(deal, "profit"):
            if deal.profit < 0:
                loss_streak += 1
            elif deal.profit > 0:
                break
    return loss_streak


def get_daily_loss_ratio(symbol: str, balance: float) -> float:
    """Return the fraction of account balance lost today."""
    now = datetime.now()
    start_of_day = datetime(now.year, now.month, now.day)
    deals = mt5.history_deals_get(start_of_day, now, group=symbol)
    if deals is None or balance <= 0:
        return 0.0
    total_loss = 0.0
    for deal in deals:
        if getattr(deal, "magic", None) != MAGIC_NUMBER:
            continue
        try:
            profit = deal.profit
        except AttributeError:
            try:
                profit = deal._asdict().get("profit", 0)
            except Exception:
                profit = 0
        if profit < 0:
            total_loss += -profit
    return total_loss / balance


def get_dynamic_risk_factor(daily_loss_ratio: float, consecutive_losses: int) -> float:
    """Compute a risk factor multiplier based on soft loss limit and loss streak."""
    factor = 1.0
    if daily_loss_ratio >= SOFT_DAILY_RISK_LIMIT:
        factor *= SOFT_RISK_FACTOR
    if consecutive_losses >= 2:
        factor *= SOFT_RISK_FACTOR
    return max(0.1, min(1.0, factor))


def check_volatility_and_spread(data: pd.DataFrame) -> bool:
    """Return True if trading should be skipped due to high volatility or spread.

    The spread filter is stricter for scalping (1.5x average) since tight stops
    make the bot more sensitive to spread costs.
    """
    if data is None or len(data) < 50:
        return True
    last_atr = data["atr"].iloc[-1]
    avg_atr = data["atr"].iloc[-50:].mean()
    if avg_atr == 0 or np.isnan(avg_atr):
        return False
    if last_atr > avg_atr * VOLATILITY_THRESHOLD:
        logger.info(
            "Skipping trading due to high volatility: "
            f"ATR {last_atr:.5f} > {avg_atr * VOLATILITY_THRESHOLD:.5f}"
        )
        return True
    current_spread = data["spread"].iloc[-1]
    avg_spread = data["spread"].iloc[-50:].mean()
    if avg_spread == 0 or np.isnan(avg_spread):
        return False
    if current_spread > avg_spread * SPREAD_THRESHOLD_MULTIPLIER:
        logger.info(
            "Skipping trading due to wide spread: "
            f"spread {current_spread} > {avg_spread * SPREAD_THRESHOLD_MULTIPLIER}"
        )
        return True
    return False


def calculate_open_exposure(
    symbol: str,
    account_balance: float,
    symbol_info: mt5.SymbolInfo,
    default_risk_percent: float,
) -> float:
    """Return the total risk exposure of currently open positions as a fraction of balance."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or account_balance <= 0:
        return 0.0
    total_exposure = 0.0
    contract_size = getattr(symbol_info, "trade_contract_size", None)
    if contract_size is None or contract_size <= 0:
        tick_value = getattr(symbol_info, "trade_tick_value", 0)
        tick_size = getattr(symbol_info, "trade_tick_size", 0)
        if tick_value > 0 and tick_size > 0:
            contract_size = tick_value / tick_size
        else:
            contract_size = None
    use_contract = contract_size is not None and contract_size > 0
    for pos in positions:
        if pos.sl is None or pos.sl == 0:
            continue
        entry_price = pos.price_open
        sl = pos.sl
        risk_distance = abs(entry_price - sl)
        if risk_distance <= 0:
            continue
        if use_contract:
            risk_per_lot = risk_distance * contract_size
        else:
            point = symbol_info.point
            tick_value = symbol_info.trade_tick_value
            if point <= 0 or tick_value <= 0:
                continue
            risk_per_lot = (risk_distance / point) * tick_value
        risk_amount = risk_per_lot * pos.volume
        exposure = risk_amount / account_balance
        if exposure > default_risk_percent:
            exposure = default_risk_percent
        total_exposure += exposure
    return total_exposure


def manage_time_exit(symbol: str, max_bars: int) -> None:
    """Close positions that have been open longer than `max_bars` M5 periods."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or max_bars <= 0:
        return
    now = datetime.now()
    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue
        open_time = datetime.fromtimestamp(pos.time)
        elapsed_minutes = (now - open_time).total_seconds() / 60.0
        bar_length_minutes = 5  # M5 timeframe
        bars_open = elapsed_minutes / bar_length_minutes
        if bars_open >= max_bars:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                continue
            volume = pos.volume
            close_type = (
                mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            )
            price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "deviation": 20,
                "magic": MAGIC_NUMBER,
                "comment": "Time exit",
            }
            result = mt5.order_send(close_request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(
                    "Position %s closed due to max holding time (%.1f bars)",
                    pos.ticket,
                    bars_open,
                )
            else:
                logger.warning(
                    "Failed to close position %s on time exit: %s", pos.ticket, result
                )


def close_all_session_positions(symbol: str) -> None:
    """Close all positions opened by this bot. Called at end of Asian session."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return
    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            continue
        close_type = (
            mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        )
        price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": "Session end exit",
        }
        result = mt5.order_send(close_request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info("Position %s closed at session end", pos.ticket)
        else:
            logger.warning(
                "Failed to close position %s at session end: %s", pos.ticket, result
            )


# ---------------------------------------------------------------------------
# Profit Management and Trailing Stops (scalping-adapted)
# ---------------------------------------------------------------------------


def manage_open_positions(symbol: str) -> None:
    """Apply staged profit management to open positions.

    For scalping: partial close at 0.75R, full exit at 1.5R.
    """
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return
    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue
        sl = pos.sl
        if sl is None or sl == 0:
            continue
        entry_price = pos.price_open
        if pos.type == mt5.ORDER_TYPE_BUY:
            current_price = tick.bid
            risk_distance = entry_price - sl
            profit_distance = current_price - entry_price
        else:
            current_price = tick.ask
            risk_distance = sl - entry_price
            profit_distance = entry_price - current_price
        if risk_distance <= 0 or profit_distance <= 0:
            continue
        r_ratio = profit_distance / risk_distance
        # Partial close at 0.75R (faster profit-taking for scalping)
        if r_ratio >= 0.75 and pos.volume >= MIN_LOT * 2:
            half_volume = round(pos.volume / 2, 2)
            close_type = (
                mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            )
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": half_volume,
                "type": close_type,
                "position": pos.ticket,
                "price": tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask,
                "deviation": 20,
                "magic": MAGIC_NUMBER,
                "comment": "Partial profit",
            }
            result = mt5.order_send(close_request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(
                    "Partial close executed for position %s: closed %s at %.2f",
                    pos.ticket,
                    half_volume,
                    current_price,
                )
                new_sl = entry_price
                modify_request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": symbol,
                    "position": pos.ticket,
                    "sl": new_sl,
                    "tp": pos.tp,
                    "type": pos.type,
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK,
                    "magic": MAGIC_NUMBER,
                    "comment": "Move SL to breakeven",
                }
                mod = mt5.order_send(modify_request)
                if mod and mod.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info("Stop moved to breakeven for position %s", pos.ticket)
            else:
                logger.warning(
                    "Partial close failed for position %s: %s", pos.ticket, result
                )
        # Full exit at 1.5R (tighter than swing bot's 2R)
        elif r_ratio >= 1.5:
            close_type = (
                mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            )
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask,
                "deviation": 20,
                "magic": MAGIC_NUMBER,
                "comment": "Full exit at 1.5R",
            }
            result = mt5.order_send(close_request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info("Position %s fully closed at 1.5R profit", pos.ticket)
            else:
                logger.warning(
                    "Failed to fully close position %s: %s", pos.ticket, result
                )


def update_trailing_stops(symbol: str, atr: float) -> None:
    """Update stop-loss levels for open positions based on a tight trailing ATR stop."""
    if atr is None or np.isnan(atr) or atr <= 0:
        return
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return
    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue
        current_sl = pos.sl
        if current_sl is None or current_sl == 0:
            continue
        direction = pos.type
        if direction == mt5.ORDER_TYPE_BUY:
            current_price = tick.bid
            new_sl_candidate = current_price - atr * TRAIL_MULTIPLIER
            new_sl = max(current_sl, new_sl_candidate)
            if new_sl >= current_price or new_sl >= pos.tp:
                continue
            if new_sl > current_sl:
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": symbol,
                    "position": pos.ticket,
                    "sl": new_sl,
                    "tp": pos.tp,
                    "type": pos.type,
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK,
                    "magic": MAGIC_NUMBER,
                    "comment": "Trailing stop update",
                }
                result = mt5.order_send(req)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(
                        "Trailing stop updated for position %s: %.2f -> %.2f",
                        pos.ticket,
                        current_sl,
                        new_sl,
                    )
                else:
                    logger.warning(
                        "Failed to update trailing stop for position %s: %s",
                        pos.ticket,
                        result,
                    )
        elif direction == mt5.ORDER_TYPE_SELL:
            current_price = tick.ask
            new_sl_candidate = current_price + atr * TRAIL_MULTIPLIER
            new_sl = min(current_sl, new_sl_candidate)
            if new_sl <= current_price or new_sl <= pos.tp:
                continue
            if new_sl < current_sl:
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": symbol,
                    "position": pos.ticket,
                    "sl": new_sl,
                    "tp": pos.tp,
                    "type": pos.type,
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK,
                    "magic": MAGIC_NUMBER,
                    "comment": "Trailing stop update",
                }
                result = mt5.order_send(req)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(
                        "Trailing stop updated for position %s: %.2f -> %.2f",
                        pos.ticket,
                        current_sl,
                        new_sl,
                    )
                else:
                    logger.warning(
                        "Failed to update trailing stop for position %s: %s",
                        pos.ticket,
                        result,
                    )


# ---------------------------------------------------------------------------
# Trade Execution
# ---------------------------------------------------------------------------


def execute_trade(
    symbol: str,
    direction: str,
    entry_price: float,
    sl: float,
    tp: float,
    lot_size: float,
) -> bool:
    """Send a market order to MetaTrader 5 and update the daily trade count."""
    global TRADES_TODAY
    if direction == "buy":
        order_type = mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error("Failed to retrieve tick data for BUY order")
            return False
        price = tick.ask
    elif direction == "sell":
        order_type = mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error("Failed to retrieve tick data for SELL order")
            return False
        price = tick.bid
    else:
        logger.error(f"Invalid trade direction: {direction}")
        return False
    info = mt5.symbol_info(symbol)
    if info:
        buffer = max(info.point * 10, 0.1)
    else:
        buffer = 0.1
    if direction == "buy":
        if sl >= price:
            sl = price - buffer
        if tp <= price:
            tp = price + buffer
    elif direction == "sell":
        if sl <= price:
            sl = price + buffer
        if tp >= price:
            tp = price - buffer
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "Asian scalp",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    result = mt5.order_send(request)
    if result is None:
        logger.error("order_send returned None")
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Trade failed: {result.comment} (retcode {result.retcode})")
        return False
    logger.info(
        "Trade placed: %s %s lots at %.2f, SL %.2f, TP %.2f",
        direction,
        lot_size,
        price,
        sl,
        tp,
    )
    try:
        if getattr(result, "deal", 0) != 0:
            TRADES_TODAY += 1
    except Exception:
        TRADES_TODAY += 1
    return True


# ---------------------------------------------------------------------------
# Main trading loop
# ---------------------------------------------------------------------------


def main() -> None:
    """Main loop for the Asian session scalping bot."""
    global TRADES_TODAY
    check_python_version()
    try:
        login = int(os.environ.get("MT5_LOGIN") or input("Enter MT5 login: "))
        password = os.environ.get("MT5_PASSWORD") or input("Enter MT5 password: ")
        server = os.environ.get("MT5_SERVER") or input("Enter MT5 server: ")
    except ValueError:
        logger.error("Invalid login provided.")
        return
    connect_to_mt5(login, password, server)
    logger.info(
        "Starting Asian session scalping bot for %s on M5 timeframe "
        "(session %02d:00-%02d:00 UTC)",
        SYMBOL,
        ASIAN_SESSION_START_UTC,
        ASIAN_SESSION_END_UTC,
    )
    calendar_events: List[datetime] = load_calendar_events(NEWS_EVENTS_FILE)

    while True:
        account_info = mt5.account_info()
        if not account_info:
            logger.error("Failed to retrieve account info; reconnecting...")
            mt5.shutdown()
            time.sleep(10)
            connect_to_mt5(login, password, server)
            continue

        now = datetime.now()
        now_utc = datetime.now(tz=timezone.utc)

        # Reset daily counters at midnight
        reset_daily_counters(now)

        # ---- Asian session gate ----
        if not is_within_asian_session(now_utc):
            # Close all positions at session end
            close_all_session_positions(SYMBOL)
            logger.info("Outside Asian session; waiting...")
            time.sleep(60)
            continue

        # Check drawdown limit
        if not check_drawdown_limit(account_info):
            time.sleep(SLEEP_INTERVAL)
            continue

        # Check for news and calendar events
        if should_skip_due_to_news(now) or should_skip_due_to_calendar(now, calendar_events):
            logger.info("Skipping trading due to scheduled news event.")
            time.sleep(SLEEP_INTERVAL)
            continue

        # Fetch market data (300 M5 bars = 25 hours)
        data = fetch_live_market_data(SYMBOL, TIMEFRAME, bars=300)
        if data is None or len(data) < 50:
            logger.warning("Insufficient data; retrying later.")
            time.sleep(SLEEP_INTERVAL)
            continue

        # Apply volatility and spread filters (stricter for scalping)
        if check_volatility_and_spread(data):
            time.sleep(SLEEP_INTERVAL)
            continue

        # Determine dynamic risk factor based on intraday performance
        daily_loss_ratio = get_daily_loss_ratio(SYMBOL, account_info.balance)
        consecutive_losses = get_consecutive_losses(SYMBOL)
        risk_factor = get_dynamic_risk_factor(daily_loss_ratio, consecutive_losses)

        base_risk_per_trade = get_risk_percent_for_balance(account_info.balance)

        # Enforce consecutive loss circuit breaker
        if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            logger.warning(
                "Consecutive loss limit reached (%s losses). Pausing trading.",
                consecutive_losses,
            )
            time.sleep(SLEEP_INTERVAL)
            continue

        active_positions, active_orders = get_active_bot_orders(SYMBOL)
        if active_orders:
            logger.info("Pending orders exist; waiting for them to clear.")
            time.sleep(SLEEP_INTERVAL)
            continue

        if TRADES_TODAY >= MAX_TRADES_PER_DAY:
            if not active_positions and not active_orders:
                TRADES_TODAY = 0
            else:
                logger.info("Maximum trades per day reached; skipping further entries.")
                time.sleep(SLEEP_INTERVAL)
                continue

        # Compute session range for dynamic S/R levels
        session_range = get_session_range(data, now_utc)

        # Generate scalping signals (confluence-based)
        scalp_signals = generate_scalp_signals(data, session_range)

        if not scalp_signals:
            logger.info("No scalping signals with sufficient confluence.")
            # Still manage existing positions
            last_atr = data["atr"].iloc[-1]
            update_trailing_stops(SYMBOL, last_atr)
            manage_open_positions(SYMBOL)
            manage_time_exit(SYMBOL, MAX_HOLDING_BARS)
            time.sleep(SLEEP_INTERVAL)
            continue

        last_atr = data["atr"].iloc[-1]
        symbol_info = mt5.symbol_info(SYMBOL)
        if symbol_info is None:
            logger.error("Failed to retrieve symbol info.")
            time.sleep(SLEEP_INTERVAL)
            continue

        current_exposure = calculate_open_exposure(
            SYMBOL, account_info.balance, symbol_info, base_risk_per_trade
        )

        for signal in scalp_signals:
            idx = signal["index"]
            entry_price = float(data["close"].iloc[idx])
            direction = signal["direction"]
            stop_levels = calculate_stop_levels(entry_price, last_atr, direction)
            sl = stop_levels["sl"]
            tp = stop_levels["tp"]
            stop_distance = stop_levels["stop_distance"]

            effective_risk = base_risk_per_trade * risk_factor
            lot_size = calculate_lot_size(
                account_info.balance, effective_risk, stop_distance, symbol_info
            )

            # Estimate prospective exposure
            contract_size = getattr(symbol_info, "trade_contract_size", None)
            if contract_size is None or contract_size <= 0:
                tick_value = getattr(symbol_info, "trade_tick_value", 0)
                tick_size = getattr(symbol_info, "trade_tick_size", 0)
                if tick_value > 0 and tick_size > 0:
                    contract_size = tick_value / tick_size
                else:
                    contract_size = None
            if contract_size is not None and contract_size > 0:
                prospective_risk_amount = stop_distance * contract_size * lot_size
            else:
                if symbol_info.point <= 0 or symbol_info.trade_tick_value <= 0:
                    prospective_risk_amount = 0.0
                else:
                    prospective_risk_amount = (
                        (stop_distance / symbol_info.point)
                        * symbol_info.trade_tick_value
                        * lot_size
                    )
            prospective_exposure = (
                prospective_risk_amount / account_info.balance
                if account_info.balance > 0
                else 0.0
            )
            if prospective_exposure > effective_risk:
                prospective_exposure = effective_risk
            if current_exposure + prospective_exposure > MAX_EXPOSURE_LIMIT:
                logger.info(
                    "Exposure limit reached: current %.2f%%, prospective %.2f%%. "
                    "Skipping trade.",
                    current_exposure * 100,
                    prospective_exposure * 100,
                )
                continue

            reasons_str = ", ".join(signal.get("reasons", []))
            logger.info(
                "Scalp signal: %s (score=%d, reasons: %s)",
                direction,
                signal["score"],
                reasons_str,
            )
            success = execute_trade(SYMBOL, direction, entry_price, sl, tp, lot_size)
            if success:
                current_exposure += prospective_exposure

        # Update trailing stops and manage existing positions
        update_trailing_stops(SYMBOL, last_atr)
        manage_open_positions(SYMBOL)
        manage_time_exit(SYMBOL, MAX_HOLDING_BARS)
        time.sleep(SLEEP_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot terminated by user.")
    finally:
        mt5.shutdown()
