#!/usr/bin/env bash
# Genera los informes de outcomes. Pensado para cron.
#
#   bash deploy/informe.sh hora    instantanea horaria (ultimo.txt + serie CSV)
#   bash deploy/informe.sh dia     informe completo del dia, en fichero fechado
#   bash deploy/informe.sh timers  instala los dos timers de systemd
#                                  (alias: cron — pero NO usa crontab, que
#                                  Ubuntu Server no trae instalado)
#
# Lee solo SQLite: funciona aunque el servicio este parado.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$RAIZ/backend/venv/bin/python"
DIR="$RAIZ/informes"
[ -x "$PY" ] || PY="python3"
mkdir -p "$DIR"
cd "$RAIZ/backend" || exit 1

limpiar() { grep -v "SQLite inicializado"; }

case "${1:-hora}" in

  hora)
    # Estado actual, se sobrescribe. Para mirar "como va" sin abrir 30 ficheros.
    {
        echo "Instantanea — $(date '+%Y-%m-%d %H:%M:%S %Z')"
        echo "(se regenera cada hora; el informe firme del dia es diario_*.txt)"
        echo
        "$PY" analyze_outcomes.py --incluir-vivas 2>&1
    } | limpiar > "$DIR/ultimo.txt"

    # Serie temporal: una linea por hora. Leyendola de golpe se ve la evolucion.
    CSV="$DIR/evolucion.csv"
    [ -f "$CSV" ] || "$PY" analyze_outcomes.py --cabecera-csv > "$CSV" 2>/dev/null
    "$PY" analyze_outcomes.py --incluir-vivas --csv 2>/dev/null | limpiar >> "$CSV"
    echo "OK: $DIR/ultimo.txt y linea añadida a evolucion.csv"
    ;;

  dia)
    # Informe completo, fichero fechado. Es el que tiene veredictos firmes:
    # la ventana de seguimiento es de 24h, asi que una corrida diaria recoge
    # justo la tanda que acaba de cumplirla.
    DEST="$DIR/diario_$(date '+%Y-%m-%d').txt"
    {
        echo "=============================================================="
        echo "  INFORME DIARIO SACBinance — $(date '+%Y-%m-%d %H:%M %Z')"
        echo "=============================================================="
        echo
        echo "########## 1. SOLO VENTANA CUMPLIDA (veredicto firme) ##########"
        "$PY" analyze_outcomes.py 2>&1
        echo
        echo "########## 2. INCLUYENDO LAS VIVAS ##########"
        "$PY" analyze_outcomes.py --incluir-vivas 2>&1
        echo
        echo "########## 3. POR TIER ##########"
        "$PY" analyze_outcomes.py --incluir-vivas --por tier 2>&1
        echo
        echo "########## 4. POR ESTADO ##########"
        "$PY" analyze_outcomes.py --incluir-vivas --por display_state 2>&1
        echo
        echo "########## 5. POR TAXONOMIA ##########"
        "$PY" analyze_outcomes.py --incluir-vivas --por taxonomia 2>&1
    } | limpiar > "$DEST"

    # Retencion: 60 dias de informes diarios
    find "$DIR" -name 'diario_*.txt' -mtime +60 -delete 2>/dev/null
    echo "OK: $DEST"
    ;;

  cron|timers)
    # systemd timers, no crontab: Ubuntu Server suele venir SIN cron
    # instalado, y systemd ya esta ahi por definicion. Ademas se integra con
    # el mismo gestor que el servicio y sobrevive reinicios con `enable`.
    if ! command -v systemctl >/dev/null 2>&1; then
        echo "No hay systemd. Instala cron:  sudo apt install -y cron"
        exit 1
    fi
    echo ">> Instalando timers de systemd (necesita sudo)"

    for modo in hora dia; do
        sudo tee "/etc/systemd/system/sacbinance-informe-${modo}.service" >/dev/null <<UNIT
[Unit]
Description=SACBinance - informe ${modo}
After=sacbinance.service

[Service]
Type=oneshot
User=${USER}
WorkingDirectory=${RAIZ}
ExecStart=/usr/bin/env bash ${RAIZ}/deploy/informe.sh ${modo}
UNIT
    done

    # Horaria: al minuto 5 de cada hora
    sudo tee /etc/systemd/system/sacbinance-informe-hora.timer >/dev/null <<'UNIT'
[Unit]
Description=SACBinance - instantanea horaria

[Timer]
OnCalendar=*:05
Persistent=true

[Install]
WantedBy=timers.target
UNIT

    # Diaria: 06:30. Persistent=true la ejecuta al arrancar si el servidor
    # estuvo apagado a esa hora.
    sudo tee /etc/systemd/system/sacbinance-informe-dia.timer >/dev/null <<'UNIT'
[Unit]
Description=SACBinance - informe completo del dia

[Timer]
OnCalendar=*-*-* 06:30:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT

    sudo systemctl daemon-reload
    sudo systemctl enable --now sacbinance-informe-hora.timer sacbinance-informe-dia.timer
    echo ""
    echo "Timers activos:"
    systemctl list-timers 'sacbinance-*' --no-pager
    ;;

  *)
    echo "Uso: bash deploy/informe.sh [hora|dia|timers]"; exit 1 ;;
esac
