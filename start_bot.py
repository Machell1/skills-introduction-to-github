#!/usr/bin/env python3
"""
ONE-CLICK LAUNCHER — Smart Money Concepts Trading Bot

Double-click this file or run: python start_bot.py

This script will:
1. Check Python version
2. Install all required packages automatically
3. Prompt you for MT5 credentials (if not already configured)
4. Launch the trading bot

Works on any Windows machine with Python 3.9+ and MT5 installed.
"""

import subprocess
import sys
import os
import json
import platform
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
BOT_DIR = SCRIPT_DIR / "smart_money_bot"
SETTINGS_FILE = BOT_DIR / "settings.json"
REQUIREMENTS_FILE = SCRIPT_DIR / "requirements.txt"
MIN_PYTHON = (3, 9)

BANNER = r"""
 ╔══════════════════════════════════════════════════════════════╗
 ║         SMART MONEY CONCEPTS (SMC) TRADING BOT              ║
 ║                                                             ║
 ║  Multi-Pair  |  1H Timeframe  |  MT5  |  Deriv Broker      ║
 ║  XAUUSD | EURUSD | GBPUSD | USDJPY | GBPJPY | EURJPY      ║
 ║                                                             ║
 ║  One-Click Installer & Launcher                             ║
 ╚══════════════════════════════════════════════════════════════╝
"""


def print_step(step_num, total, message):
    print(f"\n  [{step_num}/{total}] {message}")
    print(f"  {'─' * 50}")


def check_python_version():
    """Ensure Python version meets minimum requirement."""
    v = sys.version_info
    if (v.major, v.minor) < MIN_PYTHON:
        print(f"\n  ERROR: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required.")
        print(f"  You have Python {v.major}.{v.minor}.{v.micro}")
        print("  Download latest Python from https://www.python.org/downloads/")
        input("\n  Press Enter to exit...")
        sys.exit(1)
    print(f"  Python {v.major}.{v.minor}.{v.micro} — OK")


def check_platform():
    """Check OS — MT5 Python package only works on Windows."""
    if platform.system() != "Windows":
        print("\n  WARNING: MetaTrader5 Python package only runs on Windows.")
        print("  The bot will start in PAPER TRADING mode (no MT5 connection).")
        print("  For live trading, run this on a Windows machine with MT5 installed.")
        return False
    return True


