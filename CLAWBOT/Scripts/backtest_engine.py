#!/usr/bin/env python3
"""
CLAWBOT Python Backtesting Engine
===================================
Mirrors the CLAWBOT MQL5 EA logic for fast local backtesting.
Uses real/synthetic XAUUSD H1 OHLC data.

Features implemented:
  - ATR-based SL/TP with configurable multipliers
  - 5-strategy confluence engine (Trend, Momentum, Session, MeanRevert, SMC)
  - Smart Money Concepts: swing detection, OB, FVG, premium/discount zones
  - Adaptive Brain: regime detection + strategy weighting
  - H4 MTF trend filter
  - Pending order retracement entries (Fibonacci + OTE)
  - Partial close at TP1 + breakeven + trailing stop
  - Dynamic position closure (max loss cap, stale trade, adverse momentum)
  - Risk management (daily loss limit, max drawdown, position sizing)
"""

import sys
import json
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ============================================================
#  CONFIGURATION - mirrors tester_template.ini
# ============================================================
@dataclass
class Config:
    # Risk
    initial_balance: float = 10000.0
    risk_per_trade: float = 1.5       # %
    max_daily_loss: float = 4.0       # %
    max_drawdown: float = 12.0        # %
    max_concurrent: int = 3
    max_daily_trades: int = 8
    min_risk_reward: float = 1.5

    # SL / TP
    sl_atr: float = 0.5
    tp_atr: float = 2.0
    min_sl_pts: float = 150.0
    max_sl_pts: float = 600.0
    trail_activation: float = 1.5     # ATR mult - let winners develop before trailing
    trail_distance: float = 0.6       # ATR mult - wide enough to avoid shakeouts

    # Spread
    max_spread: float = 35.0          # points
    avg_spread: float = 10.0          # simulated spread points (Deriv XAUUSD typical)

    # Strategies
    enable_trend: bool = True
    enable_momentum: bool = True
    enable_session: bool = True
    enable_mean_revert: bool = True
    enable_smc: bool = False
    enable_brain: bool = True
    enable_mtf: bool = False

    # Pending orders
    use_pending: bool = True
    pending_exp_bars: int = 4
    pullback_atr: float = 0.3

    # Dynamic closure
    enable_dyn_closure: bool = True
    dyn_max_loss_atr: float = 0.7     # hard ceiling at 1.4x SL
    dyn_stale_bars: int = 12
    dyn_stale_range: float = 0.2
    dyn_adverse_mom: float = 0.15     # cut early on adverse momentum

    # Dynamic TP
    enable_dynamic_tp: bool = True
    dyn_tp_trend_mult: float = 2.0
    dyn_tp_range_mult: float = 0.8

    # Partial close
    enable_partial_close: bool = True
    tp1_atr: float = 1.0             # wait for real profit before partial
    partial_close_pct: float = 0.15   # keep 85% running

    # Confluence
    min_score: int = 40
    min_strategies: int = 2
    min_strat_score: int = 25
    cooldown_losses: int = 2
    cooldown_bars: int = 4

    # Trend strategy
    ema_fast: int = 8
    ema_signal: int = 21
    ema_trend: int = 50
    ema_major: int = 200
    adx_period: int = 14
    adx_threshold: float = 25.0

    # Momentum strategy
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0

    # Session strategy
    asian_start: int = 0
    asian_end: int = 7
    london_start: int = 7
    london_end: int = 16
    exit_hour: int = 20

    # SMC
    smc_swing_str: int = 3
    smc_ob_max_age: int = 72
    smc_fvg_min: float = 2.0
    smc_fvg_max: float = 15.0
    smc_impulse_atr: float = 2.5

    # BB Mean Reversion
    bb_period: int = 20
    bb_deviation: float = 2.0
    bb_touch_buffer: float = 0.2

    # Point value for XAUUSD (Deriv: 1 point = 0.01, tick_value ~1.0 for 1 lot)
    point: float = 0.01
    tick_value: float = 1.0  # $ per point per 1 lot
    min_lot: float = 0.01
    max_lot: float = 10.0
    lot_step: float = 0.01


# ============================================================
#  POSITION / TRADE tracking
# ============================================================
@dataclass
class Position:
    ticket: int
    direction: int           # 1=buy, -1=sell
    entry_price: float
    sl: float
    tp: float
    volume: float
    open_bar: int
    open_time: object = None
    original_sl: float = 0.0
    partial_closed: bool = False
    strategy_idx: int = 0
    partial_profit: float = 0.0  # Accumulated profit from partial closes


@dataclass
class ClosedTrade:
    ticket: int
    direction: int
    entry_price: float
    exit_price: float
    volume: float
    profit: float
    bars_held: int
    strategy_idx: int = 0


