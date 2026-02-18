#!/usr/bin/env python3
"""
==========================================================================
  CLAWBOT - One-Click Launcher
==========================================================================

  Run this file in PyCharm (or any Python IDE) to:

    1. Auto-detect your MetaTrader 5 installation
    2. Install & compile the CLAWBOT EA
    3. Run a 2-year automated backtest on XAUUSD H1
    4. Analyze results against the 80% win rate threshold
    5. If passed: enter credentials & launch live trading

  Requirements:
    - Windows 10/11 with MetaTrader 5 installed
    - Python 3.8+
    - pip install MetaTrader5 cryptography python-dotenv

  Usage:
    Just click Run in PyCharm, or:
      python main.py

==========================================================================
"""

import os
import sys
import time
import getpass
import subprocess
from pathlib import Path
from datetime import datetime

# ── Project paths ──────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.resolve()
SCRIPTS_DIR  = PROJECT_ROOT / "Scripts"
CONFIG_DIR   = PROJECT_ROOT / "Config"
MQL5_SRC     = PROJECT_ROOT / "MQL5" / "Experts" / "CLAWBOT"

# Add Scripts to path so we can import our modules
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))


# ── Banner ─────────────────────────────────────────────────────────────
BANNER = r"""
   ██████╗██╗      █████╗ ██╗    ██╗██████╗  ██████╗ ████████╗
  ██╔════╝██║     ██╔══██╗██║    ██║██╔══██╗██╔═══██╗╚══██╔══╝
  ██║     ██║     ███████║██║ █╗ ██║██████╔╝██║   ██║   ██║
  ██║     ██║     ██╔══██║██║███╗██║██╔══██╗██║   ██║   ██║
  ╚██████╗███████╗██║  ██║╚███╔███╔╝██████╔╝╚██████╔╝   ██║
   ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ ╚═════╝  ╚═════╝    ╚═╝

  Multi-Strategy Confluence EA for XAUUSD on Deriv MT5
  ─────────────────────────────────────────────────────
  Trend + Momentum + Session Breakout | 80% Win Gate
"""


# ======================================================================
#  PHASE 0: Dependency Check
# ======================================================================
def check_platform():
    """Ensure we're on Windows (MT5 is Windows-only)."""
    if sys.platform != "win32":
        print("\n  [ERROR] MetaTrader 5 only runs on Windows.")
        print("  This launcher requires Windows 10/11.")
        print("  If you're on Mac/Linux, use Wine or a Windows VM.")
        sys.exit(1)


def install_dependencies():
    """Auto-install required pip packages if missing."""
    required = {
        "MetaTrader5": "MetaTrader5",
        "cryptography": "cryptography",
        "dotenv": "python-dotenv",
    }

    missing = []
    for import_name, pip_name in required.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if not missing:
        print("  [OK] All Python dependencies installed.")
        return True

    print(f"  Installing missing packages: {', '.join(missing)}")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing,
            stdout=subprocess.DEVNULL,
        )
        print("  [OK] Packages installed successfully.")
        return True
    except subprocess.CalledProcessError:
        print(f"\n  [ERROR] Failed to install: {', '.join(missing)}")
        print(f"  Run manually: pip install {' '.join(missing)}")
        return False


# ======================================================================
#  PHASE 1: MT5 Setup
# ======================================================================
def phase_setup():
    """Detect MT5, install EA files, compile."""
    from mt5_manager import setup_mt5

    env_path = os.environ.get("MT5_TERMINAL_PATH")
    if env_path:
        print(f"  Using MT5_TERMINAL_PATH: {env_path}")

    result = setup_mt5(PROJECT_ROOT)
    if result is None:
        print("\n  [FATAL] MT5 setup failed. Cannot continue.")
        print("  Fix the issues above and re-run this script.")
        sys.exit(1)

    if not result["compiled"]:
        print("\n  [WARNING] EA not compiled. Attempting to continue anyway.")
        print("  If the backtest fails, compile CLAWBOT.mq5 in MetaEditor (F7).")

    return result


