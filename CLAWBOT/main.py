#!/usr/bin/env python3
"""
==========================================================================
  CLAWBOT - One-Click Launcher
==========================================================================

  Run this in PyCharm to:
    1. Find your Deriv MT5 (auto-picks Deriv over other brokers)
    2. Install & compile the CLAWBOT EA
    3. Run a 2-year backtest on XAUUSD H1
    4. Evaluate results (80 % win-rate gate)
    5. If passed -> credentials -> live trading

  Requirements:  Windows 10/11, Python 3.8+, Deriv MT5 installed
  Usage:         Click Run in PyCharm  -or-  python main.py

==========================================================================
"""

import os
import sys
import subprocess
import getpass
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────
ROOT    = Path(__file__).parent.resolve()
SCRIPTS = ROOT / "Scripts"
CONFIG  = ROOT / "Config"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

BANNER = r"""
   ██████╗██╗      █████╗ ██╗    ██╗██████╗  ██████╗ ████████╗
  ██╔════╝██║     ██╔══██╗██║    ██║██╔══██╗██╔═══██╗╚══██╔══╝
  ██║     ██║     ███████║██║ █╗ ██║██████╔╝██║   ██║   ██║
  ██║     ██║     ██╔══██║██║███╗██║██╔══██╗██║   ██║   ██║
  ╚██████╗███████╗██║  ██║╚███╔███╔╝██████╔╝╚██████╔╝   ██║
   ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ ╚═════╝  ╚═════╝    ╚═╝

  Multi-Strategy Confluence EA  |  XAUUSD H1  |  Deriv MT5
"""


# ======================================================================
#  Phase 0 – Environment
# ======================================================================
def check_env():
    if sys.platform != "win32":
        sys.exit("  [FATAL] MetaTrader 5 requires Windows.")

    needed = {"MetaTrader5": "MetaTrader5", "cryptography": "cryptography",
              "dotenv": "python-dotenv"}
    missing = []
    for mod, pkg in needed.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"  Installing: {', '.join(missing)} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing,
            stdout=subprocess.DEVNULL)
    print("  [OK] Dependencies ready.")


# ======================================================================
#  Phase 1 – MT5 Setup
# ======================================================================
def phase_setup():
    from mt5_manager import setup_mt5
    result = setup_mt5(ROOT)
    if result is None:
        sys.exit("\n  [FATAL] MT5 setup failed. Fix the issues above and re-run.")
    if not result["compiled"]:
        print("\n  [WARN] EA not compiled. Backtest may fail.")
        print("  Compile CLAWBOT.mq5 in MetaEditor (F7) if it does.")
    return result


# ======================================================================
#  Phase 2 – Backtest
# ======================================================================
def phase_backtest(mt5):
    from backtest_runner import run_backtest

    print("\n" + "=" * 55)
    print("  PHASE 2: BACKTEST")
    print("=" * 55)

    symbol = input("  Symbol [XAUUSD]: ").strip() or "XAUUSD"

    now = datetime.now()
    default_from = now.replace(year=now.year - 2).strftime("%Y.%m.%d")
    default_to   = now.strftime("%Y.%m.%d")
    from_date = input(f"  From [{default_from}]: ").strip() or default_from
    to_date   = input(f"  To   [{default_to}]: ").strip() or default_to

    deposit  = int((input("  Deposit [$10000]: ").strip() or "10000").replace("$","").replace(",",""))
    leverage = int((input("  Leverage [100]: ").strip() or "100").replace("1:",""))

    print("\n  Demo account for backtest (Enter to skip):")
    demo_login = input("  Demo Login: ").strip() or "0"
    demo_pw, demo_srv = "", "Deriv-Demo"
    if demo_login != "0":
        demo_pw  = getpass.getpass("  Demo Password: ")
        demo_srv = input("  Demo Server [Deriv-Demo]: ").strip() or "Deriv-Demo"

    print(f"\n  {symbol} | {from_date} -> {to_date} | ${deposit:,} | 1:{leverage}")
    if input("  Start? [Y/n]: ").strip().lower() == "n":
        return None

    tpl = CONFIG / "tester_template.ini"
    if not tpl.exists():
        sys.exit(f"  [FATAL] Missing: {tpl}")

    return run_backtest(
        terminal=mt5["terminal"], data_path=mt5["data_path"],
        config_template=tpl,
        login=demo_login, password=demo_pw, server=demo_srv,
        symbol=symbol, from_date=from_date, to_date=to_date,
        deposit=deposit, leverage=leverage, timeout_min=120,
    )


