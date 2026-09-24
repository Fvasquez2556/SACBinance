#!/usr/bin/env bash
# Instala el servicio de IA en sombra en el servidor. NO toca SAC.
#
# Uso (como flox, desde /home/flox/sacbinance):  bash deploy/instalar_ia.sh
#
# Descarga, una sola vez:
#   - torch para CPU (~200 MB) desde download.pytorch.org
#   - las dependencias de ia_sombra/requirements.txt (~40 MB)
#   - 3 ficheros del codigo de Kronos (~55 KB) en el commit fijado (MIT)
#   - pesos de Kronos-mini (16 MB) y de su tokenizador (16 MB) en las
#     revisiones fijadas en sac_ia/registro.py
# Despues el servicio corre sin red hacia Hugging Face (HF_HUB_OFFLINE=1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IA="$ROOT/ia_sombra"
cd "$IA"

COMMIT="$(python3 -c 'import sys; sys.path.insert(0, "."); from sac_ia import registro; print(registro.KRONOS["codigo_commit"])')"

echo ">> Entorno virtual propio (no el de SAC)"
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
./venv/bin/pip install --quiet -r requirements.txt

echo ">> Codigo de Kronos en el commit $COMMIT"
mkdir -p vendor/Kronos/model
for f in __init__.py kronos.py module.py; do
    curl -fsSL "https://raw.githubusercontent.com/shiyu-coder/Kronos/$COMMIT/model/$f" \
         -o "vendor/Kronos/model/$f"
done
curl -fsSL "https://raw.githubusercontent.com/shiyu-coder/Kronos/$COMMIT/LICENSE" \
     -o vendor/Kronos/LICENSE
echo "$COMMIT" > vendor/Kronos/COMMIT

echo ">> Pesos de Kronos en las revisiones fijadas"
./venv/bin/python - <<'EOF'
from huggingface_hub import snapshot_download
from sac_ia import registro
k = registro.KRONOS
for repo, rev in ((k["modelo"], k["revision_modelo"]),
                  (k["tokenizador"], k["revision_tokenizador"])):
    print(repo, "->", snapshot_download(repo, revision=rev))
EOF

echo ">> Directorios de datos y secretos"
mkdir -p datos secretos
chmod 700 secretos

echo ">> Pruebas (con el Python de SAC: crean una base con su esquema real)"
"$ROOT/backend/venv/bin/python" -m unittest discover -s tests 2>&1 | tail -3 || true

echo ""
echo ">> Listo. Siguientes pasos:"
echo "   1. sudo cp $ROOT/deploy/sac-ia.service /etc/systemd/system/"
echo "      sudo systemctl daemon-reload && sudo systemctl enable --now sac-ia"
echo "      (arranca en RODAJE: observa, no gasta)"
echo "   2. ./venv/bin/python -m sac_ia probar-kronos -n 3     # latencia real en este equipo"
echo "   3. Clave de OpenAI:  nano secretos/openai.key && chmod 600 secretos/openai.key"
echo "      ./venv/bin/python -m sac_ia probar-llm --si-gastar  # ~1 centavo"
echo "   4. Tras 48 h de rodaje:  ./venv/bin/python -m sac_ia medir"
