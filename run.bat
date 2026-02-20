@echo off
REM ================================================================
REM  Trading Bot - Backtest to Live (Windows / MT5 / Deriv)
REM ================================================================
REM  Usage:
REM    Double-click run.bat          -> Connect MT5, backtest, go live
REM    run.bat --mode backtest       -> Backtest only (no live trading)
REM    run.bat --mode synthetic      -> Use synthetic data (no MT5)
REM    run.bat --symbol "EURUSD"     -> Trade a different symbol
REM    run.bat --login 123 --password xxx --server Deriv-Demo
REM ================================================================

cd /d "%~dp0"

echo.
echo ==============================================================
echo   TRADING BOT - BACKTEST TO LIVE (MT5 / Deriv)
echo ==============================================================
echo.

REM -- Step 1: Find Python ----------------------------------------
echo [1/4] Checking Python installation ...

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
echo [2/4] Setting up virtual environment ...

if not exist ".venv" (
    echo   Creating virtual environment ...
    %PY% -m venv .venv
    echo   Created.
) else (
    echo   Already exists - reusing.
)

REM Use venv python directly (no activate.bat needed)
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

REM -- Step 3: Dependencies ---------------------------------------
echo [3/4] Installing dependencies ...

REM Always reinstall if requirements changed
"%VENV_PY%" -m pip install --quiet --upgrade pip
"%VENV_PY%" -m pip install --quiet -r requirements.txt
echo   Dependencies ready.

REM -- Step 4: Launch bot -----------------------------------------
echo.
echo [4/4] Launching trading bot ...
echo ==============================================================
echo.

"%VENV_PY%" main.py %*

echo.
echo ==============================================================
echo   DONE
echo ==============================================================
pause
