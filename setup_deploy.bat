@echo off
title Keji Agent Deploy
cd /d "%~dp0"

where powershell >nul 2>&1
if errorlevel 1 (
    echo ERROR: PowerShell not found.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deploy.ps1"
set ERR=%ERRORLEVEL%
echo.
if %ERR% neq 0 (
    echo Deploy failed. Code: %ERR%
) else (
    echo Deploy OK. Edit .env then run launch_keji.bat
)
pause
exit /b %ERR%
