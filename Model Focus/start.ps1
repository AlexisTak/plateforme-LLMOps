# Launches the full Biscuits Focus stack: Ollama, FastAPI backend, Next.js console.
# Each service opens in its own PowerShell window so logs stay visible and each
# can be closed independently without killing the others.
#
# Usage:
#   .\start.ps1            # start everything, open the browser
#   .\start.ps1 -NoBrowser # start everything, skip opening the browser

param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "== Biscuits Focus - starting stack ==" -ForegroundColor Cyan

# --- Preflight ---------------------------------------------------------

if (-not (Test-Path $venvPython)) {
    Write-Host "No .venv found at $venvPython - run setup first (see README.md)." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $root "web\node_modules"))) {
    Write-Host "web/node_modules missing - running npm install..." -ForegroundColor Yellow
    Push-Location (Join-Path $root "web")
    npm install
    Pop-Location
}

function Test-Port {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

# --- Ollama --------------------------------------------------------------

if (Test-Port -Port 11434) {
    Write-Host "Ollama already running on :11434" -ForegroundColor Green
} else {
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($null -eq $ollamaCmd) {
        Write-Host "Ollama not found on PATH - install it (https://ollama.com) or start it manually." -ForegroundColor Yellow
    } else {
        Write-Host "Starting Ollama..." -ForegroundColor Cyan
        Start-Process -WindowStyle Minimized -FilePath "ollama" -ArgumentList "serve"
        Start-Sleep -Seconds 2
    }
}

# --- FastAPI backend -------------------------------------------------------

$apiJustStarted = $false
if (Test-Port -Port 8000) {
    Write-Host "API already running on :8000 - leaving it as is." -ForegroundColor Yellow
} else {
    Write-Host "Starting API on :8000..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$root'; & '$venvPython' -m uvicorn api.main:app --port 8000"
    )
    $apiJustStarted = $true
}

# --- Next.js console -------------------------------------------------------

if (Test-Port -Port 3000) {
    Write-Host "Web console already running on :3000 - leaving it as is." -ForegroundColor Yellow
} else {
    Write-Host "Starting web console on :3000..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$root\web'; npm run dev"
    )
}

# --- Wait for API health (only if we just started it), then open browser ---

if ($apiJustStarted) {
    Write-Host "Waiting for API to become healthy..." -NoNewline
    $healthy = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($resp.StatusCode -eq 200) { $healthy = $true; break }
        } catch {}
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 1
    }
    Write-Host ""

    if ($healthy) {
        Write-Host "API healthy." -ForegroundColor Green
    } else {
        Write-Host "API did not respond within 30s - check its window for errors." -ForegroundColor Red
    }
}

if (-not $NoBrowser) {
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:3000"
}

Write-Host "`n== Stack starting up ==" -ForegroundColor Cyan
Write-Host "  API:     http://localhost:8000  (health checks at /api/system/health)"
Write-Host "  Console: http://localhost:3000"
Write-Host "  Ollama:  http://localhost:11434"
Write-Host "`nEach service runs in its own window - close a window to stop that service."