# ======================================================================
#  Phase 3 – Analyze
# ======================================================================
def phase_analyze(reports, data_path) -> bool:
    from backtest_analyzer import BacktestAnalyzer
    from backtest_runner import parse_mt5_html

    print("\n" + "=" * 55)
    print("  PHASE 3: ANALYSIS")
    print("=" * 55)

    analyzer = BacktestAnalyzer(threshold=80.0)

    # Try EA audit CSV first
    if reports and "audit_report" in reports:
        if analyzer.load_report(filepath=reports["audit_report"]):
            passed = analyzer.evaluate()
            txt = analyzer.generate_pass_report() if passed else analyzer.generate_weakness_report()
            print("\n" + txt)
            # Save report
            out = data_path / "MQL5" / "Files" / "CLAWBOT_Reports"
            out.mkdir(parents=True, exist_ok=True)
            tag = "PASS" if passed else "WEAK"
            (out / f"CLAWBOT_Analysis_{tag}.txt").write_text(txt)
            return passed

    # Auto-find any existing report
    if analyzer.load_report():
        passed = analyzer.evaluate()
        txt = analyzer.generate_pass_report() if passed else analyzer.generate_weakness_report()
        print("\n" + txt)
        return passed

    # Fallback: MT5 HTML
    if reports and "mt5_report" in reports:
        print("  Parsing MT5 HTML report ...")
        m = parse_mt5_html(reports["mt5_report"])
        if m:
            wr = m.get("win_rate", 0)
            n  = m.get("total_trades", 0)
            pf = m.get("profit_factor", 0)
            dd = m.get("max_drawdown_pct", 0)
            print(f"  Trades: {n}  WR: {wr:.1f}%  PF: {pf:.2f}  DD: {dd:.1f}%")
            passed = wr >= 80 and n >= 50
            print(f"  Result: {'PASSED' if passed else 'FAILED'}")
            return passed

    print("  [ERROR] No results found. Check MT5 Journal tab for errors.")
    return False


# ======================================================================
#  Phase 4 – Live
# ======================================================================
def phase_live(mt5):
    from credential_manager import collect_credentials, save_credentials, setup_encryption_passphrase
    from live_launcher import launch_live, verify_live_readiness

    print("\n" + "=" * 55)
    print("  PHASE 4: LIVE TRADING")
    print("=" * 55)

    issues = verify_live_readiness(mt5["data_path"])
    if issues:
        for i in issues:
            print(f"  - {i}")
        return False

    print("\n  *** BACKTEST PASSED ***")
    print("\n  WARNINGS:")
    print("    - Start with MINIMUM lots for 2 weeks")
    print("    - Monitor daily vs. backtest expectations")
    print("    - Past results do not guarantee future performance")
    print("    - Only risk capital you can afford to lose")

    if input("\n  Proceed to live setup? [yes/NO]: ").strip().lower() != "yes":
        print("  Cancelled. Re-run main.py when ready.")
        return False

    creds = collect_credentials()
    pp = setup_encryption_passphrase()
    save_credentials(creds, pp)

    print("\n  Launching Deriv MT5 in live mode ...")
    ok = launch_live(
        terminal=mt5["terminal"], data_path=mt5["data_path"],
        login=creds["login"], password=creds["password"], server=creds["server"],
    )

    if ok:
        print("\n" + "=" * 55)
        print("  *** CLAWBOT IS LIVE ***")
        print("=" * 55)
        print(f"  Account: {creds['login']} @ {creds['server']}")
        print("  Symbol:  XAUUSD H1  |  Mode: LIVE")
        print("\n  Checklist:")
        print("  [ ] AutoTrading enabled (Ctrl+E in MT5)")
        print("  [ ] Trade tab shows CLAWBOT activity")
        print("  [ ] Journal tab shows CLAWBOT log messages")
        print("  [ ] SL/TP set on every trade")

    return ok


# ======================================================================
#  Main
# ======================================================================
def main():
    print(BANNER)
    print(f"  {datetime.now():%Y-%m-%d %H:%M}  |  {ROOT}\n")

    # Phase 0
    print("=" * 55)
    print("  PHASE 0: ENVIRONMENT")
    print("=" * 55)
    check_env()

    # Phase 1
    print("\n" + "=" * 55)
    print("  PHASE 1: MT5 SETUP")
    print("=" * 55)
    mt5 = phase_setup()

    # Phase 2
    reports = phase_backtest(mt5)

    # Phase 3
    passed = phase_analyze(reports, mt5["data_path"])

    # Phase 4 or retry
    if passed:
        phase_live(mt5)
    else:
        print("\n" + "=" * 55)
        print("  BACKTEST DID NOT PASS")
        print("=" * 55)
        print("  1. Upload the weakness report to Claude for fixes")
        print("  2. Adjust parameters in Config/clawbot_config.ini")
        print("  3. Re-run main.py to test again")

    print(f"\n  Done: {datetime.now():%H:%M:%S}")
    input("  Press Enter to exit ...")


if __name__ == "__main__":
    main()
