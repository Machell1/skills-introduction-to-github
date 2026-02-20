#!/usr/bin/env python3
"""
=======================================================================
  TRADING BOT - ONE-CLICK: Backtest on Real MT5 Data -> Go Live
=======================================================================
  ONE FILE. ONE CLICK. EVERYTHING.

  This script:
    1. Creates a Python 3.9 virtual environment (if needed)
    2. Installs numpy, pandas, MetaTrader5 into it
    3. Re-launches itself inside the venv
    4. Connects to your Deriv MT5 terminal
    5. Fetches REAL historical data
    6. Calibrates strategy parameters via backtesting
    7. If target is met -> transitions to LIVE TRADING

  Requirements:
    - Windows PC with Python 3.9 installed
    - Deriv MT5 terminal running and logged in

  Usage:
    Double-click trading_bot.py          (default: auto-connect, go live)
    python trading_bot.py --mode backtest
    python trading_bot.py --login 12345 --password xxx --server Deriv-Demo
    python trading_bot.py --symbol "Volatility 75 Index" --timeframe H1
    python trading_bot.py --bars 10000 --target 500
=======================================================================
"""

from __future__ import annotations

import os
import sys
import subprocess

# =====================================================================
#  PHASE 0: SELF-BOOTSTRAPPING VENV SETUP
#  If we're not running inside the venv, set it up and re-launch.
# =====================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(SCRIPT_DIR, ".venv")
VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
REQUIREMENTS = ["numpy>=1.24.0,<2.0.0", "pandas>=1.5.0,<3.0.0", "MetaTrader5>=5.0.45"]


def _is_in_venv() -> bool:
    """Check if we're running inside the .venv."""
    return hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )


