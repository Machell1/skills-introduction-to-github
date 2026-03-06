@echo off
title FNID Portal
cd /d "%~dp0"

echo ============================================
echo        FNID Portal - One Click Launcher
echo ============================================
echo.

:: Create venv if missing
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

:: Activate venv
call .venv\Scripts\activate.bat

:: Install dependencies
echo Installing dependencies...
pip install -e ".[dev]" --quiet 2>nul

:: Launch
echo.
echo Starting FNID Portal at http://localhost:5000
echo Press Ctrl+C to stop.
echo.
python main.py

pause
