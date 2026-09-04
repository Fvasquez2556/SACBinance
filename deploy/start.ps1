# Arranca SACBinance v3 con reinicio automatico ante fallo.
# Equivalente de la unidad systemd (Restart=always, RestartSec=10) en Windows.
#
# Uso:  powershell -ExecutionPolicy Bypass -File deploy\start.ps1

$ErrorActionPreference = "Continue"
$Root    = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Python  = Join-Path $Backend "venv\Scripts\python.exe"
$LogDir  = Join-Path $Root "logs"

if (-not (Test-Path $Python)) {
    Write-Host "No existe el venv. Corre primero: deploy\deploy.ps1" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory $LogDir | Out-Null }

Set-Location $Backend
Write-Host "SACBinance v3 — http://localhost:8000   (Ctrl+C para parar)" -ForegroundColor Green

while ($true) {
    $stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
    $log   = Join-Path $LogDir "sacbinance_$stamp.log"
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] arrancando — log: $log" -ForegroundColor Cyan

    # ToString() evita que PowerShell envuelva el stderr normal de uvicorn
    # (warnings, banner) en ErrorRecord y lo pinte como fallo del script.
    & $Python main.py 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] el proceso termino. Reintento en 10s..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10

    # Rotacion simple: conservar los 20 logs mas recientes
    Get-ChildItem $LogDir -Filter "sacbinance_*.log" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 20 |
        Remove-Item -Force -ErrorAction SilentlyContinue
}
