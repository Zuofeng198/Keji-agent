@echo off
chcp 65001 >nul
title 构建科吉 AI 助手

echo ============================================
echo     科吉 AI 助手 — 构建打包脚本
echo ============================================
echo.

cd /d "%~dp0"

:: 检查虚拟环境
if not exist "venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境...
    python -m venv venv
)

echo [1/3] 安装依赖...
"venv\Scripts\pip.exe" install -q pyinstaller 2>nul

echo [2/3] 打包应用程序...
"venv\Scripts\pyinstaller.exe" --onefile --name "科吉AI助手" ^
  --add-data "web;web" ^
  --add-data "knowledge;knowledge" ^
  --add-data "config.yaml;." ^
  --hidden-import "uvicorn" ^
  --hidden-import "uvicorn.logging" ^
  --hidden-import "uvicorn.loops.auto" ^
  --hidden-import "uvicorn.protocols.http.auto" ^
  --hidden-import "chromadb" ^
  --hidden-import "yaml" ^
  --hidden-import "docx" ^
  --hidden-import "openpyxl" ^
  --hidden-import "pdfplumber" ^
  --hidden-import "webview" ^
  --hidden-import "requests" ^
  --hidden-import "fastapi" ^
  --hidden-import "python_multipart" ^
  --hidden-import "py7zr" ^
  --hidden-import "rarfile" ^
  --hidden-import "extract_msg" ^
  --collect-all "chromadb" ^
  --collect-all "uvicorn" ^
  --noconfirm ^
  --log-level "WARN" ^
  desktop.py

if %errorlevel% neq 0 (
    echo [错误] 打包失败！
    pause
    exit /b 1
)

echo [3/3] 创建桌面快捷方式...
powershell -ExecutionPolicy Bypass -File "install_shortcut.ps1"

echo.
echo ============================================
echo     构建完成！
echo     可执行文件: dist\科吉AI助手.exe
echo     桌面快捷方式已创建
echo ============================================
echo.

pause
