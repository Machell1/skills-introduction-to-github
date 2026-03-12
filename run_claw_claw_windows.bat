@echo off
setlocal

REM One-click setup + run for Windows (Python 3.9)
REM Creates .venv, installs dependencies, then launches the bot.

if not exist ".venv" (
  py -3.9 -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo Starting Claw Claw...
python claw_claw\main.py
pause
