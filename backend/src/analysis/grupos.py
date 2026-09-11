"""
Objetivo por grupo de moneda. SOLO MIDE: no decide ni veta nada.

Por que existe
--------------
El objetivo de 3.2% es el mismo numero para BTC que para una moneda de un
millon de volumen, y el analisis del 11-sep (775 operaciones cerradas con sus
24h de velas de 1m) dice que eso no se sostiene:

    grupo           vol.1m    sube (mediana)   baja (mediana)   llega a 3.2%
    MUY_TRANQUILA   0.046%         +1.23%          -3.48%          23.7%
    TRANQUILA       0.087%         +1.38%          -4.41%          24.7%
    MOVIDA          0.132%         +1.81%          -4.92%          30.9%
    MUY_VOLATIL     0.220%         +2.49%          -6.06%          41.5%

En NINGUN grupo la senal mediana llega al 3.2%, y en todos la caida maxima
mediana es mas profunda que la subida maxima mediana. Un objetivo escalado a lo
que la moneda se mueve de verdad es la primera correccion evidente — pero antes
de cambiar ninguna emision hay que MEDIRLO en vivo, que es lo que hace esto.

Que se mide
-----------
Por cada outcome se guarda la volatilidad previa (cruda, para poder reagrupar
despues sin volver a desplegar), su grupo, el objetivo que le tocaria, y cuanto
tarda en alcanzarlo. Con eso y la escalera que ya existe (1.0 / 1.2 / 2.0 / 3.2
/ 4.2 / 5.0 / 10.0) se puede responder despues, sobre datos reales, si un
objetivo por grupo habria sido mejor que el fijo — y a que horizonte, que
importa: el uso real es intradia, de horas, no de 24.

Nada de esto entra en `trade_levels`, ni en el veto, ni en el aviso. Si manana
se decide cambiar la emision, sera con estas columnas ya llenas y no con la
tabla de arriba, que sale de tres dias.

Procedencia de los numeros
--------------------------
audit/2026-09-11/objetivo_alcanzable.py sobre el snapshot del 10-sep. La
volatilidad se mide SIEMPRE en los 60 minutos ANTERIORES a la senal: agrupar
por lo que pasa despues seria elegir sabiendo el futuro, y la regla no se
podria aplicar en vivo.
"""
from __future__ import annotations

from typing import Optional, Sequence

# Recorrido medio de la vela de 1m, en % del cierre, en la hora previa.
# Son los cuartiles observados; por eso los cortes no son numeros redondos.
CORTE_TRANQUILA = 0.068
CORTE_MOVIDA = 0.106
CORTE_VOLATIL = 0.165

MUY_TRANQUILA = "MUY_TRANQUILA"
TRANQUILA = "TRANQUILA"
MOVIDA = "MOVIDA"
MUY_VOLATIL = "MUY_VOLATIL"

# Subida maxima MEDIANA de cada grupo en 24h: el objetivo que alcanzaria la
# mitad de sus senales. No es una promesa de rentabilidad — es el techo
# realista contra el que comparar el 3.2% fijo.
OBJETIVO = {
    MUY_TRANQUILA: 1.23,
    TRANQUILA: 1.38,
    MOVIDA: 1.81,
    MUY_VOLATIL: 2.49,
}

# Minimo de velas para que la medida signifique algo. Con menos se devuelve
# None y la fila queda sin grupo, que es mejor que inventarle uno.
MIN_VELAS = 30
VENTANA_VELAS = 60


def volatilidad_previa(candles: Sequence) -> Optional[float]:
    """
    Recorrido medio de la vela de 1m en la ultima hora, en % del cierre.

    Se prefiere esto al ATR o a sigma porque es lo que de verdad separa los
    grupos en la medicion, y porque se calcula con lo que hay en el buffer sin
    depender de que los indicadores esten calientes.
    """
    if candles is None:
        return None
    ultimas = list(candles)[-VENTANA_VELAS:]
    if len(ultimas) < MIN_VELAS:
        return None
    vals = [(c.h - c.l) / c.c * 100.0 for c in ultimas if getattr(c, "c", 0)]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)


def grupo(vol_previa: Optional[float]) -> Optional[str]:
    """El grupo de volatilidad, o None si no se pudo medir."""
    if vol_previa is None:
        return None
    if vol_previa <= CORTE_TRANQUILA:
        return MUY_TRANQUILA
    if vol_previa <= CORTE_MOVIDA:
        return TRANQUILA
    if vol_previa <= CORTE_VOLATIL:
        return MOVIDA
    return MUY_VOLATIL


def objetivo_de(vol_previa: Optional[float]) -> Optional[float]:
    """El objetivo, en %, que le tocaria a una senal con esa volatilidad."""
    g = grupo(vol_previa)
    return OBJETIVO.get(g) if g else None


def campos(vol_previa: Optional[float]) -> dict:
    """Las columnas de sombra que se guardan al abrir un outcome."""
    return {
        "vol_previa_pct": vol_previa,
        "grupo_vol": grupo(vol_previa),
        "objetivo_grupo_pct": objetivo_de(vol_previa),
    }
