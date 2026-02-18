#!/usr/bin/env python3
"""
CLAWBOT MT5 Manager
====================
Detects all MT5 terminals, prefers Deriv, resolves the writable user-data
directory, copies EA source files, and compiles via MetaEditor CLI.
"""

import os
import sys
import shutil
import subprocess
import time
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None  # Not on Windows – handled at call-site

# ── EA source files shipped with the project ──────────────────────────
EA_FILES = [
    "CLAWBOT.mq5",
    "ClawUtils.mqh",
    "ClawStrategy_Trend.mqh",
    "ClawStrategy_Momentum.mqh",
    "ClawStrategy_Session.mqh",
    "ClawRisk.mqh",
    "ClawAudit.mqh",
]

# ── Deriv detection keyword ──────────────────────────────────────────
_DERIV_KEYWORDS = ["deriv"]


def _is_deriv(name: str) -> bool:
    low = name.lower()
    return any(kw in low for kw in _DERIV_KEYWORDS)


# =====================================================================
#  Terminal discovery
# =====================================================================
def find_all_mt5_terminals() -> list:
    """
    Return every MT5 terminal found on the machine.
    Each entry: {"path": Path to terminal64.exe, "name": folder name}
    """
    # env-var override
    env = os.environ.get("MT5_TERMINAL_PATH")
    if env:
        p = Path(env)
        if p.is_file() and p.name.lower() == "terminal64.exe":
            return [{"path": p, "name": f"(env) {p.parent.name}"}]
        if p.is_dir() and (p / "terminal64.exe").exists():
            return [{"path": p / "terminal64.exe", "name": f"(env) {p.name}"}]

    candidate_dirs: list[Path] = []

    # 1. Windows registry
    if winreg:
        for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                key = winreg.OpenKey(
                    hive, r"SOFTWARE\MetaQuotes\Terminal", 0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                )
                i = 0
                while True:
                    try:
                        sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                        val, _ = winreg.QueryValueEx(sub, "InstallPath")
                        if val:
                            candidate_dirs.append(Path(val))
                        winreg.CloseKey(sub)
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except OSError:
                pass

    # 2. Common install locations
    bases = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))),
        Path.home() / "AppData" / "Local",
        Path("C:\\"),
        Path("D:\\"),
    ]
    for base in bases:
        if not base.exists():
            continue
        for fixed in [
            "MetaTrader 5", "Deriv MT5", "Deriv MetaTrader 5",
            "HFM Metatrader 5", "HFM MetaTrader 5",
        ]:
            p = base / fixed
            if p.exists():
                candidate_dirs.append(p)
        try:
            for pattern in ("*MetaTrader*5*", "*Metatrader*5*", "*MT5*", "*Deriv*"):
                for d in base.glob(pattern):
                    if d.is_dir():
                        candidate_dirs.append(d)
        except (PermissionError, OSError):
            pass

    # 3. De-duplicate and resolve terminal64.exe
    seen: set[Path] = set()
    terminals = []
    for cand in candidate_dirs:
        exe = cand / "terminal64.exe"
        if exe.exists():
            r = exe.resolve()
            if r not in seen:
                seen.add(r)
                terminals.append({"path": exe, "name": cand.name})
            continue
        try:
            for sub in cand.rglob("terminal64.exe"):
                r = sub.resolve()
                if r not in seen:
                    seen.add(r)
                    terminals.append({"path": sub, "name": sub.parent.name})
                break
        except (PermissionError, OSError):
            pass

    return terminals


