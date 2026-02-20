#!/usr/bin/env python3
"""
Trading Bot - Backtest on Real MT5 Data, Then Go Live (Deriv)
--------------------------------------------------------------
Full workflow:
  1. Connect to Deriv MT5 automatically
  2. Fetch REAL historical data for the configured symbol
  3. Calibrate strategy parameters via backtesting on that data
  4. If target is met -> transition to LIVE TRADING automatically
  5. If target not met -> stay in backtest loop

NO synthetic data. All backtesting uses real market history from MT5.

Usage:
    python main.py                                          # default
    python main.py --symbol "Volatility 75 Index" --timeframe H1
    python main.py --login 12345 --password xxx --server Deriv-Demo
    python main.py --mode backtest                          # no live transition
"""

from __future__ import annotations

import argparse
import sys
import json
from datetime import datetime

from config import (
    INITIAL_BALANCE, PROFIT_TARGET_PCT,
    MT5_SYMBOL, MT5_TIMEFRAME, MT5_BARS,
)
from calibrator import calibrate, default_params
from backtester import run_backtest
import mt5_connector as mt5c


def main() -> None:
    args = parse_args()

    print("=" * 70)
    print("  TRADING BOT - REAL DATA BACKTEST TO LIVE (MT5 / Deriv)")
    print("=" * 70)
    print(f"  Mode:              {args.mode.upper()}")
    print(f"  Symbol:            {args.symbol}")
    print(f"  Timeframe:         {args.timeframe}")
    print(f"  Historical bars:   {args.bars:,}")
    print(f"  Profit target:     {args.target:,.0f}%")
    print(f"  Optimising for:    VOLUME WON PER TRADE (NOT win rate)")
    print("=" * 70)
    print()

    # ── Step 1: Connect to Deriv MT5 ─────────────────────────────
    print("[1/4] Connecting to Deriv MT5 ...")

    if not mt5c.check_mt5_available():
        print()
        print("  FATAL: MetaTrader5 package is required.")
        print("  Install it:  pip install MetaTrader5")
        print("  Requires:    Python 3.9-3.12 on Windows")
        sys.exit(1)

    connected = mt5c.connect(
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
        print("       python main.py --login YOUR_ID --password YOUR_PASS --server Deriv-Demo")
        sys.exit(1)

    # Use live account balance
    live_balance = mt5c.get_account_balance()
    if live_balance > 0:
        args.balance = live_balance
        print(f"  Using live account balance: ${live_balance:,.2f}")

    print()

    # ── Step 2: Fetch real historical data ────────────────────────
    print("[2/4] Fetching real historical data from MT5 ...")
    df = mt5c.fetch_historical_data(
        symbol=args.symbol,
        timeframe=args.timeframe,
        bars=args.bars,
    )

    if df is None or len(df) < 100:
        print()
        print("  FATAL: Not enough historical data returned.")
        print(f"  Requested {args.bars} bars of {args.symbol} ({args.timeframe})")
        print("  Check that the symbol is available in your MT5 terminal.")
        mt5c.disconnect()
        sys.exit(1)

    print(f"  Got {len(df)} bars of real market data.")
    print()

    # ── Step 3: Calibrate on real historical data ─────────────────
    print("[3/4] Calibrating strategy on REAL historical data ...")
    print(f"      Target: {args.target}% return | Max rounds: 300")
    print(f"      Balance: ${args.balance:,.2f} -> Goal: ${args.balance * (1 + args.target / 100):,.2f}")
    print("-" * 70)

    params = default_params()
    params["INITIAL_BALANCE"] = args.balance
    params["PROFIT_TARGET_PCT"] = args.target

    result = calibrate(df, params=params, verbose=True)

    # ── Validate on different time windows of the real data ───────
    print()
    print("  Validating on time windows of real data ...")
    validation_results = []
    cal_params = result["best_params"]

    total_bars = len(df)
    chunk = total_bars // 4
    if chunk >= 200:
        for i in range(3):
            start = i * chunk
            end = start + chunk
            df_val = df.iloc[start:end].copy()
            val_metrics = run_backtest(df_val, cal_params)
            validation_results.append(val_metrics)
            status = "PASS" if val_metrics["total_return_pct"] >= args.target else "----"
            print(
                f"      Window {i+1}: {val_metrics['total_return_pct']:>9.1f}% return  |  "
                f"VolWon/Trade: ${val_metrics['avg_volume_won_per_trade']:>8.2f}  |  "
                f"Trades: {val_metrics['total_trades']}  |  {status}"
            )
    else:
        print("      (Not enough bars for window validation)")

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
    print("  Calibrated Parameters:")
    display_keys = sorted(
        k for k in p
        if k not in ("INITIAL_BALANCE", "PROFIT_TARGET_PCT", "MIN_POSITION_SIZE_PCT")
    )
    for k in display_keys:
        print(f"    {k:<30s} = {p[k]}")

    print("=" * 70)

    # ── Save results ──────────────────────────────────────────────
    output = {
        "timestamp": datetime.now().isoformat(),
        "mode": args.mode,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "data_source": "MT5 real historical",
        "bars_used": len(df),
        "target_met": result["target_met"],
        "calibrated_params": {k: v for k, v in p.items()},
        "metrics": {k: v for k, v in m.items() if k not in ("equity_curve", "trades")},
        "validation": [
            {k: v for k, v in vm.items() if k not in ("equity_curve", "trades")}
            for vm in validation_results
        ],
        "rounds_run": result["rounds_run"],
    }
    with open("calibration_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to calibration_results.json")

    # ── Decision: Go Live or Stay in Backtest ─────────────────────
    if result["target_met"] and args.mode == "live":
        print()
        print("*" * 70)
        print("  TARGET ACHIEVED ON REAL DATA - GOING LIVE NOW")
        print("*" * 70)
        print()

        from live_trader import run_live

        run_live(
            symbol=args.symbol,
            timeframe=args.timeframe,
            params=cal_params,
            max_daily_loss_pct=args.max_daily_loss,
            check_interval_seconds=args.check_interval,
        )

        mt5c.disconnect()

    elif result["target_met"] and args.mode == "backtest":
        print(f"\n  Backtest mode - target met but NOT going live.")
        print(f"  To go live: python main.py --mode live")
        mt5c.disconnect()

    elif not result["target_met"]:
        print(f"\n  Target not reached on real data.")
        print(f"  Try: more --bars, different --timeframe, or different --symbol")
        mt5c.disconnect()
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trading Bot - Real MT5 Data Backtest to Live (Deriv)"
    )

    # Mode
    parser.add_argument(
        "--mode", type=str, default="live",
        choices=["live", "backtest"],
        help="live = backtest on real data then go live | backtest = backtest only"
    )

    # MT5 connection
    parser.add_argument("--login", type=int, default=None, help="MT5 account number")
    parser.add_argument("--password", type=str, default=None, help="MT5 account password")
    parser.add_argument("--server", type=str, default=None, help="MT5 server (e.g. Deriv-Demo)")
    parser.add_argument("--mt5-path", type=str, default=None, help="Path to terminal64.exe")

    # Trading settings
    parser.add_argument("--symbol", type=str, default=MT5_SYMBOL, help="MT5 trading symbol")
    parser.add_argument("--timeframe", type=str, default=MT5_TIMEFRAME, help="Candle timeframe")
    parser.add_argument("--bars", type=int, default=MT5_BARS, help="Number of historical bars")

    # Calibration
    parser.add_argument("--balance", type=float, default=INITIAL_BALANCE, help="Starting balance ($)")
    parser.add_argument("--target", type=float, default=PROFIT_TARGET_PCT, help="Profit target (%%)")

    # Live trading safety
    parser.add_argument("--max-daily-loss", type=float, default=10.0, help="Max daily loss %% before stopping")
    parser.add_argument("--check-interval", type=int, default=60, help="Seconds between bar checks")

    return parser.parse_args()


if __name__ == "__main__":
    main()
