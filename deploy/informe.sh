#!/usr/bin/env bash
# Genera los informes de outcomes. Pensado para cron.
#
#   bash deploy/informe.sh hora    instantanea horaria (ultimo.txt + serie CSV)
#   bash deploy/informe.sh dia     informe completo del dia, en fichero fechado
#   bash deploy/informe.sh cron    instala las dos entradas en crontab
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

  cron)
    TMP="$(mktemp)"
    crontab -l 2>/dev/null | grep -v 'deploy/informe.sh' > "$TMP" || true
    {
        echo "# SACBinance — instantanea cada hora"
        echo "5 * * * * bash ${RAIZ}/deploy/informe.sh hora >/dev/null 2>&1"
        echo "# SACBinance — informe completo del dia"
        echo "30 6 * * * bash ${RAIZ}/deploy/informe.sh dia >/dev/null 2>&1"
    } >> "$TMP"
    crontab "$TMP" && rm -f "$TMP"
    echo "Cron instalado:"
    crontab -l | grep -A1 SACBinance
    ;;

  *)
    echo "Uso: bash deploy/informe.sh [hora|dia|cron]"; exit 1 ;;
esac
