@echo off
REM ================================================================
REM  Trading Bot - Real Data Backtest to Live (MT5 / Deriv)
REM ================================================================
REM  Requires: Python 3.9 + Deriv MT5 terminal running
REM
REM  Usage:
REM    Double-click run.bat                                -> default
REM    run.bat --mode backtest                             -> no live
REM    run.bat --symbol "Volatility 75 Index" --timeframe H1
REM    run.bat --login 123 --password xxx --server Deriv-Demo
REM ================================================================

cd /d "%~dp0"

echo.
echo ==============================================================
echo   TRADING BOT - REAL DATA BACKTEST TO LIVE (MT5 / Deriv)
echo ==============================================================
echo.

REM -- Step 1: Find Python 3.9 ------------------------------------
echo [1/4] Checking for Python 3.9 ...

REM Try py launcher first (finds specific versions on Windows)
set "PY="

py -3.9 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY=py -3.9"
    goto :found_python
)

REM Fall back to python in PATH
where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PY=python"
    goto :found_python
)

echo   ERROR: Python is not installed or not in PATH.
echo   Install Python 3.9 from https://www.python.org/downloads/release/python-3913/
echo   Make sure to check "Add Python to PATH" during install.
pause
exit /b 1

:found_python
%PY% --version
echo.

REM -- Step 2: Virtual environment --------------------------------
echo [2/4] Setting up virtual environment ...

if not exist ".venv" (
    echo   Creating virtual environment with Python 3.9 ...
    %PY% -m venv .venv
    if %errorlevel% neq 0 (
        echo   ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo   Created.
) else (
    echo   Already exists - reusing.
)

REM Use venv python directly (no activate.bat needed)
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo   ERROR: venv python not found at %VENV_PY%
    echo   Delete the .venv folder and run again.
    pause
    exit /b 1
)

REM -- Step 3: Dependencies ---------------------------------------
echo [3/4] Installing dependencies ...

"%VENV_PY%" -m pip install --quiet --upgrade pip 2>nul
"%VENV_PY%" -m pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo   ERROR: Failed to install dependencies.
    echo   If MetaTrader5 failed, you need Python 3.9-3.12.
    echo   Your current Python:
    "%VENV_PY%" --version
    echo.
    echo   To fix: install Python 3.9 from
    echo   https://www.python.org/downloads/release/python-3913/
    echo   Then delete .venv and run again.
    pause
    exit /b 1
)
echo   All dependencies ready (numpy, pandas, MetaTrader5).

REM -- Step 4: Launch bot -----------------------------------------
echo.
echo [4/4] Launching trading bot ...
echo ==============================================================
echo   Make sure your Deriv MT5 terminal is running!
echo ==============================================================
echo.

"%VENV_PY%" main.py %*

echo.
echo ==============================================================
echo   DONE
echo ==============================================================
pause
