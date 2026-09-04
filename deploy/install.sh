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
for cmd in python3 npm; do
    if command -v "$cmd" >/dev/null 2>&1; then
        echo "   $cmd  $($cmd --version 2>&1 | head -1)"
    else
        echo "   FALTA: $cmd"; falta=1
    fi
done
if ! python3 -c "import venv" 2>/dev/null; then
    echo "   FALTA: python3-venv"; falta=1
fi
if [ "$falta" = "1" ]; then
    echo ""
    echo "Instala lo que falta y vuelve a ejecutar:"
    echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip nodejs npm"
    exit 1
fi

# --- 2. Backend ---
echo ">> Backend: entorno virtual + dependencias"
cd "$RAIZ/backend"
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt
echo "   dependencias instaladas"

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
