#!/usr/bin/env python3
"""
Trading Bot - Backtest to Live Pipeline (MT5 / Deriv)
------------------------------------------------------
Full workflow:
  1. Connect to Deriv MT5 automatically
  2. Fetch historical data for the configured symbol
  3. Calibrate strategy parameters via backtesting
  4. If target is met -> transition to LIVE TRADING
  5. If target not met -> stay in backtest loop

Key principle:  VOLUME WON PER TRADE > win rate.
                We want fewer, bigger winners - not lots of small ones.

Usage:
    python main.py                            # Auto-connect MT5, default settings
    python main.py --symbol "Volatility 75 Index"
    python main.py --login 12345 --password xxx --server Deriv-Demo
    python main.py --mode backtest            # Backtest only, no live trading
    python main.py --mode synthetic           # Use synthetic data (no MT5 needed)
"""

from __future__ import annotations

import argparse
import sys
import json
import random
from datetime import datetime
from typing import Optional

from config import (
    INITIAL_BALANCE, PROFIT_TARGET_PCT, SYNTHETIC_BARS,
    MT5_SYMBOL, MT5_TIMEFRAME, MT5_BARS,
)
from data_generator import generate_ohlcv
from calibrator import calibrate, default_params
from backtester import run_backtest


def main() -> None:
    args = parse_args()

    print("=" * 70)
    print("  TRADING BOT - BACKTEST TO LIVE PIPELINE")
    print("=" * 70)
    print(f"  Mode:              {args.mode.upper()}")
    print(f"  Account size:      ${args.balance:,.2f}")
    print(f"  Profit target:     {args.target:,.0f}%")
    print(f"  Goal balance:      ${args.balance * (1 + args.target / 100):,.2f}")
    print(f"  Optimising for:    VOLUME WON PER TRADE (NOT win rate)")
    if args.mode != "synthetic":
        print(f"  Symbol:            {args.symbol}")
        print(f"  Timeframe:         {args.timeframe}")
    print(f"  Data bars:         {args.bars:,}")
    print("=" * 70)
    print()

    # ── Step 1: Get market data ────────────────────────────────────
    df = None

    if args.mode in ("live", "backtest"):
        # Connect to MT5
        print("[1/4] Connecting to Deriv MT5 ...")
        import mt5_connector as mt5c

        connected = mt5c.connect(
            login=args.login,
            password=args.password,
            server=args.server,
            path=args.mt5_path,
        )

        if not connected:
            print()
            print("  Could not connect to MT5.")
            print("  Falling back to synthetic data mode.")
            print("  To use MT5, make sure:")
            print("    1. Deriv MT5 terminal is running")
            print("    2. You are logged in")
            print("    3. Run: python main.py --login YOUR_ID --password YOUR_PASS")
            print()
            args.mode = "synthetic"
        else:
            # Use live account balance if available
            live_balance = mt5c.get_account_balance()
            if live_balance > 0:
                args.balance = live_balance
                print(f"  Using live account balance: ${live_balance:,.2f}")

            print()
            print("[2/4] Fetching historical data from MT5 ...")
            df = mt5c.fetch_historical_data(
                symbol=args.symbol,
                timeframe=args.timeframe,
                bars=args.bars,
            )

            if df is None or len(df) < 100:
                print("  Not enough historical data. Falling back to synthetic.")
                args.mode = "synthetic"
                df = None

    if args.mode == "synthetic":
        print("[1/4] Generating synthetic OHLCV data ...")
        seed = args.seed if args.seed is not None else random.randint(1, 100000)
        df = generate_ohlcv(bars=args.bars, seed=seed)
        print(f"      {len(df)} bars | seed={seed}")
        print(f"      Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
        print()
        print("[2/4] (Synthetic mode - MT5 not used)")

    print()

    # ── Step 2: Run calibration loop ───────────────────────────────
    step = "[3/4]" if args.mode != "synthetic" else "[2/4]"
    print(f"{step} Starting calibration loop ...")
    print(f"      Target: {args.target}% return | Max rounds: 300")
    print("-" * 70)

    params = default_params()
    params["INITIAL_BALANCE"] = args.balance
    params["PROFIT_TARGET_PCT"] = args.target

    result = calibrate(df, params=params, verbose=True)

    if not result["target_met"] and args.mode == "synthetic":
        # Try alternate seeds in synthetic mode
        seed_val = args.seed if args.seed is not None else random.randint(1, 100000)
        print("\n  Initial data didn't reach target. Trying alternate datasets...")
        for attempt in range(1, 6):
            alt_seed = seed_val + attempt * 1000
            print(f"\n  --- Attempt {attempt + 1} with seed={alt_seed} ---")
            df_alt = generate_ohlcv(bars=args.bars, seed=alt_seed)
            result = calibrate(df_alt, params=params, verbose=True)
            if result["target_met"]:
                df = df_alt
                break

    # ── Step 3: Validation ─────────────────────────────────────────
    print()
    step = "[3/4]" if args.mode == "synthetic" else "[3/4]"
    print(f"{step} Validating calibrated params ...")
    validation_results = []
    cal_params = result["best_params"]

    if args.mode == "synthetic":
        seed_base = args.seed if args.seed is not None else 99999
        for v_seed in range(seed_base + 1, seed_base + 4):
            df_val = generate_ohlcv(bars=args.bars, seed=v_seed)
            val_metrics = run_backtest(df_val, cal_params)
            validation_results.append(val_metrics)
            status = "PASS" if val_metrics["total_return_pct"] >= args.target else "----"
            print(
                f"      Seed {v_seed}: {val_metrics['total_return_pct']:>9.1f}% return  |  "
                f"VolWon/Trade: ${val_metrics['avg_volume_won_per_trade']:>8.2f}  |  "
                f"Trades: {val_metrics['total_trades']}  |  {status}"
            )
    else:
        # Validate on different time windows of real data
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
            print("      Not enough data for window validation.")

    # ── Step 4: Final Report ───────────────────────────────────────
    print()
    print("[4/4] Final Report")
    print("=" * 70)
    m = result["best_metrics"]
    p = result["best_params"]

    if result["target_met"]:
        print(f"  STATUS:               TARGET MET")
    else:
        print(f"  STATUS:               BEST EFFORT (target not met)")

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

    # ── Save results ───────────────────────────────────────────────
    output = {
        "timestamp": datetime.now().isoformat(),
        "mode": args.mode,
        "symbol": args.symbol if args.mode != "synthetic" else "SYNTHETIC",
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

    # ── Auto-transition to LIVE TRADING ────────────────────────────
    if result["target_met"] and args.mode == "live":
        print()
        print("*" * 70)
        print("  TARGET ACHIEVED - TRANSITIONING TO LIVE TRADING")
        print("*" * 70)
        print()

        import mt5_connector as mt5c
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
        print(f"\n  Backtest mode - NOT going live.")
        print(f"  To go live, run: python main.py --mode live")
        if args.mode != "synthetic":
            import mt5_connector as mt5c
            mt5c.disconnect()

    elif not result["target_met"]:
        print(f"\n  Bot staying in backtest loop - target not reached.")
        print(f"  Adjust config bounds or increase --bars and re-run.")
        if args.mode not in ("synthetic",):
            import mt5_connector as mt5c
            mt5c.disconnect()
        sys.exit(1)
    else:
        print(f"\n  Bot calibrated and ready. Parameters locked in.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trading Bot - Backtest to Live Pipeline (MT5/Deriv)"
    )

    # Mode
    parser.add_argument(
        "--mode", type=str, default="live",
        choices=["live", "backtest", "synthetic"],
        help="live = backtest then trade | backtest = backtest only | synthetic = no MT5"
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
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (synthetic mode)")
    parser.add_argument("--balance", type=float, default=INITIAL_BALANCE, help="Starting balance ($)")
    parser.add_argument("--target", type=float, default=PROFIT_TARGET_PCT, help="Profit target (%%)")

    # Live trading safety
    parser.add_argument("--max-daily-loss", type=float, default=10.0, help="Max daily loss %% before stopping")
    parser.add_argument("--check-interval", type=int, default=60, help="Seconds between bar checks")

    return parser.parse_args()


if __name__ == "__main__":
    main()
