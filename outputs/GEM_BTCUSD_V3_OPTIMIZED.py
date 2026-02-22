#!/usr/bin/env python3
"""
GEM_BTCUSD_V3 — BTCUSD Pyramiding Trading Bot for MetaTrader 5
Multi-indicator confluence system with pyramiding (adding to winners)
Designed for $400 micro accounts with 0.01 minimum lot size on M15 timeframe.
"""
# ===========================================================================
# OPTIMIZED by optimizer.py on 2026-02-22 15:38:21
# Score: -2.4 | Return: -2.4% | MaxDD: 2.41%
# Trades: 1 | WinRate: 0.0% | PF: 0.00
# Starting balance: $400 -> $390.37
# ===========================================================================


import os
import sys
import time
import logging
import math
from datetime import datetime, timezone, timedelta
from collections import defaultdict

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MetaTrader5 package not found. Install with: pip install MetaTrader5")
    sys.exit(1)

import numpy as np

# =============================================================================
# CONFIGURATION — All parameters via environment variables with defaults
# =============================================================================

SYMBOL = os.environ.get("SYMBOL", "BTCUSD")
MAGIC_NUMBER = int(os.environ.get("MAGIC_NUMBER", "314159"))
TIMEFRAME = mt5.TIMEFRAME_M15
BARS_NEEDED = int(os.environ.get("BARS_NEEDED", "250"))

# Confluence & Entry
MIN_CONFLUENCE_SCORE = int(os.environ.get("MIN_CONFLUENCE_SCORE", "65"))
MAX_TRADES_PER_DAY = int(os.environ.get("MAX_TRADES_PER_DAY", "6"))
MAX_CONSECUTIVE_LOSSES = int(os.environ.get("MAX_CONSECUTIVE_LOSSES", "1"))

# Stop Loss & Take Profit
STOP_MULTIPLIER = float(os.environ.get("STOP_MULTIPLIER", "1.4"))
TP_MULTIPLIER = float(os.environ.get("TP_MULTIPLIER", "6.0"))

# Trailing Stop
TRAIL_LOCK_R = float(os.environ.get("TRAIL_LOCK_R", "0.3"))
TRAIL_TIGHT_MULT = float(os.environ.get("TRAIL_TIGHT_MULT", "0.9"))
TRAIL_VTIGHT_MULT = float(os.environ.get("TRAIL_VTIGHT_MULT", "0.3"))

# Exposure & Risk
MAX_EXPOSURE_LIMIT = float(os.environ.get("MAX_EXPOSURE_LIMIT", "0.08"))
DD_HALT = float(os.environ.get("DD_HALT", "0.03"))
MAX_HOLDING_BARS = int(os.environ.get("MAX_HOLDING_BARS", "64"))

# ATR filters
ATR_MIN_PCT = float(os.environ.get("ATR_MIN_PCT", "0.001"))
ATR_MAX_PCT = float(os.environ.get("ATR_MAX_PCT", "0.08"))

# Risk tiers (balance thresholds)
RISK_TIER_1 = float(os.environ.get("RISK_TIER_1", "0.03"))  # < $500
RISK_TIER_2 = float(os.environ.get("RISK_TIER_2", "0.015"))  # $500-$1000
RISK_TIER_3 = float(os.environ.get("RISK_TIER_3", "0.015"))  # $1000-$5000
RISK_TIER_4 = float(os.environ.get("RISK_TIER_4", "0.010"))  # $5000-$20000
RISK_TIER_5 = float(os.environ.get("RISK_TIER_5", "0.005"))  # $20000-$50000
RISK_TIER_6 = float(os.environ.get("RISK_TIER_6", "0.003"))  # $50000+

# Pyramid parameters
PYRAMID_ENABLED = os.environ.get("PYRAMID_ENABLED", "True").lower() in ("true", "1", "yes")
MAX_PYRAMID_ADDONS = int(os.environ.get("MAX_PYRAMID_ADDONS", "3"))
PYRAMID_ADD_1_AT_R = float(os.environ.get("PYRAMID_ADD_1_AT_R", "0.8"))
PYRAMID_ADD_2_AT_R = float(os.environ.get("PYRAMID_ADD_2_AT_R", "2.3"))
PYRAMID_ADD_3_AT_R = float(os.environ.get("PYRAMID_ADD_3_AT_R", "3.8"))
PYRAMID_ADD_1_SIZE = float(os.environ.get("PYRAMID_ADD_1_SIZE", "0.5"))
PYRAMID_ADD_2_SIZE = float(os.environ.get("PYRAMID_ADD_2_SIZE", "0.4"))
PYRAMID_ADD_3_SIZE = float(os.environ.get("PYRAMID_ADD_3_SIZE", "0.5"))
PYRAMID_MIN_CONFLUENCE = int(os.environ.get("PYRAMID_MIN_CONFLUENCE", "35"))
PYRAMID_STOP_ATR_MULT = float(os.environ.get("PYRAMID_STOP_ATR_MULT", "0.8"))
PYRAMID_LOCK_AFTER_ADD1_R = float(os.environ.get("PYRAMID_LOCK_AFTER_ADD1_R", "0.1"))
PYRAMID_LOCK_AFTER_ADD2_R = float(os.environ.get("PYRAMID_LOCK_AFTER_ADD2_R", "0.5"))
PYRAMID_LOCK_AFTER_ADD3_R = float(os.environ.get("PYRAMID_LOCK_AFTER_ADD3_R", "0.75"))
PYRAMID_MAX_ADDON_EXPOSURE = float(os.environ.get("PYRAMID_MAX_ADDON_EXPOSURE", "0.04"))
PYRAMID_HTF_MODE = os.environ.get("PYRAMID_HTF_MODE", "both")  # "any" or "both"
PYRAMID_ADX_MIN = float(os.environ.get("PYRAMID_ADX_MIN", "22"))

