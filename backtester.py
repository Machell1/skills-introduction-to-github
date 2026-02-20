"""
Backtesting Engine
───────────────────
Simulates trades bar-by-bar with:
  • Long AND short positions
  • Aggressive compounding position sizing (volume-won focus)
  • ATR-based trailing stop losses
  • Wide take-profit targets (let winners run)
  • Full equity compounding — winners grow the account exponentially
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from strategy import generate_signals


class Trade:
    __slots__ = (
        "entry_bar", "entry_price", "direction", "size", "stop",
        "take_profit", "trail_stop", "exit_bar", "exit_price", "pnl",
    )

    def __init__(
        self,
        entry_bar: int,
        entry_price: float,
        direction: int,
        size: float,
        stop: float,
        take_profit: float,
    ):
        self.entry_bar = entry_bar
        self.entry_price = entry_price
        self.direction = direction  # +1 long, -1 short
        self.size = size
        self.stop = stop
        self.take_profit = take_profit
        self.trail_stop = stop
        self.exit_bar: int | None = None
        self.exit_price: float | None = None
        self.pnl: float | None = None


def run_backtest(df: pd.DataFrame, params: dict) -> dict:
    """
    Execute the strategy on `df` and return performance metrics.
    Supports both long (+1) and short (-1) trades.
    Position sizes compound with equity growth.
    """
    signals = generate_signals(df, params)
    signals = signals.dropna().reset_index(drop=True)

    balance = params["INITIAL_BALANCE"]
    peak_balance = balance
    max_drawdown = 0.0
    equity_curve = [balance]
    trades: list[Trade] = []
    open_trade: Trade | None = None

    trail_mult = params["TRAILING_STOP_ATR_MULT"]
    tp_mult = params["TAKE_PROFIT_ATR_MULT"]

    for i in range(1, len(signals)):
        row = signals.iloc[i]

        # ── Manage open trade ────────────────────────────────────────
        if open_trade is not None:
            atr_now = row["atr"] if not np.isnan(row["atr"]) and row["atr"] > 0 else 0

            if open_trade.direction == 1:  # LONG
                # Update trailing stop (only tighten)
                if atr_now > 0:
                    new_trail = row["close"] - trail_mult * atr_now
                    if new_trail > open_trade.trail_stop:
                        open_trade.trail_stop = new_trail

                # Stop hit
                if row["low"] <= open_trade.trail_stop:
                    _close_trade(open_trade, i, max(open_trade.trail_stop, row["low"]))
                    balance += open_trade.pnl
                    balance = max(balance, 1.0)  # prevent going to zero
                    trades.append(open_trade)
                    open_trade = None
                # Take profit hit
                elif row["high"] >= open_trade.take_profit:
                    _close_trade(open_trade, i, open_trade.take_profit)
                    balance += open_trade.pnl
                    trades.append(open_trade)
                    open_trade = None

            elif open_trade.direction == -1:  # SHORT
                # Update trailing stop (only tighten — for shorts, stop moves DOWN)
                if atr_now > 0:
                    new_trail = row["close"] + trail_mult * atr_now
                    if new_trail < open_trade.trail_stop:
                        open_trade.trail_stop = new_trail

                # Stop hit (price goes UP past stop)
                if row["high"] >= open_trade.trail_stop:
                    _close_trade(open_trade, i, min(open_trade.trail_stop, row["high"]))
                    balance += open_trade.pnl
                    balance = max(balance, 1.0)
                    trades.append(open_trade)
                    open_trade = None
                # Take profit hit (price goes DOWN past TP)
                elif row["low"] <= open_trade.take_profit:
                    _close_trade(open_trade, i, open_trade.take_profit)
                    balance += open_trade.pnl
                    trades.append(open_trade)
                    open_trade = None

        # ── New entry signal (only if flat) ──────────────────────────
        if open_trade is None and row["signal"] != 0:
            atr = row["atr"]
            if atr <= 0 or np.isnan(atr):
                equity_curve.append(balance)
                continue

            entry_price = row["close"]
            direction = int(row["signal"])  # +1 or -1

            if direction == 1:  # LONG
                stop_price = entry_price - trail_mult * atr
                tp_price = entry_price + tp_mult * atr
                risk_per_unit = entry_price - stop_price
            else:  # SHORT
                stop_price = entry_price + trail_mult * atr
                tp_price = entry_price - tp_mult * atr
                risk_per_unit = stop_price - entry_price

            if risk_per_unit <= 0:
                equity_curve.append(balance)
                continue

            # Position sizing: risk a fixed % of CURRENT equity (compounding)
            dollar_risk = balance * (params["RISK_PER_TRADE_PCT"] / 100.0)
            units = dollar_risk / risk_per_unit
            position_value = units * entry_price

            # Clamp position size
            max_val = balance * (params["MAX_POSITION_SIZE_PCT"] / 100.0)
            min_val = balance * (params["MIN_POSITION_SIZE_PCT"] / 100.0)
            if position_value > max_val:
                units = max_val / entry_price
            if position_value < min_val:
                equity_curve.append(balance)
                continue

            open_trade = Trade(
                entry_bar=i,
                entry_price=entry_price,
                direction=direction,
                size=units,
                stop=stop_price,
                take_profit=tp_price,
            )

        # Track equity
        if open_trade is not None:
            unrealised = (row["close"] - open_trade.entry_price) * open_trade.size * open_trade.direction
            equity_curve.append(balance + unrealised)
        else:
            equity_curve.append(balance)

        # Drawdown tracking
        if equity_curve[-1] > peak_balance:
            peak_balance = equity_curve[-1]
        dd = (peak_balance - equity_curve[-1]) / peak_balance * 100 if peak_balance > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

    # Close any remaining trade at last bar
    if open_trade is not None:
        _close_trade(open_trade, len(signals) - 1, signals.iloc[-1]["close"])
        balance += open_trade.pnl
        trades.append(open_trade)
        equity_curve[-1] = balance

    return _compile_metrics(trades, equity_curve, params["INITIAL_BALANCE"], max_drawdown)


def _close_trade(trade: Trade, bar: int, price: float) -> None:
    trade.exit_bar = bar
    trade.exit_price = price
    trade.pnl = (price - trade.entry_price) * trade.size * trade.direction


def _compile_metrics(
    trades: list[Trade],
    equity_curve: list[float],
    initial_balance: float,
    max_drawdown: float,
) -> dict:
    final = equity_curve[-1] if equity_curve else initial_balance
    total_return = (final - initial_balance) / initial_balance * 100

    winners = [t for t in trades if t.pnl and t.pnl > 0]
    losers = [t for t in trades if t.pnl and t.pnl <= 0]

    avg_win = float(np.mean([t.pnl for t in winners])) if winners else 0.0
    avg_loss = float(np.mean([abs(t.pnl) for t in losers])) if losers else 0.0

    gross_profit = sum(t.pnl for t in winners) if winners else 0.0
    gross_loss = sum(abs(t.pnl) for t in losers) if losers else 1.0

    # Volume won per trade: the key metric we optimise for
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