def _bootstrap():
    """Create venv, install deps, re-launch this script inside the venv."""
    print()
    print("=" * 70)
    print("  TRADING BOT - FIRST-TIME SETUP")
    print("=" * 70)
    print()

    # Find Python 3.9
    py_cmd = None

    # Try py launcher first (Windows)
    try:
        result = subprocess.run(
            ["py", "-3.9", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            py_cmd = ["py", "-3.9"]
            print(f"  Found: {result.stdout.strip()} (via py launcher)")
    except Exception:
        pass

    # Fall back to python in PATH
    if py_cmd is None:
        try:
            result = subprocess.run(
                [sys.executable, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                ver = result.stdout.strip()
                print(f"  Found: {ver}")
                py_cmd = [sys.executable]
        except Exception:
            pass

    if py_cmd is None:
        print("  ERROR: Python not found.")
        print("  Install Python 3.9 from:")
        print("  https://www.python.org/downloads/release/python-3913/")
        print("  Make sure to check 'Add Python to PATH' during install.")
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    # Create venv
    if not os.path.exists(VENV_PYTHON):
        print()
        print("  [1/3] Creating virtual environment ...")
        ret = subprocess.run(py_cmd + ["-m", "venv", VENV_DIR])
        if ret.returncode != 0 or not os.path.exists(VENV_PYTHON):
            print("  ERROR: Failed to create virtual environment.")
            print(f"  Tried: {' '.join(py_cmd)} -m venv {VENV_DIR}")
            print("  Delete the .venv folder if it exists and try again.")
            input("\n  Press Enter to exit ...")
            sys.exit(1)
        print("  Done.")
    else:
        print("  [1/3] Virtual environment already exists.")

    # Upgrade pip
    print("  [2/3] Upgrading pip ...")
    subprocess.run(
        [VENV_PYTHON, "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        capture_output=True,
    )

    # Install dependencies
    print("  [3/3] Installing dependencies (numpy, pandas, MetaTrader5) ...")
    ret = subprocess.run(
        [VENV_PYTHON, "-m", "pip", "install", "--quiet"] + REQUIREMENTS,
    )
    if ret.returncode != 0:
        print()
        print("  ERROR: Failed to install dependencies.")
        print("  If MetaTrader5 failed, you need Python 3.9-3.12 on Windows.")
        print()
        print("  To fix:")
        print("    1. Install Python 3.9 from:")
        print("       https://www.python.org/downloads/release/python-3913/")
        print("    2. Delete the .venv folder")
        print("    3. Double-click this script again")
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    print("  All dependencies installed.")
    print()
    print("  Re-launching inside virtual environment ...")
    print("=" * 70)
    print()

    # Re-launch this same script inside the venv
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])


# If not in the venv, bootstrap first
if not _is_in_venv():
    _bootstrap()
    sys.exit(0)  # Should not reach here due to os.execv


# =====================================================================
#  PHASE 1: ALL IMPORTS (now inside venv with deps installed)
# =====================================================================

import argparse
import copy
import json
import random
import time as time_mod
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None


# =====================================================================
#  CONFIG
# =====================================================================

INITIAL_BALANCE = 500.0
PROFIT_TARGET_PCT = 1000.0

MT5_SYMBOL = "Volatility 75 Index"
MT5_TIMEFRAME = "H1"
MT5_BARS = 8000

RISK_PER_TRADE_PCT = 5.0
MAX_POSITION_SIZE_PCT = 80.0
MIN_POSITION_SIZE_PCT = 2.0

LOOKBACK_PERIOD = 14
BREAKOUT_THRESHOLD = 1.0
VOLUME_SURGE_MULT = 1.3
ATR_PERIOD = 14

REWARD_RISK_RATIO = 3.0
TRAILING_STOP_ATR_MULT = 1.5
TAKE_PROFIT_ATR_MULT = 5.0

MAX_CALIBRATION_ROUNDS = 300
PARAM_STEP_SIZES = {
    "LOOKBACK_PERIOD": 2,
    "BREAKOUT_THRESHOLD": 0.1,
    "VOLUME_SURGE_MULT": 0.1,
    "TRAILING_STOP_ATR_MULT": 0.15,
    "TAKE_PROFIT_ATR_MULT": 0.5,
    "RISK_PER_TRADE_PCT": 0.5,
    "MAX_POSITION_SIZE_PCT": 5.0,
}
PARAM_BOUNDS = {
    "LOOKBACK_PERIOD": (5, 40),
    "BREAKOUT_THRESHOLD": (0.3, 3.0),
    "VOLUME_SURGE_MULT": (1.0, 3.0),
    "TRAILING_STOP_ATR_MULT": (0.3, 4.0),
    "TAKE_PROFIT_ATR_MULT": (2.0, 15.0),
    "RISK_PER_TRADE_PCT": (2.0, 15.0),
    "MAX_POSITION_SIZE_PCT": (30.0, 100.0),
}

# Execution cost model — makes the backtest more realistic.
# SPREAD_POINTS: half-spread applied on entry AND exit (full round-trip cost).
# SLIPPAGE_POINTS: additional adverse slippage on stop-loss fills.
SPREAD_POINTS = 50.0        # ~50 points typical for Vol 75 on Deriv
SLIPPAGE_POINTS = 30.0      # conservative estimate for stop slippage


# =====================================================================
#  MT5 CONNECTOR
# =====================================================================

DERIV_SERVERS = [
    "Deriv-Demo",
    "Deriv-Server",
    "Deriv-Real",
    "Deriv-Server-02",
]

TIMEFRAME_MAP = {
    "M1":  mt5.TIMEFRAME_M1  if mt5 else 1,
    "M5":  mt5.TIMEFRAME_M5  if mt5 else 5,
    "M15": mt5.TIMEFRAME_M15 if mt5 else 15,
    "M30": mt5.TIMEFRAME_M30 if mt5 else 30,
    "H1":  mt5.TIMEFRAME_H1  if mt5 else 16385,
    "H4":  mt5.TIMEFRAME_H4  if mt5 else 16388,
    "D1":  mt5.TIMEFRAME_D1  if mt5 else 16408,
}


def mt5_check_available() -> bool:
    if mt5 is None:
        print("  FATAL: MetaTrader5 package not installed.")
        print("  This should not happen — re-run this script to reinstall.")
        return False
    if sys.platform != "win32":
        print("  FATAL: MetaTrader5 only works on Windows.")
        return False
    return True


def mt5_connect(
    login: Optional[int] = None,
    password: Optional[str] = None,
    server: Optional[str] = None,
    path: Optional[str] = None,
    timeout: int = 30000,
) -> bool:
    if not mt5_check_available():
        return False

    init_kwargs = {"login": login, "timeout": timeout}
    if path:
        init_kwargs["path"] = path
    if password:
        init_kwargs["password"] = password

    if server:
        init_kwargs["server"] = server
        if mt5.initialize(**{k: v for k, v in init_kwargs.items() if v is not None}):
            _mt5_print_info()
            return True
        print(f"  Failed to connect to {server}: {mt5.last_error()}")
        return False

    if mt5.initialize(timeout=timeout):
        _mt5_print_info()
        return True

    if login and password:
        for srv in DERIV_SERVERS:
            init_kwargs["server"] = srv
            print(f"  Trying server: {srv} ...")
            if mt5.initialize(**{k: v for k, v in init_kwargs.items() if v is not None}):
                _mt5_print_info()
                return True

    print(f"  ERROR: Could not connect to MT5: {mt5.last_error()}")
    print("  Make sure your Deriv MT5 terminal is running.")
    return False


def mt5_disconnect():
    if mt5 is not None:
        mt5.shutdown()
        print("  MT5 disconnected.")


def _mt5_print_info():
    info = mt5.terminal_info()
    account = mt5.account_info()
    if info and account:
        print(f"  Connected to MT5:")
        print(f"    Terminal:  {info.name}")
        print(f"    Company:   {info.company}")
        print(f"    Account:   {account.login}")
        print(f"    Server:    {account.server}")
        print(f"    Balance:   ${account.balance:,.2f}")
        print(f"    Leverage:  1:{account.leverage}")
        print(f"    Currency:  {account.currency}")


def mt5_get_balance() -> float:
    account = mt5.account_info()
    return float(account.balance) if account else 0.0


def mt5_get_account_info() -> dict:
    account = mt5.account_info()
    if account is None:
        return {}
    return {
        "login": account.login, "server": account.server,
        "balance": account.balance, "equity": account.equity,
        "margin": account.margin, "free_margin": account.margin_free,
        "leverage": account.leverage, "currency": account.currency,
        "profit": account.profit,
    }


def mt5_fetch_data(symbol: str, timeframe: str = "H1", bars: int = 8000) -> Optional[pd.DataFrame]:
    tf = TIMEFRAME_MAP.get(timeframe.upper())
    if tf is None:
        print(f"  ERROR: Unknown timeframe '{timeframe}'")
        print(f"  Valid: {', '.join(TIMEFRAME_MAP.keys())}")
        return None

    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"  ERROR: Symbol '{symbol}' not found in MT5.")
        symbols = mt5.symbols_get()
        if symbols:
            matches = [s.name for s in symbols if "volatility" in s.name.lower()]
            for name in matches[:10]:
                print(f"    - {name}")
        return None

    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"  ERROR: Could not select symbol '{symbol}'")
            return None

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
    if rates is None or len(rates) == 0:
        print(f"  ERROR: No data returned for {symbol} {timeframe}")
        print(f"  MT5 error: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")
    df = df.rename(columns={"tick_volume": "volume"})
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df = df.astype(float)

    print(f"  Fetched {len(df)} bars of {symbol} ({timeframe})")
    print(f"  Date range: {df.index[0]} to {df.index[-1]}")
    print(f"  Price range: ${df['close'].min():.5f} - ${df['close'].max():.5f}")
    return df


def mt5_get_symbol_info(symbol: str) -> Optional[dict]:
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    return {
        "name": info.name, "point": info.point, "digits": info.digits,
        "spread": info.spread, "trade_contract_size": info.trade_contract_size,
        "volume_min": info.volume_min, "volume_max": info.volume_max,
        "volume_step": info.volume_step,
    }


def _get_filling_mode(symbol):
    """Auto-detect the supported filling mode for a symbol.

    IMPORTANT: symbol_info().filling_mode is a bitmask using SYMBOL_FILLING_*
    constants (FOK=1, IOC=2), which are DIFFERENT from ORDER_FILLING_* constants
    (FOK=0, IOC=1, RETURN=2). You cannot use ORDER_FILLING_* for bitwise checks.

    For Deriv synthetic indices, ORDER_FILLING_RETURN is the correct mode.
    """
    info = mt5.symbol_info(symbol)
    if info is not None:
        modes = info.filling_mode
        # SYMBOL_FILLING_FOK = 1 (bit 0), SYMBOL_FILLING_IOC = 2 (bit 1)
        if modes & 1:  # FOK supported
            return mt5.ORDER_FILLING_FOK
        if modes & 2:  # IOC supported
            return mt5.ORDER_FILLING_IOC
    # RETURN works for Deriv synthetics and most exchange-execution brokers
    return mt5.ORDER_FILLING_RETURN


def mt5_place_order(symbol, direction, volume, sl=0.0, tp=0.0, comment="TradingBot", deviation=20):
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"  ERROR: Symbol '{symbol}' not found")
        return None

    vol_step = info.volume_step
    volume = max(info.volume_min, round(round(volume / vol_step) * vol_step, 8))
    volume = min(volume, info.volume_max)

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"  ERROR: Cannot get price for '{symbol}'")
        return None

    if direction == 1:
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid

    # Normalize SL/TP to symbol's digits and enforce minimum stop distance
    digits = info.digits
    point = info.point
    stops_level = info.trade_stops_level  # minimum distance in points
    min_distance = stops_level * point
    if min_distance <= 0:
        min_distance = 10 * point  # safe fallback if broker reports 0

    if sl > 0:
        sl = round(sl, digits)
        # Ensure SL is at least min_distance from current price
        if direction == 1 and price - sl < min_distance:
            sl = round(price - min_distance, digits)
            print(f"    SL adjusted to min distance: {sl}")
        elif direction == -1 and sl - price < min_distance:
            sl = round(price + min_distance, digits)
            print(f"    SL adjusted to min distance: {sl}")

    if tp > 0:
        tp = round(tp, digits)
        # Ensure TP is at least min_distance from current price
        if direction == 1 and tp - price < min_distance:
            tp = round(price + min_distance, digits)
            print(f"    TP adjusted to min distance: {tp}")
        elif direction == -1 and price - tp < min_distance:
            tp = round(price - min_distance, digits)
            print(f"    TP adjusted to min distance: {tp}")

    filling = _get_filling_mode(symbol)
    filling_names = {0: "FOK", 1: "IOC", 2: "RETURN"}
    print(f"    Filling: {filling_names.get(filling, filling)} | "
          f"Digits: {digits} | StopsLevel: {stops_level} pts ({min_distance:.{digits}f})")

    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume,
        "type": order_type, "price": price, "sl": sl, "tp": tp,
        "deviation": deviation, "magic": 202602, "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling,
    }

    # Pre-check the order before sending
    check = mt5.order_check(request)
    if check is None:
        print(f"  ERROR: order_check failed: {mt5.last_error()}")
        return None
    if check.retcode != 0:
        print(f"  PRE-CHECK rejected: {check.comment} (code {check.retcode})")
        # If filling mode was rejected, try RETURN as fallback
        if check.retcode == 10030:
            print(f"    Retrying with ORDER_FILLING_RETURN ...")
            request["type_filling"] = mt5.ORDER_FILLING_RETURN
            check = mt5.order_check(request)
            if check is None or check.retcode != 0:
                err = check.comment if check else mt5.last_error()
                print(f"    RETURN also rejected: {err}")
                return None
            print(f"    ORDER_FILLING_RETURN accepted")
        # If stops are invalid, place order without SL/TP, then set via modify
        elif check.retcode == 10016:
            print(f"    Placing order WITHOUT SL/TP, will set them via modify ...")
            saved_sl, saved_tp = request.pop("sl", 0), request.pop("tp", 0)
            request["sl"] = 0.0
            request["tp"] = 0.0
            check2 = mt5.order_check(request)
            if check2 is None or check2.retcode != 0:
                err = check2.comment if check2 else mt5.last_error()
                print(f"    Still rejected without stops: {err}")
                return None
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                err = result.comment if result else mt5.last_error()
                print(f"  ERROR: Order send failed: {err}")
                return None
            print(f"  ORDER FILLED: {'BUY' if direction == 1 else 'SELL'} {volume} {symbol} @ {result.price}")
            print(f"    Ticket: {result.order}")
            # Now set SL/TP via position modify
            if saved_sl > 0 or saved_tp > 0:
                mod_request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": result.order,
                    "symbol": symbol,
                    "sl": saved_sl if saved_sl > 0 else 0.0,
                    "tp": saved_tp if saved_tp > 0 else 0.0,
                }
                mod_result = mt5.order_send(mod_request)
                if mod_result and mod_result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"    SL/TP set: SL={saved_sl:.{digits}f} TP={saved_tp:.{digits}f}")
                else:
                    err = mod_result.comment if mod_result else mt5.last_error()
                    print(f"    WARNING: Could not set SL/TP: {err}")
                    print(f"    Position is OPEN without stops — monitor manually!")
            return {
                "ticket": result.order, "price": result.price,
                "volume": result.volume, "symbol": symbol, "direction": direction,
            }
        else:
            return None

    result = mt5.order_send(request)
    if result is None:
        print(f"  ERROR: Order send failed: {mt5.last_error()}")
        return None
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"  ERROR: Order rejected: {result.comment} (code {result.retcode})")
        return None

    print(f"  ORDER FILLED: {'BUY' if direction == 1 else 'SELL'} {volume} {symbol} @ {result.price}")
    if sl > 0:
        print(f"    SL: {sl:.5f}")
    if tp > 0:
        print(f"    TP: {tp:.5f}")
    print(f"    Ticket: {result.order}")
    return {"ticket": result.order, "price": result.price, "volume": result.volume, "symbol": symbol, "direction": direction}


