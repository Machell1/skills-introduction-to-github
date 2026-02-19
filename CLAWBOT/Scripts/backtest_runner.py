#!/usr/bin/env python3
"""
CLAWBOT Backtest Runner
========================
Generates a tester config, launches MT5 in Strategy-Tester CLI mode,
waits for completion (ShutdownTerminal=1), and locates result files.

Report locations (MT5 writes to different places depending on context):
  FILE_COMMON  -> Terminal/Common/Files/
  Tester       -> Tester/Agent-xxx/MQL5/Files/  (sandbox)
  Live/Normal  -> {data_path}/MQL5/Files/
"""

import os
import re
import time
import shutil
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
#  Report discovery — search EVERY possible location
# =====================================================================
def _check_dir_for_reports(directory: Path, found: dict):
    """Helper: check a directory for CLAWBOT report CSVs."""
    if not directory.exists():
        return
    for name, key in [
        (AUDIT_REPORT, "audit_report"),
        (AUDIT_PASS,   "pass_report"),
        (AUDIT_WEAK,   "weakness_report"),
    ]:
        if key not in found:
            p = directory / name
            if p.exists():
                found[key] = p


def _get_common_files_path() -> Path:
    """Return the MT5 FILE_COMMON directory."""
    return Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files"


def find_reports(data_path: Path) -> dict:
    """Search EVERY possible location for CLAWBOT reports."""
    found = {}

    # 1. FILE_COMMON area (our EA now writes here)
    common = _get_common_files_path()
    _check_dir_for_reports(common / "CLAWBOT_Reports", found)
    _check_dir_for_reports(common, found)

    # 2. Standard MQL5/Files/ (live mode writes here)
    _check_dir_for_reports(data_path / "MQL5" / "Files" / "CLAWBOT_Reports", found)
    _check_dir_for_reports(data_path / "MQL5" / "Files", found)

    # 3. Tester agent sandboxes (non-FILE_COMMON tester writes here)
    tester = data_path / "Tester"
    if tester.exists():
        try:
            for agent_dir in tester.iterdir():
                if agent_dir.is_dir() and agent_dir.name.startswith("Agent"):
                    _check_dir_for_reports(agent_dir / "MQL5" / "Files" / "CLAWBOT_Reports", found)
                    _check_dir_for_reports(agent_dir / "MQL5" / "Files", found)
        except (PermissionError, OSError):
            pass

    # 4. MT5-generated HTML report (the tester's own HTML output)
    if tester.exists():
        for htm in tester.rglob("CLAWBOT*.htm"):
            found.setdefault("mt5_report", htm)
            break

    # 5. Other alternate locations
    for alt_dir in [
        data_path / "CLAWBOT_Reports",
        data_path / "Tester" / "CLAWBOT_Reports",
    ]:
        if alt_dir.exists():
            for csv in alt_dir.glob("*.csv"):
                if "Pass" in csv.name:
                    found.setdefault("pass_report", csv)
                elif "Weakness" in csv.name:
                    found.setdefault("weakness_report", csv)
                elif "Backtest" in csv.name:
                    found.setdefault("audit_report", csv)

    # 6. Deep recursive search if nothing found yet
    if not found:
        # Search under data_path
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
        # Search under Common files
        if common.exists():
            try:
                for csv in common.rglob("CLAWBOT_*_Report.csv"):
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
    """Remove old CLAWBOT reports from ALL known locations."""
    dirs_to_clean = [
        data_path / "MQL5" / "Files" / "CLAWBOT_Reports",
        _get_common_files_path() / "CLAWBOT_Reports",
        _get_common_files_path(),
    ]
    # Also clean tester agent sandboxes
    tester = data_path / "Tester"
    if tester.exists():
        try:
            for agent_dir in tester.iterdir():
                if agent_dir.is_dir() and agent_dir.name.startswith("Agent"):
                    dirs_to_clean.append(agent_dir / "MQL5" / "Files" / "CLAWBOT_Reports")
                    dirs_to_clean.append(agent_dir / "MQL5" / "Files")
        except (PermissionError, OSError):
            pass

    for d in dirs_to_clean:
        if not d.exists():
            continue
        for f in d.glob("CLAWBOT_*.csv"):
            try:
                f.unlink()
                print(f"  [CLEAN] {f}")
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
#  MT5 log parser — extract results from Experts/Tester journal
# =====================================================================
def parse_mt5_logs(data_path: Path) -> dict:
    """
    Parse MT5 Experts and Tester logs for CLAWBOT output.
    The EA prints results via Print() in OnTester() and LogMessage() in OnDeinit().
    This is a reliable fallback when CSV files can't be found.
    """
    results = {}
    log_dirs = [
        data_path / "Tester" / "logs",
        data_path / "logs",
    ]
    # Also check tester agent log directories
    tester = data_path / "Tester"
    if tester.exists():
        try:
            for agent_dir in tester.iterdir():
                if agent_dir.is_dir() and agent_dir.name.startswith("Agent"):
                    log_dirs.append(agent_dir / "logs")
        except (PermissionError, OSError):
            pass

    all_lines = []
    for log_dir in log_dirs:
        if not log_dir.exists():
            continue
        logs = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        for log_file in logs[:3]:
            try:
                content = log_file.read_text(encoding="utf-16-le", errors="ignore")
            except Exception:
                try:
                    content = log_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
            for line in content.splitlines():
                if "CLAWBOT" in line or "AUDIT" in line:
                    all_lines.append(line.strip())

    if not all_lines:
        return None

    # Parse known patterns from the EA's Print/LogMessage output
    for line in all_lines:
        # From GetReportSummary(): "Trades: 123 | Win Rate: 85.0% | PF: 2.10 | ..."
        m = re.search(r'Trades:\s*(\d+)\s*\|\s*Win Rate:\s*([\d.]+)%\s*\|\s*PF:\s*([\d.]+)\s*\|\s*Net:\s*\$([-\d.]+)\s*\|\s*MaxDD:\s*([\d.]+)%\s*\|\s*Sharpe:\s*([-\d.]+)', line)
        if m:
            results["total_trades"]    = int(m.group(1))
            results["win_rate"]        = float(m.group(2))
            results["profit_factor"]   = float(m.group(3))
            results["net_profit"]      = float(m.group(4))
            results["max_drawdown_pct"] = float(m.group(5))
            results["sharpe_ratio"]    = float(m.group(6))
            results["source"] = "mt5_log"
            break

        # From threshold check: "Win Rate: 60.0% (need >=55.0%) -> PASS"
        m = re.search(r'Win Rate:\s*([\d.]+)%.*?(PASS|FAIL)', line)
        if m and "win_rate" not in results:
            results["win_rate"] = float(m.group(1))
            results["win_rate_passed"] = m.group(2) == "PASS"

        # "Total Trades: 123"
        m = re.search(r'Total Trades:\s*(\d+)', line)
        if m and "total_trades" not in results:
            results["total_trades"] = int(m.group(1))

        # OVERALL: PASSED or FAILED
        if "OVERALL: PASSED" in line:
            results["overall_passed"] = True
        elif "OVERALL: FAILED" in line:
            results["overall_passed"] = False

        # "CLAWBOT BACKTEST COMPLETE"
        if "BACKTEST COMPLETE" in line:
            results["backtest_ran"] = True

        # Fitness Score
        m = re.search(r'Fitness Score:\s*([\d.]+)', line)
        if m:
            results["fitness"] = float(m.group(1))

    # Also capture raw CLAWBOT log lines for display
    results["_raw_lines"] = all_lines[-30:]

    return results if len(results) > 1 else None


