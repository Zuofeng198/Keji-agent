@echo off
title Package offline wheels for Python 3.12
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package_offline.ps1" -PythonVersion 3.12
echo.
pause
