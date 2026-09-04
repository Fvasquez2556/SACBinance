# Para SACBinance: primero el bucle de reinicio, luego el backend.
# Equivalente de `systemctl stop sacbinance`.
#
# Uso:  powershell -ExecutionPolicy Bypass -File deploy\stop.ps1

$ErrorActionPreference = "SilentlyContinue"
$Root = Split-Path -Parent $PSScriptRoot

# 1. El bucle primero: si se matara el backend antes, el bucle lo relanzaria.
$bucles = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
    Where-Object { $_.CommandLine -like '*start.ps1*' }
foreach ($b in $bucles) {
    Write-Host "Parando bucle de reinicio (PID $($b.ProcessId))" -ForegroundColor Cyan
    Stop-Process -Id $b.ProcessId -Force
}

# 2. El backend: solo los python de este proyecto, no los del usuario.
$backend = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*$($Root -replace '\\','\\')*" -or $_.CommandLine -like '*main.py*' }
foreach ($p in $backend) {
    Write-Host "Parando backend (PID $($p.ProcessId))" -ForegroundColor Cyan
    Stop-Process -Id $p.ProcessId -Force
}

Start-Sleep -Seconds 2
if (-not (Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
          Where-Object { $_.CommandLine -like '*main.py*' })) {
    Write-Host "SACBinance detenido." -ForegroundColor Green
} else {
    Write-Host "Quedan procesos vivos — revisa con: Get-Process python" -ForegroundColor Yellow
}
