# 科吉 AI 助手 — 桌面快捷方式安装脚本
# 右键点击此文件，选择「使用 PowerShell 运行」

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "科吉AI助手.lnk"
$ExePath = Join-Path $ProjectDir "dist\科吉AI助手.exe"
$BatPath = Join-Path $ProjectDir "启动科吉.bat"

# 优先使用打包后的 exe，回退到 bat
if (Test-Path $ExePath) {
    $TargetPath = $ExePath
    $Desc = "科吉 AI 助手 v2.0 (桌面应用)"
    $IconLocation = $ExePath + ",0"
} elseif (Test-Path $BatPath) {
    $TargetPath = $BatPath
    $Desc = "科吉 AI 助手 v2.0 (启动脚本)"
    # Bat 文件可以自身作为图标源
    $IconLocation = "$env:SystemRoot\system32\shell32.dll,21"
} else {
    Write-Host "未找到可执行文件！请先运行 build.bat 打包。" -ForegroundColor Red
    pause
    exit 1
}

$WScript = New-Object -ComObject WScript.Shell
$Shortcut = $WScript.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.Description = $Desc
$Shortcut.IconLocation = $IconLocation
$Shortcut.Save()

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  科吉 AI 助手 快捷方式已创建！" -ForegroundColor Green
Write-Host "  桌面快捷方式: $ShortcutPath" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "双击桌面「科吉AI助手」图标即可启动！" -ForegroundColor Yellow

pause
