#!/usr/bin/env python3
"""
CLAWBOT Launcher & Workflow Controller
========================================
Master script that orchestrates the CLAWBOT workflow:

1. Validate MT5 installation and Deriv connection
2. Install CLAWBOT EA files to MT5 data directory
3. Configure and launch 2-year backtest
4. Analyze results against 80% threshold
5. If PASS: prompt for credentials and save securely
6. If FAIL: generate weakness report for upload to Claude

Usage:
  python clawbot_launcher.py [--mt5-path PATH] [--skip-install]
"""

import os
import sys
import shutil
import subprocess
import time
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent
EA_SOURCE_DIR = PROJECT_DIR / "MQL5" / "Experts" / "CLAWBOT"


def print_banner():
    """Print CLAWBOT startup banner."""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║      ██████╗██╗      █████╗ ██╗    ██╗██████╗  ██████╗ ████████╗  ║
    ║     ██╔════╝██║     ██╔══██╗██║    ██║██╔══██╗██╔═══██╗╚══██╔══╝  ║
    ║     ██║     ██║     ███████║██║ █╗ ██║██████╔╝██║   ██║   ██║     ║
    ║     ██║     ██║     ██╔══██║██║███╗██║██╔══██╗██║   ██║   ██║     ║
    ║     ╚██████╗███████╗██║  ██║╚███╔███╔╝██████╔╝╚██████╔╝   ██║     ║
    ║      ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ ╚═════╝  ╚═════╝    ╚═╝     ║
    ║                                                          ║
    ║          Multi-Strategy Confluence Trading Bot            ║
    ║             XAUUSD H1 | Deriv MT5 Broker                 ║
    ║                     v1.0.0                               ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)


def find_mt5_installation() -> Path:
    """Find MT5 installation directory."""
    common_paths = []

    if sys.platform == "win32":
        common_paths = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Deriv MT5",
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "MetaTrader 5",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Deriv MT5",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "MetaTrader 5",
            Path.home() / "AppData" / "Local" / "Programs" / "MetaTrader 5",
        ]
    else:
        # Linux/Mac with Wine
        common_paths = [
            Path.home() / ".wine" / "drive_c" / "Program Files" / "Deriv MT5",
            Path.home() / ".wine" / "drive_c" / "Program Files" / "MetaTrader 5",
            Path("/opt/mt5"),
        ]

    for path in common_paths:
        if path.exists():
            return path

    return None