def mt5_modify_position(ticket, sl=0.0, tp=0.0):
    positions = mt5.positions_get(ticket=ticket)
    if not positions or len(positions) == 0:
        print(f"  ERROR: Position {ticket} not found")
        return False
    position = positions[0]
    request = {
        "action": mt5.TRADE_ACTION_SLTP, "position": ticket,
        "symbol": position.symbol,
        "sl": sl if sl > 0 else position.sl,
        "tp": tp if tp > 0 else position.tp,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        error = result.comment if result else mt5.last_error()
        print(f"  ERROR: Modify failed: {error}")
        return False
    print(f"  Position {ticket} modified: SL={sl:.5f} TP={tp:.5f}")
    return True


def mt5_close_position(ticket):
    positions = mt5.positions_get(ticket=ticket)
    if not positions or len(positions) == 0:
        print(f"  ERROR: Position {ticket} not found")
        return False
    position = positions[0]
    symbol = position.symbol
    volume = position.volume
    if position.type == mt5.ORDER_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        price = tick.bid if tick else 0
    else:
        order_type = mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if tick else 0
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume,
        "type": order_type, "position": ticket, "price": price,
        "deviation": 20, "magic": 202602, "comment": "TradingBot close",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": _get_filling_mode(symbol),
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        error = result.comment if result else mt5.last_error()
        print(f"  ERROR: Close failed: {error}")
        return False
    print(f"  Position {ticket} closed @ {result.price}")
    return True


def mt5_get_open_positions(symbol=None):
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if positions is None:
        return []
    return [
        {
            "ticket": p.ticket, "symbol": p.symbol,
            "direction": 1 if p.type == mt5.ORDER_TYPE_BUY else -1,
            "volume": p.volume, "price_open": p.price_open,
            "sl": p.sl, "tp": p.tp, "profit": p.profit,
            "time": datetime.fromtimestamp(p.time),
        }
        for p in positions
    ]


# =====================================================================
#  STRATEGY — Momentum Breakout (Long + Short)
# =====================================================================

def compute_indicators(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    lookback = int(params["LOOKBACK_PERIOD"])
    atr_period = int(params.get("ATR_PERIOD", 14))
    out = df.copy()

    out["momentum"] = out["close"].pct_change(lookback)
    out["rolling_mean"] = out["close"].rolling(lookback).mean()
    out["rolling_std"] = out["close"].rolling(lookback).std()

    threshold = params["BREAKOUT_THRESHOLD"]
    out["upper_band"] = out["rolling_mean"] + threshold * out["rolling_std"]
    out["lower_band"] = out["rolling_mean"] - threshold * out["rolling_std"]

    tr = pd.DataFrame({
        "hl": out["high"] - out["low"],
        "hc": (out["high"] - out["close"].shift(1)).abs(),
        "lc": (out["low"] - out["close"].shift(1)).abs(),
    })
    out["atr"] = tr.max(axis=1).rolling(atr_period).mean()

    out["vol_avg"] = out["volume"].rolling(lookback).mean()
    out["vol_surge"] = out["volume"] > (params["VOLUME_SURGE_MULT"] * out["vol_avg"])

    out["ema_fast"] = out["close"].ewm(span=max(5, lookback // 2), adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=lookback * 2, adjust=False).mean()
    out["trend_up"] = out["ema_fast"] > out["ema_slow"]

    return out


def generate_signals(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    ind = compute_indicators(df, params)
    long_cond = (ind["close"] > ind["upper_band"]) & ind["vol_surge"] & ind["trend_up"]
    short_cond = (ind["close"] < ind["lower_band"]) & ind["vol_surge"] & (~ind["trend_up"])
    ind["signal"] = 0
    ind.loc[long_cond, "signal"] = 1
    ind.loc[short_cond, "signal"] = -1
    return ind


# =====================================================================
#  BACKTESTER
# =====================================================================

class Trade:
    __slots__ = (
        "entry_bar", "entry_price", "direction", "size", "stop",
        "take_profit", "trail_stop", "exit_bar", "exit_price", "pnl",
    )

    def __init__(self, entry_bar, entry_price, direction, size, stop, take_profit):
        self.entry_bar = entry_bar
        self.entry_price = entry_price
        self.direction = direction
        self.size = size
        self.stop = stop
        self.take_profit = take_profit
        self.trail_stop = stop
        self.exit_bar = None
        self.exit_price = None
        self.pnl = None


def _close_trade(trade, bar, price):
    trade.exit_bar = bar
    trade.exit_price = price
    trade.pnl = (price - trade.entry_price) * trade.size * trade.direction


def run_backtest(df: pd.DataFrame, params: dict) -> dict:
    signals = generate_signals(df, params)
    signals = signals.dropna().reset_index(drop=True)

    balance = params["INITIAL_BALANCE"]
    peak_balance = balance
    max_drawdown = 0.0
    equity_curve = [balance]
    trades = []
    open_trade = None

    trail_mult = params["TRAILING_STOP_ATR_MULT"]
    tp_mult = params["TAKE_PROFIT_ATR_MULT"]

    for i in range(1, len(signals)):
        row = signals.iloc[i]

        if open_trade is not None:
            atr_now = row["atr"] if not np.isnan(row["atr"]) and row["atr"] > 0 else 0

            if open_trade.direction == 1:
                # Check SL/TP BEFORE updating trail (fixes intra-bar ordering bias)
                if row["low"] <= open_trade.trail_stop:
                    # Stop hit — add slippage (adverse fill on stops)
                    fill = open_trade.trail_stop - SLIPPAGE_POINTS
                    _close_trade(open_trade, i, fill)
                    balance += open_trade.pnl
                    balance = max(balance, 1.0)
                    trades.append(open_trade)
                    open_trade = None
                elif row["high"] >= open_trade.take_profit:
                    # TP hit — apply spread on exit (sell at bid = tp - half_spread)
                    fill = open_trade.take_profit - SPREAD_POINTS
                    _close_trade(open_trade, i, fill)
                    balance += open_trade.pnl
                    trades.append(open_trade)
                    open_trade = None
                else:
                    # Only ratchet trail AFTER confirming no SL/TP was hit this bar
                    if atr_now > 0:
                        new_trail = row["close"] - trail_mult * atr_now
                        if new_trail > open_trade.trail_stop:
                            open_trade.trail_stop = new_trail

            elif open_trade.direction == -1:
                # Check SL/TP BEFORE updating trail
                if row["high"] >= open_trade.trail_stop:
                    # Stop hit — add slippage (adverse fill on stops)
                    fill = open_trade.trail_stop + SLIPPAGE_POINTS
                    _close_trade(open_trade, i, fill)
                    balance += open_trade.pnl
                    balance = max(balance, 1.0)
                    trades.append(open_trade)
                    open_trade = None
                elif row["low"] <= open_trade.take_profit:
                    # TP hit — apply spread on exit (buy at ask = tp + half_spread)
                    fill = open_trade.take_profit + SPREAD_POINTS
                    _close_trade(open_trade, i, fill)
                    balance += open_trade.pnl
                    trades.append(open_trade)
                    open_trade = None
                else:
                    # Only ratchet trail AFTER confirming no SL/TP was hit this bar
                    if atr_now > 0:
                        new_trail = row["close"] + trail_mult * atr_now
                        if new_trail < open_trade.trail_stop:
                            open_trade.trail_stop = new_trail

        if open_trade is None and row["signal"] != 0:
            atr = row["atr"]
            if atr <= 0 or np.isnan(atr):
                equity_curve.append(balance)
                continue

            direction = int(row["signal"])
            # Apply half-spread to entry (BUY at ask = close + spread/2, SELL at bid = close - spread/2)
            half_spread = SPREAD_POINTS
            if direction == 1:
                entry_price = row["close"] + half_spread  # buy at ask
            else:
                entry_price = row["close"] - half_spread  # sell at bid

            if direction == 1:
                stop_price = entry_price - trail_mult * atr
                tp_price = entry_price + tp_mult * atr
                risk_per_unit = entry_price - stop_price
            else:
                stop_price = entry_price + trail_mult * atr
                tp_price = entry_price - tp_mult * atr
                risk_per_unit = stop_price - entry_price

            if risk_per_unit <= 0:
                equity_curve.append(balance)
                continue

            dollar_risk = balance * (params["RISK_PER_TRADE_PCT"] / 100.0)
            units = dollar_risk / risk_per_unit
            position_value = units * entry_price

            max_val = balance * (params["MAX_POSITION_SIZE_PCT"] / 100.0)
            min_val = balance * (params["MIN_POSITION_SIZE_PCT"] / 100.0)
            if position_value > max_val:
                units = max_val / entry_price
            if position_value < min_val:
                equity_curve.append(balance)
                continue

            open_trade = Trade(
                entry_bar=i, entry_price=entry_price, direction=direction,
                size=units, stop=stop_price, take_profit=tp_price,
            )

        if open_trade is not None:
            unrealised = (row["close"] - open_trade.entry_price) * open_trade.size * open_trade.direction
            equity_curve.append(balance + unrealised)
        else:
            equity_curve.append(balance)

        if equity_curve[-1] > peak_balance:
            peak_balance = equity_curve[-1]
        dd = (peak_balance - equity_curve[-1]) / peak_balance * 100 if peak_balance > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

    if open_trade is not None:
        _close_trade(open_trade, len(signals) - 1, signals.iloc[-1]["close"])
        balance += open_trade.pnl
        trades.append(open_trade)
        equity_curve[-1] = balance

    return _compile_metrics(trades, equity_curve, params["INITIAL_BALANCE"], max_drawdown)


def _compile_metrics(trades, equity_curve, initial_balance, max_drawdown):
    final = equity_curve[-1] if equity_curve else initial_balance
    total_return = (final - initial_balance) / initial_balance * 100

    winners = [t for t in trades if t.pnl and t.pnl > 0]
    losers = [t for t in trades if t.pnl and t.pnl <= 0]

    avg_win = float(np.mean([t.pnl for t in winners])) if winners else 0.0
    avg_loss = float(np.mean([abs(t.pnl) for t in losers])) if losers else 0.0

    gross_profit = sum(t.pnl for t in winners) if winners else 0.0
    gross_loss = sum(abs(t.pnl) for t in losers) if losers else 1.0

    all_pnls = [t.pnl for t in trades if t.pnl is not None]
    avg_volume_won = float(np.mean(all_pnls)) if all_pnls else 0.0
    total_volume_won = sum(p for p in all_pnls if p > 0) if all_pnls else 0.0

    return {
        "total_return_pct": round(total_return, 2),
        "final_balance": round(final, 2),
        "initial_balance": initial_balance,
        "total_trades": len(trades),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate_pct": round(len(winners) / max(len(trades), 1) * 100, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_volume_won_per_trade": round(avg_volume_won, 2),
        "total_volume_won": round(total_volume_won, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "max_drawdown_pct": round(max_drawdown, 2),
        "equity_curve": equity_curve,
        "trades": trades,
    }


# =====================================================================
#  CALIBRATOR
# =====================================================================

def default_params() -> dict:
    return {
        "INITIAL_BALANCE": INITIAL_BALANCE,
        "LOOKBACK_PERIOD": LOOKBACK_PERIOD,
        "BREAKOUT_THRESHOLD": BREAKOUT_THRESHOLD,
        "VOLUME_SURGE_MULT": VOLUME_SURGE_MULT,
        "ATR_PERIOD": ATR_PERIOD,
        "REWARD_RISK_RATIO": REWARD_RISK_RATIO,
        "TRAILING_STOP_ATR_MULT": TRAILING_STOP_ATR_MULT,
        "TAKE_PROFIT_ATR_MULT": TAKE_PROFIT_ATR_MULT,
        "RISK_PER_TRADE_PCT": RISK_PER_TRADE_PCT,
        "MAX_POSITION_SIZE_PCT": MAX_POSITION_SIZE_PCT,
        "MIN_POSITION_SIZE_PCT": MIN_POSITION_SIZE_PCT,
        "PROFIT_TARGET_PCT": PROFIT_TARGET_PCT,
    }


def _score(metrics, target):
    vol_won = metrics["avg_volume_won_per_trade"]
    ret = metrics["total_return_pct"]
    total_vol = metrics["total_volume_won"]
    if ret >= target:
        return total_vol + vol_won * 10 + (ret - target) * 2.0
    else:
        progress = ret / max(target, 1) * 100
        return vol_won + progress * 0.5 - (target - ret) * 0.1


def calibrate(df, params=None, verbose=True):
    if params is None:
        params = default_params()

    target = params.get("PROFIT_TARGET_PCT", PROFIT_TARGET_PCT)
    best_params = copy.deepcopy(params)
    best_metrics = run_backtest(df, best_params)
    best_score = _score(best_metrics, target)

    history = []
    tunable_keys = list(PARAM_STEP_SIZES.keys())

    if verbose:
        _log_round(0, best_metrics, best_score, "INIT")

    stall_count = 0
    max_stall = 12

    for round_num in range(1, MAX_CALIBRATION_ROUNDS + 1):
        improved = False
        random.shuffle(tunable_keys)

        for key in tunable_keys:
            step = PARAM_STEP_SIZES[key]
            lo, hi = PARAM_BOUNDS[key]

            for mult in [1.0, 2.0, 0.5]:
                actual_step = step * mult
                for direction in [+1, -1]:
                    candidate = copy.deepcopy(best_params)
                    new_val = candidate[key] + direction * actual_step

                    if isinstance(PARAM_BOUNDS[key][0], int) or key == "LOOKBACK_PERIOD":
                        new_val = int(round(new_val))
                    else:
                        new_val = round(new_val, 4)

                    new_val = max(lo, min(hi, new_val))
                    if new_val == best_params[key]:
                        continue

                    candidate[key] = new_val
                    metrics = run_backtest(df, candidate)
                    score = _score(metrics, target)

                    if score > best_score:
                        best_params = candidate
                        best_metrics = metrics
                        best_score = score
                        improved = True
                        if verbose:
                            _log_round(round_num, best_metrics, best_score, f"{key}={candidate[key]}")
                        break
                if improved:
                    break

        history.append({
            "round": round_num, "score": best_score,
            "return_pct": best_metrics["total_return_pct"],
            "avg_vol_won": best_metrics["avg_volume_won_per_trade"],
        })

        if best_metrics["total_return_pct"] >= target:
            if verbose:
                print(f"\n{'='*65}")
                print(f"  TARGET HIT: {best_metrics['total_return_pct']:.1f}% return")
                print(f"  Avg volume won/trade: ${best_metrics['avg_volume_won_per_trade']:.2f}")
                print(f"  Total volume won: ${best_metrics['total_volume_won']:.2f}")
                print(f"  Calibrated in {round_num} rounds")
                print(f"{'='*65}\n")

            extra_rounds = min(20, MAX_CALIBRATION_ROUNDS - round_num)
            if extra_rounds > 0 and verbose:
                print(f"  Running {extra_rounds} extra rounds to maximise volume won...")
            for _ in range(extra_rounds):
                any_improved = False
                random.shuffle(tunable_keys)
                for key in tunable_keys:
                    step = PARAM_STEP_SIZES[key]
                    lo, hi = PARAM_BOUNDS[key]
                    for direction in [+1, -1]:
                        candidate = copy.deepcopy(best_params)
                        new_val = candidate[key] + direction * step
                        if key == "LOOKBACK_PERIOD":
                            new_val = int(round(new_val))
                        else:
                            new_val = round(new_val, 4)
                        new_val = max(lo, min(hi, new_val))
                        if new_val == best_params[key]:
                            continue
                        candidate[key] = new_val
                        metrics = run_backtest(df, candidate)
                        score = _score(metrics, target)
                        if score > best_score and metrics["total_return_pct"] >= target:
                            best_params = candidate
                            best_metrics = metrics
                            best_score = score
                            any_improved = True
                            if verbose:
                                _log_round(round_num, metrics, score, f"OPT {key}={new_val}")
                            break
                if not any_improved:
                    break
            break

        if not improved:
            stall_count += 1
            if stall_count >= max_stall:
                if verbose:
                    print(f"  [Round {round_num:>3}] Stall detected — random restart")
                best_params = _random_perturb(best_params)
                best_metrics = run_backtest(df, best_params)
                best_score = _score(best_metrics, target)
                stall_count = 0
        else:
            stall_count = 0

    return {
        "best_params": best_params, "best_metrics": best_metrics,
        "rounds_run": min(round_num, MAX_CALIBRATION_ROUNDS),
        "calibration_history": history,
        "target_met": best_metrics["total_return_pct"] >= target,
    }


def _random_perturb(params):
    p = copy.deepcopy(params)
    for key in PARAM_STEP_SIZES:
        lo, hi = PARAM_BOUNDS[key]
        if key == "LOOKBACK_PERIOD":
            p[key] = random.randint(int(lo), int(hi))
        else:
            p[key] = round(random.uniform(lo, hi), 4)
    return p


def _log_round(round_num, metrics, score, change):
    ret = metrics["total_return_pct"]
    vol = metrics["avg_volume_won_per_trade"]
    tvol = metrics["total_volume_won"]
    trades = metrics["total_trades"]
    wr = metrics["win_rate_pct"]
    dd = metrics["max_drawdown_pct"]
    print(
        f"  [Round {round_num:>3}] Return: {ret:>9.1f}%  |  "
        f"VolWon/Trade: ${vol:>9.2f}  |  "
        f"TotalVolWon: ${tvol:>10.2f}  |  "
        f"Trades: {trades:>4}  |  WR: {wr:>5.1f}%  |  "
        f"DD: {dd:>5.1f}%  |  {change}"
    )


# =====================================================================
#  LIVE TRADER
# =====================================================================

def run_live(symbol, timeframe, params, max_daily_loss_pct=10.0, check_interval_seconds=60):
    print()
    print("=" * 70)
    print("  LIVE TRADING MODE")
    print("=" * 70)

    account = mt5_get_account_info()
    if not account:
        print("  ERROR: Cannot get account info. Is MT5 connected?")
        return

    start_balance = account["balance"]
    daily_loss_limit = start_balance * (max_daily_loss_pct / 100.0)

    print(f"  Symbol:           {symbol}")
    print(f"  Timeframe:        {timeframe}")
    print(f"  Account balance:  ${start_balance:,.2f}")
    print(f"  Daily loss limit: ${daily_loss_limit:,.2f} ({max_daily_loss_pct}%)")
    print(f"  Check interval:   {check_interval_seconds}s")
    print("=" * 70)
    print()

    sym_info = mt5_get_symbol_info(symbol)
    if sym_info is None:
        print(f"  ERROR: Cannot get info for '{symbol}'")
        return

    print(f"  Symbol specs:")
    print(f"    Contract size: {sym_info['trade_contract_size']}")
    print(f"    Min lot:       {sym_info['volume_min']}")
    print(f"    Max lot:       {sym_info['volume_max']}")
    print(f"    Lot step:      {sym_info['volume_step']}")
    print(f"    Digits:        {sym_info['digits']}")
    print()

    trail_mult = params["TRAILING_STOP_ATR_MULT"]
    tp_mult = params["TAKE_PROFIT_ATR_MULT"]

    open_ticket = None
    open_direction = 0
    open_trail_stop = 0.0
    last_bar_time = None
    trade_count = 0

    print("  Monitoring for signals ... (Ctrl+C to stop)")
    print("-" * 70)

    try:
        while True:
            lookback_bars = max(100, int(params["LOOKBACK_PERIOD"]) * 4)
            df = mt5_fetch_data(symbol, timeframe, bars=lookback_bars)

            if df is None or len(df) < int(params["LOOKBACK_PERIOD"]) * 2:
                print(f"  [{_now()}] Waiting for data ...")
                time_mod.sleep(check_interval_seconds)
                continue

            # Drop the last row — it's the current INCOMPLETE bar (position 0).
            # The backtest only uses complete bars, so live must too.
            df = df.iloc[:-1]

            current_bar_time = df.index[-1]
            if last_bar_time is not None and current_bar_time <= last_bar_time:
                time_mod.sleep(check_interval_seconds)
                continue

            last_bar_time = current_bar_time

            signals = generate_signals(df, params)
            signals = signals.dropna()
            if len(signals) == 0:
                time_mod.sleep(check_interval_seconds)
                continue

            latest = signals.iloc[-1]
            atr = latest["atr"] if not np.isnan(latest["atr"]) else 0

            current_balance = mt5_get_balance()
            daily_pnl = current_balance - start_balance
            if daily_pnl < -daily_loss_limit:
                print(f"  [{_now()}] DAILY LOSS LIMIT HIT: ${daily_pnl:,.2f}")
                print("  Stopping live trading for today.")
                if open_ticket is not None:
                    mt5_close_position(open_ticket)
                break

            if open_ticket is not None:
                positions = mt5_get_open_positions(symbol)
                pos = None
                for p in positions:
                    if p["ticket"] == open_ticket:
                        pos = p
                        break

                if pos is None:
                    print(f"  [{_now()}] Position {open_ticket} closed externally")
                    open_ticket = None
                    open_direction = 0
                elif atr > 0:
                    close_price = latest["close"]
                    if open_direction == 1:
                        new_trail = close_price - trail_mult * atr
                        if new_trail > open_trail_stop:
                            open_trail_stop = new_trail
                            mt5_modify_position(open_ticket, sl=open_trail_stop)
                            print(f"  [{_now()}] Trail stop updated: {open_trail_stop:.5f}")
                    elif open_direction == -1:
                        new_trail = close_price + trail_mult * atr
                        if new_trail < open_trail_stop:
                            open_trail_stop = new_trail
                            mt5_modify_position(open_ticket, sl=open_trail_stop)
                            print(f"  [{_now()}] Trail stop updated: {open_trail_stop:.5f}")

            if open_ticket is None and latest["signal"] != 0 and atr > 0:
                direction = int(latest["signal"])

                # Get the LIVE bid/ask for SL/TP calculation (not bar close)
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    time_mod.sleep(check_interval_seconds)
                    continue
                entry_price = tick.ask if direction == 1 else tick.bid

                if direction == 1:
                    sl_price = entry_price - trail_mult * atr
                    tp_price = entry_price + tp_mult * atr
                    risk_per_unit = entry_price - sl_price
                else:
                    sl_price = entry_price + trail_mult * atr
                    tp_price = entry_price - tp_mult * atr
                    risk_per_unit = sl_price - entry_price

                if risk_per_unit <= 0:
                    time_mod.sleep(check_interval_seconds)
                    continue

                balance = mt5_get_balance()
                dollar_risk = balance * (params["RISK_PER_TRADE_PCT"] / 100.0)
                units = dollar_risk / risk_per_unit

                contract_size = sym_info["trade_contract_size"]
                lots = units / contract_size if contract_size > 0 else units

                position_value = units * entry_price
                max_val = balance * (params["MAX_POSITION_SIZE_PCT"] / 100.0)
                min_val = balance * (params["MIN_POSITION_SIZE_PCT"] / 100.0)

                if position_value > max_val:
                    lots = (max_val / entry_price) / contract_size if contract_size > 0 else max_val / entry_price
                if position_value < min_val:
                    time_mod.sleep(check_interval_seconds)
                    continue

                print(f"\n  [{_now()}] SIGNAL: {'BUY' if direction == 1 else 'SELL'}")
                print(f"    Live {'Ask' if direction == 1 else 'Bid'}: {entry_price:.5f}")
                print(f"    ATR:    {atr:.5f}")
                print(f"    SL:     {sl_price:.5f}")
                print(f"    TP:     {tp_price:.5f}")
                print(f"    Lots:   {lots:.2f}")

                result = mt5_place_order(
                    symbol=symbol, direction=direction, volume=lots,
                    sl=sl_price, tp=tp_price, comment=f"Bot-{trade_count + 1}",
                )

                if result:
                    open_ticket = result["ticket"]
                    open_direction = direction
                    open_trail_stop = sl_price
                    trade_count += 1
                    # Recalculate SL/TP from actual fill price if it differs
                    actual_fill = result["price"]
                    if abs(actual_fill - entry_price) > 0.01:
                        if direction == 1:
                            sl_price = actual_fill - trail_mult * atr
                            tp_price = actual_fill + tp_mult * atr
                        else:
                            sl_price = actual_fill + trail_mult * atr
                            tp_price = actual_fill - tp_mult * atr
                        open_trail_stop = sl_price
                        mt5_modify_position(open_ticket, sl=sl_price, tp=tp_price)
                        print(f"    Adjusted SL/TP to actual fill {actual_fill:.5f}")
                    print(f"    Trade #{trade_count} opened: ticket {open_ticket}")
                else:
                    print(f"    Order failed - will retry on next signal")

            if trade_count > 0 or open_ticket is not None:
                bal = mt5_get_balance()
                pnl = bal - start_balance
                print(f"  [{_now()}] Balance: ${bal:,.2f} | "
                      f"PnL: ${pnl:+,.2f} | "
                      f"Trades: {trade_count} | "
                      f"{'IN TRADE' if open_ticket else 'FLAT'}")

            time_mod.sleep(check_interval_seconds)

    except KeyboardInterrupt:
        print(f"\n  [{_now()}] Stopping live trading (Ctrl+C) ...")
        if open_ticket is not None:
            mt5_close_position(open_ticket)

    final_balance = mt5_get_balance()
    total_pnl = final_balance - start_balance
    print()
    print("=" * 70)
    print("  LIVE TRADING SESSION ENDED")
    print(f"  Start balance:  ${start_balance:,.2f}")
    print(f"  Final balance:  ${final_balance:,.2f}")
    print(f"  Total PnL:      ${total_pnl:+,.2f} ({total_pnl / start_balance * 100:+.1f}%)")
    print(f"  Trades taken:   {trade_count}")
    print("=" * 70)


def _now():
    return datetime.now().strftime("%H:%M:%S")


# =====================================================================
#  MAIN — The full pipeline
# =====================================================================

def main():
    args = parse_args()

    print("=" * 70)
    print("  TRADING BOT - ONE CLICK: REAL DATA BACKTEST -> LIVE")
    print("=" * 70)
    print(f"  Mode:              {args.mode.upper()}")
    print(f"  Symbol:            {args.symbol}")
    print(f"  Timeframe:         {args.timeframe}")
    print(f"  Historical bars:   {args.bars:,}")
    print(f"  Profit target:     {args.target:,.0f}%")
    print(f"  Optimising for:    VOLUME WON PER TRADE (NOT win rate)")
    print("=" * 70)
    print()

    # ── Step 1: Connect to MT5 ──────────────────────────────────
    print("[1/4] Connecting to Deriv MT5 ...")

    if not mt5_check_available():
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    connected = mt5_connect(
        login=args.login,
        password=args.password,
        server=args.server,
        path=args.mt5_path,
    )

    if not connected:
        print()
        print("  FATAL: Could not connect to MT5.")
        print("  Make sure:")
        print("    1. Deriv MT5 terminal is running on your PC")
        print("    2. You are logged into your account")
        print("    3. Or provide credentials:")
        print("       python trading_bot.py --login YOUR_ID --password YOUR_PASS --server Deriv-Demo")
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    live_balance = mt5_get_balance()
    if live_balance > 0:
        args.balance = live_balance
        print(f"  Using live account balance: ${live_balance:,.2f}")
    print()

    # ── Step 2: Fetch real historical data ────────────────────────
    print("[2/4] Fetching REAL historical data from MT5 ...")
    df = mt5_fetch_data(
        symbol=args.symbol,
        timeframe=args.timeframe,
        bars=args.bars,
    )

    if df is None or len(df) < 100:
        print()
        print("  FATAL: Not enough historical data.")
        print(f"  Requested {args.bars} bars of {args.symbol} ({args.timeframe})")
        print("  Check that the symbol is available in your MT5 terminal.")
        mt5_disconnect()
        input("\n  Press Enter to exit ...")
        sys.exit(1)

    print(f"  Got {len(df)} bars of real market data.")
    print()

    # ── Step 3: Calibrate on real data (with proper train/test split) ─
    #  Use first 70% for calibration (in-sample), last 30% for validation (out-of-sample)
    train_size = int(len(df) * 0.70)
    df_train = df.iloc[:train_size].copy()
    df_test = df.iloc[train_size:].copy()

    print("[3/4] Calibrating strategy on REAL historical data ...")
    print(f"      Train set: {len(df_train)} bars ({df_train.index[0]} to {df_train.index[-1]})")
    print(f"      Test set:  {len(df_test)} bars ({df_test.index[0]} to {df_test.index[-1]})")
    print(f"      Target: {args.target}% return | Max rounds: {MAX_CALIBRATION_ROUNDS}")
    print(f"      Balance: ${args.balance:,.2f} -> Goal: ${args.balance * (1 + args.target / 100):,.2f}")
    print("-" * 70)

    params = default_params()
    params["INITIAL_BALANCE"] = args.balance
    params["PROFIT_TARGET_PCT"] = args.target

    result = calibrate(df_train, params=params, verbose=True)

    # Out-of-sample validation on unseen test data
    print()
    print("  OUT-OF-SAMPLE validation on unseen test data ...")
    validation_results = []
    cal_params = result["best_params"]

    oos_metrics = run_backtest(df_test, cal_params)
    validation_results.append(oos_metrics)
    oos_status = "PASS" if oos_metrics["total_return_pct"] > 0 else "FAIL"
    print(
        f"      OOS Test: {oos_metrics['total_return_pct']:>9.1f}% return  |  "
        f"VolWon/Trade: ${oos_metrics['avg_volume_won_per_trade']:>8.2f}  |  "
        f"Trades: {oos_metrics['total_trades']}  |  WR: {oos_metrics['win_rate_pct']:.1f}%  |  "
        f"DD: {oos_metrics['max_drawdown_pct']:.1f}%  |  {oos_status}"
    )

    # Also validate on rolling windows of the test set
    total_test_bars = len(df_test)
    chunk = total_test_bars // 3
    if chunk >= 100:
        for i in range(3):
            start = i * chunk
            end = min(start + chunk, total_test_bars)
            df_val = df_test.iloc[start:end].copy()
            val_metrics = run_backtest(df_val, cal_params)
            validation_results.append(val_metrics)
            status = "PASS" if val_metrics["total_return_pct"] > 0 else "----"
            print(
                f"      OOS Window {i+1}: {val_metrics['total_return_pct']:>9.1f}% return  |  "
                f"VolWon/Trade: ${val_metrics['avg_volume_won_per_trade']:>8.2f}  |  "
                f"Trades: {val_metrics['total_trades']}  |  {status}"
            )
    else:
        print("      (Not enough test bars for window validation)")

    # Warn if OOS performance severely degrades vs in-sample
    in_sample_ret = result["best_metrics"]["total_return_pct"]
    oos_ret = oos_metrics["total_return_pct"]
    if in_sample_ret > 0 and oos_ret < in_sample_ret * 0.2:
        print()
        print("  WARNING: Out-of-sample return is <20% of in-sample return.")
        print(f"           In-sample: {in_sample_ret:.1f}%  |  Out-of-sample: {oos_ret:.1f}%")
        print("           This suggests the parameters are OVERFIT to training data.")
        print("           Live performance is likely to disappoint.")

    # ── Step 4: Final Report ──────────────────────────────────────
    print()
    print("[4/4] Final Report")
    print("=" * 70)
    m = result["best_metrics"]
    p = result["best_params"]

    if result["target_met"]:
        print(f"  STATUS:               TARGET MET")
    else:
        print(f"  STATUS:               BEST EFFORT (target not met)")

    print(f"  Data source:          MT5 real historical ({args.symbol})")
    print(f"  Total Return:         {m['total_return_pct']:,.1f}%")
    print(f"  Final Balance:        ${m['final_balance']:,.2f}  (from ${m['initial_balance']:,.2f})")
    print(f"  Total Trades:         {m['total_trades']}")
    print(f"  Winners:              {m['winners']}  |  Losers: {m['losers']}")
    print(f"  Win Rate:             {m['win_rate_pct']:.1f}%  (NOT our focus)")
    print(f"  Avg Win:              ${m['avg_win']:,.2f}")
    print(f"  Avg Loss:             ${m['avg_loss']:,.2f}")
    print(f"  -------------------------------------------------------")
    print(f"  AVG VOLUME WON/TRADE: ${m['avg_volume_won_per_trade']:,.2f}  << PRIMARY METRIC")
    print(f"  TOTAL VOLUME WON:     ${m['total_volume_won']:,.2f}")
    print(f"  -------------------------------------------------------")
    print(f"  Profit Factor:        {m['profit_factor']:.2f}")
    print(f"  Max Drawdown:         {m['max_drawdown_pct']:.1f}%")
    print(f"  Calibration Rounds:   {result['rounds_run']}")
    print()
    print(f"  OUT-OF-SAMPLE (unseen data):")
    print(f"    OOS Return:         {oos_metrics['total_return_pct']:.1f}%")
    print(f"    OOS Win Rate:       {oos_metrics['win_rate_pct']:.1f}%")
    print(f"    OOS Max Drawdown:   {oos_metrics['max_drawdown_pct']:.1f}%")
    print(f"    OOS Trades:         {oos_metrics['total_trades']}")
    print()
    print("  Calibrated Parameters:")
    display_keys = sorted(
        k for k in p
        if k not in ("INITIAL_BALANCE", "PROFIT_TARGET_PCT", "MIN_POSITION_SIZE_PCT")
    )
    for k in display_keys:
        print(f"    {k:<30s} = {p[k]}")
    print("=" * 70)

    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "mode": args.mode, "symbol": args.symbol,
        "timeframe": args.timeframe, "data_source": "MT5 real historical",
        "bars_used": len(df), "target_met": result["target_met"],
        "calibrated_params": {k: v for k, v in p.items()},
        "metrics": {k: v for k, v in m.items() if k not in ("equity_curve", "trades")},
        "validation": [
            {k: v for k, v in vm.items() if k not in ("equity_curve", "trades")}
            for vm in validation_results
        ],
        "rounds_run": result["rounds_run"],
    }
    results_path = os.path.join(SCRIPT_DIR, "calibration_results.json")
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to calibration_results.json")

    # ── Decision: Go Live or Stay ─────────────────────────────────
    # Require positive OOS return before going live
    oos_positive = oos_metrics["total_return_pct"] > 0
    if not oos_positive and result["target_met"]:
        print()
        print("  SAFETY: Target met in-sample but OUT-OF-SAMPLE return is NEGATIVE.")
        print("          Refusing to go live — parameters are likely overfit.")
        print("          Try with more --bars or a different --timeframe.")
        result["target_met"] = False

    if result["target_met"] and args.mode == "live":
        print()
        print("*" * 70)
        print("  TARGET ACHIEVED ON REAL DATA - GOING LIVE NOW")
        print("*" * 70)
        print()

        run_live(
            symbol=args.symbol, timeframe=args.timeframe,
            params=cal_params,
            max_daily_loss_pct=args.max_daily_loss,
            check_interval_seconds=args.check_interval,
        )
        mt5_disconnect()

    elif result["target_met"] and args.mode == "backtest":
        print(f"\n  Backtest mode - target met but NOT going live.")
        print(f"  To go live: python trading_bot.py --mode live")
        mt5_disconnect()

    elif not result["target_met"]:
        print(f"\n  Target not reached on real data.")
        print(f"  Try: more --bars, different --timeframe, or different --symbol")
        mt5_disconnect()
        input("\n  Press Enter to exit ...")
        sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Trading Bot - One-Click: Real MT5 Data Backtest to Live"
    )
    parser.add_argument("--mode", type=str, default="live", choices=["live", "backtest"],
                        help="live = backtest then go live | backtest = backtest only")
    parser.add_argument("--login", type=int, default=None, help="MT5 account number")
    parser.add_argument("--password", type=str, default=None, help="MT5 account password")
    parser.add_argument("--server", type=str, default=None, help="MT5 server (e.g. Deriv-Demo)")
    parser.add_argument("--mt5-path", type=str, default=None, help="Path to terminal64.exe")
    parser.add_argument("--symbol", type=str, default=MT5_SYMBOL, help="Trading symbol")
    parser.add_argument("--timeframe", type=str, default=MT5_TIMEFRAME, help="Candle timeframe")
    parser.add_argument("--bars", type=int, default=MT5_BARS, help="Historical bars to fetch")
    parser.add_argument("--balance", type=float, default=INITIAL_BALANCE, help="Starting balance ($)")
    parser.add_argument("--target", type=float, default=PROFIT_TARGET_PCT, help="Profit target (%%)")
    parser.add_argument("--max-daily-loss", type=float, default=10.0, help="Max daily loss %% for live")
    parser.add_argument("--check-interval", type=int, default=60, help="Seconds between live checks")
    return parser.parse_args()


if __name__ == "__main__":
    main()