def pick_terminal(terminals: list) -> Path:
    """
    Given a list of terminals, auto-pick Deriv or prompt.
    """
    if not terminals:
        return None
    if len(terminals) == 1:
        return terminals[0]["path"]

    deriv = [t for t in terminals if _is_deriv(t["name"])]
    if len(deriv) == 1:
        print(f"  [AUTO] Selecting Deriv terminal: {deriv[0]['name']}")
        return deriv[0]["path"]

    print("\n  Multiple MT5 terminals detected:")
    for i, t in enumerate(terminals, 1):
        tag = " [DERIV]" if _is_deriv(t["name"]) else ""
        print(f"    {i}. {t['name']}{tag}  ({t['path']})")

    while True:
        raw = input(f"\n  Select terminal [1-{len(terminals)}]: ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(terminals):
                return terminals[idx]["path"]
        except ValueError:
            pass
        print(f"  Enter a number between 1 and {len(terminals)}.")


def find_metaeditor(terminal_path: Path) -> Path:
    editor = terminal_path.parent / "metaeditor64.exe"
    return editor if editor.exists() else None


# =====================================================================
#  Data-path resolution
# =====================================================================
def _is_writable(path: Path) -> bool:
    try:
        tmp = path / ".clawbot_write_test"
        tmp.write_text("ok")
        tmp.unlink()
        return True
    except (OSError, PermissionError):
        return False


def _match_appdata_to_terminal(terminal_dir: Path) -> Path:
    """Walk AppData/Roaming/MetaQuotes/Terminal/ and match origin.txt."""
    appdata = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
    if not appdata.exists():
        return None

    resolved_terminal = terminal_dir.resolve()

    # Pass 1: exact origin.txt match
    for d in appdata.iterdir():
        if not d.is_dir() or not (d / "MQL5").exists():
            continue
        origin = d / "origin.txt"
        if origin.exists():
            try:
                if Path(origin.read_text().strip()).resolve() == resolved_terminal:
                    return d
            except (OSError, ValueError):
                pass

    # Pass 2: most-recently-modified data dir
    dirs = [d for d in appdata.iterdir() if d.is_dir() and (d / "MQL5").exists()]
    if dirs:
        return max(dirs, key=lambda d: d.stat().st_mtime)

    return None


def get_data_path(terminal_path: Path) -> Path:
    """
    Return the *writable* MT5 user-data directory for this terminal.

    Standard install → AppData/Roaming/MetaQuotes/Terminal/<hash>/
    Portable install → same folder as terminal64.exe (only if writable)
    """
    terminal_dir = terminal_path.parent

    # env-var override
    env = os.environ.get("MT5_DATA_PATH")
    if env:
        p = Path(env)
        if p.exists() and (p / "MQL5").exists():
            print(f"  [OK] Using MT5_DATA_PATH: {p}")
            return p
        else:
            print(f"  [WARNING] MT5_DATA_PATH is set but invalid: {env}")

    # 1. Always try AppData first (standard installs, e.g. Program Files)
    appdata = _match_appdata_to_terminal(terminal_dir)
    if appdata:
        return appdata

    # 2. Portable mode: MQL5/ beside terminal AND writable
    if (terminal_dir / "MQL5").exists() and _is_writable(terminal_dir):
        return terminal_dir

    # 3. Not found – give clear instructions
    expected = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
    print(f"  [ERROR] Writable MT5 data directory not found.")
    print()
    print(f"  The install folder ({terminal_dir}) is read-only.")
    print(f"  MT5 creates a writable data folder the first time you open it.")
    print(f"  Expected: {expected}\\<hash>\\")
    print()
    print(f"  Fix:")
    print(f"    1. Open your Deriv MT5 terminal")
    print(f"    2. Log into any account (demo is fine)")
    print(f"    3. Close MT5")
    print(f"    4. Re-run this script")
    return None


# =====================================================================
#  EA installation
# =====================================================================
def install_ea(project_root: Path, data_path: Path) -> bool:
    """Copy EA source files into the MT5 data directory."""
    src_dir = project_root / "MQL5" / "Experts" / "CLAWBOT"
    dst_dir = data_path / "MQL5" / "Experts" / "CLAWBOT"

    if not src_dir.exists():
        print(f"  [ERROR] Source not found: {src_dir}")
        return False

    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"  [ERROR] Cannot write to: {dst_dir}")
        print(f"  This folder is read-only. Check data-path detection above.")
        return False

    copied = 0
    for name in EA_FILES:
        s, d = src_dir / name, dst_dir / name
        if not s.exists():
            print(f"  [WARN] Missing: {name}")
            continue
        if d.exists() and s.stat().st_mtime <= d.stat().st_mtime:
            print(f"  [SKIP] {name} (up to date)")
            continue
        shutil.copy2(s, d)
        print(f"  [COPY] {name}")
        copied += 1

    if copied == 0:
        print("  All files up to date.")
    else:
        print(f"  Installed {copied} file(s) → {dst_dir}")
    return True


