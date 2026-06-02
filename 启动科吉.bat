@echo off
chcp 65001 >nul
title 科吉 AI 助手

echo ============================================
echo     科吉 AI 助手 v2.0
echo     启动中，请稍候...
echo ============================================

cd /d "%~dp0"

:: 检查虚拟环境
if not exist "venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境，请先运行：python -m venv venv
    pause
    exit /b 1
)

:: 启动桌面模式
"venv\Scripts\python.exe" desktop.py --mode desktop

:: 如果桌面模式失败，提示切换到 Web 模式
if errorlevel 1 (
    echo.
    echo 桌面模式启动失败，是否尝试 Web 模式？（浏览器打开）
    choice /c YN /m "打开 Web 模式"
    if errorlevel 2 exit /b
    start http://127.0.0.1:8000
    "venv\Scripts\python.exe" desktop.py --mode web
)

pause
