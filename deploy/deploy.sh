#!/usr/bin/env bash
# Instala/actualiza SACBinance v3 en el servidor Ubuntu.
# Uso:  bash deploy/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ">> Backend: entorno virtual + dependencias"
cd "$ROOT/backend"
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

echo ">> Frontend: dependencias + build de produccion"
cd "$ROOT/frontend"
npm install --no-audit --no-fund
npm run build

echo ""
echo ">> Listo. Para aplicar los cambios reinicia el servicio:"
echo "   sudo systemctl restart sacbinance"
