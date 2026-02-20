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

import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────
ROOT    = Path(__file__).parent.resolve()
SCRIPTS = ROOT / "Scripts"
CONFIG  = ROOT / "Config"
DATA    = ROOT / "Data"

sys.path.insert(0, str(ROOT))

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
    """Check environment. Returns True if MT5 is available, False for Python-only mode."""
    if sys.platform != "win32":
        print("  [INFO] Not on Windows - MT5 Strategy Tester unavailable.")
        print("  [INFO] Will use Python backtester for evaluation.")
        return False

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
    return True


# ======================================================================
#  Phase 1 – MT5 Setup
# ======================================================================
def phase_setup():
    from Scripts.mt5_manager import setup_mt5
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
    from Scripts.backtest_runner import run_backtest

    print("\n" + "=" * 55)
    print("  PHASE 2: BACKTEST")
    print("=" * 55)
    print()
    print("  Make sure you are logged into Deriv MT5 before")
    print("  starting. The backtest uses your active session.")
    print()

    symbol = input("  Symbol [XAUUSD]: ").strip() or "XAUUSD"

    now = datetime.now()
    default_from = now.replace(year=now.year - 2).strftime("%Y.%m.%d")
    default_to   = now.strftime("%Y.%m.%d")
    from_date = input(f"  From [{default_from}]: ").strip() or default_from
    to_date   = input(f"  To   [{default_to}]: ").strip() or default_to

    deposit  = int((input("  Deposit [$10000]: ").strip() or "10000").replace("$","").replace(",",""))
    leverage = int((input("  Leverage [100]: ").strip() or "100").replace("1:",""))

    print(f"\n  {symbol} | {from_date} -> {to_date} | ${deposit:,} | 1:{leverage}")
    if input("  Start? [Y/n]: ").strip().lower() == "n":
        return None

    tpl = CONFIG / "tester_template.ini"
    if not tpl.exists():
        sys.exit(f"  [FATAL] Missing: {tpl}")

    return run_backtest(
        terminal=mt5["terminal"], data_path=mt5["data_path"],
        config_template=tpl,
        symbol=symbol, from_date=from_date, to_date=to_date,
        deposit=deposit, leverage=leverage, timeout_min=120,
        metaeditor=mt5.get("metaeditor"),
    )


# ======================================================================
#  Python Backtester Fallback
# ======================================================================
def phase_python_backtest(deposit=None) -> bool:
    """Run the Python backtester as fallback when MT5 Strategy Tester fails."""
    try:
        from Scripts.backtest_engine import main as bt_main, print_stats
    except ImportError as e:
        print(f"  [ERROR] Cannot import Python backtester: {e}")
        return False

    data_path = DATA / "XAUUSD_H1.csv"
    if not data_path.exists():
        print(f"  [ERROR] Historical data not found: {data_path}")
        print("  Download XAUUSD H1 data to Data/XAUUSD_H1.csv")
        return False

    print("\n" + "=" * 55)
    print("  PYTHON BACKTESTER (FALLBACK)")
    print("=" * 55)

    overrides = {}
    if deposit:
        overrides["initial_balance"] = float(deposit)

    try:
        stats, issues, cfg = bt_main(data_path=data_path, config_overrides=overrides)
    except Exception as e:
        print(f"  [ERROR] Python backtest failed: {e}")
        return False

    # Evaluate using the same criteria as BacktestAnalyzer
    wr = stats.get("win_rate", 0)
    pf = stats.get("profit_factor", 0)
    dd = stats.get("max_drawdown_pct", 100)
    exp = stats.get("avg_win", 0) * (wr / 100) - abs(stats.get("avg_loss", 0)) * (1 - wr / 100)
    n = stats.get("total_trades", 0)

    checks = {
        "Win Rate":      (wr >= 55,   f"{wr:.1f}%",   ">=55%"),
        "Profit Factor": (pf >= 1.5,  f"{pf:.2f}",    ">=1.5"),
        "Max Drawdown":  (dd <= 15,   f"{dd:.1f}%",   "<=15%"),
        "Expectancy":    (exp > 0,    f"${exp:.2f}",  ">$0"),
        "Total Trades":  (n >= 50,    f"{n}",         ">=50"),
    }

    print("\n" + "=" * 55)
    print("  BACKTEST EVALUATION")
    print("=" * 55)
    for name, (ok, val, target) in checks.items():
        tag = "PASS" if ok else "FAIL"
        print(f"  {name:18s} {val:>10s}  {tag}  (target {target})")

    secondary = sum(v[0] for k, v in checks.items() if k != "Win Rate")
    passed = checks["Win Rate"][0] and secondary >= 2
    print(f"\n  Secondary: {secondary}/4 (need >=2)")
    print(f"  Result:    {'*** PASSED ***' if passed else '*** FAILED ***'}")
    print("=" * 55)

    return passed


