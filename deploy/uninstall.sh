#!/usr/bin/env bash
# Elimina SACBinance del servidor por completo: servicio, codigo, venv,
# base de datos y logs. Deja la maquina como si nunca se hubiera instalado.
#
# Uso:  sudo bash deploy/uninstall.sh            (pide confirmacion)
#       sudo bash deploy/uninstall.sh --si       (sin preguntar)
#
# Pensado para una reinstalacion limpia: los datos acumulados NO sobreviven.
set -uo pipefail

SERVICIO="sacbinance"
USUARIO="${SUDO_USER:-flox}"
RAIZ="/home/${USUARIO}/sacbinance"
UNIDAD="/etc/systemd/system/${SERVICIO}.service"

echo "=============================================================="
echo "  DESINSTALACION DE SACBinance"
echo "=============================================================="
echo "  Servicio      : ${SERVICIO}"
echo "  Directorio    : ${RAIZ}"
echo "  Unidad systemd: ${UNIDAD}"
echo ""
echo "  SE BORRARA TAMBIEN:"
echo "    - la base de datos (senales, outcomes, historial de estados)"
echo "    - el entorno virtual y las dependencias"
echo "    - el codigo y el frontend compilado"
echo ""

if [ "${1:-}" != "--si" ]; then
    read -rp "Escribe BORRAR para confirmar: " respuesta
    [ "$respuesta" = "BORRAR" ] || { echo "Cancelado. No se ha tocado nada."; exit 0; }
fi

echo ""
echo ">> Parando el servicio"
systemctl stop "$SERVICIO" 2>/dev/null && echo "   detenido" || echo "   no estaba corriendo"
systemctl disable "$SERVICIO" 2>/dev/null && echo "   deshabilitado" || echo "   no estaba habilitado"

echo ">> Quitando la unidad systemd"
if [ -f "$UNIDAD" ]; then
    rm -f "$UNIDAD"
    systemctl daemon-reload
    systemctl reset-failed 2>/dev/null || true
    echo "   ${UNIDAD} eliminada"
else
    echo "   no existia"
fi

echo ">> Matando procesos sueltos"
pkill -f "sacbinance.*main.py" 2>/dev/null && echo "   procesos terminados" || echo "   ninguno"

echo ">> Borrando el directorio"
if [ -d "$RAIZ" ]; then
    TAM=$(du -sh "$RAIZ" 2>/dev/null | cut -f1)
    rm -rf "$RAIZ"
    echo "   ${RAIZ} eliminado (${TAM})"
else
    echo "   no existia"
fi

echo ">> Buscando restos"
for extra in "/home/${USUARIO}/.sacbinance" "/var/log/${SERVICIO}"; do
    [ -e "$extra" ] && { rm -rf "$extra"; echo "   ${extra} eliminado"; }
done

echo ""
echo "=============================================================="
echo "  Limpio. Para reinstalar:"
echo "    git clone https://github.com/Fvasquez2556/SACBinance.git ${RAIZ}"
echo "    cd ${RAIZ} && bash deploy/install.sh"
echo "=============================================================="