# =====================================================================
#  Compilation
# =====================================================================
def _ea_is_current(data_path: Path) -> bool:
    ex5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.ex5"
    mq5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.mq5"
    if not ex5.exists():
        return False
    if mq5.exists() and mq5.stat().st_mtime > ex5.stat().st_mtime:
        return False
    return True


def compile_ea(metaeditor: Path, data_path: Path) -> bool:
    mq5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.mq5"
    if not mq5.exists():
        print(f"  [ERROR] Source not found: {mq5}")
        return False

    print(f"  Compiling {mq5.name} ...")
    log = mq5.parent / "compile.log"

    try:
        subprocess.run(
            [str(metaeditor), f"/compile:{mq5}", f"/log:{log}",
             "/include:" + str(data_path / "MQL5")],
            capture_output=True, text=True, timeout=120,
            cwd=str(metaeditor.parent),
        )
        time.sleep(2)

        ex5 = mq5.with_suffix(".ex5")
        if ex5.exists():
            print(f"  [OK] Compiled: {ex5.name}")
            return True

        print("  [ERROR] No .ex5 produced.")
        if log.exists():
            for line in log.read_text(encoding="utf-16-le", errors="ignore").splitlines():
                if line.strip():
                    print(f"    {line.strip()}")
        return False
    except subprocess.TimeoutExpired:
        print("  [ERROR] Compilation timed out.")
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


# =====================================================================
#  Public entry point
# =====================================================================
def setup_mt5(project_root: Path) -> dict:
    """
    Full setup pipeline.  Returns {"terminal","metaeditor","data_path","compiled"}
    or None on fatal error.
    """
    info = {"terminal": None, "metaeditor": None, "data_path": None, "compiled": False}

    # Step 1 – find terminals
    print("\n[STEP 1] Scanning for MetaTrader 5 ...")
    all_terms = find_all_mt5_terminals()
    if all_terms:
        print(f"  Found {len(all_terms)} installation(s):")
        for t in all_terms:
            tag = " [DERIV]" if _is_deriv(t["name"]) else ""
            print(f"    - {t['name']}{tag}: {t['path']}")
    else:
        print("  [ERROR] No MT5 installations found.")
        print("  Install Deriv MT5 from your Deriv dashboard, open it once, then re-run.")
        return None

    terminal = pick_terminal(all_terms)
    if not terminal:
        return None
    info["terminal"] = terminal
    print(f"  [OK] Using: {terminal}")

    me = find_metaeditor(terminal)
    info["metaeditor"] = me
    if me:
        print(f"  [OK] MetaEditor: {me}")

    # Step 2 – data path
    print("\n[STEP 2] Locating writable data directory ...")
    dp = get_data_path(terminal)
    if not dp:
        return None
    info["data_path"] = dp
    print(f"  [OK] Data path: {dp}")

    # Step 3 – install EA
    print("\n[STEP 3] Installing EA files ...")
    if not install_ea(project_root, dp):
        return None

    # Step 4 – compile
    print("\n[STEP 4] Compiling EA ...")
    if _ea_is_current(dp):
        print("  [OK] CLAWBOT.ex5 is up to date.")
        info["compiled"] = True
    elif me:
        info["compiled"] = compile_ea(me, dp)
        if not info["compiled"]:
            print("  [FALLBACK] Compile manually: open MetaEditor → MQL5/Experts/CLAWBOT/CLAWBOT.mq5 → F7")
    else:
        print("  [WARN] MetaEditor not found. Compile CLAWBOT.mq5 manually (F7).")

    return info
