@echo off
title Package offline bundle
cd /d "%~dp0"
echo.
echo [1] Wheels only - smaller, target still needs Python installed
echo [2] Wheels + copy venv - larger, same Windows x64 and Python version on target
echo [3] Wheels + venv + node_modules - largest, fully offline MCP
echo.
choice /c 123 /n /m "Select [1/2/3]: "
if errorlevel 3 goto full
if errorlevel 2 goto venv
goto wheels

:wheels
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package_offline.ps1"
goto end

:venv
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package_offline.ps1" -IncludeVenv
goto end

:full
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package_offline.ps1" -IncludeVenv -IncludeNodeModules
goto end

:end
echo.
pause