# Logging
LOG_FILE = os.environ.get("LOG_FILE", "gem_btcusd_v3.log")

# =============================================================================
# LOGGING SETUP
# =============================================================================

logger = logging.getLogger("GEM_BTCUSD_V3")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logger.addHandler(console_handler)
logger.addHandler(file_handler)

# =============================================================================
# GLOBAL STATE
# =============================================================================

PYRAMID_STATE = {}  # ticket -> {addons, original_volume, original_risk_distance, addon_tickets, direction}
DAILY_TRADES = defaultdict(int)
DAILY_LOSSES = defaultdict(int)
CONSECUTIVE_LOSSES = 0
LAST_BAR_TIME = None
PEAK_BALANCE = None


# =============================================================================
# INDICATOR CALCULATIONS
# =============================================================================

def calc_ema(data, period):
    """Calculate Exponential Moving Average."""
    ema = np.zeros_like(data, dtype=float)
    if len(data) < period:
        return ema
    ema[period - 1] = np.mean(data[:period])
    mult = 2.0 / (period + 1)
    for i in range(period, len(data)):
        ema[i] = data[i] * mult + ema[i - 1] * (1 - mult)
    # Fill initial values
    ema[:period - 1] = np.nan
    return ema


def calc_rsi(close, period=14):
    """Calculate RSI with Wilder smoothing."""
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    rsi = np.full(len(close), np.nan)
    if len(close) < period + 1:
        return rsi

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def calc_macd(close, fast=12, slow=26, signal=9):
    """Calculate MACD line, signal line, and histogram."""
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line[~np.isnan(macd_line)], signal)
    # Align signal_line
    full_signal = np.full_like(close, np.nan)
    offset = len(close) - len(signal_line)
    full_signal[offset:] = signal_line
    histogram = macd_line - full_signal
    return macd_line, full_signal, histogram


def calc_bollinger(close, period=20, std_dev=2.0):
    """Calculate Bollinger Bands."""
    middle = np.full_like(close, np.nan)
    upper = np.full_like(close, np.nan)
    lower = np.full_like(close, np.nan)

    for i in range(period - 1, len(close)):
        window = close[i - period + 1:i + 1]
        m = np.mean(window)
        s = np.std(window, ddof=0)
        middle[i] = m
        upper[i] = m + std_dev * s
        lower[i] = m - std_dev * s

    return upper, middle, lower