# =====================================================================
#  Pre-flight & diagnostics
# =====================================================================
def preflight_check(data_path: Path, metaeditor: Path = None) -> bool:
    """Verify EA is compiled. Auto-recompile if MetaEditor is available.
    Returns True if ready, False if fatal.
    """
    ex5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.ex5"
    mq5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.mq5"

    if not mq5.exists():
        print(f"  [ERROR] EA source not found: {mq5}")
        return False

    needs_compile = False
    if not ex5.exists():
        print("  [!] CLAWBOT.ex5 not found — must compile.")
        needs_compile = True
    elif mq5.stat().st_mtime > ex5.stat().st_mtime:
        print("  [!] Source code is newer than .ex5 — recompiling.")
        needs_compile = True

    if needs_compile and metaeditor and metaeditor.exists():
        print(f"  [AUTO] Compiling via MetaEditor ...")
        log = mq5.parent / "compile.log"
        include_dir = data_path / "MQL5"
        # Use a single command string with explicit quoting so that paths
        # with spaces (e.g. "Sanique Richards") are handled correctly.
        cmd = f'"{metaeditor}" /compile:"{mq5}" /log:"{log}" /include:"{include_dir}"'
        try:
            subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120,
                cwd=str(metaeditor.parent),
            )
            time.sleep(3)
            if ex5.exists() and ex5.stat().st_mtime >= mq5.stat().st_mtime:
                print(f"  [OK] Compiled successfully: {ex5.name} ({ex5.stat().st_size:,} bytes)")
                return True
            else:
                print("  [ERROR] Compilation failed. MetaEditor did not produce .ex5")
                # Try to read compile log with multiple encodings
                if log.exists():
                    for enc in ["utf-16-le", "utf-16", "utf-8", "latin-1"]:
                        try:
                            lines = [l.strip() for l in log.read_text(encoding=enc, errors="ignore").splitlines() if l.strip()]
                            if lines:
                                print(f"  Compile log:")
                                for line in lines[-15:]:
                                    print(f"    {line}")
                                break
                        except Exception:
                            continue
                print()
                print("  You must compile manually:")
                print("    1. Open MetaEditor (press F4 in MT5)")
                print("    2. File -> Open -> MQL5/Experts/CLAWBOT/CLAWBOT.mq5")
                print("    3. Press F7 to compile")
                print("    4. Close MetaEditor, then re-run main.py")
                return False
        except Exception as e:
            print(f"  [ERROR] Auto-compile failed: {e}")

    if needs_compile:
        print()
        print("  MetaEditor not found for auto-compile. You must compile manually:")
        print("    1. Open MetaEditor (press F4 in MT5)")
        print("    2. File -> Open -> MQL5/Experts/CLAWBOT/CLAWBOT.mq5")
        print("    3. Press F7 to compile")
        print("    4. Close MetaEditor, then re-run main.py")
        return False

    print(f"  [OK] CLAWBOT.ex5 ready ({ex5.stat().st_size:,} bytes)")
    return True


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


