@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv not found. Run deploy first: setup_deploy.bat
    pause
    exit /b 1
)

powershell -NoProfile -Command "exit ([int](-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)))" 2>nul
if %errorlevel%==0 (
    start "" "http://127.0.0.1:8000/"
    exit /b 0
)

start "" /B "venv\Scripts\pythonw.exe" main.py
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000/"
exit /b 0