def install_packages():
    """Install all required packages using pip."""
    packages = ["MetaTrader5", "numpy", "pandas"]

    # Upgrade pip first
    print("  Upgrading pip...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for pkg in packages:
        print(f"  Installing {pkg}...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            print(f"    {pkg} — OK")
        except subprocess.CalledProcessError:
            if pkg == "MetaTrader5" and platform.system() != "Windows":
                print(f"    {pkg} — SKIPPED (not on Windows, paper mode only)")
            else:
                print(f"    {pkg} — FAILED (will retry with requirements.txt)")

    # Also try requirements.txt as fallback
    if REQUIREMENTS_FILE.exists():
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            pass

    print("  All packages installed.")


def verify_mt5():
    """Check if MT5 terminal is installed and accessible."""
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            info = mt5.terminal_info()
            mt5.shutdown()
            if info:
                print(f"  MT5 Terminal found: {info.name}")
                print(f"  Data path: {info.data_path}")
                return True
        else:
            print("  MT5 terminal found but could not initialize.")
            print("  Make sure MT5 is running and logged in.")
            return False
    except ImportError:
        print("  MetaTrader5 package not available (non-Windows or install failed).")
        return False
    except Exception as e:
        print(f"  MT5 check error: {e}")
        return False


def load_settings():
    """Load current settings."""
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_settings(settings):
    """Save settings to file."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def setup_credentials(settings, mt5_available):
    """Interactive credential setup if not configured."""
    mt5_cfg = settings.get("mt5", {})
    current_login = mt5_cfg.get("login", 0)

    if current_login and current_login != 0:
        print(f"  MT5 Login: {current_login}")
        print(f"  Server:    {mt5_cfg.get('server', 'Deriv-Demo')}")
        choice = input("\n  Use existing credentials? (Y/n): ").strip().lower()
        if choice != "n":
            return settings

    if not mt5_available:
        print("  MT5 not available — running in paper trading mode.")
        settings.setdefault("execution", {})["paper_trading"] = True
        return settings

    print("\n  Enter your Deriv MT5 credentials:")
    print("  (Find these in your Deriv account under MT5 > Account Info)")
    print()

    login = input("  MT5 Login (number):  ").strip()
    password = input("  MT5 Password:        ").strip()

    print()
    print("  Server options for Deriv:")
    print("    1. Deriv-Demo      (demo account)")
    print("    2. Deriv-Server    (real account)")
    print("    3. Deriv-Server-02 (real account)")
    print("    4. Custom")
    server_choice = input("  Select server (1-4): ").strip()

    server_map = {
        "1": "Deriv-Demo",
        "2": "Deriv-Server",
        "3": "Deriv-Server-02",
    }
    if server_choice in server_map:
        server = server_map[server_choice]
    elif server_choice == "4":
        server = input("  Enter custom server: ").strip()
    else:
        server = "Deriv-Demo"

    # Ask about trading mode
    print()
    print("  Trading mode:")
    print("    1. Paper trading  (simulated, no real money — RECOMMENDED for first run)")
    print("    2. Live trading   (real orders on your account)")
    mode = input("  Select mode (1/2): ").strip()
    paper = mode != "2"

    if not paper:
        confirm = input("\n  CONFIRM: You want LIVE trading with real money? (type YES): ").strip()
        if confirm != "YES":
            print("  Switching to paper trading mode for safety.")
            paper = True

    # Update settings
    settings.setdefault("mt5", {})
    settings["mt5"]["login"] = int(login) if login.isdigit() else 0
    settings["mt5"]["password"] = password
    settings["mt5"]["server"] = server
    settings.setdefault("execution", {})["paper_trading"] = paper

    save_settings(settings)
    print(f"\n  Settings saved to {SETTINGS_FILE}")
    return settings


def configure_symbol(settings):
    """Let user choose trading symbol(s)."""
    current = settings.get("mt5", {}).get("symbol", "XAUUSD")
    print(f"  Current symbol: {current}")
    print()
    print("  Supported Deriv symbols (ICT/SMC auto-tuned):")
    print("    1. XAUUSD  (Gold)         — Sharp sweeps, large FVGs")
    print("    2. EURUSD  (EUR/USD)      — #1 ICT pair, cleanest structure")
    print("    3. GBPUSD  (GBP/USD)      — Volatile, explosive London moves")
    print("    4. USDJPY  (USD/JPY)      — Clean technician, Tokyo+NY")
    print("    5. GBPJPY  (GBP/JPY)      — High volatility cross")
    print("    6. EURJPY  (EUR/JPY)      — Tokyo/London overlap")
    print("    7. ALL 6 PAIRS            — Multi-pair mode (one bot per pair)")
    print("    8. Keep current")
    print("    9. Custom")

    choice = input("  Select (1-9): ").strip()
    symbol_map = {
        "1": "XAUUSD", "2": "EURUSD", "3": "GBPUSD",
        "4": "USDJPY", "5": "GBPJPY", "6": "EURJPY",
    }

    if choice == "7":
        settings["_multi_pair"] = True
        save_settings(settings)
        print("  Multi-pair mode selected — will launch all 6 pairs simultaneously.")
        return settings
    elif choice in symbol_map:
        settings.setdefault("mt5", {})["symbol"] = symbol_map[choice]
    elif choice == "9":
        custom = input("  Enter symbol (e.g., XAUUSD): ").strip().upper()
        if custom:
            settings.setdefault("mt5", {})["symbol"] = custom
    # choice 8 or anything else keeps current

    settings.pop("_multi_pair", None)
    save_settings(settings)
    symbol = settings.get("mt5", {}).get("symbol", "XAUUSD")
    print(f"  Symbol set to: {symbol}")
    return settings


def launch_bot(settings):
    """Launch the trading bot (single-pair or multi-pair)."""
    paper = settings.get("execution", {}).get("paper_trading", True)
    mode_str = "PAPER" if paper else "LIVE"
    multi_pair = settings.get("_multi_pair", False)

    if multi_pair:
        print(f"\n  Launching ALL 6 pairs in {mode_str} mode...")
        print("  Press Ctrl+C at any time to stop all bots.\n")
        print("=" * 60)

        bot_script = SCRIPT_DIR / "run_multi.py"
        cmd = [sys.executable, str(bot_script), "--config", str(SETTINGS_FILE)]
        if paper:
            cmd.append("--paper")
        else:
            cmd.append("--live")
    else:
        symbol = settings.get("mt5", {}).get("symbol", "XAUUSD")
        print(f"\n  Launching bot in {mode_str} mode for {symbol}...")
        print("  Press Ctrl+C at any time to stop the bot.\n")
        print("=" * 60)

        bot_script = SCRIPT_DIR / "run_bot.py"
        cmd = [sys.executable, str(bot_script), "--config", str(SETTINGS_FILE)]
        cmd.extend(["--symbol", symbol])
        if paper:
            cmd.append("--paper")
        else:
            cmd.append("--live")

    try:
        process = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
        return process.returncode
    except KeyboardInterrupt:
        print("\n\n  Bot stopped by user.")
        return 0


# ── Main ──────────────────────────────────────────────────────────

def main():
    os.chdir(SCRIPT_DIR)
    print(BANNER)

    total_steps = 6

    # Step 1: Check Python
    print_step(1, total_steps, "Checking Python version")
    check_python_version()

    # Step 2: Check platform
    print_step(2, total_steps, "Checking platform")
    is_windows = check_platform()

    # Step 3: Install packages
    print_step(3, total_steps, "Installing required packages")
    install_packages()

    # Step 4: Check MT5
    print_step(4, total_steps, "Checking MetaTrader 5")
    mt5_ok = verify_mt5() if is_windows else False

    # Step 5: Setup credentials & config
    print_step(5, total_steps, "Configuring bot")
    settings = load_settings()
    settings = setup_credentials(settings, mt5_ok)
    settings = configure_symbol(settings)

    # Step 6: Launch
    print_step(6, total_steps, "Starting trading bot")
    exit_code = launch_bot(settings)

    if exit_code != 0:
        print(f"\n  Bot exited with code {exit_code}")

    input("\n  Press Enter to close...")
    sys.exit(exit_code or 0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled by user.")
    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("\n  Press Enter to close...")
        sys.exit(1)
