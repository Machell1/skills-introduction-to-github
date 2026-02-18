#!/usr/bin/env python3
"""
CLAWBOT Backtest Runner
========================
Generates a tester config, launches MT5 in Strategy-Tester CLI mode,
waits for completion (ShutdownTerminal=1), and locates result files.
"""

import os
import re
import time
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

# Report filenames produced by the EA audit module
AUDIT_REPORT = "CLAWBOT_Backtest_Report.csv"
AUDIT_PASS   = "CLAWBOT_Pass_Report.csv"
AUDIT_WEAK   = "CLAWBOT_Weakness_Report.csv"


# =====================================================================
#  Tester configuration
# =====================================================================
def generate_tester_config(
    template: Path,
    output: Path,
    *,
    symbol="XAUUSD", period="H1",
    from_date=None, to_date=None,
    deposit=10000, leverage=100,
) -> Path:
    if to_date is None:
        to_date = datetime.now().strftime("%Y.%m.%d")
    if from_date is None:
        from_date = (datetime.now() - timedelta(days=730)).strftime("%Y.%m.%d")

    text = template.read_text().format(
        symbol=symbol, period=period,
        from_date=from_date, to_date=to_date,
        deposit=deposit, leverage=leverage,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    return output


# =====================================================================
#  Process helpers
# =====================================================================
def is_mt5_running() -> bool:
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq terminal64.exe"],
            capture_output=True, text=True, timeout=10,
        )
        return "terminal64.exe" in r.stdout.lower()
    except Exception:
        return False


def _kill_mt5():
    """Try to close any running MT5 gracefully."""
    try:
        subprocess.run(["taskkill", "/IM", "terminal64.exe"], timeout=10,
                       capture_output=True)
        time.sleep(5)
    except Exception:
        pass


# =====================================================================
#  Report discovery
# =====================================================================
def find_reports(data_path: Path) -> dict:
    """Search for CLAWBOT report files in the MT5 data tree."""
    found = {}

    # Primary: EA writes via FileOpen() -> MQL5/Files/
    files_dir = data_path / "MQL5" / "Files" / "CLAWBOT_Reports"
    for name, key in [
        (AUDIT_REPORT, "audit_report"),
        (AUDIT_PASS,   "pass_report"),
        (AUDIT_WEAK,   "weakness_report"),
    ]:
        p = files_dir / name
        if p.exists():
            found[key] = p

    # Also search MQL5/Files/ root (EA may write there without subfolder)
    files_root = data_path / "MQL5" / "Files"
    if files_root.exists():
        for name, key in [
            (AUDIT_REPORT, "audit_report"),
            (AUDIT_PASS,   "pass_report"),
            (AUDIT_WEAK,   "weakness_report"),
        ]:
            if key not in found:
                p = files_root / name
                if p.exists():
                    found[key] = p

    # MT5-generated HTML report (from tester Report= setting)
    tester = data_path / "Tester"
    if tester.exists():
        for htm in tester.rglob("CLAWBOT*.htm"):
            found.setdefault("mt5_report", htm)
            break

    # Also check for MT5 HTML in the report subfolder
    report_dir = data_path / "CLAWBOT_Reports"
    if report_dir.exists():
        for htm in report_dir.glob("*.htm"):
            found.setdefault("mt5_report", htm)
            break

    # Alternate folder (CSV reports)
    for alt in [
        data_path / "CLAWBOT_Reports",
        data_path / "Tester" / "CLAWBOT_Reports",
    ]:
        if alt.exists():
            for csv in alt.glob("*.csv"):
                if "Pass" in csv.name:
                    found.setdefault("pass_report", csv)
                elif "Weakness" in csv.name:
                    found.setdefault("weakness_report", csv)
                elif "Backtest" in csv.name:
                    found.setdefault("audit_report", csv)

    # Deep search: find any CLAWBOT CSV anywhere under data_path
    if not found:
        try:
            for csv in data_path.rglob("CLAWBOT_*_Report.csv"):
                if "Pass" in csv.name:
                    found.setdefault("pass_report", csv)
                elif "Weakness" in csv.name:
                    found.setdefault("weakness_report", csv)
                elif "Backtest" in csv.name:
                    found.setdefault("audit_report", csv)
        except (PermissionError, OSError):
            pass

    return found


def clean_old_reports(data_path: Path):
    d = data_path / "MQL5" / "Files" / "CLAWBOT_Reports"
    if not d.exists():
        return
    for f in d.glob("CLAWBOT_*.csv"):
        try:
            f.unlink()
            print(f"  [CLEAN] {f.name}")
        except OSError:
            pass


# =====================================================================
#  MT5 HTML report parser (fallback)
# =====================================================================
def parse_mt5_html(path: Path) -> dict:
    if not path or not path.exists():
        return None
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    m = {}
    for label, key, conv in [
        (r"Total Net Profit",  "net_profit",      float),
        (r"Total Trades",      "total_trades",    int),
        (r"Profit Factor",     "profit_factor",   float),
        (r"Sharpe Ratio",      "sharpe_ratio",    float),
    ]:
        match = re.search(label + r'.*?>([-\d\s.]+)<', html)
        if match:
            m[key] = conv(match.group(1).replace(" ", ""))

    # Drawdown %
    match = re.search(r'Maximal Drawdown.*?>([\d.]+)%', html)
    if match:
        m["max_drawdown_pct"] = float(match.group(1))

    # Win %
    match = re.search(r'Profit Trades.*?>(\d+).*?of total.*?>([\d.]+)%', html, re.DOTALL)
    if match:
        m["win_trades"] = int(match.group(1))
        m["win_rate"]   = float(match.group(2))

    return m if m else None


