#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  Trading Bot — One-Click Install & Run
# ═══════════════════════════════════════════════════════════════════
#  Usage:
#    chmod +x run.sh && ./run.sh          # default settings
#    ./run.sh --seed 42                   # reproducible run
#    ./run.sh --balance 250 --target 2000 # custom settings
#
#  This script handles everything:
#    1. Checks for Python 3.10+
#    2. Creates a virtual environment (if needed)
#    3. Installs dependencies (if needed)
#    4. Runs the trading bot calibration
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
PYTHON=""

# ── Find a suitable Python ────────────────────────────────────────
find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                PYTHON="$cmd"
                return 0
            fi
        fi
    done
    return 1
}

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  TRADING BOT — ONE-CLICK INSTALLER"
echo "══════════════════════════════════════════════════════════════"
echo ""

# ── Step 1: Python check ──────────────────────────────────────────
echo "[1/3] Checking Python installation ..."
if ! find_python; then
    echo "  ERROR: Python 3.10+ is required but not found."
    echo "  Install it from https://www.python.org/downloads/"
    exit 1
fi
echo "  Found: $PYTHON ($($PYTHON --version))"

# ── Step 2: Virtual environment ───────────────────────────────────
echo "[2/3] Setting up virtual environment ..."
if [ ! -d "$VENV_DIR" ]; then
    echo "  Creating virtual environment in $VENV_DIR ..."
    $PYTHON -m venv "$VENV_DIR"
    echo "  Created."
else
    echo "  Already exists — reusing."
fi

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── Step 3: Dependencies ──────────────────────────────────────────
echo "[3/3] Installing dependencies ..."
MARKER="$VENV_DIR/.deps_installed"
if [ ! -f "$MARKER" ] || [ requirements.txt -nt "$MARKER" ]; then
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    touch "$MARKER"
    echo "  Installed."
else
    echo "  Already up to date — skipping."
fi

# ── Run the bot ───────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  LAUNCHING TRADING BOT"
echo "══════════════════════════════════════════════════════════════"
echo ""

python main.py "$@"
