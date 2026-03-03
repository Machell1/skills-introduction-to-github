#!/usr/bin/env python3
"""
Multi-Symbol Launcher for SMC Trading Bot.

Spawns one independent bot process per configured symbol.
All processes share the same MT5 account but use different magic numbers
(assigned automatically by the symbol profile system) for trade isolation.

Usage:
    python run_multi.py                              # All 6 default pairs
    python run_multi.py --symbols EURUSD GBPUSD      # Specific pairs only
    python run_multi.py --paper                      # All pairs, paper mode
    python run_multi.py --exclude GBPJPY EURJPY      # All except these
    python run_multi.py --symbols EURUSD --live       # Single pair, live
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DEFAULT_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURJPY"]

BANNER = r"""
 ╔══════════════════════════════════════════════════════════════╗
 ║     SMART MONEY CONCEPTS (SMC) — MULTI-PAIR LAUNCHER       ║
 ║                                                             ║
 ║  XAUUSD | EURUSD | GBPUSD | USDJPY | GBPJPY | EURJPY      ║
 ║                                                             ║
 ║  1H Timeframe  |  MT5  |  Deriv Broker                     ║
 ║  Each pair runs with its own ICT/SMC-tuned profile          ║
 ╚══════════════════════════════════════════════════════════════╝
"""


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Symbol SMC Bot Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--symbols", nargs="+", default=None,
        help=f"Symbols to trade (default: {' '.join(DEFAULT_SYMBOLS)})",
    )
    parser.add_argument(
        "--exclude", nargs="+", default=[],
        help="Symbols to exclude from the default list",
    )
    parser.add_argument(
        "--config", "-c",
        default=str(SCRIPT_DIR / "smart_money_bot" / "settings.json"),
        help="Base config file (shared MT5 credentials)",
    )
    parser.add_argument(
        "--paper", action="store_true",
        help="Force paper trading mode for all pairs",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Force live trading mode for all pairs",
    )
    parser.add_argument(
        "--stagger", type=int, default=5,
        help="Seconds between process launches (default: 5)",
    )
    parser.add_argument(
        "--log-level", default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level for all pairs",
    )

    args = parser.parse_args()
    symbols = args.symbols or [s for s in DEFAULT_SYMBOLS if s not in args.exclude]

    print(BANNER)
    mode_str = "PAPER" if args.paper else "LIVE" if args.live else "from config"
    print(f"  Pairs:   {', '.join(symbols)} ({len(symbols)} total)")
    print(f"  Config:  {args.config}")
    print(f"  Mode:    {mode_str}")
    print(f"  Stagger: {args.stagger}s between launches")
    print()

    # Confirm live mode
    if args.live:
        confirm = input("  CONFIRM: Launch ALL pairs in LIVE mode? (type YES): ").strip()
        if confirm != "YES":
            print("  Switching to paper mode for safety.")
            args.paper = True
            args.live = False

    processes: dict[str, subprocess.Popen] = {}
    run_bot_script = str(SCRIPT_DIR / "run_bot.py")

    # Launch each symbol as a subprocess
    for i, symbol in enumerate(symbols):
        cmd = [
            sys.executable, run_bot_script,
            "--config", args.config,
            "--symbol", symbol,
        ]
        if args.paper:
            cmd.append("--paper")
        elif args.live:
            cmd.append("--live")
        if args.log_level:
            cmd.extend(["--log-level", args.log_level])

        proc = subprocess.Popen(cmd, cwd=str(SCRIPT_DIR))
        processes[symbol] = proc
        print(f"  [{symbol}] Started (PID {proc.pid})")

        # Stagger launches to avoid MT5 initialization race
        if i < len(symbols) - 1:
            time.sleep(args.stagger)

    print(f"\n  All {len(processes)} bots running. Press Ctrl+C to stop all.\n")

    # Graceful shutdown handler
    shutting_down = False

    def shutdown(signum=None, frame=None):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        print("\n  Shutting down all bots...")
        for sym, proc in processes.items():
            if proc.poll() is None:
                try:
                    proc.terminate()
                    print(f"  [{sym}] SIGTERM sent (PID {proc.pid})")
                except OSError:
                    pass
        # Wait for graceful shutdown
        for sym, proc in processes.items():
            try:
                proc.wait(timeout=30)
                print(f"  [{sym}] Stopped (exit code {proc.returncode})")
            except subprocess.TimeoutExpired:
                proc.kill()
                print(f"  [{sym}] Force killed")
        print("\n  All bots stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Monitor loop — restart crashed processes
    try:
        while not shutting_down:
            for sym in list(processes.keys()):
                proc = processes[sym]
                if proc.poll() is not None and not shutting_down:
                    print(f"  [{sym}] DIED (exit code {proc.returncode}), restarting in 10s...")
                    time.sleep(10)
                    if shutting_down:
                        break
                    # Rebuild command from original process
                    cmd = [
                        sys.executable, run_bot_script,
                        "--config", args.config,
                        "--symbol", sym,
                    ]
                    if args.paper:
                        cmd.append("--paper")
                    elif args.live:
                        cmd.append("--live")
                    if args.log_level:
                        cmd.extend(["--log-level", args.log_level])
                    processes[sym] = subprocess.Popen(cmd, cwd=str(SCRIPT_DIR))
                    print(f"  [{sym}] Restarted (PID {processes[sym].pid})")
            time.sleep(5)
    except (KeyboardInterrupt, SystemExit):
        if not shutting_down:
            shutdown()


if __name__ == "__main__":
    main()
