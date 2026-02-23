@echo off
title SMC Trading Bot - One Click Launcher
echo.
echo  ============================================================
echo   SMC Trading Bot - One Click Launcher
echo   Double-click this file to install everything and run the bot
echo  ============================================================
echo.

REM Try python first, then py launcher
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python "%~dp0start_bot.py"
    goto end
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 "%~dp0start_bot.py"
    goto end
)

echo  ERROR: Python not found!
echo.
echo  Please install Python 3.10 or newer:
echo  https://www.python.org/downloads/
echo.
echo  IMPORTANT: Check "Add Python to PATH" during installation!
echo.

:end
pause
