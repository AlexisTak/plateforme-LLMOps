# Prepares a fresh Windows checkout: Python 3.11 venv, PyTorch (CUDA or CPU),
# pinned Python deps, web console deps and a local .env.
#
# Usage:
#   .\setup-windows.ps1          # auto-detects an NVIDIA GPU (nvidia-smi)
#   .\setup-windows.ps1 -Cpu     # force the CPU-only PyTorch wheel
#   .\setup-windows.ps1 -Force   # recreate .venv from scratch
#
# If script execution is blocked:
#   powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1

param(
    [switch]$Cpu,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venvDir = Join-Path $root ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

function Invoke-Checked {
    param([string]$What, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "$What failed (exit code $LASTEXITCODE)." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "== Biscuits Focus - Windows setup ==" -ForegroundColor Cyan

# --- Prerequisites -----------------------------------------------------------

if ($null -eq (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "Python launcher 'py' not found. Install Python 3.11 from python.org (keep 'py launcher' checked)." -ForegroundColor Red
    exit 1
}
& py -3.11 -c "import sys" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python 3.11 not found ('py -3.11'). This project requires 3.11 exactly (pyproject.toml)." -ForegroundColor Red
    Write-Host "Installed versions:" -ForegroundColor Yellow
    & py -0
    exit 1
}

if ($null -eq (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "npm not found. Install Node.js 20+ (https://nodejs.org)." -ForegroundColor Red
    exit 1
}
$nodeMajor = [int]((& node --version).TrimStart("v").Split(".")[0])
if ($nodeMajor -lt 20) {
    Write-Host "Node.js $nodeMajor detected - version 20+ is required." -ForegroundColor Red
    exit 1
}

if ($null -eq (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Ollama not found on PATH - optional, but needed for Ollama-served models (https://ollama.com)." -ForegroundColor Yellow
}

# --- PyTorch flavour -----------------------------------------------------------

$torchIndex = "https://download.pytorch.org/whl/cu124"
if ($Cpu) {
    $torchIndex = "https://download.pytorch.org/whl/cpu"
    Write-Host "CPU-only PyTorch requested." -ForegroundColor Yellow
} elseif ($null -eq (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    $torchIndex = "https://download.pytorch.org/whl/cpu"
    Write-Host "nvidia-smi not found - installing CPU-only PyTorch (training and 4-bit inference need a CUDA GPU)." -ForegroundColor Yellow
} else {
    Write-Host "NVIDIA GPU detected - installing PyTorch CUDA 12.4." -ForegroundColor Green
}

# --- Python venv -----------------------------------------------------------------

if ($Force -and (Test-Path $venvDir)) {
    Write-Host "Removing existing .venv..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvDir
}
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating .venv (Python 3.11)..." -ForegroundColor Cyan
    Invoke-Checked "venv creation" { py -3.11 -m venv $venvDir }
}

Invoke-Checked "pip upgrade" { & $venvPython -m pip install --upgrade pip }
# torch first, from its own index: requirements.txt would otherwise pull a CPU wheel from PyPI.
Invoke-Checked "PyTorch install" { & $venvPython -m pip install torch==2.6.0 --index-url $torchIndex }
Invoke-Checked "requirements install" { & $venvPython -m pip install -r (Join-Path $root "requirements.txt") }

# --- Web console -------------------------------------------------------------------

Push-Location (Join-Path $root "web")
try {
    Invoke-Checked "npm install" { npm install }
} finally {
    Pop-Location
}

# --- .env ------------------------------------------------------------------------------

$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root ".env.example") $envFile
    Write-Host "Created .env from .env.example - review it before starting." -ForegroundColor Green
} else {
    Write-Host ".env already exists - left untouched." -ForegroundColor Yellow
}

# --- Sanity check ------------------------------------------------------------------------

& $venvPython -c "import torch; print('torch', torch.__version__, '| CUDA available:', torch.cuda.is_available())"

Write-Host "`n== Setup complete ==" -ForegroundColor Cyan
Write-Host "Not in git, to restore on this machine if needed:"
Write-Host "  - model weights/adapters under projects\<id>\models\ (copy them or retrain)"
Write-Host "  - RAG index: .venv\Scripts\python -m rag.index"
Write-Host "  - login mode accounts: .venv\Scripts\python scripts\create_user.py"
Write-Host "Then run: .\start.ps1"
