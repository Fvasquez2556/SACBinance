#!/bin/sh
# Observador independiente y sin privilegios. Nunca invoca la aplicación principal.
set -eu
umask 077
cd /home/flox/sacbinance
mkdir -p moderadas_sombra/datos
# Sin solapes; prioridad baja, duración y memoria acotadas. Si un ciclo falla,
# el siguiente minuto lo reintenta.
ulimit -v 393216
exec /usr/bin/flock -n moderadas_sombra/datos/observador.lock \
  /usr/bin/timeout --signal=TERM 55s /usr/bin/nice -n 15 \
  /usr/bin/python3 -m moderadas_sombra una-vez
