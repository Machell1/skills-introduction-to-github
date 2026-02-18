#!/usr/bin/env python3
"""
CLAWBOT MT5 Manager
====================
Handles MetaTrader 5 detection, EA file installation, and compilation.
Supports both standard and portable MT5 installations.
"""

import os
import sys
import shutil
import subprocess
import time
import winreg
from pathlib import Path


# EA source files relative to the CLAWBOT project root
EA_FILES = [
    "CLAWBOT.mq5",
    "ClawUtils.mqh",
    "ClawStrategy_Trend.mqh",
    "ClawStrategy_Momentum.mqh",
    "ClawStrategy_Session.mqh",
    "ClawRisk.mqh",
    "ClawAudit.mqh",
]


def find_mt5_terminal() -> Path:
    """
    Find the MetaTrader 5 terminal installation path.
    Searches: env var, registry, standard install paths.
    Returns the path to terminal64.exe or None.
    """
    # 0. Check environment variable override
    env_path = os.environ.get("MT5_TERMINAL_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists() and p.name.lower() == "terminal64.exe":
            return p
        # Maybe they pointed to the folder
        if p.is_dir() and (p / "terminal64.exe").exists():
            return p / "terminal64.exe"

    candidates = []

    # 1. Check registry (most reliable on Windows)
    try:
        for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            try:
                key = winreg.OpenKey(hive, r"SOFTWARE\MetaQuotes\Terminal", 0,
                                     winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        install_path, _ = winreg.QueryValueEx(subkey, "InstallPath")
                        if install_path:
                            candidates.append(Path(install_path))
                        winreg.CloseKey(subkey)
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except OSError:
                pass
    except Exception:
        pass

    # 2. Standard installation paths
    for base in [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", "")),
        Path.home() / "AppData" / "Local",
        Path("C:\\"),
        Path("D:\\"),
    ]:
        if not base.exists():
            continue
        standard_paths = [
            base / "MetaTrader 5",
            base / "Deriv MT5",
            base / "HFM Metatrader 5",
            base / "HFM MetaTrader 5",
            base / "MetaQuotes" / "Terminal",
        ]
        for p in standard_paths:
            if p.exists():
                candidates.append(p)

        # Glob for any MT5-like folders (covers broker-branded installs)
        try:
            for pattern in ["*MetaTrader*5*", "*Metatrader*5*", "*MT5*", "*mt5*"]:
                for mt5_dir in base.glob(pattern):
                    if mt5_dir.is_dir():
                        candidates.append(mt5_dir)
        except (PermissionError, OSError):
            pass

    # 3. Check each candidate for terminal64.exe
    for candidate in candidates:
        terminal = candidate / "terminal64.exe"
        if terminal.exists():
            return terminal
        # Some installs nest it
        for sub_terminal in candidate.rglob("terminal64.exe"):
            return sub_terminal

    return None


def find_metaeditor(terminal_path: Path) -> Path:
    """Find metaeditor64.exe relative to the terminal."""
    terminal_dir = terminal_path.parent
    editor = terminal_dir / "metaeditor64.exe"
    if editor.exists():
        return editor
    return None


def _is_writable(path: Path) -> bool:
    """Check if we can create files in this directory."""
    try:
        test_file = path / ".clawbot_write_test"
        test_file.write_text("test")
        test_file.unlink()
        return True
    except (OSError, PermissionError):
        return False


def _find_appdata_data_path(terminal_dir: Path) -> Path:
    """
    Search AppData/Roaming/MetaQuotes/Terminal/ for the user data folder
    that corresponds to this terminal installation.
    """
    appdata = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
    if not appdata.exists():
        return None

    # First pass: match by origin.txt (exact match to this terminal)
    for data_dir in appdata.iterdir():
        if not data_dir.is_dir() or not (data_dir / "MQL5").exists():
            continue
        origin = data_dir / "origin.txt"
        if origin.exists():
            try:
                origin_path = origin.read_text().strip()
                if Path(origin_path).resolve() == terminal_dir.resolve():
                    return data_dir
            except (OSError, ValueError):
                pass

    # Second pass: return the most recently modified data folder
    data_dirs = [d for d in appdata.iterdir()
                 if d.is_dir() and (d / "MQL5").exists()]
    if data_dirs:
        return max(data_dirs, key=lambda d: d.stat().st_mtime)

    return None


def get_mt5_data_path(terminal_path: Path) -> Path:
    """
    Find the MT5 user data directory (where we can write MQL5/ files).

    MT5 has two directory layouts:
      1. Standard install: terminal in Program Files, user data in
         AppData/Roaming/MetaQuotes/Terminal/<hash>/
      2. Portable mode: everything in one folder (terminal + MQL5/)

    We ALWAYS prefer the AppData user data path because:
      - Program Files is write-protected without admin
      - The install dir may have MQL5/ but it's read-only
      - AppData is where MT5 actually reads EA files from at runtime
    """
    terminal_dir = terminal_path.parent

    # 1. Always check AppData first (works for standard installs)
    appdata_path = _find_appdata_data_path(terminal_dir)
    if appdata_path:
        return appdata_path

    # 2. Portable mode: MQL5/ next to terminal AND we can write to it
    portable_mql5 = terminal_dir / "MQL5"
    if portable_mql5.exists() and _is_writable(terminal_dir):
        return terminal_dir

    # 3. MQL5/ exists next to terminal but isn't writable (e.g. Program Files)
    #    Create the AppData structure ourselves so MT5 can find it
    if portable_mql5.exists():
        appdata_base = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
        print(f"  [INFO] Install dir ({terminal_dir}) is read-only.")
        print(f"  [INFO] MT5 stores user data in: {appdata_base}")
        print(f"  [INFO] Open MT5 at least once so it creates the data folder,")
        print(f"         then re-run this script.")

    return None


def install_ea_files(project_root: Path, data_path: Path) -> bool:
    """
    Copy CLAWBOT EA files from the project to the MT5 data directory.
    Creates the destination folder if it doesn't exist.
    """
    source_dir = project_root / "MQL5" / "Experts" / "CLAWBOT"
    dest_dir = data_path / "MQL5" / "Experts" / "CLAWBOT"

    if not source_dir.exists():
        print(f"  [ERROR] EA source directory not found: {source_dir}")
        return False

    # Create destination (with permission error handling)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"  [ERROR] Permission denied writing to: {dest_dir}")
        print(f"  This path is read-only (likely Program Files).")
        print(f"  The EA must be installed to your MT5 user data folder instead.")
        print(f"  Open MT5 once, close it, then re-run this script.")
        return False

    # Copy each file
    copied = 0
    for filename in EA_FILES:
        src = source_dir / filename
        dst = dest_dir / filename

        if not src.exists():
            print(f"  [WARNING] Missing source file: {filename}")
            continue

        # Check if file is already up to date
        if dst.exists():
            if src.stat().st_mtime <= dst.stat().st_mtime:
                print(f"  [SKIP] {filename} (up to date)")
                continue

        shutil.copy2(src, dst)
        print(f"  [COPY] {filename}")
        copied += 1

    if copied == 0:
        print("  All EA files are already up to date.")
    else:
        print(f"  Installed {copied} file(s) to {dest_dir}")

    return True


def compile_ea(metaeditor_path: Path, data_path: Path) -> bool:
    """
    Compile CLAWBOT.mq5 using MetaEditor CLI.
    Returns True if compilation succeeds.
    """
    mq5_file = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.mq5"

    if not mq5_file.exists():
        print(f"  [ERROR] Source file not found: {mq5_file}")
        return False

    print(f"  Compiling {mq5_file.name}...")

    # MetaEditor CLI: /compile:"path" /log
    log_file = mq5_file.parent / "compile.log"
    cmd = [
        str(metaeditor_path),
        f"/compile:{mq5_file}",
        f"/log:{log_file}",
        "/include:" + str(data_path / "MQL5"),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(metaeditor_path.parent),
        )

        # Check for the compiled .ex5 file
        ex5_file = mq5_file.with_suffix(".ex5")

        # Give MetaEditor a moment to finish writing
        time.sleep(2)

        if ex5_file.exists():
            print(f"  [OK] Compilation successful: {ex5_file.name}")
            # Show log if available
            if log_file.exists():
                log_content = log_file.read_text(encoding="utf-16-le", errors="ignore")
                if "error" in log_content.lower():
                    print("\n  --- Compiler Warnings ---")
                    for line in log_content.split("\n"):
                        if line.strip():
                            print(f"  {line.strip()}")
                    print("  --- End Warnings ---\n")
            return True
        else:
            print(f"  [ERROR] Compilation failed. No .ex5 file produced.")
            if log_file.exists():
                log_content = log_file.read_text(encoding="utf-16-le", errors="ignore")
                print("\n  --- Compiler Output ---")
                for line in log_content.split("\n"):
                    if line.strip():
                        print(f"  {line.strip()}")
                print("  --- End Output ---\n")
            return False

    except subprocess.TimeoutExpired:
        print("  [ERROR] Compilation timed out after 120 seconds")
        return False
    except FileNotFoundError:
        print(f"  [ERROR] MetaEditor not found at: {metaeditor_path}")
        return False
    except Exception as e:
        print(f"  [ERROR] Compilation failed: {e}")
        return False


def check_compiled_ea(data_path: Path) -> bool:
    """Check if the compiled EA (.ex5) exists and is recent."""
    ex5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.ex5"
    mq5 = data_path / "MQL5" / "Experts" / "CLAWBOT" / "CLAWBOT.mq5"

    if not ex5.exists():
        return False

    # Check if .ex5 is newer than .mq5
    if mq5.exists() and mq5.stat().st_mtime > ex5.stat().st_mtime:
        return False  # Source is newer, needs recompilation

    return True


def setup_mt5(project_root: Path) -> dict:
    """
    Complete MT5 setup pipeline.
    Returns dict with paths or raises SystemExit on failure.
    """
    result = {
        "terminal": None,
        "metaeditor": None,
        "data_path": None,
        "compiled": False,
    }

    print("\n[STEP 1] Detecting MetaTrader 5 installation...")

    terminal = find_mt5_terminal()
    if not terminal:
        print("  [ERROR] MetaTrader 5 not found on this system.")
        print("\n  To fix this:")
        print("  1. Download MT5 from your Deriv account dashboard")
        print("  2. Install it to the default location")
        print("  3. Open MT5 at least once and log in")
        print("  4. Close MT5 and re-run this script")
        print("\n  Or set the MT5_TERMINAL_PATH environment variable:")
        print('  set MT5_TERMINAL_PATH=C:\\path\\to\\terminal64.exe')
        return None

    result["terminal"] = terminal
    print(f"  [OK] Found MT5: {terminal}")

    metaeditor = find_metaeditor(terminal)
    result["metaeditor"] = metaeditor
    if metaeditor:
        print(f"  [OK] Found MetaEditor: {metaeditor}")
    else:
        print("  [WARNING] MetaEditor not found. Manual compilation may be needed.")

    print("\n[STEP 2] Locating MT5 data directory...")

    # Check for manual override first
    env_data_path = os.environ.get("MT5_DATA_PATH")
    if env_data_path:
        override = Path(env_data_path)
        if override.exists() and (override / "MQL5").exists():
            print(f"  [OK] Using MT5_DATA_PATH override: {override}")
            result["data_path"] = override
            data_path = override
        else:
            print(f"  [WARNING] MT5_DATA_PATH set but invalid: {env_data_path}")
            print(f"  (Must contain an MQL5/ subfolder)")
            data_path = get_mt5_data_path(terminal)
    else:
        data_path = get_mt5_data_path(terminal)
    if not data_path:
        appdata_expected = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
        print("  [ERROR] MT5 user data directory not found.")
        print()
        print("  MT5 creates its writable data folder the first time you open it.")
        print("  Expected location: " + str(appdata_expected))
        print()
        print("  To fix this:")
        print("  1. Open your HFM MetaTrader 5 (or any MT5 terminal)")
        print("  2. Log into any account (even demo)")
        print("  3. Close MT5")
        print("  4. Re-run this script")
        print()
        print("  If you've already done this, set the path manually:")
        print('  set MT5_DATA_PATH=C:\\Users\\YourName\\AppData\\Roaming\\MetaQuotes\\Terminal\\<hash>')
        return None

    result["data_path"] = data_path
    print(f"  [OK] Data path: {data_path}")

    print("\n[STEP 3] Installing EA files...")

    if not install_ea_files(project_root, data_path):
        print("  [ERROR] Failed to install EA files.")
        return None

    print("\n[STEP 4] Compiling EA...")

    if check_compiled_ea(data_path):
        print("  [OK] Compiled EA is up to date. Skipping compilation.")
        result["compiled"] = True
    elif metaeditor:
        result["compiled"] = compile_ea(metaeditor, data_path)
        if not result["compiled"]:
            print("\n  [FALLBACK] Automatic compilation failed.")
            print("  Please compile manually:")
            print(f"  1. Open MetaEditor (in MT5: Tools > MetaQuotes Language Editor)")
            print(f"  2. Open: MQL5/Experts/CLAWBOT/CLAWBOT.mq5")
            print(f"  3. Press F7 to compile")
            print(f"  4. Re-run this script after compilation")
    else:
        print("  [WARNING] Cannot auto-compile (MetaEditor not found).")
        print("  Please compile CLAWBOT.mq5 manually in MetaEditor (F7).")

    return result
