# Genera el informe de outcomes y lo deja en informes\.
# Lee solo la base de datos: funciona aunque el backend este parado.
#
# Uso:  powershell -ExecutionPolicy Bypass -File deploy\informe.ps1

$ErrorActionPreference = "Continue"
$Root    = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Python  = Join-Path $Backend "venv\Scripts\python.exe"
$OutDir  = Join-Path $Root "informes"

if (-not (Test-Path $Python)) { $Python = "python" }
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory $OutDir | Out-Null }

$stamp   = Get-Date -Format "yyyy-MM-dd_HH-mm"
$destino = Join-Path $OutDir "outcomes_$stamp.txt"

Set-Location $Backend

$cabecera = @"
================================================================
  INFORME SACBinance — generado $(Get-Date -Format 'yyyy-MM-dd HH:mm')
================================================================

Se incluyen tres vistas:
  1. Solo señales con la ventana de 24h cumplida (el veredicto firme)
  2. Incluyendo las que siguen en seguimiento (mas muestras, parciales)
  3. Desglose por tier

"@

$partes = @($cabecera)

$partes += "`n########## 1. SOLO VENTANA CUMPLIDA ##########`n"
$partes += (& $Python analyze_outcomes.py 2>&1 | ForEach-Object { $_.ToString() }) -join "`n"

$partes += "`n`n########## 2. INCLUYENDO LAS VIVAS ##########`n"
$partes += (& $Python analyze_outcomes.py --incluir-vivas 2>&1 | ForEach-Object { $_.ToString() }) -join "`n"

$partes += "`n`n########## 3. DESGLOSE POR TIER ##########`n"
$partes += (& $Python analyze_outcomes.py --incluir-vivas --por tier 2>&1 | ForEach-Object { $_.ToString() }) -join "`n"

# El backend escribe una linea de log al abrir SQLite; fuera del informe.
$texto = ($partes -join "`n") -split "`n" | Where-Object { $_ -notmatch "SQLite inicializado" }
$texto -join "`r`n" | Set-Content -Path $destino -Encoding utf8

Write-Host "Informe guardado en: $destino" -ForegroundColor Green
