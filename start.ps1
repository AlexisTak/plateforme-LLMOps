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

# --- .env (see .env.example) - variables already set in the shell win ------

$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $name = $Matches[1]
            $value = $Matches[2].Trim('"').Trim("'")
            if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
                [Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
    }
}

# --- Preflight ---------------------------------------------------------

if (-not (Test-Path $venvPython)) {
    Write-Host "No .venv found at $venvPython - run .\setup.ps1 first." -ForegroundColor Red
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

function Test-ApiHealth {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2 -ErrorAction Stop
        return $resp.status -eq "ok"
    } catch {
        return $false
    }
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

if (Test-ApiHealth) {
    Write-Host "API already healthy on 127.0.0.1:8000 - leaving it as is." -ForegroundColor Yellow
} elseif (Test-Port -Port 8000) {
    Write-Host "Port 8000 is occupied, but Biscuits Focus API is not healthy." -ForegroundColor Red
    Write-Host "Stop the process using this port, then run start.ps1 again." -ForegroundColor Red
    exit 1
} else {
    Write-Host "Starting API on :8000..." -ForegroundColor Cyan
    # Auth mode comes from .env / the shell (inherited by the child window); unset, the
    # API defaults to "login" (accounts required, first-run screen creates the admin).
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$root'; & '$venvPython' -m uvicorn api.main:app --host 127.0.0.1 --port 8000"
    )
}

# --- Wait for API health before starting the web console -------------------

Write-Host "Waiting for API to become healthy..." -NoNewline
$healthy = $false
for ($i = 0; $i -lt 90; $i++) {
    if (Test-ApiHealth) { $healthy = $true; break }
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 1
}
Write-Host ""

if (-not $healthy) {
    Write-Host "API did not respond within 90s - check its window for errors." -ForegroundColor Red
    exit 1
}
Write-Host "API healthy." -ForegroundColor Green

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

if (-not $NoBrowser) {
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:3000"
}

Write-Host "`n== Stack starting up ==" -ForegroundColor Cyan
Write-Host "  API:     http://localhost:8000  (health checks at /api/system/health)"
Write-Host "  Console: http://localhost:3000"
Write-Host "  Ollama:  http://localhost:11434"
Write-Host "`nEach service runs in its own window - close a window to stop that service."
