@echo off
setlocal

REM Claw Claw quick setup for Windows + PyCharm

if not exist ".venv" (
  py -3.9 -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo Setup complete. In PyCharm, select the .venv interpreter and run claw_claw_full.py or claw_claw/main.py
pause
