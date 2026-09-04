# Registra SACBinance para que arranque solo al iniciar sesion en Windows.
# Equivalente de `systemctl enable sacbinance` en Ubuntu.
#
# Uso:      powershell -ExecutionPolicy Bypass -File deploy\install-autostart.ps1
# Quitar:   powershell -ExecutionPolicy Bypass -File deploy\install-autostart.ps1 -Remove
#
# Crea una tarea programada en el usuario actual (no requiere admin).

param([switch]$Remove)

$ErrorActionPreference = "Stop"
$TaskName = "SACBinance"
$Root     = Split-Path -Parent $PSScriptRoot
$Start    = Join-Path $Root "deploy\start.ps1"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Arranque automatico desactivado." -ForegroundColor Yellow
    exit 0
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Start`"" `
    -WorkingDirectory (Join-Path $Root "backend")

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# start.ps1 ya reintenta solo, asi que la tarea no necesita reinicio propio.
# ExecutionTimeLimit 0 = sin limite (es un servicio 24/7).
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "SACBinance v3 - analisis de mercado Binance 24/7" `
    -Force | Out-Null

Write-Host "Arranque automatico activado (tarea '$TaskName', al iniciar sesion)." -ForegroundColor Green
Write-Host "Para desactivarlo:  deploy\install-autostart.ps1 -Remove"