# ======================================================================
#  PHASE 2: Backtest
# ======================================================================
def phase_backtest(mt5_info: dict):
    """Run automated backtest via MT5 Strategy Tester."""
    from backtest_runner import run_backtest

    print("\n" + "=" * 60)
    print("  PHASE 2: AUTOMATED BACKTEST")
    print("=" * 60)

    # Backtest settings
    print("\n  Backtest Configuration:")
    print("  ─────────────────────────")

    # Default symbol
    symbol = input("  Symbol [XAUUSD]: ").strip() or "XAUUSD"

    # Date range
    to_date = datetime.now().strftime("%Y.%m.%d")
    default_from = (datetime.now().replace(year=datetime.now().year - 2)).strftime("%Y.%m.%d")
    from_date = input(f"  From date [{default_from}]: ").strip() or default_from
    to_date_input = input(f"  To date [{to_date}]: ").strip() or to_date

    # Deposit
    deposit_str = input("  Starting deposit [$10000]: ").strip() or "10000"
    deposit = int(deposit_str.replace("$", "").replace(",", ""))

    # Leverage
    leverage_str = input("  Leverage [100]: ").strip() or "100"
    leverage = int(leverage_str.replace("1:", ""))

    # Demo account for backtest (optional)
    print("\n  Demo account (optional, press Enter to skip):")
    demo_login = input("  Demo Login ID: ").strip() or "0"
    demo_password = ""
    demo_server = "Deriv-Demo"
    if demo_login != "0":
        demo_password = getpass.getpass("  Demo Password: ")
        demo_server = input("  Demo Server [Deriv-Demo]: ").strip() or "Deriv-Demo"

    print("\n  ─────────────────────────")
    print(f"  Symbol:    {symbol}")
    print(f"  Period:    {from_date} → {to_date_input}")
    print(f"  Deposit:   ${deposit:,}")
    print(f"  Leverage:  1:{leverage}")
    print("  ─────────────────────────")

    confirm = input("\n  Start backtest? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("  Backtest cancelled.")
        return None

    template_path = CONFIG_DIR / "tester_template.ini"
    if not template_path.exists():
        print(f"  [ERROR] Tester template not found: {template_path}")
        return None

    reports = run_backtest(
        terminal_path=mt5_info["terminal"],
        data_path=mt5_info["data_path"],
        config_template=template_path,
        login=demo_login,
        password=demo_password,
        server=demo_server,
        symbol=symbol,
        from_date=from_date,
        to_date=to_date_input,
        deposit=deposit,
        leverage=leverage,
        timeout_minutes=120,
    )

    return reports


# ======================================================================
#  PHASE 3: Analyze Results
# ======================================================================
def phase_analyze(reports: dict, data_path: Path) -> bool:
    """Analyze backtest results against the 80% threshold."""
    from backtest_analyzer import BacktestAnalyzer

    print("\n" + "=" * 60)
    print("  PHASE 3: RESULT ANALYSIS")
    print("=" * 60)

    if not reports:
        print("\n  [WARNING] No reports found from backtest.")
        print("  Would you like to analyze existing reports instead?")
        choice = input("  [Y/n]: ").strip().lower()
        if choice == "n":
            return False

    # Try EA audit report first (most detailed)
    analyzer = BacktestAnalyzer(threshold=80.0)

    report_loaded = False
    if reports and "audit_report" in reports:
        report_loaded = analyzer.load_report(str(reports["audit_report"]))
    else:
        report_loaded = analyzer.load_report()

    if report_loaded:
        passed = analyzer.evaluate()

        if passed:
            report_text = analyzer.generate_pass_report()
            print("\n" + report_text)
            report_file = data_path / "MQL5" / "Files" / "CLAWBOT_Reports" / "CLAWBOT_Analysis_PASS.txt"
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(report_text)
            print(f"\n  Report saved: {report_file}")
        else:
            report_text = analyzer.generate_weakness_report()
            print("\n" + report_text)
            report_file = data_path / "MQL5" / "Files" / "CLAWBOT_Reports" / "CLAWBOT_Analysis_WEAK.txt"
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(report_text)
            print(f"\n  Weakness report saved: {report_file}")
            print("  Upload this file to Claude for optimization suggestions.")

        return passed

    # Fallback: parse MT5 HTML report
    if reports and "mt5_report" in reports:
        print("\n  [INFO] EA audit report not found. Parsing MT5 HTML report...")
        from backtest_runner import parse_mt5_html_report
        metrics = parse_mt5_html_report(reports["mt5_report"])

        if metrics:
            win_rate = metrics.get("win_rate", 0)
            total_trades = metrics.get("total_trades", 0)
            pf = metrics.get("profit_factor", 0)
            dd = metrics.get("max_drawdown_pct", 0)

            print(f"\n  --- MT5 Report Metrics ---")
            print(f"  Total Trades:   {total_trades}")
            print(f"  Win Rate:       {win_rate:.1f}%")
            print(f"  Profit Factor:  {pf:.2f}")
            print(f"  Max Drawdown:   {dd:.1f}%")

            passed = win_rate >= 80.0 and total_trades >= 50
            print(f"\n  Result: {'PASSED' if passed else 'FAILED'}")
            return passed

    print("\n  [ERROR] Could not analyze results. No valid report files found.")
    print("  Try running the backtest again, or check MT5 for errors.")
    return False


# ======================================================================
#  PHASE 4: Credential Setup & Live Launch
# ======================================================================
def phase_live(mt5_info: dict):
    """Collect credentials and launch live trading."""
    from credential_manager import collect_credentials, save_credentials, setup_encryption_passphrase
    from live_launcher import launch_live, verify_live_readiness

    print("\n" + "=" * 60)
    print("  PHASE 4: LIVE TRADING SETUP")
    print("=" * 60)

    # Pre-flight checks
    issues = verify_live_readiness(mt5_info["data_path"])
    if issues:
        print("\n  Pre-flight issues:")
        for issue in issues:
            print(f"    - {issue}")
        print("\n  Fix these issues before launching live.")
        return False

    print("\n  *** BACKTEST PASSED! Ready for live deployment. ***")
    print("\n  IMPORTANT WARNINGS:")
    print("  ─────────────────────────────────────────────────────")
    print("  1. Start with MINIMUM lot sizes for the first 2 weeks")
    print("  2. Monitor daily and compare with backtest metrics")
    print("  3. Past backtest performance does not guarantee future results")
    print("  4. Only risk capital you can afford to lose")
    print("  ─────────────────────────────────────────────────────")

    proceed = input("\n  Proceed to live setup? [yes/NO]: ").strip().lower()
    if proceed != "yes":
        print("\n  Live setup cancelled. You can re-run this script later.")
        print("  The backtest results are saved - you won't need to re-test.")
        return False

    # Collect credentials
    print("\n  --- Deriv MT5 Account Credentials ---")
    credentials = collect_credentials()

    # Encrypt and save
    print("\n  --- Encryption Setup ---")
    passphrase = setup_encryption_passphrase()
    save_credentials(credentials, passphrase)

    # Launch MT5 in live mode
    print("\n  --- Launching Live Trading ---")
    success = launch_live(
        terminal_path=mt5_info["terminal"],
        data_path=mt5_info["data_path"],
        login=credentials["login"],
        password=credentials["password"],
        server=credentials["server"],
    )

    if success:
        print("\n" + "=" * 60)
        print("  *** CLAWBOT IS NOW LIVE ***")
        print("=" * 60)
        print(f"\n  Account: {credentials['login']} @ {credentials['server']}")
        print("  Symbol:  XAUUSD H1")
        print("  Mode:    LIVE (auto-trading enabled)")
        print("\n  The EA is attached to your XAUUSD H1 chart.")
        print("  Make sure AutoTrading is enabled in MT5 (Ctrl+E).")
        print("\n  Monitor checklist:")
        print("  [ ] Check the Trade tab for open positions")
        print("  [ ] Check the Journal tab for CLAWBOT log messages")
        print("  [ ] Verify SL/TP are set on every trade")
        print("  [ ] Review daily P/L against backtest expectations")

    return success


# ======================================================================
#  PHASE 5: Failed Backtest - Optimization Loop
# ======================================================================
def phase_failed_backtest():
    """Handle a failed backtest - offer rerun or optimization."""
    print("\n" + "=" * 60)
    print("  BACKTEST DID NOT PASS")
    print("=" * 60)
    print("\n  The bot did not achieve the 80% win rate threshold.")
    print("  This is normal - most strategies need 3-5 iterations.")
    print("\n  Options:")
    print("  1. Upload the weakness report to Claude for optimization")
    print("  2. Adjust EA parameters in Config/clawbot_config.ini")
    print("  3. Re-run this script to test again")
    print("\n  The weakness report identifies exactly what to fix:")
    print("  - Which strategies underperform")
    print("  - Which sessions/days lose money")
    print("  - Specific parameter adjustment recommendations")


# ======================================================================
#  MAIN PIPELINE
# ======================================================================
def main():
    print(BANNER)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Project: {PROJECT_ROOT}")
    print()

    # ── Phase 0: Platform & Dependencies ──
    print("=" * 60)
    print("  PHASE 0: ENVIRONMENT CHECK")
    print("=" * 60)

    check_platform()
    print("  [OK] Platform: Windows")

    if not install_dependencies():
        print("\n  [FATAL] Cannot install required packages.")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    # ── Phase 1: MT5 Setup ──
    print("\n" + "=" * 60)
    print("  PHASE 1: MT5 SETUP")
    print("=" * 60)

    mt5_info = phase_setup()

    # ── Phase 2: Backtest ──
    reports = phase_backtest(mt5_info)

    # ── Phase 3: Analyze ──
    passed = phase_analyze(reports, mt5_info["data_path"])

    # ── Phase 4 or 5: Live or Optimize ──
    if passed:
        phase_live(mt5_info)
    else:
        phase_failed_backtest()

    print("\n" + "=" * 60)
    print(f"  CLAWBOT finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    input("\n  Press Enter to exit...")


if __name__ == "__main__":
    main()
