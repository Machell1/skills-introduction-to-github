"""
Live Trading Engine
--------------------
Runs the calibrated strategy in real-time on MT5/Deriv.

Workflow:
  1. Receives calibrated params from backtesting
  2. Connects to MT5 and monitors price bars
  3. Generates signals using the same strategy as backtesting
  4. Executes trades with proper position sizing, SL, and TP
  5. Manages open positions (trailing stops)

Safety features:
  - Max daily loss limit
  - Max concurrent positions = 1 (same as backtest)
  - Logs every action
"""

from __future__ import annotations

import time
import json
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

import mt5_connector as mt5c
from strategy import compute_indicators, generate_signals


def run_live(
    symbol: str,
    timeframe: str,
    params: dict,
    max_daily_loss_pct: float = 10.0,
    check_interval_seconds: int = 60,
) -> None:
    """
    Run the trading bot live on MT5.

    Parameters
    ----------
    symbol : str
        MT5 symbol to trade (e.g. "Volatility 75 Index")
    timeframe : str
        Candle timeframe (M1, M5, M15, M30, H1, H4, D1)
    params : dict
        Calibrated strategy parameters from backtesting
    max_daily_loss_pct : float
        Stop trading if daily loss exceeds this % of starting balance
    check_interval_seconds : int
        How often to check for new bars (seconds)
    """
    print()
    print("=" * 70)
    print("  LIVE TRADING MODE")
    print("=" * 70)

    # Get starting balance
    account = mt5c.get_account_info()
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

    # Get symbol info for lot sizing
    sym_info = mt5c.get_symbol_info(symbol)
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
    open_entry_price = 0.0
    open_trail_stop = 0.0
    last_bar_time = None
    trade_count = 0

    print("  Monitoring for signals ... (Ctrl+C to stop)")
    print("-" * 70)

    try:
        while True:
            # Fetch recent bars for signal generation
            lookback_bars = max(100, int(params["LOOKBACK_PERIOD"]) * 4)
            df = mt5c.fetch_historical_data(symbol, timeframe, bars=lookback_bars)

            if df is None or len(df) < int(params["LOOKBACK_PERIOD"]) * 2:
                print(f"  [{_now()}] Waiting for data ...")
                time.sleep(check_interval_seconds)
                continue

            current_bar_time = df.index[-1]

            # Only act on new bars
            if last_bar_time is not None and current_bar_time <= last_bar_time:
                time.sleep(check_interval_seconds)
                continue

            last_bar_time = current_bar_time

            # Generate signals on the latest data
            signals = generate_signals(df, params)
            signals = signals.dropna()

            if len(signals) == 0:
                time.sleep(check_interval_seconds)
                continue

            latest = signals.iloc[-1]
            atr = latest["atr"] if not np.isnan(latest["atr"]) else 0

            # Check daily loss limit
            current_balance = mt5c.get_account_balance()
            daily_pnl = current_balance - start_balance
            if daily_pnl < -daily_loss_limit:
                print(f"  [{_now()}] DAILY LOSS LIMIT HIT: ${daily_pnl:,.2f}")
                print("  Stopping live trading for today.")
                _close_if_open(open_ticket)
                break

            # ── Manage open position ──────────────────────────────────
            if open_ticket is not None:
                positions = mt5c.get_open_positions(symbol)
                pos = None
                for p in positions:
                    if p["ticket"] == open_ticket:
                        pos = p
                        break

                if pos is None:
                    # Position was closed (hit SL or TP on server side)
                    print(f"  [{_now()}] Position {open_ticket} closed externally")
                    open_ticket = None
                    open_direction = 0
                elif atr > 0:
                    # Update trailing stop
                    close_price = latest["close"]
                    if open_direction == 1:  # LONG
                        new_trail = close_price - trail_mult * atr
                        if new_trail > open_trail_stop:
                            open_trail_stop = new_trail
                            mt5c.modify_position(open_ticket, sl=open_trail_stop)
                            print(f"  [{_now()}] Trail stop updated: {open_trail_stop:.5f}")
                    elif open_direction == -1:  # SHORT
                        new_trail = close_price + trail_mult * atr
                        if new_trail < open_trail_stop:
                            open_trail_stop = new_trail
                            mt5c.modify_position(open_ticket, sl=open_trail_stop)
                            print(f"  [{_now()}] Trail stop updated: {open_trail_stop:.5f}")

            # ── New entry signal (only if flat) ───────────────────────
            if open_ticket is None and latest["signal"] != 0 and atr > 0:
                direction = int(latest["signal"])
                entry_price = latest["close"]

                if direction == 1:  # LONG
                    sl_price = entry_price - trail_mult * atr
                    tp_price = entry_price + tp_mult * atr
                    risk_per_unit = entry_price - sl_price
                else:  # SHORT
                    sl_price = entry_price + trail_mult * atr
                    tp_price = entry_price - tp_mult * atr
                    risk_per_unit = sl_price - entry_price

                if risk_per_unit <= 0:
                    time.sleep(check_interval_seconds)
                    continue

                # Position sizing (same logic as backtester)
                balance = mt5c.get_account_balance()
                dollar_risk = balance * (params["RISK_PER_TRADE_PCT"] / 100.0)
                units = dollar_risk / risk_per_unit

                # Convert units to lots
                contract_size = sym_info["trade_contract_size"]
                lots = units / contract_size if contract_size > 0 else units

                # Clamp
                position_value = units * entry_price
                max_val = balance * (params["MAX_POSITION_SIZE_PCT"] / 100.0)
                min_val = balance * (params["MIN_POSITION_SIZE_PCT"] / 100.0)

                if position_value > max_val:
                    lots = (max_val / entry_price) / contract_size if contract_size > 0 else max_val / entry_price
                if position_value < min_val:
                    time.sleep(check_interval_seconds)
                    continue

                print(f"\n  [{_now()}] SIGNAL: {'BUY' if direction == 1 else 'SELL'}")
                print(f"    Price:  {entry_price:.5f}")
                print(f"    ATR:    {atr:.5f}")
                print(f"    SL:     {sl_price:.5f}")
                print(f"    TP:     {tp_price:.5f}")
                print(f"    Lots:   {lots:.2f}")

                result = mt5c.place_market_order(
                    symbol=symbol,
                    direction=direction,
                    volume=lots,
                    sl=sl_price,
                    tp=tp_price,
                    comment=f"Bot-{trade_count + 1}",
                )

                if result:
                    open_ticket = result["ticket"]
                    open_direction = direction
                    open_entry_price = result["price"]
                    open_trail_stop = sl_price
                    trade_count += 1
                    print(f"    Trade #{trade_count} opened: ticket {open_ticket}")
                else:
                    print(f"    Order failed - will retry on next signal")

            # Log status periodically
            if trade_count > 0 or open_ticket is not None:
                bal = mt5c.get_account_balance()
                pnl = bal - start_balance
                print(f"  [{_now()}] Balance: ${bal:,.2f} | "
                      f"PnL: ${pnl:+,.2f} | "
                      f"Trades: {trade_count} | "
                      f"{'IN TRADE' if open_ticket else 'FLAT'}")

            time.sleep(check_interval_seconds)

    except KeyboardInterrupt:
        print(f"\n  [{_now()}] Stopping live trading (Ctrl+C) ...")
        _close_if_open(open_ticket)

    # Final report
    final_balance = mt5c.get_account_balance()
    total_pnl = final_balance - start_balance
    print()
    print("=" * 70)
    print("  LIVE TRADING SESSION ENDED")
    print(f"  Start balance:  ${start_balance:,.2f}")
    print(f"  Final balance:  ${final_balance:,.2f}")
    print(f"  Total PnL:      ${total_pnl:+,.2f} ({total_pnl / start_balance * 100:+.1f}%)")
    print(f"  Trades taken:   {trade_count}")
    print("=" * 70)


def _close_if_open(ticket: Optional[int]) -> None:
    """Close a position if it exists."""
    if ticket is not None:
        print(f"  Closing open position {ticket} ...")
        mt5c.close_position(ticket)


def _now() -> str:
    """Return current time as a string."""
    return datetime.now().strftime("%H:%M:%S")
