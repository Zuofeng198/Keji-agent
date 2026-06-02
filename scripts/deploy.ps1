# Keji Agent - one-click venv setup (Windows)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

function Write-Step([string]$Msg) { Write-Host "`n==> $Msg" -ForegroundColor Cyan }
function Write-Ok([string]$Msg) { Write-Host "OK  $Msg" -ForegroundColor Green }
function Write-Warn2([string]$Msg) { Write-Host "!!  $Msg" -ForegroundColor Yellow }

Write-Host "========================================" -ForegroundColor Green
Write-Host "  Keji Agent - Deploy / Setup venv" -ForegroundColor Green
Write-Host "  $Root" -ForegroundColor DarkGray
Write-Host "========================================" -ForegroundColor Green

# --- Python + venv ---
Write-Step "Create venv (Python 3.10+)"
$venvPy = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    $created = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($ver in @("-3.12", "-3.11", "-3.10", "-3")) {
            & py $ver -m venv (Join-Path $Root "venv") 2>$null
            if (Test-Path $venvPy) { Write-Ok ("venv via py $ver"); $created = $true; break }
        }
    }
    if (-not $created -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -m venv (Join-Path $Root "venv")
        if (Test-Path $venvPy) { Write-Ok "venv via python"; $created = $true }
    }
    if (-not $created) {
        Write-Host "ERROR: Need Python 3.10+. Install from python.org and enable 'py' launcher." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Ok "venv already exists"
}
$pyVer = & $venvPy -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
Write-Ok "Python in venv: $pyVer"

$pip = Join-Path $Root "venv\Scripts\pip.exe"
$req = Join-Path $Root "requirements.txt"
if (-not (Test-Path $req)) {
    Write-Host "ERROR: requirements.txt missing. Copy full project folder." -ForegroundColor Red
    exit 1
}

$wheelsDir = Join-Path $Root "offline_packages\pip_wheels"
$portableVenv = Join-Path $Root "portable_bundle\venv"
$usedPortable = $false

if (Test-Path $portableVenv) {
    Write-Step "Restore venv from portable_bundle (offline copy)"
    if (Test-Path (Join-Path $Root "venv")) { Remove-Item (Join-Path $Root "venv") -Recurse -Force }
    New-Item -ItemType Directory -Path (Join-Path $Root "venv") -Force | Out-Null
    robocopy $portableVenv (Join-Path $Root "venv") /E /NFL /NDL /NJH /NJS | Out-Null
    if (Test-Path $venvPy) {
        Write-Ok "venv restored from portable_bundle - no pip download"
        $usedPortable = $true
        $pip = Join-Path $Root "venv\Scripts\pip.exe"
    } else {
        Write-Warn2 "portable venv copy failed, fallback to pip install"
    }
}

if (-not $usedPortable) {
    Write-Step "Install Python packages"
    & $pip install --upgrade pip wheel -q
    if ((Test-Path $wheelsDir) -and ((Get-ChildItem $wheelsDir -File -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0)) {
        Write-Ok "Using offline wheels: offline_packages\pip_wheels"
        & $pip install --no-index --find-links $wheelsDir -r $req
    } else {
        Write-Warn2 "No offline wheels - downloading from PyPI (need network)"
        & $pip install -r $req --default-timeout=120
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: pip install failed." -ForegroundColor Red
        exit 1
    }
    Write-Ok "Python dependencies installed"
}

# --- Node (optional, for MCP) ---
Write-Step "Node.js / MCP (optional)"
$nmBundle = Join-Path $Root "offline_packages\node_modules_root"
$nmProj = Join-Path $nmBundle "project"
$nmQuack = Join-Path $nmBundle "quack-mcp-main"
if (Test-Path $nmProj) {
    if (Test-Path (Join-Path $Root "node_modules")) { Remove-Item (Join-Path $Root "node_modules") -Recurse -Force }
    robocopy $nmProj (Join-Path $Root "node_modules") /E /NFL /NDL /NJH /NJS | Out-Null
    Write-Ok "node_modules restored from offline bundle"
}
if (Test-Path $nmQuack) {
    $qdst = Join-Path $Root "mcp\quack-mcp-main\node_modules"
    New-Item -ItemType Directory -Path (Split-Path $qdst) -Force | Out-Null
    if (Test-Path $qdst) { Remove-Item $qdst -Recurse -Force }
    robocopy $nmQuack $qdst /E /NFL /NDL /NJH /NJS | Out-Null
    Write-Ok "quack-mcp node_modules restored from offline bundle"
}
if (-not (Test-Path $nmProj)) {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) {
        if (Test-Path (Join-Path $Root "package.json")) {
            Push-Location $Root
            npm install --no-fund --no-audit 2>&1 | Out-Host
            Pop-Location
            Write-Ok "npm install (root)"
        }
        $quack = Join-Path $Root "mcp\quack-mcp-main\package.json"
        if (Test-Path $quack) {
            Push-Location (Join-Path $Root "mcp\quack-mcp-main")
            npm install --no-fund --no-audit 2>&1 | Out-Host
            Pop-Location
            Write-Ok "npm install (quack-mcp)"
        }
    } else {
        Write-Warn2 "Node.js not found - MCP tools may be limited."
    }
}

# --- config ---
Write-Step "Config files"
$cfg = Join-Path $Root "config.yaml"
$cfgEx = Join-Path $Root "config.example.yaml"
if (-not (Test-Path $cfg) -and (Test-Path $cfgEx)) {
    Copy-Item $cfgEx $cfg
    Write-Ok "Created config.yaml from config.example.yaml"
} elseif (Test-Path $cfg) {
    Write-Warn2 "config.yaml already exists - kept"
}

$envFile = Join-Path $Root ".env"
$envEx = Join-Path $Root ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envEx)) {
    Copy-Item $envEx $envFile
    $jwt = [guid]::NewGuid().ToString("N")
    Add-Content -Path $envFile -Value "KEJI_JWT_SECRET=$jwt" -Encoding UTF8
    Write-Ok "Created .env from .env.example (auto KEJI_JWT_SECRET)"
} elseif (Test-Path $envFile) {
    Write-Warn2 ".env already exists - kept"
} else {
    @"
KEJI_API_KEY=
KEJI_JWT_SECRET=$([guid]::NewGuid().ToString('N'))
KEJI_ADMIN_PASSWORD=admin123
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
TAVILY_API_KEY=
FEISHU_APP_ID=
FEISHU_APP_SECRET=
"@ | Set-Content -Path $envFile -Encoding UTF8
    Write-Ok "Created default .env"
}

Write-Warn2 "Edit .env: set DEEPSEEK_API_KEY (required for chat), KEJI_ADMIN_PASSWORD (first admin login)"

# --- data dirs ---
Write-Step "Data directories"
@(
    "data\workspace\shared",
    "data\workspace\users",
    "logs",
    "sessions"
) | ForEach-Object {
    $p = Join-Path $Root $_
    New-Item -ItemType Directory -Path $p -Force | Out-Null
}
Write-Ok "workspace / logs ready"

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  Deploy finished!" -ForegroundColor Green
Write-Host "  1. Edit .env (DEEPSEEK_API_KEY, etc.)" -ForegroundColor White
Write-Host "  2. Start: launch_keji.bat (browser) or run_server.bat (console)" -ForegroundColor White
Write-Host "     CN: setup_deploy.bat = deploy, same as one-click deploy bat" -ForegroundColor DarkGray
Write-Host "  Open: http://127.0.0.1:8000/" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Green

exit 0
