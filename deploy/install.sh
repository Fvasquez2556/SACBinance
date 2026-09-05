#!/usr/bin/env bash
# Instalacion limpia de SACBinance en Ubuntu Server.
#
# Uso:  bash deploy/install.sh
#
# Deja el sistema corriendo como servicio systemd, arrancando solo al
# reiniciar la maquina y reintentando si el proceso muere.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USUARIO="${SUDO_USER:-$(whoami)}"
SERVICIO="sacbinance"

echo "=============================================================="
echo "  INSTALACION DE SACBinance"
echo "=============================================================="
echo "  Directorio: ${RAIZ}"
echo "  Usuario   : ${USUARIO}"
echo ""

# --- 1. Requisitos ---
echo ">> Comprobando requisitos"
falta=0
for cmd in git npm node; do
    if command -v "$cmd" >/dev/null 2>&1; then
        echo "   $cmd  $($cmd --version 2>&1 | head -1)"
    else
        echo "   FALTA: $cmd"; falta=1
    fi
done

# Elegir interprete. Se prefiere una version PROBADA: las muy nuevas suelen
# no tener wheels publicados para numpy/scipy/pydantic, y pip cae a compilar
# desde fuente, que necesita toolchain de C, C++, Fortran y Rust.
PY=""
for cand in python3.13 python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import venv" 2>/dev/null; then
        PY="$cand"; break
    fi
done
if [ -z "$PY" ]; then
    echo "   FALTA: python3 con modulo venv"; falta=1
else
    VER="$($PY -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    echo "   python  $PY ($VER)"
    case "$VER" in
        3.10|3.11|3.12|3.13) ;;
        *)
            echo ""
            echo "   AVISO: $VER esta fuera de las versiones probadas (3.10-3.13)."
            echo "   requirements.txt usa minimos, no pines, asi que pip deberia"
            echo "   resolver wheels validos. Si la instalacion falla compilando"
            echo "   numpy o scipy, instala una version probada y repite:"
            echo "     sudo apt install -y python3.12 python3.12-venv"
            echo ""
            ;;
    esac
fi

if [ "$falta" = "1" ]; then
    echo ""
    echo "Instala lo que falta y vuelve a ejecutar:"
    echo "  sudo apt update && sudo apt install -y git python3 python3-venv python3-pip nodejs npm"
    exit 1
fi

# --- 2. Backend ---
echo ">> Backend: entorno virtual + dependencias"
cd "$RAIZ/backend"
[ -d venv ] || "$PY" -m venv venv
./venv/bin/pip install --quiet --upgrade pip
if ! ./venv/bin/pip install --quiet -r requirements.txt; then
    echo "   Fallo la instalacion completa. Reintentando sin scipy (es opcional:"
    echo "   solo acelera la EMA; sin el se usa el bucle Python)."
    grep -v '^scipy' requirements.txt > /tmp/req-sin-scipy.txt
    ./venv/bin/pip install --quiet -r /tmp/req-sin-scipy.txt
fi
./venv/bin/python -c "import fastapi, numpy; print('   dependencias OK - numpy', numpy.__version__)"
./venv/bin/python -c "import scipy; print('   scipy', scipy.__version__)" 2>/dev/null || echo "   scipy no instalado (se usara el fallback)"

# .env a partir del ejemplo, si no existe
if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
    echo "   .env creado desde .env.example"
fi

# --- 3. Frontend ---
echo ">> Frontend: dependencias + build de produccion"
cd "$RAIZ/frontend"
npm install --no-audit --no-fund --silent
npm run build
echo "   frontend compilado en frontend/dist"

# --- 4. Servicio systemd ---
echo ">> Registrando el servicio systemd"
UNIDAD="/etc/systemd/system/${SERVICIO}.service"
sudo tee "$UNIDAD" >/dev/null <<UNIT
[Unit]
Description=SACBinance v3 - Analisis de mercado Binance 24/7
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USUARIO}
WorkingDirectory=${RAIZ}/backend
ExecStart=${RAIZ}/backend/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:${RAIZ}/logs/sacbinance.log
StandardError=append:${RAIZ}/logs/sacbinance.log

[Install]
WantedBy=multi-user.target
UNIT

mkdir -p "$RAIZ/logs"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICIO"
sudo systemctl restart "$SERVICIO"

echo ""
echo "=============================================================="
sleep 5
if systemctl is-active --quiet "$SERVICIO"; then
    echo "  ACTIVO — http://$(hostname -I | awk '{print $1}'):8000"
else
    echo "  El servicio NO arranco. Revisa:  journalctl -u ${SERVICIO} -n 50"
fi
echo ""
echo "  Ver el log      : tail -f ${RAIZ}/logs/sacbinance.log"
echo "  Estado          : systemctl status ${SERVICIO}"
echo "  Parar / arrancar: sudo systemctl stop|start ${SERVICIO}"
echo "  Informe         : cd ${RAIZ}/backend && ./venv/bin/python analyze_outcomes.py"
echo "  Desinstalar     : sudo bash ${RAIZ}/deploy/uninstall.sh"
echo "=============================================================="