# =====================================================================
#  Main backtest pipeline
# =====================================================================
def wait_for_mt5(timeout_min: int = 120) -> bool:
    """Block until MT5 exits (ShutdownTerminal=1 in the config)."""
    print(f"  Waiting for MT5 to finish (timeout {timeout_min} min) ...")

    # wait for it to start
    for _ in range(30):
        if is_mt5_running():
            break
        time.sleep(1)

    start = time.time()
    last_msg = start
    while time.time() - start < timeout_min * 60:
        if not is_mt5_running():
            elapsed = int(time.time() - start)
            print(f"\n  [OK] MT5 closed after {elapsed // 60}m {elapsed % 60}s")
            return True
        if time.time() - last_msg >= 30:
            e = int(time.time() - start)
            print(f"  ... running ({e // 60}m {e % 60}s)")
            last_msg = time.time()
        time.sleep(5)

    print(f"\n  [TIMEOUT] Exceeded {timeout_min} min.")
    return False


def preflight_check(data_path: Path) -> list:
    """Verify EA is compiled and ready before launching backtest."""
    issues = []
    ex5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.ex5"
    mq5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.mq5"

    if not mq5.exists():
        issues.append("EA source not installed: " + str(mq5))
    if not ex5.exists():
        issues.append("EA not compiled: CLAWBOT.ex5 missing. Compile in MetaEditor (F7) first.")
    elif mq5.exists() and mq5.stat().st_mtime > ex5.stat().st_mtime:
        issues.append("EA source is newer than compiled .ex5. Recompile in MetaEditor (F7).")

    return issues


def read_tester_journal(data_path: Path) -> list:
    """Read recent MT5 tester journal logs for error diagnostics."""
    lines = []
    for log_dir in [data_path / "Tester" / "logs", data_path / "logs"]:
        if not log_dir.exists():
            continue
        logs = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        for log_file in logs[:2]:
            try:
                content = log_file.read_text(encoding="utf-16-le", errors="ignore")
            except Exception:
                try:
                    content = log_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
            for line in content.splitlines()[-50:]:
                stripped = line.strip()
                if stripped:
                    lines.append(stripped)
    return lines


def run_backtest(
    terminal: Path,
    data_path: Path,
    config_template: Path,
    *,
    symbol="XAUUSD",
    from_date=None, to_date=None,
    deposit=10000, leverage=100,
    timeout_min=120,
) -> dict:
    """Full pipeline: config → clean → launch → wait → find reports."""

    # Pre-flight check
    issues = preflight_check(data_path)
    if issues:
        print("\n[PRE-FLIGHT CHECK]")
        for issue in issues:
            print(f"  [WARN] {issue}")
        print("  The backtest may fail. Continuing anyway ...")
        print()

    print("\n[STEP 5] Writing tester configuration ...")
    cfg = data_path / "tester" / "CLAWBOT_tester.ini"
    generate_tester_config(
        config_template, cfg,
        symbol=symbol, from_date=from_date, to_date=to_date,
        deposit=deposit, leverage=leverage,
    )
    print(f"  [OK] {cfg}")

    print("\n[STEP 6] Cleaning old reports ...")
    clean_old_reports(data_path)

    print("\n[STEP 7] Launching MT5 Strategy Tester ...")
    if is_mt5_running():
        print("  [WARN] MT5 already running – closing it first ...")
        _kill_mt5()
        if is_mt5_running():
            print("  [ERROR] Cannot close MT5. Please close it manually and re-run.")
            return None

    try:
        proc = subprocess.Popen(
            [str(terminal), f"/config:{cfg}"],
            cwd=str(terminal.parent),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print(f"  [OK] Launched (PID {proc.pid})")
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

    print("\n[STEP 8] Waiting for backtest ...")
    wait_for_mt5(timeout_min)
    time.sleep(3)

    print("\n[STEP 9] Collecting results ...")
    reports = find_reports(data_path)
    if reports:
        print(f"  Found {len(reports)} report(s):")
        for k, v in reports.items():
            print(f"    {k}: {v.name}")
    else:
        print("  [WARN] No reports found.")
        print()
        print("  --- DIAGNOSTICS ---")

        # Check if .ex5 exists
        ex5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.ex5"
        if not ex5.exists():
            print("  [!] CLAWBOT.ex5 NOT FOUND - EA was never compiled.")
            print("      Open MetaEditor -> MQL5/Experts/CLAWBOT/CLAWBOT.mq5 -> press F7")
        else:
            print(f"  [OK] CLAWBOT.ex5 exists ({ex5.stat().st_size:,} bytes)")

        # Check tester journal for errors
        journal = read_tester_journal(data_path)
        if journal:
            print()
            print("  Recent tester journal entries:")
            for line in journal[-15:]:
                print(f"    {line}")
        else:
            print("  [!] No tester journal logs found.")
            print("      MT5 may not have started the backtest at all.")

        # Suggest common fixes
        print()
        print("  Common causes:")
        print("    1. EA not compiled (.ex5 missing) -> Compile in MetaEditor (F7)")
        print("    2. No historical data for the symbol -> Open MT5, load XAUUSD chart first")
        print("    3. Symbol name mismatch -> Check if your broker uses XAUUSDm or #XAUUSD")
        print("    4. Not logged into any account -> Log into Deriv MT5 (demo is fine)")

    return reports
