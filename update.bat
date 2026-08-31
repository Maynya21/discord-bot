@echo off
REM Pull the latest code, install any new dependencies, then run.
REM Use this after changes are pushed; start.bat alone just runs what is here.
chcp 65001 >nul
cd /d "%~dp0"
title Chara Bot - update

echo == Fetching latest code ==
git pull
if errorlevel 1 (
    echo.
    echo [!] git pull failed. Read the message above.
    echo     Local edits to tracked files are the usual cause.
    echo.
    pause
    exit /b 1
)

echo.
echo == Installing dependencies ==
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo [!] Dependency install failed. Read the message above.
    echo.
    pause
    exit /b 1
)

echo.
echo == Starting ==
python bot.py

echo.
echo ---------------------------------------------
echo Bot stopped. Press any key to close.
pause >nul
