@echo off
title Keji Agent Server
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo.
    echo [ERROR] venv not found. Run setup_deploy.bat first.
    echo.
    pause
    exit /b 1
)

echo Starting... Keep this window open. Press Ctrl+C to stop.
echo Open: http://127.0.0.1:8000/
echo.

"venv\Scripts\python.exe" main.py
echo.
echo Exit code: %ERRORLEVEL%
pause
