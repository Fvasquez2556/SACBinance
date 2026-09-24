"""Clasificacion direccional de rupturas cortas para avisos y seguimiento."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


RUPTURA_ALCISTA = "RUPTURA_ALCISTA"
RUPTURA_BAJISTA = "RUPTURA_BAJISTA"


@dataclass(frozen=True)
class Ruptura:
    direccion: str
    etiqueta: str
    razon: str


def clasificar(snapshot: dict) -> Optional[Ruptura]:
    """Devuelve una ruptura observada o ``None`` cuando no la hay.

    Esta es una lectura de estado del mercado, no una orden ni una prediccion
    de rentabilidad. Debe mantenerse alineada con las etiquetas del tablero.
    """
    estado = snapshot.get("display_state")
    impulso = snapshot.get("impulso") or {}
    sr = snapshot.get("sr_levels") or {}

    if estado == "CAYENDO":
        if impulso.get("caida_acelerando"):
            razon = "caída acelerando en 3m y 5m"
        elif sr.get("perdido"):
            razon = "soporte perdido y caída activa"
        else:
            razon = "caída activa detectada por el sistema"
        return Ruptura(RUPTURA_BAJISTA, "Ruptura bajista corta", razon)

    fase = impulso.get("fase")
    impulso_continuo = bool(impulso.get("valid")) and fase in ("ACELERANDO", "SOSTENIDA")
    alcista = estado == "BREAKOUT_INCIPIENTE" or (
        estado == "SUBIENDO" and snapshot.get("trend_up") is True and impulso_continuo
    )
    if alcista and not snapshot.get("is_fakeout"):
        if estado == "BREAKOUT_INCIPIENTE":
            razon = f"ruptura detectada con impulso {(fase or 'activo').lower()}"
        else:
            razon = f"subida continua con impulso {(fase or 'activo').lower()}"
        return Ruptura(RUPTURA_ALCISTA, "Ruptura alcista continua", razon)

    return None