def run_backtest(
    terminal: Path,
    data_path: Path,
    config_template: Path,
    *,
    symbol="XAUUSD",
    from_date=None, to_date=None,
    deposit=10000, leverage=100,
    timeout_min=120,
    metaeditor: Path = None,
) -> dict:
    """Full pipeline: check → config → clean → launch → wait → find reports."""

    # Pre-flight: verify EA is compiled (auto-compile if possible)
    print("\n[PRE-FLIGHT] Checking EA compilation ...")
    if not preflight_check(data_path, metaeditor):
        print("\n  [FATAL] Cannot proceed without compiled EA.")
        return None

    # Generate tester config
    print("\n[STEP 5] Writing tester configuration ...")
    cfg = data_path / "tester" / "CLAWBOT_tester.ini"
    generate_tester_config(
        config_template, cfg,
        symbol=symbol, from_date=from_date, to_date=to_date,
        deposit=deposit, leverage=leverage,
    )
    print(f"  [OK] {cfg}")

    # If the data path has spaces, also copy INI to terminal directory
    # (some MT5 builds have trouble parsing /config: paths with spaces)
    terminal_dir = terminal.parent
    cfg_for_launch = cfg
    if " " in str(cfg):
        alt_cfg = terminal_dir / "CLAWBOT_tester.ini"
        try:
            shutil.copy2(cfg, alt_cfg)
            cfg_for_launch = alt_cfg
            print(f"  [OK] Also copied to: {alt_cfg} (avoids space-in-path issue)")
        except (PermissionError, OSError):
            pass  # Use original path

    # Print config contents for debugging
    print(f"\n  --- Tester Config ---")
    for line in cfg.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith(";"):
            print(f"    {line}")
    print(f"  ---------------------")

    # Clean old reports from ALL locations
    print("\n[STEP 6] Cleaning old reports ...")
    clean_old_reports(data_path)

    # Launch MT5
    print("\n[STEP 7] Launching MT5 Strategy Tester ...")
    if is_mt5_running():
        print("  [WARN] MT5 already running – closing it first ...")
        _kill_mt5()
        if is_mt5_running():
            print("  [ERROR] Cannot close MT5. Please close it manually and re-run.")
            return None

    try:
        cmd = [str(terminal), f"/config:{cfg_for_launch}"]
        print(f"  Command: {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            cwd=str(terminal_dir),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print(f"  [OK] Launched (PID {proc.pid})")
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

    # Wait for backtest to complete
    print("\n[STEP 8] Waiting for backtest ...")
    wait_for_mt5(timeout_min)
    # Give MT5 extra time to flush file writes
    time.sleep(10)

    # Collect results
    print("\n[STEP 9] Collecting results ...")
    reports = find_reports(data_path)

    if reports:
        print(f"  Found {len(reports)} report(s):")
        for k, v in reports.items():
            print(f"    {k}: {v}")
        return reports

    # No CSV/HTML reports found — try parsing MT5 logs as fallback
    print("  [WARN] No report files found. Checking MT5 logs ...")
    log_results = parse_mt5_logs(data_path)

    if log_results and log_results.get("backtest_ran"):
        print("  [OK] Found backtest results in MT5 logs!")
        # Store log results so Phase 3 can use them
        reports["log_results"] = log_results
        if "_raw_lines" in log_results:
            print()
            for line in log_results["_raw_lines"][-10:]:
                print(f"    {line}")
        return reports

    # Nothing at all — show diagnostics
    print("  [ERROR] No reports and no log output found.")
    print()
    print("  --- DIAGNOSTICS ---")

    ex5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.ex5"
    if not ex5.exists():
        print("  [!] CLAWBOT.ex5 NOT FOUND")
    else:
        print(f"  [OK] CLAWBOT.ex5 exists ({ex5.stat().st_size:,} bytes)")

    # Show searched locations
    common = _get_common_files_path()
    print()
    print("  Searched locations:")
    print(f"    1. Common:  {common / 'CLAWBOT_Reports'} -> {'EXISTS' if (common / 'CLAWBOT_Reports').exists() else 'not found'}")
    print(f"    2. Files:   {data_path / 'MQL5' / 'Files' / 'CLAWBOT_Reports'} -> {'EXISTS' if (data_path / 'MQL5' / 'Files' / 'CLAWBOT_Reports').exists() else 'not found'}")
    tester_dir = data_path / "Tester"
    if tester_dir.exists():
        agents = [d for d in tester_dir.iterdir() if d.is_dir() and d.name.startswith("Agent")]
        for a in agents:
            af = a / "MQL5" / "Files"
            print(f"    3. Agent:   {af} -> {'EXISTS' if af.exists() else 'not found'}")
        if not agents:
            print("    3. Agents:  (none found - tester never ran)")
    else:
        print("    3. Tester:  (directory does not exist)")

    # Show journal
    journal = read_tester_journal(data_path)
    if journal:
        print()
        print("  Recent journal entries:")
        for line in journal[-20:]:
            print(f"    {line}")
    else:
        print()
        print("  [!] No journal logs found. The Strategy Tester likely never started.")
        print("      This usually means MT5 was not logged into an account.")

    print()
    print("  TO FIX THIS:")
    print("    1. Open Deriv MT5 manually")
    print("    2. Log into your Deriv account (demo is fine)")
    print("    3. Open a XAUUSD H1 chart (to download history)")
    print("    4. Then in MT5: View -> Strategy Tester (Ctrl+R)")
    print("    5. Select EA: CLAWBOT\\CLAWBOT")
    print("    6. Set: XAUUSD, H1, 2-year range, $10000")
    print("    7. Click Start and wait for it to finish")
    print("    8. Then re-run main.py (it will find the reports)")

    return reports