# ============================================================
#  INDICATORS
# ============================================================
def calc_atr(high, low, close, period=14):
    """Calculate ATR as a pandas Series."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=1).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def calc_adx(high, low, close, period=14):
    """Simplified ADX."""
    plus_dm = (high - high.shift(1)).clip(lower=0)
    minus_dm = (low.shift(1) - low).clip(lower=0)
    mask = plus_dm > minus_dm
    plus_dm = plus_dm.where(mask, 0)
    minus_dm = minus_dm.where(~mask, 0)

    tr = calc_atr(high, low, close, 1) * 1  # just TR
    tr_smooth = tr.rolling(period, min_periods=1).sum()
    tr_smooth = tr_smooth.replace(0, 1e-10)

    plus_di = 100 * plus_dm.rolling(period, min_periods=1).sum() / tr_smooth
    minus_di = 100 * minus_dm.rolling(period, min_periods=1).sum() / tr_smooth

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10) * 100
    adx = dx.rolling(period, min_periods=1).mean()
    return adx, plus_di, minus_di


def calc_bollinger(close, period=20, dev=2.0):
    sma = close.rolling(period, min_periods=1).mean()
    std = close.rolling(period, min_periods=1).std()
    upper = sma + dev * std
    lower = sma - dev * std
    return upper, sma, lower


# ============================================================
#  STRATEGY SIGNALS
# ============================================================
def eval_trend(i, df, cfg):
    """Trend strategy: Strong trend confirmation with pullback entry.
    High WR approach: only trade pullbacks IN strong trends."""
    if i < cfg.ema_major + 5:
        return 0, 0
    ema_f = df['ema_fast'].iloc[i]
    ema_s = df['ema_signal'].iloc[i]
    ema_t = df['ema_trend'].iloc[i]
    ema_m = df['ema_major'].iloc[i]
    adx_val = df['adx'].iloc[i]
    close = df['close'].iloc[i]
    low = df['low'].iloc[i]
    high = df['high'].iloc[i]
    prev_close = df['close'].iloc[i - 1]
    rsi = df['rsi'].iloc[i]

    # GATE: ADX must show trend strength
    if adx_val < cfg.adx_threshold:
        return 0, 0

    score = 0
    direction = 0

    # === BULLISH TREND + PULLBACK ===
    # Full EMA alignment AND price pulled back to signal/trend EMA zone
    if (ema_f > ema_s and ema_s > ema_t and close > ema_m and
            ema_t > ema_m):
        # PULLBACK REQUIRED: price must have touched EMA zone on this or recent bar
        pullback_zone = (low <= ema_s * 1.002) or (df['low'].iloc[i - 1] <= ema_s * 1.002)
        # BOUNCE: current close is back above EMA fast
        bounce = close > ema_f and close > prev_close

        if pullback_zone and bounce:
            score = 30
            direction = 1
            # RSI confirmation: mid-range (not overbought)
            if 40 < rsi < 65:
                score += 8
            # Strong ADX bonus
            if adx_val > 30:
                score += 5
            # Plus DI > Minus DI
            if df['plus_di'].iloc[i] > df['minus_di'].iloc[i]:
                score += 5
        elif ema_f > ema_s > ema_t > ema_m and close > ema_f:
            # Strong alignment without pullback: weaker signal
            score = 18
            direction = 1

    # === BEARISH TREND + PULLBACK ===
    elif (ema_f < ema_s and ema_s < ema_t and close < ema_m and
            ema_t < ema_m):
        pullback_zone = (high >= ema_s * 0.998) or (df['high'].iloc[i - 1] >= ema_s * 0.998)
        bounce = close < ema_f and close < prev_close

        if pullback_zone and bounce:
            score = 30
            direction = -1
            if 35 < rsi < 60:
                score += 8
            if adx_val > 30:
                score += 5
            if df['minus_di'].iloc[i] > df['plus_di'].iloc[i]:
                score += 5
        elif ema_f < ema_s < ema_t < ema_m and close < ema_f:
            score = 18
            direction = -1

    return direction, score


def eval_momentum(i, df, cfg):
    """Momentum: RSI extremes + trend confirmation for high probability."""
    if i < cfg.rsi_period + 5:
        return 0, 0

    rsi = df['rsi'].iloc[i]
    rsi_prev = df['rsi'].iloc[i - 1]
    close = df['close'].iloc[i]
    ema_m = df['ema_major'].iloc[i]

    score = 0
    direction = 0

    # Only signal when RSI reversal aligns with major trend
    if rsi < cfg.rsi_oversold and rsi > rsi_prev and close > ema_m:
        # Oversold bounce IN uptrend = high probability
        direction = 1
        score = 25 + int((cfg.rsi_oversold - rsi) * 0.8)
    elif rsi > cfg.rsi_overbought and rsi < rsi_prev and close < ema_m:
        # Overbought rejection IN downtrend = high probability
        direction = -1
        score = 25 + int((rsi - cfg.rsi_overbought) * 0.8)

    return direction, min(score, 40)


def eval_session(i, df, cfg):
    """Session: only trade during London/NY with candle confirmation."""
    hour = df['hour'].iloc[i]

    if hour < cfg.london_start or hour >= cfg.exit_hour:
        return 0, 0

    score = 0
    if 12 <= hour < 16:
        score = 20  # London/NY overlap = highest liquidity
    elif cfg.london_start <= hour < 12:
        score = 16  # London prime
    elif 16 <= hour < cfg.exit_hour:
        score = 14  # NY afternoon

    # Require strong directional candle (body > 60% of range)
    close = df['close'].iloc[i]
    open_ = df['open'].iloc[i]
    high = df['high'].iloc[i]
    low = df['low'].iloc[i]
    candle_range = high - low
    body = abs(close - open_)

    if candle_range <= 0 or body / candle_range < 0.55:
        return 0, 0  # Indecision candle

    direction = 1 if close > open_ else -1

    # Confirm with 3-bar momentum (consistent direction)
    if i >= 3:
        c1 = df['close'].iloc[i - 1]
        c2 = df['close'].iloc[i - 2]
        c3 = df['close'].iloc[i - 3]
        if direction == 1 and c1 > c2 > c3:
            score += 5  # 3-bar bull momentum
        elif direction == -1 and c1 < c2 < c3:
            score += 5  # 3-bar bear momentum

    return direction, score


def eval_mean_revert(i, df, cfg):
    """Mean reversion: BB touch + RSI divergence."""
    if i < cfg.bb_period + 5:
        return 0, 0

    close = df['close'].iloc[i]
    bb_up = df['bb_upper'].iloc[i]
    bb_lo = df['bb_lower'].iloc[i]
    bb_mid = df['bb_mid'].iloc[i]
    rsi = df['rsi'].iloc[i]
    bb_width = bb_up - bb_lo
    if bb_width <= 0:
        return 0, 0

    buf = bb_width * cfg.bb_touch_buffer

    score = 0
    direction = 0

    # Near lower band + RSI oversold = buy signal
    if close <= bb_lo + buf and rsi < 40:
        direction = 1
        score = 20
        if rsi < 30:
            score = 28
    elif close >= bb_up - buf and rsi > 60:
        direction = -1
        score = 20
        if rsi > 70:
            score = 28

    return direction, score


def eval_smc(i, df, cfg):
    """SMC: structure + premium/discount zone + FVG/OB retest."""
    if i < 50:
        return 0, 0

    close = df['close'].iloc[i]
    high = df['high'].iloc[i]
    low = df['low'].iloc[i]
    atr = df['atr'].iloc[i]
    if atr <= 0:
        return 0, 0

    lookback = min(i, 60)
    highs = df['high'].iloc[i - lookback:i + 1]
    lows = df['low'].iloc[i - lookback:i + 1]
    closes = df['close'].iloc[i - lookback:i + 1]

    recent_high = highs.max()
    recent_low = lows.min()
    swing_range = recent_high - recent_low

    if swing_range < atr * 2:
        return 0, 0  # Range too tight

    # Price zone
    position = (close - recent_low) / swing_range

    score = 0
    direction = 0

    # ===  STRUCTURE CHECK: HH/HL or LH/LL ===
    mid_idx = lookback // 2
    first_half = closes.iloc[:mid_idx]
    second_half = closes.iloc[mid_idx:]
    fh_high = highs.iloc[:mid_idx].max()
    sh_high = highs.iloc[mid_idx:].max()
    fh_low = lows.iloc[:mid_idx].min()
    sh_low = lows.iloc[mid_idx:].min()

    bullish_struct = (sh_high > fh_high and sh_low > fh_low)  # HH + HL
    bearish_struct = (sh_high < fh_high and sh_low < fh_low)  # LH + LL

    # === DISCOUNT ZONE BUY (position < 0.35) + bullish structure ===
    if position < 0.35 and bullish_struct:
        direction = 1
        score = 18
        if position < 0.25:
            score = 25

        # FVG retest: check if price is filling a recent gap
        for j in range(max(i - 20, 2), i):
            if df['low'].iloc[j] > df['high'].iloc[j + 2]:  # Bullish FVG
                gap_low = df['high'].iloc[j + 2]
                gap_high = df['low'].iloc[j]
                if low <= gap_high and close >= gap_low:
                    score += 8  # Inside bullish FVG
                    break

    # === PREMIUM ZONE SELL (position > 0.65) + bearish structure ===
    elif position > 0.65 and bearish_struct:
        direction = -1
        score = 18
        if position > 0.75:
            score = 25

        for j in range(max(i - 20, 2), i):
            if df['high'].iloc[j] < df['low'].iloc[j + 2]:  # Bearish FVG
                gap_high = df['low'].iloc[j + 2]
                gap_low = df['high'].iloc[j]
                if high >= gap_low and close <= gap_high:
                    score += 8
                    break

    return direction, min(score, 35)


# ============================================================
#  H4 MTF FILTER
# ============================================================
def calc_h4_trend(df, i, ema_period=50):
    """Approximate H4 trend using 4-bar grouping of H1 data."""
    if i < ema_period * 4:
        return 0  # Not enough data
    # Use 200-bar EMA as proxy for H4 50-EMA (50*4=200 H1 bars)
    close = df['close'].iloc[i]
    ema_val = df['ema_major'].iloc[i]  # 200 EMA
    if close > ema_val * 1.001:
        return 1  # Bullish
    elif close < ema_val * 0.999:
        return -1  # Bearish
    return 0


# ============================================================
#  BRAIN: regime detection + weighting
# ============================================================
def detect_regime(i, df, cfg):
    """Detect market regime and return strategy weight multipliers."""
    adx = df['adx'].iloc[i]
    atr = df['atr'].iloc[i]
    atr_avg = df['atr'].iloc[max(0, i - 50):i + 1].mean() if i > 10 else atr

    atr_ratio = atr / max(atr_avg, 0.01)

    # Default weights
    w = {'trend': 1.0, 'momentum': 1.0, 'session': 1.0,
         'mean_revert': 1.0, 'smc': 1.0, 'lot_mult': 1.0,
         'score_adj': 0, 'allow': True}

    if atr_ratio > 1.5:
        # Volatile expansion
        w['trend'] = 0.4
        w['momentum'] = 0.4
        w['mean_revert'] = 0.2
        w['session'] = 0.2
        w['smc'] = 0.7
        w['lot_mult'] = 0.3
        w['score_adj'] = 15
        w['allow'] = atr_ratio < 2.5
    elif adx > 30 and atr_ratio >= 1.0:
        # Strong trend
        w['trend'] = 1.6
        w['momentum'] = 1.3
        w['mean_revert'] = 0.2
        w['session'] = 1.1
        w['smc'] = 1.5
        w['lot_mult'] = 1.2
        w['score_adj'] = -8
    elif adx > 20:
        # Weak trend
        w['trend'] = 1.3
        w['momentum'] = 1.1
        w['mean_revert'] = 0.4
        w['session'] = 0.9
        w['smc'] = 1.3
        w['lot_mult'] = 0.85
        w['score_adj'] = 0
    elif adx < 20 and atr_ratio < 1.2:
        # Ranging
        w['trend'] = 0.2
        w['momentum'] = 0.6
        w['mean_revert'] = 1.6
        w['session'] = 0.4
        w['smc'] = 1.0
        w['lot_mult'] = 0.45
        w['score_adj'] = 8
    else:
        # Transitioning
        w['trend'] = 0.3
        w['momentum'] = 1.1
        w['mean_revert'] = 0.9
        w['session'] = 0.4
        w['smc'] = 1.4
        w['lot_mult'] = 0.4
        w['score_adj'] = 8

    return w


# ============================================================
#  MAIN BACKTESTER
# ============================================================
class ClawbotBacktester:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.balance = cfg.initial_balance
        self.equity = cfg.initial_balance
        self.peak_balance = cfg.initial_balance
        self.daily_start_balance = cfg.initial_balance
        self.positions: list[Position] = []
        self.closed_trades: list[ClosedTrade] = []
        self.ticket_counter = 0
        self.daily_trades = 0
        self.consec_losses = 0
        self.cooldown_remaining = 0
        self.current_day = None
        self.partial_closed_tickets = set()

    def run(self, df: pd.DataFrame, silent: bool = False) -> dict:
        """Run full backtest on H1 OHLC data. Returns stats dict."""
        # Pre-compute indicators
        df = self._prepare_indicators(df)

        n = len(df)
        if not silent:
            print(f"Running backtest on {n} bars...")
            print(f"Date range: {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")
            print(f"Starting balance: ${self.cfg.initial_balance:,.2f}")

        # Convert to numpy arrays for fast inner loop (avoids pandas iloc overhead)
        self._d = {}
        for col in df.columns:
            if col != 'datetime':
                self._d[col] = df[col].values
        self._dt = df['datetime'].values
        dt_series = pd.to_datetime(df['datetime'])
        self._days = dt_series.dt.date.values

        for i in range(max(self.cfg.ema_major + 10, 50), n):
            # New day tracking
            day = self._days[i]
            if day != self.current_day:
                self.current_day = day
                self.daily_start_balance = self.balance
                self.daily_trades = 0

            # PHASE 1: Manage existing positions (every bar)
            self._manage_positions_np(i)

            # PHASE 2: New trade signals
            if self.cooldown_remaining > 0:
                self.cooldown_remaining -= 1
                continue

            self._evaluate_signals_np(i)

        # Close remaining positions at last bar
        for pos in list(self.positions):
            self._close_position_np(pos, n - 1, "END")

        return self._compute_stats()

    def _prepare_indicators(self, df):
        """Add all technical indicators."""
        df = df.copy()
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['hour'] = df['datetime'].dt.hour
        df['day_of_week'] = df['datetime'].dt.dayofweek

        # ATR
        df['atr'] = calc_atr(df['high'], df['low'], df['close'], 14)

        # EMAs
        df['ema_fast'] = calc_ema(df['close'], self.cfg.ema_fast)
        df['ema_signal'] = calc_ema(df['close'], self.cfg.ema_signal)
        df['ema_trend'] = calc_ema(df['close'], self.cfg.ema_trend)
        df['ema_major'] = calc_ema(df['close'], self.cfg.ema_major)

        # RSI
        df['rsi'] = calc_rsi(df['close'], self.cfg.rsi_period)

        # ADX
        df['adx'], df['plus_di'], df['minus_di'] = calc_adx(
            df['high'], df['low'], df['close'], self.cfg.adx_period)

        # Bollinger Bands
        df['bb_upper'], df['bb_mid'], df['bb_lower'] = calc_bollinger(
            df['close'], self.cfg.bb_period, self.cfg.bb_deviation)

        return df

    # ============================================================
    #  FAST NUMPY-BASED METHODS
    # ============================================================
    def _manage_positions_np(self, i):
        d = self._d; cfg = self.cfg
        atr = d['atr'][i]
        if atr <= 0: return
        for pos in list(self.positions):
            bh = d['high'][i]; bl = d['low'][i]; bc = d['close'][i]
            bars_held = i - pos.open_bar
            unr = (bc - pos.entry_price) if pos.direction == 1 else (pos.entry_price - bc)
            # SL/TP
            if pos.direction == 1:
                if bl <= pos.sl: self._close_position_np(pos, i, "SL", pos.sl); continue
                if bh >= pos.tp: self._close_position_np(pos, i, "TP", pos.tp); continue
            else:
                if bh >= pos.sl: self._close_position_np(pos, i, "SL", pos.sl); continue
                if bl <= pos.tp: self._close_position_np(pos, i, "TP", pos.tp); continue
            # Dynamic closure
            if cfg.enable_dyn_closure and bars_held >= 3:
                if unr < -(cfg.dyn_max_loss_atr * atr):
                    self._close_position_np(pos, i, "DML"); continue
                if unr < -(cfg.dyn_adverse_mom * atr) and i >= 2:
                    c1, o1 = d['close'][i-1], d['open'][i-1]
                    c2, o2 = d['close'][i-2], d['open'][i-2]
                    if (pos.direction == 1 and c1 < o1 and c2 < o2) or \
                       (pos.direction == -1 and c1 > o1 and c2 > o2):
                        self._close_position_np(pos, i, "DAD"); continue
                if bars_held >= cfg.dyn_stale_bars and unr < 0:
                    if abs(unr) < cfg.dyn_stale_range * atr:
                        self._close_position_np(pos, i, "DST"); continue
            # Partial close
            if cfg.enable_partial_close and not pos.partial_closed and pos.ticket not in self.partial_closed_tickets:
                tp1d = atr * cfg.tp1_atr
                if unr >= tp1d:
                    cv = round(pos.volume * cfg.partial_close_pct, 2)
                    cv = max(cv, cfg.min_lot)
                    if cv < pos.volume:
                        pft = unr * cv * (cfg.tick_value / cfg.point)
                        self.balance += pft
                        pos.partial_profit += pft
                        pos.volume = round(pos.volume - cv, 2)
                        pos.partial_closed = True
                        self.partial_closed_tickets.add(pos.ticket)
                        sp = cfg.avg_spread * cfg.point
                        if pos.direction == 1: pos.sl = max(pos.sl, pos.entry_price + sp)
                        else: pos.sl = min(pos.sl, pos.entry_price - sp)
            # Breakeven: activate at 50% of trailing activation (separate from trail)
            be_act = atr * cfg.trail_activation * 0.5
            if pos.direction == 1:
                pd_ = bc - pos.entry_price
                if pd_ >= be_act and pos.sl < pos.entry_price:
                    sp = cfg.avg_spread * cfg.point
                    be_sl = pos.entry_price + sp
                    if be_sl > pos.sl: pos.sl = be_sl
            else:
                pd_ = pos.entry_price - bc
                if pd_ >= be_act and (pos.sl > pos.entry_price or pos.sl == 0):
                    sp = cfg.avg_spread * cfg.point
                    be_sl = pos.entry_price - sp
                    if be_sl < pos.sl: pos.sl = be_sl
            # Trailing: only after full activation distance
            ta = atr * cfg.trail_activation; td = atr * cfg.trail_distance
            if pos.direction == 1:
                pd_ = bc - pos.entry_price
                if pd_ >= ta:
                    ns = bc - td
                    if ns > pos.sl and ns > pos.entry_price: pos.sl = ns
            else:
                pd_ = pos.entry_price - bc
                if pd_ >= ta:
                    ns = bc + td
                    if ns < pos.sl and ns < pos.entry_price: pos.sl = ns
            # Progressive SL (aggressive schedule matching ClawRisk.mqh)
            if cfg.enable_dyn_closure and unr < 0 and bars_held >= 5:
                osd = abs(pos.entry_price - pos.original_sl) or atr * cfg.sl_atr
                f = 0.30 if bars_held >= 16 else (0.45 if bars_held >= 10 else 0.65)
                if f < 1.0:
                    nsd = max(osd * f, cfg.min_sl_pts * cfg.point * 0.5)
                    if pos.direction == 1:
                        ns = pos.entry_price - nsd
                        if ns > pos.sl: pos.sl = ns
                    else:
                        ns = pos.entry_price + nsd
                        if ns < pos.sl: pos.sl = ns

    def _evaluate_signals_np(self, i):
        d = self._d; cfg = self.cfg
        atr = d['atr'][i]
        if atr <= 0: return
        if len(self.positions) >= cfg.max_concurrent: return
        if self.daily_trades >= cfg.max_daily_trades: return
        daily_pl = self.balance - self.daily_start_balance
        if daily_pl < -(self.daily_start_balance * cfg.max_daily_loss / 100): return
        if self.balance > self.peak_balance: self.peak_balance = self.balance
        dd = (self.peak_balance - self.balance) / max(self.peak_balance, 1) * 100
        if dd > cfg.max_drawdown: return
        if d['day_of_week'][i] >= 5: return
        hr = d['hour'][i]; dow = d['day_of_week'][i]
        # Session restrictions: no Asian early, no late Friday, no early Monday
        if hr < 4: return  # Early Asian - too quiet
        if hr >= 21: return  # Off hours
        if dow == 4 and hr >= 16: return  # Friday after 16:00
        if dow == 0 and hr < 5: return  # Monday early

        # Regime
        adx = d['adx'][i]
        atr_avg = d['atr'][max(0,i-50):i+1].mean() if i > 10 else atr
        ar = atr / max(atr_avg, 0.01)
        wt = wm = ws = wmr = wsmc = 1.0; lm = 1.0; sa = 0; allow = True
        if ar > 1.5 and (adx > 20 or (i >= 3 and d['adx'][i] - d['adx'][i-2] > 5)):
            # Volatile expansion
            wt=0.4; wm=0.4; ws=0.2; wmr=0.2; wsmc=0.7; lm=0.3; sa=15
            allow = ar < 2.5
        elif adx > 30 and ar >= 1.0:
            # Strong trend
            wt=1.6; wm=1.3; ws=1.1; wmr=0.2; wsmc=1.5; lm=1.2; sa=-8
        elif adx > 20:
            # Weak trend
            wt=1.3; wm=1.1; ws=0.9; wmr=0.4; wsmc=1.3; lm=0.85; sa=0
        elif adx < 20 and ar < 1.2:
            # Ranging
            wt=0.2; wm=0.6; ws=0.4; wmr=1.6; wsmc=1.0; lm=0.45; sa=8
        else:
            # Transitioning
            wt=0.3; wm=1.1; ws=0.4; wmr=0.9; wsmc=1.4; lm=0.4; sa=8
        if not allow: return
        # Session-based adjustments
        if hr < 7:  # Asian
            wt *= 0.3; wm *= 0.4; ws *= 0.2; wmr *= 1.1; wsmc *= 0.5; lm *= 0.4
        elif 7 <= hr < 10:  # London open
            wt *= 1.2; ws *= 1.5; wsmc *= 1.4; wmr *= 0.5; lm *= 1.1
        elif 12 <= hr < 16:  # Overlap
            wt *= 1.2; wm *= 1.2; ws *= 1.2; wsmc *= 1.3; lm *= 1.1
        elif 17 <= hr < 21:  # NY afternoon
            wt *= 0.6; wmr *= 1.0; wsmc *= 0.7; lm *= 0.5

        sigs = []
        if cfg.enable_trend:
            dr, s = self._t_trend(i)
            if s >= cfg.min_strat_score: sigs.append((dr, s * wt, 0))
        if cfg.enable_momentum:
            dr, s = self._t_mom(i)
            if s >= cfg.min_strat_score: sigs.append((dr, s * wm, 1))
        if cfg.enable_session:
            dr, s = self._t_sess(i)
            if s >= cfg.min_strat_score: sigs.append((dr, s * ws, 2))
        if cfg.enable_mean_revert:
            dr, s = self._t_mr(i)
            if s >= cfg.min_strat_score: sigs.append((dr, s * wmr, 3))
        if cfg.enable_smc:
            dr, s = self._t_smc(i)
            if s >= 10: sigs.append((dr, s * wsmc, 4))
        if not sigs: return

        bv = sum(1 for x,_,_ in sigs if x == 1)
        sv = sum(1 for x,_,_ in sigs if x == -1)
        bs = sum(w for x,w,_ in sigs if x == 1)
        ss = sum(w for x,w,_ in sigs if x == -1)
        ams = cfg.min_score + sa

        direction = 0; score = 0; dom = 0
        if bv >= cfg.min_strategies and bs >= ams and bs > ss:
            direction = 1; score = bs; dom = max((w,si) for x,w,si in sigs if x == 1)[1]
        elif sv >= cfg.min_strategies and ss >= ams and ss > bs:
            direction = -1; score = ss; dom = max((w,si) for x,w,si in sigs if x == -1)[1]
        if direction == 0: return

        if cfg.enable_mtf and i >= 800:
            em = d['ema_major'][i]; cl = d['close'][i]
            h4 = 1 if cl > em * 1.001 else (-1 if cl < em * 0.999 else 0)
            if h4 != 0 and h4 != direction: return

        for p in self.positions:
            if p.direction == direction: return

        close = d['close'][i]; spread = cfg.avg_spread * cfg.point
        sld = atr * cfg.sl_atr; slp = sld / cfg.point
        if slp < cfg.min_sl_pts: sld = cfg.min_sl_pts * cfg.point
        if slp > cfg.max_sl_pts: sld = cfg.max_sl_pts * cfg.point
        tpd = atr * cfg.tp_atr
        # Enforce minimum R:R of 1.5:1
        mtp = sld * max(cfg.min_risk_reward, 1.5)
        if tpd < mtp: tpd = mtp

        if direction == 1:
            entry = close + spread/2; sl = entry - sld; tp = entry + tpd
        else:
            entry = close - spread/2; sl = entry + sld; tp = entry - tpd

        ra = self.balance * (cfg.risk_per_trade / 100)
        lot = ra / (sld / cfg.point * cfg.tick_value)
        lot = max(cfg.min_lot, min(cfg.max_lot, round(lot / cfg.lot_step) * cfg.lot_step))
        lot = round(lot * lm, 2)
        if score < 50: lot = round(lot * 0.60, 2)
        elif score < 70: lot = round(lot * 0.80, 2)
        # score >= 70: full lot (reward high-confidence signals)
        lot = max(cfg.min_lot, lot)

        self.ticket_counter += 1
        self.positions.append(Position(
            ticket=self.ticket_counter, direction=direction,
            entry_price=round(entry, 2), sl=round(sl, 2), tp=round(tp, 2),
            volume=lot, open_bar=i, open_time=self._dt[i],
            original_sl=round(sl, 2), strategy_idx=dom
        ))
        self.daily_trades += 1

    def _close_position_np(self, pos, i, reason, exit_price=None):
        cfg = self.cfg; d = self._d
        if exit_price is None:
            if pos.direction == 1: exit_price = d['close'][i] - cfg.avg_spread * cfg.point / 2
            else: exit_price = d['close'][i] + cfg.avg_spread * cfg.point / 2
        pip_pl = (exit_price - pos.entry_price) if pos.direction == 1 else (pos.entry_price - exit_price)
        remaining_profit = pip_pl * pos.volume * (cfg.tick_value / cfg.point)
        profit = remaining_profit + pos.partial_profit
        self.balance += remaining_profit
        if self.balance > self.peak_balance: self.peak_balance = self.balance
        self.closed_trades.append(ClosedTrade(
            ticket=pos.ticket, direction=pos.direction, entry_price=pos.entry_price,
            exit_price=exit_price, volume=pos.volume, profit=profit,
            bars_held=i - pos.open_bar, strategy_idx=pos.strategy_idx
        ))
        if pos in self.positions: self.positions.remove(pos)
        if profit < 0:
            self.consec_losses += 1
            if self.consec_losses >= cfg.cooldown_losses:
                self.cooldown_remaining = cfg.cooldown_bars; self.consec_losses = 0
        else:
            self.consec_losses = 0

    def _t_trend(self, i):
        d = self._d; cfg = self.cfg
        if i < cfg.ema_major + 5: return 0, 0
        ef = d['ema_fast'][i]; es = d['ema_signal'][i]; et = d['ema_trend'][i]; em = d['ema_major'][i]
        ax = d['adx'][i]
        if ax < cfg.adx_threshold: return 0, 0
        cl = d['close'][i]; lo = d['low'][i]; hi = d['high'][i]; op = d['open'][i]
        pc = d['close'][i-1]; rsi = d['rsi'][i]
        body = abs(cl - op); rng = hi - lo
        sc = 0; dr = 0
        if ef > es and es > et and et > em and cl > em:
            pb = False
            for k in range(min(3, i)):
                if d['low'][i-k] <= es * 1.003 and d['low'][i-k] >= et * 0.997: pb = True; break
            bounce = cl > ef and cl > op and (rng > 0 and body / rng > 0.45)
            if pb and bounce:
                sc = 35; dr = 1
                if d['plus_di'][i] > d['minus_di'][i] * 1.2: sc += 8
                if ax > 30: sc += 5
                if 40 < rsi < 65: sc += 5
                if rng > 0 and body / rng > 0.65: sc += 5
                if i >= 1 and d['close'][i-1] > d['open'][i-1]: sc += 3
        elif ef < es and es < et and et < em and cl < em:
            pb = False
            for k in range(min(3, i)):
                if d['high'][i-k] >= es * 0.997 and d['high'][i-k] <= et * 1.003: pb = True; break
            bounce = cl < ef and cl < op and (rng > 0 and body / rng > 0.45)
            if pb and bounce:
                sc = 35; dr = -1
                if d['minus_di'][i] > d['plus_di'][i] * 1.2: sc += 8
                if ax > 30: sc += 5
                if 35 < rsi < 60: sc += 5
                if rng > 0 and body / rng > 0.65: sc += 5
                if i >= 1 and d['close'][i-1] < d['open'][i-1]: sc += 3
        return dr, sc

    def _t_mom(self, i):
        d = self._d; cfg = self.cfg
        if i < cfg.rsi_period + 5: return 0, 0
        rsi = d['rsi'][i]; rp = d['rsi'][i-1]; rp2 = d['rsi'][i-2] if i >= 2 else rp
        cl = d['close'][i]; op = d['open'][i]; em = d['ema_major'][i]; et = d['ema_trend'][i]
        if rsi < cfg.rsi_oversold and rsi > rp and rp <= rp2:
            if cl > em and cl > et and cl > op:
                sc = 30 + int((cfg.rsi_oversold - rsi) * 1.0)
                if d['plus_di'][i] > d['minus_di'][i]: sc += 5
                return 1, min(sc, 45)
        elif rsi > cfg.rsi_overbought and rsi < rp and rp >= rp2:
            if cl < em and cl < et and cl < op:
                sc = 30 + int((rsi - cfg.rsi_overbought) * 1.0)
                if d['minus_di'][i] > d['plus_di'][i]: sc += 5
                return -1, min(sc, 45)
        return 0, 0

    def _t_sess(self, i):
        d = self._d; cfg = self.cfg
        hr = d['hour'][i]
        if hr < cfg.london_start or hr >= cfg.exit_hour: return 0, 0
        cl = d['close'][i]; op = d['open'][i]; hi = d['high'][i]; lo = d['low'][i]
        rng = hi - lo; body = abs(cl - op)
        if rng <= 0 or body / rng < 0.55: return 0, 0
        dr = 1 if cl > op else -1
        em = d['ema_major'][i]
        if dr == 1 and cl < em: return 0, 0
        if dr == -1 and cl > em: return 0, 0
        sc = 25 if 12 <= hr < 16 else (20 if cfg.london_start <= hr < 12 else 16)
        if i >= 3:
            c1, c2, c3 = d['close'][i-1], d['close'][i-2], d['close'][i-3]
            if dr == 1 and c1 > c2 > c3: sc += 8
            elif dr == -1 and c1 < c2 < c3: sc += 8
            else: sc -= 5
        if body / rng > 0.7: sc += 5
        if d['adx'][i] > 25: sc += 3
        return dr, max(sc, 0)

    def _t_mr(self, i):
        d = self._d; cfg = self.cfg
        if i < cfg.bb_period + 5: return 0, 0
        cl = d['close'][i]; op = d['open'][i]
        bu = d['bb_upper'][i]; bl = d['bb_lower'][i]; rsi = d['rsi'][i]
        hi = d['high'][i]; lo = d['low'][i]; rng = hi - lo
        if bl <= bu and lo <= bl and cl > bl and rsi < 35:
            if cl > op and rng > 0:
                lw = min(cl, op) - lo
                if lw > rng * 0.3:
                    sc = 25; sc += 8 if rsi < 25 else 0; sc += 5 if d['adx'][i] < 25 else 0
                    return 1, min(sc, 40)
        if bu >= bl and hi >= bu and cl < bu and rsi > 65:
            if cl < op and rng > 0:
                uw = hi - max(cl, op)
                if uw > rng * 0.3:
                    sc = 25; sc += 8 if rsi > 75 else 0; sc += 5 if d['adx'][i] < 25 else 0
                    return -1, min(sc, 40)
        return 0, 0

    def _t_smc(self, i):
        d = self._d; cfg = self.cfg
        if i < 50: return 0, 0
        cl = d['close'][i]; hi = d['high'][i]; lo = d['low'][i]; op = d['open'][i]
        atr = d['atr'][i]
        if atr <= 0: return 0, 0
        lb = min(i, 60)
        hs = d['high'][i-lb:i+1]; ls = d['low'][i-lb:i+1]
        rh = hs.max(); rl = ls.min(); sr = rh - rl
        if sr < atr * 2: return 0, 0
        pos_ = (cl - rl) / sr; mid = lb // 2
        fhh = d['high'][i-lb:i-lb+mid].max(); shh = d['high'][i-lb+mid:i+1].max()
        fhl = d['low'][i-lb:i-lb+mid].min(); shl = d['low'][i-lb+mid:i+1].min()
        bull = shh > fhh and shl > fhl; bear = shh < fhh and shl < fhl
        sc = 0; dr = 0
        if pos_ < 0.35 and bull and cl > op:
            dr = 1; sc = 22 if pos_ < 0.25 else 18
            for j in range(max(i-20, 2), i):
                if d['low'][j] > d['high'][min(j+2, i)]:
                    if lo <= d['low'][j] and cl >= d['high'][min(j+2, i)]: sc += 10; break
            if d['ema_trend'][i] > d['ema_major'][i]: sc += 5
            rng = hi - lo
            if rng > 0 and abs(cl - op) / rng > 0.6: sc += 5
        elif pos_ > 0.65 and bear and cl < op:
            dr = -1; sc = 22 if pos_ > 0.75 else 18
            for j in range(max(i-20, 2), i):
                if d['high'][j] < d['low'][min(j+2, i)]:
                    if hi >= d['high'][j] and cl <= d['low'][min(j+2, i)]: sc += 10; break
            if d['ema_trend'][i] < d['ema_major'][i]: sc += 5
            rng = hi - lo
            if rng > 0 and abs(cl - op) / rng > 0.6: sc += 5
        return dr, min(sc, 40)

    def _manage_positions(self, i, df):
        """Phase 1: manage trailing, partial close, dynamic closure."""
        atr = df['atr'].iloc[i]
        if atr <= 0:
            return

        for pos in list(self.positions):
            bar_high = df['high'].iloc[i]
            bar_low = df['low'].iloc[i]
            bar_close = df['close'].iloc[i]
            bars_held = i - pos.open_bar

            # Current P/L
            if pos.direction == 1:
                current_price = bar_close
                unrealized = current_price - pos.entry_price
            else:
                current_price = bar_close
                unrealized = pos.entry_price - current_price

            # --- SL/TP HIT CHECK (use high/low for intra-bar) ---
            if pos.direction == 1:
                if bar_low <= pos.sl:
                    self._close_position(pos, i, df, "SL", pos.sl)
                    continue
                if bar_high >= pos.tp:
                    self._close_position(pos, i, df, "TP", pos.tp)
                    continue
            else:
                if bar_high >= pos.sl:
                    self._close_position(pos, i, df, "SL", pos.sl)
                    continue
                if bar_low <= pos.tp:
                    self._close_position(pos, i, df, "TP", pos.tp)
                    continue

            # --- Dynamic closure ---
            if self.cfg.enable_dyn_closure and bars_held >= 3:
                # Max loss cap
                if unrealized < -(self.cfg.dyn_max_loss_atr * atr):
                    self._close_position(pos, i, df, "DYN_MAXLOSS")
                    continue

                # Adverse momentum (2 consecutive adverse bars)
                if bars_held >= 3 and unrealized < -(self.cfg.dyn_adverse_mom * atr):
                    if i >= 2:
                        c1 = df['close'].iloc[i - 1]
                        o1 = df['open'].iloc[i - 1]
                        c2 = df['close'].iloc[i - 2]
                        o2 = df['open'].iloc[i - 2]
                        if pos.direction == 1:
                            if c1 < o1 and c2 < o2:
                                self._close_position(pos, i, df, "DYN_ADVERSE")
                                continue
                        else:
                            if c1 > o1 and c2 > o2:
                                self._close_position(pos, i, df, "DYN_ADVERSE")
                                continue

                # Stale trade
                if bars_held >= self.cfg.dyn_stale_bars and unrealized < 0:
                    if abs(unrealized) < self.cfg.dyn_stale_range * atr:
                        self._close_position(pos, i, df, "DYN_STALE")
                        continue

            # --- Partial close at TP1 ---
            if (self.cfg.enable_partial_close and
                    not pos.partial_closed and
                    pos.ticket not in self.partial_closed_tickets):
                tp1_dist = atr * self.cfg.tp1_atr
                if unrealized >= tp1_dist:
                    close_vol = round(pos.volume * self.cfg.partial_close_pct, 2)
                    close_vol = max(close_vol, self.cfg.min_lot)
                    if close_vol < pos.volume:
                        # Record partial profit
                        profit = unrealized * close_vol * (self.cfg.tick_value / self.cfg.point)
                        self.balance += profit
                        pos.partial_profit += profit  # Track for WR calculation
                        pos.volume = round(pos.volume - close_vol, 2)
                        pos.partial_closed = True
                        self.partial_closed_tickets.add(pos.ticket)
                        # Move SL to breakeven
                        spread = self.cfg.avg_spread * self.cfg.point
                        if pos.direction == 1:
                            pos.sl = max(pos.sl, pos.entry_price + spread)
                        else:
                            pos.sl = min(pos.sl, pos.entry_price - spread)

            # --- Breakeven: activate at 50% of trailing activation ---
            be_act_dist = atr * self.cfg.trail_activation * 0.5
            if pos.direction == 1:
                profit_dist = bar_close - pos.entry_price
                if profit_dist >= be_act_dist and pos.sl < pos.entry_price:
                    spread = self.cfg.avg_spread * self.cfg.point
                    be_sl = pos.entry_price + spread
                    if be_sl > pos.sl:
                        pos.sl = be_sl
            else:
                profit_dist = pos.entry_price - bar_close
                if profit_dist >= be_act_dist and pos.sl > pos.entry_price:
                    spread = self.cfg.avg_spread * self.cfg.point
                    be_sl = pos.entry_price - spread
                    if be_sl < pos.sl:
                        pos.sl = be_sl

            # --- Trailing stop ---
            trail_act_dist = atr * self.cfg.trail_activation
            trail_stop_dist = atr * self.cfg.trail_distance
            if pos.direction == 1:
                profit_dist = bar_close - pos.entry_price
                if profit_dist >= trail_act_dist:
                    new_sl = bar_close - trail_stop_dist
                    if new_sl > pos.sl and new_sl > pos.entry_price:
                        pos.sl = new_sl
            else:
                profit_dist = pos.entry_price - bar_close
                if profit_dist >= trail_act_dist:
                    new_sl = bar_close + trail_stop_dist
                    if new_sl < pos.sl and new_sl < pos.entry_price:
                        pos.sl = new_sl

            # --- Progressive SL tightening (aggressive schedule) ---
            if self.cfg.enable_dyn_closure and unrealized < 0 and bars_held >= 5:
                orig_sl_dist = abs(pos.entry_price - pos.original_sl)
                if orig_sl_dist <= 0:
                    orig_sl_dist = atr * self.cfg.sl_atr

                factor = 1.0
                if bars_held >= 16:
                    factor = 0.30
                elif bars_held >= 10:
                    factor = 0.45
                elif bars_held >= 5:
                    factor = 0.65

                if factor < 1.0:
                    new_sl_dist = orig_sl_dist * factor
                    min_dist = self.cfg.min_sl_pts * self.cfg.point * 0.5
                    new_sl_dist = max(new_sl_dist, min_dist)

                    if pos.direction == 1:
                        new_sl = pos.entry_price - new_sl_dist
                        if new_sl > pos.sl:
                            pos.sl = new_sl
                    else:
                        new_sl = pos.entry_price + new_sl_dist
                        if new_sl < pos.sl:
                            pos.sl = new_sl

    def _evaluate_signals(self, i, df):
        """Phase 2: evaluate confluence and place trades."""
        cfg = self.cfg
        atr = df['atr'].iloc[i]
        if atr <= 0:
            return

        # Pre-trade checks
        if len(self.positions) >= cfg.max_concurrent:
            return
        if self.daily_trades >= cfg.max_daily_trades:
            return
        # Daily loss check
        daily_pl = self.balance - self.daily_start_balance
        if daily_pl < -(self.daily_start_balance * cfg.max_daily_loss / 100):
            return
        # Drawdown check
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
        dd = (self.peak_balance - self.balance) / max(self.peak_balance, 1) * 100
        if dd > cfg.max_drawdown:
            return
        # Weekend
        dow = df['day_of_week'].iloc[i]
        if dow >= 5:
            return

        # Get regime weights
        weights = detect_regime(i, df, cfg)
        if not weights['allow']:
            return

        # Evaluate strategies
        signals = []  # (direction, weighted_score, strat_idx)

        if cfg.enable_trend:
            d, s = eval_trend(i, df, cfg)
            if s >= cfg.min_strat_score:
                signals.append((d, s * weights['trend'], 0))

        if cfg.enable_momentum:
            d, s = eval_momentum(i, df, cfg)
            if s >= cfg.min_strat_score:
                signals.append((d, s * weights['momentum'], 1))

        if cfg.enable_session:
            d, s = eval_session(i, df, cfg)
            if s >= cfg.min_strat_score:
                signals.append((d, s * weights['session'], 2))

        if cfg.enable_mean_revert:
            d, s = eval_mean_revert(i, df, cfg)
            if s >= cfg.min_strat_score:
                signals.append((d, s * weights['mean_revert'], 3))

        if cfg.enable_smc:
            d, s = eval_smc(i, df, cfg)
            if s >= 10:
                signals.append((d, s * weights['smc'], 4))

        if not signals:
            return

        # Tally votes
        buy_votes = sum(1 for d, _, _ in signals if d == 1)
        sell_votes = sum(1 for d, _, _ in signals if d == -1)
        buy_score = sum(ws for d, ws, _ in signals if d == 1)
        sell_score = sum(ws for d, ws, _ in signals if d == -1)

        adj_min_score = cfg.min_score + weights['score_adj']

        direction = 0
        score = 0
        dom_strat = 0

        if buy_votes >= cfg.min_strategies and buy_score >= adj_min_score and buy_score > sell_score:
            direction = 1
            score = buy_score
            dom_strat = max((ws, si) for d, ws, si in signals if d == 1)[1]
        elif sell_votes >= cfg.min_strategies and sell_score >= adj_min_score and sell_score > buy_score:
            direction = -1
            score = sell_score
            dom_strat = max((ws, si) for d, ws, si in signals if d == -1)[1]

        if direction == 0:
            return

        # MTF filter
        if cfg.enable_mtf:
            h4_dir = calc_h4_trend(df, i)
            if h4_dir != 0 and h4_dir != direction:
                return

        # Check no duplicate direction
        for pos in self.positions:
            if pos.direction == direction:
                return

        # Calculate SL, TP, entry
        close = df['close'].iloc[i]
        spread = cfg.avg_spread * cfg.point

        sl_dist = atr * cfg.sl_atr
        sl_pts = sl_dist / cfg.point
        if sl_pts < cfg.min_sl_pts:
            sl_dist = cfg.min_sl_pts * cfg.point
        if sl_pts > cfg.max_sl_pts:
            sl_dist = cfg.max_sl_pts * cfg.point

        tp_dist = atr * cfg.tp_atr
        min_tp = sl_dist * cfg.min_risk_reward
        if tp_dist < min_tp:
            tp_dist = min_tp

        if direction == 1:
            entry = close + spread / 2
            sl = entry - sl_dist
            tp = entry + tp_dist
        else:
            entry = close - spread / 2
            sl = entry + sl_dist
            tp = entry - tp_dist

        # Position sizing
        sl_points = sl_dist / cfg.point
        risk_amount = self.balance * (cfg.risk_per_trade / 100)
        lot = risk_amount / (sl_points * cfg.tick_value)
        lot = max(cfg.min_lot, min(cfg.max_lot, round(lot / cfg.lot_step) * cfg.lot_step))

        # Apply brain lot multiplier + score scaling
        lot = round(lot * weights['lot_mult'], 2)
        if score < 50:
            lot = round(lot * 0.60, 2)
        elif score < 70:
            lot = round(lot * 0.80, 2)
        # score >= 70: full lot (reward high-confidence signals)
        lot = max(cfg.min_lot, lot)

        # Open position
        self.ticket_counter += 1
        pos = Position(
            ticket=self.ticket_counter,
            direction=direction,
            entry_price=round(entry, 2),
            sl=round(sl, 2),
            tp=round(tp, 2),
            volume=lot,
            open_bar=i,
            open_time=df['datetime'].iloc[i],
            original_sl=round(sl, 2),
            strategy_idx=dom_strat
        )
        self.positions.append(pos)
        self.daily_trades += 1

    def _close_position(self, pos, i, df, reason, exit_price=None):
        """Close a position and record the trade."""
        if exit_price is None:
            if pos.direction == 1:
                exit_price = df['close'].iloc[i] - self.cfg.avg_spread * self.cfg.point / 2
            else:
                exit_price = df['close'].iloc[i] + self.cfg.avg_spread * self.cfg.point / 2

        if pos.direction == 1:
            pip_pl = exit_price - pos.entry_price
        else:
            pip_pl = pos.entry_price - exit_price

        remaining_profit = pip_pl * pos.volume * (self.cfg.tick_value / self.cfg.point)
        # Total trade profit includes partial close profits (already booked to balance)
        profit = remaining_profit + pos.partial_profit

        self.balance += remaining_profit  # Only add remaining (partial already in balance)
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance

        bars_held = i - pos.open_bar

        self.closed_trades.append(ClosedTrade(
            ticket=pos.ticket,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            volume=pos.volume,
            profit=profit,
            bars_held=bars_held,
            strategy_idx=pos.strategy_idx
        ))

        if pos in self.positions:
            self.positions.remove(pos)

        # Cooldown tracking
        if profit < 0:
            self.consec_losses += 1
            if self.consec_losses >= self.cfg.cooldown_losses:
                self.cooldown_remaining = self.cfg.cooldown_bars
                self.consec_losses = 0
        else:
            self.consec_losses = 0

    def _compute_stats(self) -> dict:
        """Compute final backtest statistics."""
        trades = self.closed_trades
        total = len(trades)
        if total == 0:
            return {'total_trades': 0, 'wins': 0, 'losses': 0,
                    'win_rate': 0, 'profit_factor': 0,
                    'net_profit': 0, 'return_pct': 0,
                    'gross_profit': 0, 'gross_loss': 0,
                    'avg_win': 0, 'avg_loss': 0,
                    'max_drawdown': 0, 'max_drawdown_pct': 0,
                    'final_balance': self.balance,
                    'avg_bars_held': 0, 'avg_bars_win': 0, 'avg_bars_loss': 0,
                    'strategy_breakdown': {}}

        wins = [t for t in trades if t.profit > 0]
        losses = [t for t in trades if t.profit <= 0]

        gross_profit = sum(t.profit for t in wins)
        gross_loss = abs(sum(t.profit for t in losses))

        avg_win = gross_profit / len(wins) if wins else 0
        avg_loss = gross_loss / len(losses) if losses else 0

        pf = gross_profit / max(gross_loss, 0.01)
        wr = len(wins) / total * 100
        net = self.balance - self.cfg.initial_balance
        ret = net / self.cfg.initial_balance * 100

        # Max drawdown
        equity_curve = [self.cfg.initial_balance]
        running = self.cfg.initial_balance
        for t in trades:
            running += t.profit
            equity_curve.append(running)

        peak = equity_curve[0]
        max_dd = 0
        max_dd_pct = 0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            dd_pct = dd / peak * 100 if peak > 0 else 0
            if dd_pct > max_dd_pct:
                max_dd = dd
                max_dd_pct = dd_pct

        # Strategy breakdown
        strat_names = ['Trend', 'Momentum', 'Session', 'MeanRevert', 'SMC']
        strat_stats = {}
        for idx, name in enumerate(strat_names):
            st = [t for t in trades if t.strategy_idx == idx]
            sw = [t for t in st if t.profit > 0]
            strat_stats[name] = {
                'trades': len(st),
                'wins': len(sw),
                'wr': len(sw) / len(st) * 100 if st else 0,
                'profit': sum(t.profit for t in st)
            }

        # Bars held stats
        avg_bars = np.mean([t.bars_held for t in trades])
        avg_bars_win = np.mean([t.bars_held for t in wins]) if wins else 0
        avg_bars_loss = np.mean([t.bars_held for t in losses]) if losses else 0

        # Exit reason breakdown
        # Count by exit type (using profit direction and bars held as proxy)

        stats = {
            'total_trades': total,
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(wr, 1),
            'profit_factor': round(pf, 2),
            'net_profit': round(net, 2),
            'return_pct': round(ret, 1),
            'gross_profit': round(gross_profit, 2),
            'gross_loss': round(gross_loss, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'max_drawdown': round(max_dd, 2),
            'max_drawdown_pct': round(max_dd_pct, 1),
            'final_balance': round(self.balance, 2),
            'avg_bars_held': round(avg_bars, 1),
            'avg_bars_win': round(avg_bars_win, 1),
            'avg_bars_loss': round(avg_bars_loss, 1),
            'strategy_breakdown': strat_stats,
        }
        return stats


def print_stats(stats):
    """Pretty-print backtest results."""
    print("\n" + "=" * 60)
    print("  CLAWBOT BACKTEST RESULTS")
    print("=" * 60)
    print(f"  Total Trades:      {stats['total_trades']}")
    print(f"  Wins / Losses:     {stats['wins']} / {stats['losses']}")
    print(f"  Win Rate:          {stats['win_rate']}%")
    print(f"  Profit Factor:     {stats['profit_factor']}")
    print(f"  Net Profit:        ${stats['net_profit']:,.2f}")
    print(f"  Return:            {stats['return_pct']}%")
    print(f"  Final Balance:     ${stats['final_balance']:,.2f}")
    print(f"  Max Drawdown:      ${stats['max_drawdown']:,.2f} ({stats['max_drawdown_pct']}%)")
    print(f"  Avg Win:           ${stats['avg_win']:,.2f}")
    print(f"  Avg Loss:          ${stats['avg_loss']:,.2f}")
    print(f"  Avg Bars Held:     {stats['avg_bars_held']} (win: {stats['avg_bars_win']}, loss: {stats['avg_bars_loss']})")
    print("-" * 60)
    print("  Strategy Breakdown:")
    for name, s in stats.get('strategy_breakdown', {}).items():
        if s['trades'] > 0:
            print(f"    {name:12s}: {s['trades']:3d} trades, WR {s['wr']:5.1f}%, P/L ${s['profit']:+,.2f}")
    print("=" * 60)


def diagnose(stats):
    """Diagnose issues and return list of problems + suggested fixes."""
    issues = []

    wr = stats['win_rate']
    pf = stats['profit_factor']
    avg_win = stats['avg_win']
    avg_loss = stats['avg_loss']
    ret = stats['return_pct']
    total = stats['total_trades']

    if wr < 80:
        issues.append(f"WIN_RATE: {wr}% < 80% target")
    if ret < 50:
        issues.append(f"RETURN: {ret}% < 50% target")
    if pf < 1.0:
        issues.append(f"PROFIT_FACTOR: {pf} < 1.0 (losing money)")
    if avg_loss > avg_win * 2:
        issues.append(f"LOSS_RATIO: avg_loss (${avg_loss:.2f}) > 2x avg_win (${avg_win:.2f})")
    if total < 50:
        issues.append(f"TOO_FEW_TRADES: {total} < 50 minimum")
    if stats['max_drawdown_pct'] > 20:
        issues.append(f"DRAWDOWN: {stats['max_drawdown_pct']}% > 20% limit")

    # Check strategy breakdown
    for name, s in stats.get('strategy_breakdown', {}).items():
        if s['trades'] > 10 and s['wr'] < 40:
            issues.append(f"WEAK_STRATEGY: {name} WR={s['wr']:.1f}% is dragging performance")
        if s['trades'] > 10 and s['profit'] < -100:
            issues.append(f"LOSING_STRATEGY: {name} P/L=${s['profit']:+,.2f}")

    return issues


# ============================================================
#  ENTRY POINT
# ============================================================
def main(data_path=None, config_overrides=None):
    if data_path is None:
        data_path = Path(__file__).parent.parent / "Data" / "XAUUSD_H1.csv"

    df = pd.read_csv(data_path)
    print(f"Loaded {len(df)} bars from {data_path}")

    cfg = Config()

    # Auto-load optimal_config.json if available
    opt_path = Path(__file__).parent.parent / "Data" / "optimal_config.json"
    if opt_path.exists():
        try:
            with open(opt_path) as f:
                opt = json.load(f)
            for k, v in opt.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, type(getattr(cfg, k))(v))
            print(f"Loaded config from {opt_path.name}")
        except Exception as e:
            print(f"Warning: could not load {opt_path}: {e}")

    if config_overrides:
        for k, v in config_overrides.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)

    bt = ClawbotBacktester(cfg)
    stats = bt.run(df)
    print_stats(stats)

    issues = diagnose(stats)
    if issues:
        print("\nDIAGNOSTICS:")
        for iss in issues:
            print(f"  [!] {iss}")

    return stats, issues, cfg


if __name__ == "__main__":
    main()
