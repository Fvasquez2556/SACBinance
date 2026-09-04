# Instala/actualiza SACBinance v3 en Windows.
# Equivalente de deploy/deploy.sh (Ubuntu).
#
# Uso:  powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host ">> Backend: entorno virtual + dependencias" -ForegroundColor Cyan
Set-Location "$Root\backend"
if (-not (Test-Path "venv")) { python -m venv venv }
& .\venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

Write-Host ">> Frontend: dependencias + build de produccion" -ForegroundColor Cyan
Set-Location "$Root\frontend"
npm install --no-audit --no-fund
npm run build

Write-Host ""
Write-Host ">> Listo. Para arrancar:" -ForegroundColor Green
Write-Host "   powershell -ExecutionPolicy Bypass -File deploy\start.ps1"