def calc_atr(high, low, close, period=14):
    """Calculate ATR with Wilder smoothing."""
    tr = np.zeros(len(close))
    tr[0] = high[0] - low[0]
    for i in range(1, len(close)):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))

    atr = np.full(len(close), np.nan)
    if len(close) < period:
        return atr

    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, len(close)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def calc_adx(high, low, close, period=14):
    """Calculate ADX."""
    n = len(close)
    if n < period * 2:
        return np.full(n, np.nan)

    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    tr = np.zeros(n)

    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))

    smoothed_tr = np.zeros(n)
    smoothed_plus = np.zeros(n)
    smoothed_minus = np.zeros(n)

    smoothed_tr[period] = np.sum(tr[1:period + 1])
    smoothed_plus[period] = np.sum(plus_dm[1:period + 1])
    smoothed_minus[period] = np.sum(minus_dm[1:period + 1])

    for i in range(period + 1, n):
        smoothed_tr[i] = smoothed_tr[i - 1] - smoothed_tr[i - 1] / period + tr[i]
        smoothed_plus[i] = smoothed_plus[i - 1] - smoothed_plus[i - 1] / period + plus_dm[i]
        smoothed_minus[i] = smoothed_minus[i - 1] - smoothed_minus[i - 1] / period + minus_dm[i]

    plus_di = np.where(smoothed_tr > 0, 100 * smoothed_plus / smoothed_tr, 0)
    minus_di = np.where(smoothed_tr > 0, 100 * smoothed_minus / smoothed_tr, 0)

    dx = np.where((plus_di + minus_di) > 0, 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di), 0)

    adx = np.full(n, np.nan)
    if n > period * 2:
        adx[period * 2 - 1] = np.mean(dx[period:period * 2])
        for i in range(period * 2, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return adx


def calc_stoch_rsi(close, rsi_period=14, stoch_period=14, k_smooth=3, d_smooth=3):
    """Calculate Stochastic RSI."""
    rsi = calc_rsi(close, rsi_period)
    n = len(close)
    stoch_k = np.full(n, np.nan)

    for i in range(rsi_period + stoch_period - 1, n):
        window = rsi[i - stoch_period + 1:i + 1]
        if np.any(np.isnan(window)):
            continue
        rsi_min = np.min(window)
        rsi_max = np.max(window)
        if rsi_max - rsi_min > 0:
            stoch_k[i] = (rsi[i] - rsi_min) / (rsi_max - rsi_min) * 100
        else:
            stoch_k[i] = 50.0

    # Smooth K
    k_smooth_arr = np.full(n, np.nan)
    for i in range(k_smooth - 1, n):
        window = stoch_k[i - k_smooth + 1:i + 1]
        if not np.any(np.isnan(window)):
            k_smooth_arr[i] = np.mean(window)

    # D line
    d_arr = np.full(n, np.nan)
    for i in range(d_smooth - 1, n):
        window = k_smooth_arr[i - d_smooth + 1:i + 1]
        if not np.any(np.isnan(window)):
            d_arr[i] = np.mean(window)

    return k_smooth_arr, d_arr


def calc_vwap(close, volume, period=96):
    """Calculate rolling VWAP (96-bar = 24hr on M15)."""
    vwap = np.full(len(close), np.nan)
    for i in range(period - 1, len(close)):
        window_close = close[i - period + 1:i + 1]
        window_vol = volume[i - period + 1:i + 1]
        total_vol = np.sum(window_vol)
        if total_vol > 0:
            vwap[i] = np.sum(window_close * window_vol) / total_vol
        else:
            vwap[i] = close[i]
    return vwap


def calc_volume_ma(volume, period=20):
    """Calculate simple moving average of volume."""
    ma = np.full(len(volume), np.nan)
    for i in range(period - 1, len(volume)):
        ma[i] = np.mean(volume[i - period + 1:i + 1])
    return ma


# =============================================================================
# INDICATOR CONTAINER
# =============================================================================

class Indicators:
    """Container for all computed indicator values."""
    def __init__(self):
        self.ema9 = None
        self.ema20 = None
        self.ema50 = None
        self.rsi = None
        self.macd_line = None
        self.macd_signal = None
        self.macd_hist = None
        self.bb_upper = None
        self.bb_middle = None
        self.bb_lower = None
        self.atr = None
        self.adx = None
        self.stoch_k = None
        self.stoch_d = None
        self.vwap = None
        self.vol_ma = None

    def compute(self, rates):
        """Compute all indicators from M15 rate data."""
        close = rates['close'].astype(float)
        high = rates['high'].astype(float)
        low = rates['low'].astype(float)
        volume = rates['tick_volume'].astype(float)

        self.ema9 = calc_ema(close, 9)
        self.ema20 = calc_ema(close, 20)
        self.ema50 = calc_ema(close, 50)
        self.rsi = calc_rsi(close, 14)
        self.macd_line, self.macd_signal, self.macd_hist = calc_macd(close, 12, 26, 9)
        self.bb_upper, self.bb_middle, self.bb_lower = calc_bollinger(close, 20, 2.0)
        self.atr = calc_atr(high, low, close, 14)
        self.adx = calc_adx(high, low, close, 14)
        self.stoch_k, self.stoch_d = calc_stoch_rsi(close, 14, 14, 3, 3)
        self.vwap = calc_vwap(close, volume, 96)
        self.vol_ma = calc_volume_ma(volume, 20)


# =============================================================================
# HIGHER TIMEFRAME ANALYSIS
# =============================================================================

def get_htf_trend(symbol, timeframe, num_bars=100):
    """Get higher timeframe trend from MT5 directly."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    if rates is None or len(rates) < 50:
        return "neutral"

    close = np.array([r[4] for r in rates], dtype=float)  # close price
    ema20 = calc_ema(close, 20)
    ema50 = calc_ema(close, 50)

    if np.isnan(ema20[-1]) or np.isnan(ema50[-1]):
        return "neutral"

    if ema20[-1] > ema50[-1]:
        return "bullish"
    elif ema20[-1] < ema50[-1]:
        return "bearish"
    return "neutral"


def get_htf_trends(symbol):
    """Get both H1 and H4 trends."""
    h1_trend = get_htf_trend(symbol, mt5.TIMEFRAME_H1, 100)
    h4_trend = get_htf_trend(symbol, mt5.TIMEFRAME_H4, 100)
    return h1_trend, h4_trend


# =============================================================================
# MOMENTUM REGIME DETECTION
# =============================================================================

def detect_regime(adx_val, ema9_val, ema20_val, ema50_val):
    """Classify market regime: trending, ranging, or transitioning."""
    if np.isnan(adx_val) or np.isnan(ema9_val) or np.isnan(ema20_val) or np.isnan(ema50_val):
        return "transitioning"

    ema_aligned = (ema9_val > ema20_val > ema50_val) or (ema9_val < ema20_val < ema50_val)

    if adx_val >= 25 and ema_aligned:
        return "trending"
    elif adx_val < 20:
        return "ranging"
    else:
        return "transitioning"


# =============================================================================
# CANDLESTICK PATTERN DETECTION
# =============================================================================

def detect_patterns(rates, idx):
    """Detect candlestick patterns at the given bar index. Returns list of (pattern_name, direction)."""
    patterns = []
    if idx < 2:
        return patterns

    o0, h0, l0, c0 = rates['open'][idx], rates['high'][idx], rates['low'][idx], rates['close'][idx]
    o1, h1, l1, c1 = rates['open'][idx - 1], rates['high'][idx - 1], rates['low'][idx - 1], rates['close'][idx - 1]
    o2, h2, l2, c2 = rates['open'][idx - 2], rates['high'][idx - 2], rates['low'][idx - 2], rates['close'][idx - 2]

    body0 = abs(c0 - o0)
    body1 = abs(c1 - o1)
    range0 = h0 - l0
    range1 = h1 - l1

    if range0 == 0:
        range0 = 0.01
    if range1 == 0:
        range1 = 0.01

    # Bullish Engulfing
    if c1 < o1 and c0 > o0 and body0 > body1 * 0.8 and c0 > o1 and o0 <= c1:
        patterns.append(("bullish_engulfing", "buy"))

    # Bearish Engulfing
    if c1 > o1 and c0 < o0 and body0 > body1 * 0.8 and c0 < o1 and o0 >= c1:
        patterns.append(("bearish_engulfing", "sell"))

    # Bullish Pin Bar
    lower_wick = min(o0, c0) - l0
    upper_wick = h0 - max(o0, c0)
    if lower_wick > 2 * body0 and lower_wick > 0.6 * range0 and upper_wick < body0:
        patterns.append(("bullish_pin_bar", "buy"))

    # Bearish Pin Bar
    if upper_wick > 2 * body0 and upper_wick > 0.6 * range0 and lower_wick < body0:
        patterns.append(("bearish_pin_bar", "sell"))

    # Liquidity Sweep Bull
    prev_low1 = l1
    prev_low2 = l2
    mid_range = (h0 + l0) / 2
    if l0 < prev_low1 and l0 < prev_low2 and c0 > mid_range and c0 > c1:
        patterns.append(("liquidity_sweep_bull", "buy"))

    # Liquidity Sweep Bear
    prev_high1 = h1
    prev_high2 = h2
    if h0 > prev_high1 and h0 > prev_high2 and c0 < mid_range and c0 < c1:
        patterns.append(("liquidity_sweep_bear", "sell"))

    return patterns


# =============================================================================
# CONFLUENCE SCORING
# =============================================================================

def calc_confluence_score(direction, indicators, idx, h1_trend, h4_trend, rates):
    """Calculate confluence score (0-100) for a signal direction."""
    score = 0

    rsi_val = indicators.rsi[idx] if not np.isnan(indicators.rsi[idx]) else 50
    macd_hist = indicators.macd_hist[idx] if not np.isnan(indicators.macd_hist[idx]) else 0
    ema9 = indicators.ema9[idx] if not np.isnan(indicators.ema9[idx]) else 0
    ema20 = indicators.ema20[idx] if not np.isnan(indicators.ema20[idx]) else 0
    ema50 = indicators.ema50[idx] if not np.isnan(indicators.ema50[idx]) else 0
    bb_mid = indicators.bb_middle[idx] if not np.isnan(indicators.bb_middle[idx]) else rates['close'][idx]
    adx_val = indicators.adx[idx] if not np.isnan(indicators.adx[idx]) else 0
    vol = rates['tick_volume'][idx]
    vol_ma = indicators.vol_ma[idx] if not np.isnan(indicators.vol_ma[idx]) else vol
    vwap = indicators.vwap[idx] if not np.isnan(indicators.vwap[idx]) else rates['close'][idx]
    close = rates['close'][idx]

    is_bull = direction == "buy"
    target_trend = "bullish" if is_bull else "bearish"

    # HTF alignment
    both_htf = (h1_trend == target_trend and h4_trend == target_trend)
    one_htf = (h1_trend == target_trend or h4_trend == target_trend)
    if both_htf:
        score += 30
    elif one_htf:
        score += 15

    # RSI
    if is_bull:
        if rsi_val < 40:
            score += 15
        elif rsi_val < 55:
            score += 10
    else:
        if rsi_val > 60:
            score += 15
        elif rsi_val > 45:
            score += 10

    # MACD histogram
    if is_bull and macd_hist > 0:
        score += 15
    elif not is_bull and macd_hist < 0:
        score += 15

    # EMA stack
    if is_bull and ema9 > ema20 > ema50:
        score += 10
    elif not is_bull and ema9 < ema20 < ema50:
        score += 10

    # BB middle
    if is_bull and close < bb_mid:
        score += 10
    elif not is_bull and close > bb_mid:
        score += 10

    # ADX
    if adx_val >= 25:
        score += 10
    elif adx_val >= 20:
        score += 5

    # Volume
    if vol_ma > 0 and vol > 1.3 * vol_ma:
        score += 10

    # VWAP
    if is_bull and close > vwap:
        score += 5
    elif not is_bull and close < vwap:
        score += 5

    # ADX penalty
    if adx_val < 20:
        score -= 10

    return max(0, score)


# =============================================================================
# RISK MANAGEMENT
# =============================================================================

def get_risk_percent(balance):
    """Get risk percentage based on account balance tier."""
    if balance < 500:
        return RISK_TIER_1
    elif balance < 1000:
        return RISK_TIER_2
    elif balance < 5000:
        return RISK_TIER_3
    elif balance < 20000:
        return RISK_TIER_4
    elif balance < 50000:
        return RISK_TIER_5
    else:
        return RISK_TIER_6


def calc_lot_size(balance, atr_value, symbol_info):
    """Calculate position size based on risk and ATR."""
    risk_pct = get_risk_percent(balance)
    risk_amount = balance * risk_pct
    stop_distance = atr_value * STOP_MULTIPLIER
    contract_size = symbol_info.trade_contract_size

    if stop_distance <= 0 or contract_size <= 0:
        return symbol_info.volume_min

    lot_size = risk_amount / (stop_distance * contract_size)

    # Round to volume step
    step = symbol_info.volume_step
    lot_size = math.floor(lot_size / step) * step
    lot_size = max(symbol_info.volume_min, min(symbol_info.volume_max, lot_size))
    lot_size = round(lot_size, 2)

    return lot_size


def calc_total_exposure(balance, symbol_info, positions, current_price):
    """Calculate total exposure as fraction of balance."""
    contract_size = symbol_info.trade_contract_size
    total = 0.0

    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue
        sl_dist = abs(current_price - pos.sl) if pos.sl > 0 else abs(current_price - pos.price_open) * 0.02
        total += sl_dist * pos.volume * contract_size / balance

    return total


def check_dd_halt(balance, peak_balance):
    """Check if drawdown halt threshold is breached."""
    if peak_balance <= 0:
        return False
    dd = (peak_balance - balance) / peak_balance
    return dd >= DD_HALT


# =============================================================================
# ORDER EXECUTION
# =============================================================================

def send_market_order(symbol, direction, volume, sl, tp, comment=""):
    """Send a market order via MT5."""
    order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error(f"Failed to get tick for {symbol}")
        return None

    price = tick.ask if direction == "buy" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "deviation": 30,
        "magic": MAGIC_NUMBER,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        logger.error(f"order_send failed: result is None")
        return None

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Order failed: retcode={result.retcode}, comment={result.comment}")
        return None

    logger.info(f"Order executed: {direction} {volume} {symbol} @ {price}, SL={sl:.2f}, TP={tp:.2f}, ticket={result.order}")
    return result


def modify_sl(position, new_sl):
    """Modify stop loss of an open position."""
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position.ticket,
        "symbol": position.symbol,
        "sl": round(new_sl, 2),
        "tp": round(position.tp, 2),
        "magic": MAGIC_NUMBER,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.debug(f"SL modified for #{position.ticket}: new SL={new_sl:.2f}")
        return True
    else:
        logger.warning(f"Failed to modify SL for #{position.ticket}")
        return False


def close_position(position):
    """Close an open position at market."""
    tick = mt5.symbol_info_tick(position.symbol)
    if tick is None:
        return False

    if position.type == mt5.ORDER_TYPE_BUY:
        price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL
    else:
        price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": position.volume,
        "type": order_type,
        "position": position.ticket,
        "price": price,
        "deviation": 30,
        "magic": MAGIC_NUMBER,
        "comment": "close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"Closed position #{position.ticket} @ {price}")
        return True
    else:
        logger.error(f"Failed to close #{position.ticket}")
        return False


# =============================================================================
# TRAILING STOP MANAGEMENT
# =============================================================================

def manage_trailing_stops(positions, indicators, idx, rates):
    """Manage 3-tier trailing stop for all open positions."""
    atr_val = indicators.atr[idx]
    if np.isnan(atr_val) or atr_val <= 0:
        return

    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue

        is_buy = pos.type == mt5.ORDER_TYPE_BUY
        entry = pos.price_open
        current = rates['close'][idx]
        risk_dist = abs(entry - pos.sl) if pos.sl > 0 else atr_val * STOP_MULTIPLIER

        if risk_dist <= 0:
            continue

        direction_mult = 1.0 if is_buy else -1.0
        unrealized_r = (current - entry) * direction_mult / risk_dist

        new_sl = pos.sl

        # Tier 3: >= 2.0R — very tight trail
        if unrealized_r >= 2.0:
            trail_dist = atr_val * TRAIL_VTIGHT_MULT
            if is_buy:
                candidate_sl = current - trail_dist
            else:
                candidate_sl = current + trail_dist
        # Tier 2: >= 1.5R — tight trail
        elif unrealized_r >= 1.5:
            trail_dist = atr_val * TRAIL_TIGHT_MULT
            if is_buy:
                candidate_sl = current - trail_dist
            else:
                candidate_sl = current + trail_dist
        # Tier 1: >= 1.0R — lock breakeven + 0.3R
        elif unrealized_r >= 1.0:
            lock = TRAIL_LOCK_R * risk_dist
            if is_buy:
                candidate_sl = entry + lock
            else:
                candidate_sl = entry - lock
        else:
            continue

        # Only move SL forward
        if is_buy and candidate_sl > pos.sl:
            new_sl = candidate_sl
        elif not is_buy and (pos.sl == 0 or candidate_sl < pos.sl):
            new_sl = candidate_sl

        if new_sl != pos.sl:
            modify_sl(pos, new_sl)


# =============================================================================
# TIME-BASED EXIT
# =============================================================================

def check_time_exits(positions, current_bar_time):
    """Close positions held longer than MAX_HOLDING_BARS."""
    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue

        open_time = datetime.fromtimestamp(pos.time, tz=timezone.utc)
        bars_held = (current_bar_time - open_time).total_seconds() / 900  # M15 = 900 seconds

        if bars_held >= MAX_HOLDING_BARS:
            logger.info(f"Time exit: #{pos.ticket} held for {bars_held:.0f} bars (max={MAX_HOLDING_BARS})")
            close_position(pos)


# =============================================================================
# PYRAMID SYSTEM
# =============================================================================

def calc_pyramid_momentum(indicators, idx, direction, rates):
    """Calculate pyramid momentum score (0-65 scale)."""
    score = 0

    macd_hist = indicators.macd_hist[idx] if not np.isnan(indicators.macd_hist[idx]) else 0
    prev_hist = indicators.macd_hist[idx - 1] if idx > 0 and not np.isnan(indicators.macd_hist[idx - 1]) else 0
    rsi_val = indicators.rsi[idx] if not np.isnan(indicators.rsi[idx]) else 50
    stoch_k = indicators.stoch_k[idx] if not np.isnan(indicators.stoch_k[idx]) else 50
    vol = rates['tick_volume'][idx]
    vol_ma = indicators.vol_ma[idx] if not np.isnan(indicators.vol_ma[idx]) else vol

    is_bull = direction == "buy"

    # MACD histogram accelerating
    if is_bull and macd_hist > 0 and macd_hist > prev_hist:
        score += 15
    elif not is_bull and macd_hist < 0 and macd_hist < prev_hist:
        score += 15

    # RSI in healthy range
    if is_bull and 40 <= rsi_val <= 75:
        score += 15
    elif not is_bull and 25 <= rsi_val <= 60:
        score += 15

    # Price making new high/low
    if idx > 0:
        if is_bull and rates['high'][idx] > rates['high'][idx - 1]:
            score += 10
        elif not is_bull and rates['low'][idx] < rates['low'][idx - 1]:
            score += 10

    # Volume confirmation
    if vol_ma > 0 and vol > 1.2 * vol_ma:
        score += 10

    # Stochastic RSI in middle range
    if 20 <= stoch_k <= 80:
        score += 10

    return score


def evaluate_pyramids(positions, indicators, idx, rates, balance, symbol_info, h1_trend, h4_trend):
    """Evaluate and execute pyramid additions for open positions."""
    global PYRAMID_STATE

    if not PYRAMID_ENABLED:
        return

    atr_val = indicators.atr[idx]
    adx_val = indicators.adx[idx]
    if np.isnan(atr_val) or np.isnan(adx_val):
        return

    # Regime check
    if adx_val < PYRAMID_ADX_MIN:
        return

    current_price = rates['close'][idx]
    contract_size = symbol_info.trade_contract_size

    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue

        ticket = pos.ticket
        is_buy = pos.type == mt5.ORDER_TYPE_BUY
        direction = "buy" if is_buy else "sell"

        # Initialize pyramid state if not tracked
        if ticket not in PYRAMID_STATE:
            risk_dist = abs(pos.price_open - pos.sl) if pos.sl > 0 else atr_val * STOP_MULTIPLIER
            PYRAMID_STATE[ticket] = {
                "addons": 0,
                "original_volume": pos.volume,
                "original_risk_distance": risk_dist,
                "addon_tickets": [],
                "direction": direction,
            }

        state = PYRAMID_STATE[ticket]

        # Skip if max addons reached
        if state["addons"] >= MAX_PYRAMID_ADDONS:
            continue

        # HTF check
        target_trend = "bullish" if is_buy else "bearish"
        if PYRAMID_HTF_MODE == "both":
            if h1_trend != target_trend or h4_trend != target_trend:
                continue
        else:  # "any"
            if h1_trend != target_trend and h4_trend != target_trend:
                continue

        # Calculate unrealized R
        risk_dist = state["original_risk_distance"]
        if risk_dist <= 0:
            continue

        direction_mult = 1.0 if is_buy else -1.0
        unrealized_r = (current_price - pos.price_open) * direction_mult / risk_dist

        # Determine current tier
        current_addons = state["addons"]
        thresholds = [PYRAMID_ADD_1_AT_R, PYRAMID_ADD_2_AT_R, PYRAMID_ADD_3_AT_R]
        sizes = [PYRAMID_ADD_1_SIZE, PYRAMID_ADD_2_SIZE, PYRAMID_ADD_3_SIZE]
        locks = [PYRAMID_LOCK_AFTER_ADD1_R, PYRAMID_LOCK_AFTER_ADD2_R, PYRAMID_LOCK_AFTER_ADD3_R]

        if current_addons >= len(thresholds):
            continue

        threshold = thresholds[current_addons]
        size_frac = sizes[current_addons]
        lock_r = locks[current_addons]

        # Check threshold
        if unrealized_r < threshold:
            continue

        # For add2/3, original SL must be at breakeven or better
        if current_addons >= 1:
            if is_buy and pos.sl < pos.price_open:
                continue
            elif not is_buy and pos.sl > pos.price_open:
                continue

        # Momentum check
        momentum = calc_pyramid_momentum(indicators, idx, direction, rates)
        if momentum < PYRAMID_MIN_CONFLUENCE:
            continue

        # Calculate addon lot
        addon_lot = state["original_volume"] * size_frac
        addon_lot = max(symbol_info.volume_min, round(addon_lot / symbol_info.volume_step) * symbol_info.volume_step)
        addon_lot = round(addon_lot, 2)

        # Check addon exposure
        addon_stop_dist = atr_val * PYRAMID_STOP_ATR_MULT
        addon_exposure = addon_stop_dist * addon_lot * contract_size / balance
        current_addon_exposure = sum(
            abs(current_price - p.sl) * p.volume * contract_size / balance
            for p in positions
            if p.magic == MAGIC_NUMBER and p.ticket in state.get("addon_tickets", [])
        )

        if current_addon_exposure + addon_exposure > PYRAMID_MAX_ADDON_EXPOSURE:
            logger.debug(f"Pyramid addon exposure limit reached for #{ticket}")
            continue

        # Total exposure check
        total_exp = calc_total_exposure(balance, symbol_info, positions, current_price)
        if total_exp + addon_exposure > MAX_EXPOSURE_LIMIT:
            logger.debug(f"Total exposure limit blocks pyramid for #{ticket}")
            continue

        # Execute addon
        if is_buy:
            addon_sl = current_price - addon_stop_dist
            addon_tp = pos.tp  # Same TP as original
        else:
            addon_sl = current_price + addon_stop_dist
            addon_tp = pos.tp

        result = send_market_order(
            SYMBOL, direction, addon_lot, addon_sl, addon_tp,
            comment=f"pyr_add{current_addons + 1}_of_{ticket}"
        )

        if result and result.order:
            state["addons"] += 1
            state["addon_tickets"].append(result.order)
            logger.info(f"PYRAMID ADD {state['addons']}: {addon_lot} lots for #{ticket} at R={unrealized_r:.2f}")

            # Lock profit on original position
            if is_buy:
                lock_sl = pos.price_open + lock_r * risk_dist
                if lock_sl > pos.sl:
                    modify_sl(pos, lock_sl)
            else:
                lock_sl = pos.price_open - lock_r * risk_dist
                if pos.sl == 0 or lock_sl < pos.sl:
                    modify_sl(pos, lock_sl)


def cleanup_pyramid_state(positions):
    """Remove closed positions from pyramid state."""
    global PYRAMID_STATE
    open_tickets = {pos.ticket for pos in positions if pos.magic == MAGIC_NUMBER}

    # Remove base positions that are closed
    closed = [t for t in PYRAMID_STATE if t not in open_tickets]
    for t in closed:
        del PYRAMID_STATE[t]

    # Clean up addon tickets
    for ticket, state in PYRAMID_STATE.items():
        state["addon_tickets"] = [t for t in state["addon_tickets"] if t in open_tickets]


# =============================================================================
# MAIN TRADING LOGIC
# =============================================================================

def get_positions():
    """Get all open positions for our symbol and magic number."""
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    return [p for p in positions if p.magic == MAGIC_NUMBER]


def trading_iteration():
    """Single iteration of the trading loop."""
    global LAST_BAR_TIME, PEAK_BALANCE, CONSECUTIVE_LOSSES

    # Get account info
    account = mt5.account_info()
    if account is None:
        logger.error("Failed to get account info")
        return

    balance = account.balance
    if PEAK_BALANCE is None:
        PEAK_BALANCE = balance
    PEAK_BALANCE = max(PEAK_BALANCE, balance)

    # Check DD halt
    if check_dd_halt(balance, PEAK_BALANCE):
        logger.warning(f"DD HALT: balance={balance:.2f}, peak={PEAK_BALANCE:.2f}")
        return

    # Get symbol info
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        logger.error(f"Symbol {SYMBOL} not found")
        return

    if not symbol_info.visible:
        mt5.symbol_select(SYMBOL, True)

    # Get M15 rates
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, BARS_NEEDED)
    if rates is None or len(rates) < BARS_NEEDED:
        logger.warning(f"Not enough M15 data: got {len(rates) if rates is not None else 0}")
        return

    import pandas as pd
    rates = pd.DataFrame(rates)
    rates['time'] = pd.to_datetime(rates['time'], unit='s')

    # Check for new bar
    current_bar_time = rates['time'].iloc[-2]  # Use completed bar
    if LAST_BAR_TIME is not None and current_bar_time <= LAST_BAR_TIME:
        return  # No new bar yet
    LAST_BAR_TIME = current_bar_time

    logger.info(f"New M15 bar: {current_bar_time}")

    # Compute indicators on completed data (exclude current forming bar)
    indicators = Indicators()
    indicators.compute(rates.iloc[:-1])
    idx = len(rates) - 2  # Index of last completed bar in the original array

    # Get current positions
    positions = get_positions()

    # Clean pyramid state
    cleanup_pyramid_state(positions)

    # Get HTF trends
    h1_trend, h4_trend = get_htf_trends(SYMBOL)
    logger.debug(f"HTF: H1={h1_trend}, H4={h4_trend}")

    # Manage trailing stops
    manage_trailing_stops(positions, indicators, idx, rates)

    # Time-based exits
    bar_dt = current_bar_time.to_pydatetime().replace(tzinfo=timezone.utc)
    check_time_exits(positions, bar_dt)

    # Refresh positions after potential closes
    positions = get_positions()

    # Evaluate pyramids
    evaluate_pyramids(positions, indicators, idx, rates, balance, symbol_info, h1_trend, h4_trend)

    # Refresh positions after potential pyramid adds
    positions = get_positions()

    # Entry signal detection
    today_key = current_bar_time.strftime("%Y-%m-%d")

    if DAILY_TRADES[today_key] >= MAX_TRADES_PER_DAY:
        logger.debug(f"Max trades per day reached: {DAILY_TRADES[today_key]}")
        return

    if DAILY_LOSSES[today_key] >= MAX_CONSECUTIVE_LOSSES:
        logger.info(f"Consecutive loss cooldown active for {today_key}")
        return

    # ATR filter
    atr_val = indicators.atr[idx]
    if np.isnan(atr_val) or atr_val <= 0:
        return

    close_price = rates['close'].iloc[idx]
    atr_pct = atr_val / close_price

    if atr_pct < ATR_MIN_PCT or atr_pct > ATR_MAX_PCT:
        logger.debug(f"ATR filter: {atr_pct:.4f} outside [{ATR_MIN_PCT}, {ATR_MAX_PCT}]")
        return

    # Detect patterns
    patterns = detect_patterns(rates, idx)
    if not patterns:
        return

    logger.info(f"Patterns detected: {[p[0] for p in patterns]}")

    # Score each pattern
    for pattern_name, direction in patterns:
        # Check HTF alignment
        target_trend = "bullish" if direction == "buy" else "bearish"
        if h1_trend != target_trend and h4_trend != target_trend:
            logger.debug(f"Pattern {pattern_name} rejected: no HTF alignment")
            continue

        # Confluence score
        score = calc_confluence_score(direction, indicators, idx, h1_trend, h4_trend, rates)
        logger.info(f"Pattern {pattern_name} ({direction}): confluence={score}")

        if score < MIN_CONFLUENCE_SCORE:
            continue

        # Exposure check
        current_exposure = calc_total_exposure(balance, symbol_info, positions, close_price)
        lot_size = calc_lot_size(balance, atr_val, symbol_info)

        new_stop_dist = atr_val * STOP_MULTIPLIER
        new_exposure = new_stop_dist * lot_size * symbol_info.trade_contract_size / balance

        if current_exposure + new_exposure > MAX_EXPOSURE_LIMIT:
            logger.info(f"Exposure limit: current={current_exposure:.4f}, new={new_exposure:.4f}")
            continue

        # Calculate SL/TP
        if direction == "buy":
            sl = close_price - new_stop_dist
            tp = close_price + atr_val * TP_MULTIPLIER
        else:
            sl = close_price + new_stop_dist
            tp = close_price - atr_val * TP_MULTIPLIER

        # Execute trade
        comment = f"v3_{pattern_name}_c{score}"
        result = send_market_order(SYMBOL, direction, lot_size, sl, tp, comment)

        if result and result.order:
            DAILY_TRADES[today_key] += 1
            logger.info(f"ENTRY: {direction} {lot_size} lots, score={score}, pattern={pattern_name}")
            break  # One trade per bar
        else:
            logger.warning(f"Failed to execute {direction} {lot_size} lots")


def check_closed_trades():
    """Check recently closed trades and update loss counters."""
    global CONSECUTIVE_LOSSES

    # Get deals from the last 24 hours
    from_time = datetime.now(timezone.utc) - timedelta(hours=24)
    deals = mt5.history_deals_get(from_time, datetime.now(timezone.utc))
    if deals is None:
        return

    for deal in deals:
        if deal.magic != MAGIC_NUMBER:
            continue
        if deal.entry != mt5.DEAL_ENTRY_OUT:
            continue

        if deal.profit < 0:
            CONSECUTIVE_LOSSES += 1
            today_key = datetime.fromtimestamp(deal.time, tz=timezone.utc).strftime("%Y-%m-%d")
            DAILY_LOSSES[today_key] += 1
        elif deal.profit > 0:
            CONSECUTIVE_LOSSES = 0


# =============================================================================
# MAIN LOOP
# =============================================================================

def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("GEM_BTCUSD_V3 Starting...")
    logger.info(f"Symbol: {SYMBOL}, Magic: {MAGIC_NUMBER}")
    logger.info(f"Confluence min: {MIN_CONFLUENCE_SCORE}, Pyramid: {PYRAMID_ENABLED}")
    logger.info("=" * 60)

    # Initialize MT5
    if not mt5.initialize():
        logger.error(f"MT5 initialization failed: {mt5.last_error()}")
        sys.exit(1)

    logger.info(f"MT5 initialized: {mt5.terminal_info()}")
    logger.info(f"Account: {mt5.account_info().login}")

    # Ensure symbol is available
    if not mt5.symbol_select(SYMBOL, True):
        logger.error(f"Failed to select symbol {SYMBOL}")
        mt5.shutdown()
        sys.exit(1)

    try:
        while True:
            try:
                trading_iteration()
                check_closed_trades()
            except Exception as e:
                logger.error(f"Error in trading iteration: {e}", exc_info=True)

            time.sleep(5)  # Check every 5 seconds

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        mt5.shutdown()
        logger.info("MT5 shutdown complete.")


if __name__ == "__main__":
    main()
