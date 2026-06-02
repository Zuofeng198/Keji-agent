# 设置 GitHub 仓库简介（需先安装 gh 并登录）
# 用法：在项目根目录 PowerShell 执行：
#   .\scripts\set_github_about.ps1

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "未找到 gh。请先安装 GitHub CLI：" -ForegroundColor Yellow
    Write-Host "  winget install GitHub.cli"
    Write-Host "安装后关闭并重新打开 PowerShell，再运行："
    Write-Host "  gh auth login"
    Write-Host "  .\scripts\set_github_about.ps1"
    exit 1
}

$desc = "Windows 本地/局域网 AI 助手：Web 对话、多用户与角色权限、团队文件工作区。Python 3.12 一键部署，依赖包已含（Git LFS）。"

gh repo edit Zuofeng198/keji `
    --description $desc `
    --homepage "https://github.com/Zuofeng198/keji#readme" `
    --add-topic ai-agent `
    --add-topic fastapi `
    --add-topic deepseek `
    --add-topic windows `
    --add-topic multi-user

Write-Host "已更新仓库 About / Description。" -ForegroundColor Green
gh repo view Zuofeng198/keji --json description,url
