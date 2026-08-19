# Stops the API (:8000) and web console (:3000) started by start.ps1.
# Leaves Ollama running by default (it's a shared local service, not project-specific)
# - pass -IncludeOllama to stop it too.

param(
    [switch]$IncludeOllama
)

function Stop-Port {
    param([int]$Port, [string]$Name)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "$Name (:$Port) not running." -ForegroundColor Yellow
        return
    }
    foreach ($c in $conns) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Stopped $Name (:$Port)." -ForegroundColor Green
}

Stop-Port -Port 8000 -Name "API"
Stop-Port -Port 3000 -Name "Web console"

if ($IncludeOllama) {
    Stop-Port -Port 11434 -Name "Ollama"
}
