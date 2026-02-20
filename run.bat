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

if not exist "%VENV_PY%" (
    echo   ERROR: venv python not found at %VENV_PY%
    echo   Try deleting the .venv folder and run again.
    pause
    exit /b 1
)

REM -- Step 3: Dependencies ---------------------------------------
echo [3/4] Installing dependencies ...

"%VENV_PY%" -m pip install --quiet --upgrade pip 2>nul
"%VENV_PY%" -m pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo   ERROR: Failed to install base dependencies.
    pause
    exit /b 1
)
echo   Base dependencies ready (numpy, pandas).

REM Try to install MetaTrader5 separately (may fail on Python 3.13+)
echo   Installing MetaTrader5 ...
"%VENV_PY%" -m pip install --quiet MetaTrader5 2>nul
if %errorlevel% neq 0 (
    echo   WARNING: MetaTrader5 package could not be installed.
    echo            This usually means your Python version is too new.
    echo            The bot will run in synthetic/backtest mode only.
    echo            For MT5 support, install Python 3.10 or 3.12.
    echo.
) else (
    echo   MetaTrader5 ready.
)

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
