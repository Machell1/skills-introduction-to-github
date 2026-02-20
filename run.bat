@echo off
REM ================================================================
REM  Trading Bot - One-Click Install and Run (Windows)
REM ================================================================
REM  Usage:  Double-click run.bat  OR  run.bat in a terminal
REM
REM  Handles everything:
REM    1. Checks for Python
REM    2. Creates a virtual environment (if needed)
REM    3. Installs dependencies (if needed)
REM    4. Runs the trading bot calibration
REM ================================================================

cd /d "%~dp0"

echo.
echo ==============================================================
echo   TRADING BOT - ONE-CLICK INSTALLER
echo ==============================================================
echo.

REM -- Step 1: Find Python ----------------------------------------
echo [1/3] Checking Python installation ...

where python >nul 2>&1
if %errorlevel% neq 0 (
    where python3 >nul 2>&1
    if %errorlevel% neq 0 (
        echo   ERROR: Python is not installed or not in PATH.
        echo   Download it from https://www.python.org/downloads/
        echo   Make sure to check "Add Python to PATH" during install.
        pause
        exit /b 1
    )
    set "PY=python3"
) else (
    set "PY=python"
)

%PY% --version
echo.

REM -- Step 2: Virtual environment --------------------------------
echo [2/3] Setting up virtual environment ...

if not exist ".venv" (
    echo   Creating virtual environment ...
    %PY% -m venv .venv
    echo   Created.
) else (
    echo   Already exists - reusing.
)

REM Use venv python/pip directly (no activate.bat needed)
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

REM -- Step 3: Dependencies ---------------------------------------
echo [3/3] Installing dependencies ...

if not exist ".venv\.deps_installed" (
    "%VENV_PY%" -m pip install --quiet --upgrade pip
    "%VENV_PY%" -m pip install --quiet -r requirements.txt
    echo installed> ".venv\.deps_installed"
    echo   Installed.
) else (
    echo   Already up to date - skipping.
)

REM -- Run the bot ------------------------------------------------
echo.
echo ==============================================================
echo   LAUNCHING TRADING BOT
echo ==============================================================
echo.

"%VENV_PY%" main.py %*

echo.
echo ==============================================================
echo   DONE
echo ==============================================================
pause
