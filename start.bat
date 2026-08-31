@echo off
REM Run the bot. Double-click this, or make a desktop shortcut to it.
REM Text inside this file stays ASCII: cmd.exe misparses non-ASCII batch
REM source under chcp 65001. The bot's own Korean output is fine.
chcp 65001 >nul
cd /d "%~dp0"
title Chara Bot

if not exist ".env" (
    echo [!] .env not found in %CD%
    echo     Copy .env.example to .env and fill in DISCORD_TOKEN first.
    echo.
    pause
    exit /b 1
)

python bot.py

echo.
echo ---------------------------------------------
echo Bot stopped. Press any key to close.
pause >nul