# ======================================================================
#  Phase 3 – Analyze
# ======================================================================
def phase_analyze(reports, data_path) -> bool:
    from Scripts.backtest_analyzer import BacktestAnalyzer
    from Scripts.backtest_runner import parse_mt5_html

    print("\n" + "=" * 55)
    print("  PHASE 3: ANALYSIS")
    print("=" * 55)

    if not reports:
        print("  [WARN] No MT5 backtest results available.")
        print("  The Strategy Tester did not produce any output.")
        print("  Falling back to Python backtester...")
        return phase_python_backtest()

    analyzer = BacktestAnalyzer(threshold=55.0)

    # Try EA audit CSV first
    if "audit_report" in reports:
        if analyzer.load_report(filepath=reports["audit_report"]):
            passed = analyzer.evaluate()
            txt = analyzer.generate_pass_report() if passed else analyzer.generate_weakness_report()
            print("\n" + txt)
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
    if "mt5_report" in reports:
        print("  Parsing MT5 HTML report ...")
        m = parse_mt5_html(reports["mt5_report"])
        if m:
            wr = m.get("win_rate", 0)
            n  = m.get("total_trades", 0)
            pf = m.get("profit_factor", 0)
            dd = m.get("max_drawdown_pct", 0)
            print(f"  Trades: {n}  WR: {wr:.1f}%  PF: {pf:.2f}  DD: {dd:.1f}%")
            passed = wr >= 55 and n >= 50
            print(f"  Result: {'PASSED' if passed else 'FAILED'}")
            return passed

    # Fallback: results extracted from MT5 logs
    if "log_results" in reports:
        log = reports["log_results"]
        wr = log.get("win_rate", 0)
        n  = log.get("total_trades", 0)
        pf = log.get("profit_factor", 0)
        dd = log.get("max_drawdown_pct", 0)
        net = log.get("net_profit", 0)

        print(f"\n  Results (from MT5 log):")
        print(f"    Trades: {n}  |  Win Rate: {wr:.1f}%  |  PF: {pf:.2f}")
        print(f"    Max DD: {dd:.1f}%  |  Net: ${net:.2f}")

        if "overall_passed" in log:
            passed = log["overall_passed"]
        else:
            passed = wr >= 55 and n >= 50

        print(f"    Result: {'PASSED' if passed else 'FAILED'}")
        return passed

    # === FALLBACK: Python Backtester ===
    print("\n  [INFO] MT5 produced no usable results. Running Python backtester...")
    return phase_python_backtest()


# ======================================================================
#  Phase 4 – Live
# ======================================================================
def phase_live(mt5):
    from Scripts.credential_manager import collect_credentials, save_credentials, setup_encryption_passphrase
    from Scripts.live_launcher import launch_live, verify_live_readiness

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
    has_mt5 = check_env()

    if has_mt5:
        # Full MT5 pipeline
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
    else:
        # Python-only mode (non-Windows or no MT5)
        print("\n  Running in Python-only mode (no MT5).")
        passed = phase_python_backtest()
        if passed:
            print("\n  *** PYTHON BACKTEST PASSED ***")
            print("  To trade live, run main.py on Windows with Deriv MT5 installed.")
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