def find_mt5_data_dir() -> Path:
    """Find MT5 data directory (where MQL5 files are stored)."""
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
        if base.exists():
            # Find the most recently modified terminal directory
            terminals = sorted(base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
            for terminal in terminals:
                if terminal.is_dir() and (terminal / "MQL5").exists():
                    return terminal / "MQL5"
    else:
        # Linux with Wine
        wine_base = Path.home() / ".wine" / "drive_c" / "Users"
        if wine_base.exists():
            for user_dir in wine_base.iterdir():
                mql_dir = user_dir / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
                if mql_dir.exists():
                    for terminal in mql_dir.iterdir():
                        if terminal.is_dir() and (terminal / "MQL5").exists():
                            return terminal / "MQL5"

    return None


def install_ea_files(mt5_data_dir: Path) -> bool:
    """Install CLAWBOT EA files to MT5 data directory."""
    target_dir = mt5_data_dir / "Experts" / "CLAWBOT"
    target_dir.mkdir(parents=True, exist_ok=True)

    files_to_copy = [
        "CLAWBOT.mq5",
        "ClawUtils.mqh",
        "ClawStrategy_Trend.mqh",
        "ClawStrategy_Momentum.mqh",
        "ClawStrategy_Session.mqh",
        "ClawRisk.mqh",
        "ClawAudit.mqh",
    ]

    print(f"\n  Installing EA files to: {target_dir}")

    for filename in files_to_copy:
        src = EA_SOURCE_DIR / filename
        dst = target_dir / filename

        if not src.exists():
            print(f"  [ERROR] Source file not found: {src}")
            return False

        shutil.copy2(src, dst)
        print(f"  [OK] Copied: {filename}")

    print(f"\n  [OK] All {len(files_to_copy)} files installed successfully")
    return True


def run_workflow():
    """Execute the complete CLAWBOT workflow."""
    print_banner()

    print("=" * 60)
    print("  STEP 1: Environment Check")
    print("=" * 60)

    # Check MT5
    mt5_path = find_mt5_installation()
    if mt5_path:
        print(f"  [OK] MT5 found: {mt5_path}")
    else:
        print("  [INFO] MT5 installation not auto-detected.")
        print("  This is OK if you plan to copy files manually.")

    mt5_data = find_mt5_data_dir()
    if mt5_data:
        print(f"  [OK] MT5 data dir: {mt5_data}")
    else:
        print("  [INFO] MT5 data directory not found.")

    # Check EA source files
    ea_main = EA_SOURCE_DIR / "CLAWBOT.mq5"
    if ea_main.exists():
        print(f"  [OK] CLAWBOT EA source found: {ea_main}")
    else:
        print(f"  [ERROR] CLAWBOT EA source not found at: {ea_main}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  STEP 2: Install EA Files")
    print("=" * 60)

    if mt5_data:
        install = input("\n  Install CLAWBOT to MT5? (yes/no): ").strip().lower()
        if install == "yes":
            if install_ea_files(mt5_data):
                print("\n  EA files installed. You can now compile in MT5.")
            else:
                print("\n  [ERROR] Installation failed.")
        else:
            print("  Skipping auto-install.")
    else:
        print("\n  Cannot auto-install (MT5 data directory not found).")
        print("  Manual installation:")
        print(f"    1. Copy all files from: {EA_SOURCE_DIR}")
        print("    2. Paste into: <MT5 Data>/MQL5/Experts/CLAWBOT/")
        print("    3. Open MetaEditor and compile CLAWBOT.mq5")

    print("\n" + "=" * 60)
    print("  STEP 3: Backtesting Instructions")
    print("=" * 60)

    backtest_start = (datetime.now() - timedelta(days=730)).strftime("%Y.%m.%d")
    backtest_end = datetime.now().strftime("%Y.%m.%d")

    print(f"""
  To run the required 2-year backtest:

  1. Open MT5 terminal
  2. Go to View -> Strategy Tester (Ctrl+R)
  3. Configure:
     - Expert:     CLAWBOT (under Experts/CLAWBOT/)
     - Symbol:     XAUUSD
     - Period:     H1
     - Date:       {backtest_start} to {backtest_end}
     - Model:      Every tick based on real ticks (most accurate)
     - Deposit:    Your planned starting balance
     - Leverage:   Your Deriv account leverage
     - Bot Mode:   Backtest (default)

  4. Click 'Start' to begin backtesting
  5. Wait for completion (check Journal/Results tabs)
  6. Reports are auto-generated in the CLAWBOT_Reports folder

  After backtesting completes, run this launcher again
  or use: python backtest_analyzer.py
    """)

    print("=" * 60)
    print("  STEP 4: Post-Backtest Analysis")
    print("=" * 60)

    # Check for existing reports
    check_reports = input("\n  Check for existing backtest reports? (yes/no): ").strip().lower()

    if check_reports == "yes":
        try:
            from backtest_analyzer import BacktestAnalyzer

            analyzer = BacktestAnalyzer()
            if analyzer.load_report():
                passed = analyzer.evaluate()

                if passed:
                    print("\n  *** BACKTEST PASSED! ***")
                    proceed = input("\n  Proceed to credential setup? (yes/no): ").strip().lower()
                    if proceed == "yes":
                        print("\n  Launching credential manager...\n")
                        subprocess.run([sys.executable,
                                       str(SCRIPT_DIR / "credential_manager.py")])
                else:
                    print("\n  Backtest did not meet threshold.")
                    gen_report = input("  Generate weakness report? (yes/no): ").strip().lower()
                    if gen_report == "yes":
                        report = analyzer.generate_weakness_report()
                        report_file = PROJECT_DIR / "Reports" / "CLAWBOT_Weakness_Analysis.txt"
                        report_file.parent.mkdir(parents=True, exist_ok=True)
                        report_file.write_text(report)
                        print(f"\n  Weakness report saved to: {report_file}")
                        print("  Upload this file to Claude for optimization help.")
            else:
                print("\n  No backtest reports found yet.")
                print("  Complete the backtesting step above first.")
        except ImportError:
            print("  [INFO] Could not import analyzer. Run backtest_analyzer.py separately.")

    print("\n" + "=" * 60)
    print("  CLAWBOT Launcher Complete")
    print("=" * 60)
    print("""
  Quick Reference:
    - Backtest Analysis: python Scripts/backtest_analyzer.py
    - Credential Setup:  python Scripts/credential_manager.py
    - EA Location:       MQL5/Experts/CLAWBOT/CLAWBOT.mq5

  For support, upload weakness reports to Claude for optimization.
    """)


if __name__ == "__main__":
    run_workflow()
