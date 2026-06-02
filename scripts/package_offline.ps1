# Build offline install bundle on THIS machine (run once before copying to other PCs)
# Output: offline_packages/pip_wheels  (+ optional portable_bundle/venv, node_modules)
param(
    [switch]$IncludeVenv,
    [switch]$IncludeNodeModules,
    [string]$PythonVersion = ""   # e.g. 3.12 — empty = use current venv
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

function Write-Step([string]$Msg) { Write-Host "`n==> $Msg" -ForegroundColor Cyan }
function Write-Ok([string]$Msg) { Write-Host "OK  $Msg" -ForegroundColor Green }
function Write-Warn2([string]$Msg) { Write-Host "!!  $Msg" -ForegroundColor Yellow }

Write-Host "========================================" -ForegroundColor Green
Write-Host "  Keji - Package offline bundle" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

$req = Join-Path $Root "requirements.txt"
$pipExe = $null
$pyLabel = ""

if ($PythonVersion) {
    $pyVerFlag = "-$PythonVersion"
    if ($PythonVersion -notmatch '^3\.\d+$') { $pyVerFlag = "-$PythonVersion" }
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: py launcher not found." -ForegroundColor Red
        exit 1
    }
    $pipExe = "py"
    $pyLabel = $pyVerFlag
    Write-Ok "Target wheel Python: $PythonVersion (via py $pyVerFlag)"
} else {
    $venvPy = Join-Path $Root "venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Write-Host "ERROR: venv not found. Run setup_deploy.bat or pass -PythonVersion 3.12" -ForegroundColor Red
        exit 1
    }
    $pipExe = Join-Path $Root "venv\Scripts\pip.exe"
    $pyLabel = "venv"
}
if (-not (Test-Path $req)) {
    Write-Host "ERROR: requirements.txt missing." -ForegroundColor Red
    exit 1
}

$outRoot = Join-Path $Root "offline_packages"
$wheels = Join-Path $outRoot "pip_wheels"
if (Test-Path $wheels) { Remove-Item (Join-Path $wheels "*") -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Path $wheels -Force | Out-Null

Write-Step "Download pip wheels (offline install cache)"
if ($PythonVersion) {
    & py $pyLabel -m pip download -r $req -d $wheels --default-timeout=120
} else {
    & $pipExe download -r $req -d $wheels --default-timeout=120
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip download failed." -ForegroundColor Red
    exit 1
}
$wc = (Get-ChildItem $wheels -File | Measure-Object).Count
$wmb = [math]::Round(((Get-ChildItem $wheels -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Ok "$wc wheel files, about ${wmb} MB"

# Python version hint for target machine
if ($PythonVersion) {
    $pyInfo = & py $pyLabel -c "import sys,platform; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}'); print(platform.machine())"
} else {
    $venvPy = Join-Path $Root "venv\Scripts\python.exe"
    $pyInfo = & $venvPy -c "import sys,platform; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}'); print(platform.machine())"
}
$lines = $pyInfo -split "`n"
$meta = @(
    "python_version=$($lines[0])",
    "platform=$($lines[1])",
    "built_on=$env:COMPUTERNAME",
    "built_at=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
)
$meta | Set-Content (Join-Path $outRoot "BUILD_INFO.txt") -Encoding UTF8
Write-Ok "BUILD_INFO.txt written (target needs same Python major.minor, 64-bit)"

if ($IncludeVenv) {
    if ($PythonVersion) {
        Write-Warn2 "-IncludeVenv ignored when -PythonVersion is set (use matching venv on target)"
    }
}
if ($IncludeVenv -and -not $PythonVersion) {
    Write-Step "Copy venv to portable_bundle (same OS + same Python version required on target)"
    $bundle = Join-Path $Root "portable_bundle\venv"
    if (Test-Path $bundle) { Remove-Item $bundle -Recurse -Force }
    New-Item -ItemType Directory -Path (Split-Path $bundle) -Force | Out-Null
    robocopy (Join-Path $Root "venv") $bundle /E /XD __pycache__ /NFL /NDL /NJH /NJS | Out-Null
    Copy-Item (Join-Path $outRoot "BUILD_INFO.txt") (Join-Path $Root "portable_bundle\BUILD_INFO.txt") -Force
    $vmb = [math]::Round(((Get-ChildItem $bundle -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
    Write-Ok "portable_bundle/venv copied, about ${vmb} MB"
    Write-Host "!!  Target path should match, e.g. always D:\keji. Different drive/path may break venv." -ForegroundColor Yellow
}

if ($IncludeNodeModules) {
    Write-Step "Copy node_modules for offline MCP"
    $nmRoot = Join-Path $outRoot "node_modules_root"
    if (Test-Path (Join-Path $Root "node_modules")) {
        $dst = Join-Path $nmRoot "project"
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        New-Item -ItemType Directory -Path $dst -Force | Out-Null
        robocopy (Join-Path $Root "node_modules") $dst /E /NFL /NDL /NJH /NJS | Out-Null
        Write-Ok "node_modules_root/project"
    }
    $qm = Join-Path $Root "mcp\quack-mcp-main\node_modules"
    if (Test-Path $qm) {
        $dst = Join-Path $nmRoot "quack-mcp-main"
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        New-Item -ItemType Directory -Path $dst -Force | Out-Null
        robocopy $qm $dst /E /NFL /NDL /NJH /NJS | Out-Null
        Write-Ok "node_modules_root/quack-mcp-main"
    }
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  Done. Copy to target PC:" -ForegroundColor Green
Write-Host "    - whole project folder" -ForegroundColor White
Write-Host "    - folder offline_packages\" -ForegroundColor White
if ($IncludeVenv) { Write-Host "    - folder portable_bundle\ (if -IncludeVenv)" -ForegroundColor White }
Write-Host "  On target: setup_deploy.bat (uses offline cache, no pip download)" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Green
