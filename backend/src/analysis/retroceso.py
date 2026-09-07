"""
El patron que si resulto: "viene de caer".

De los cuatro ingredientes que se midieron el 7-sep-2026 sobre 191 pares y
627k velas de 1m (research/marea_ingredientes.py), este es el unico que
sobrevivio al grupo de control:

    caida previa >= 2%   ->  llega a +3.2% en 3h el 30.1% de las veces
    control (cualquier instante)                     13.1%
    version cobrable (llega antes de caer -1.2%)     19.8% contra 10.5%

n=1673 detecciones deduplicadas. Es 2.3x la tasa base.

Lo que NO entra aqui, y por que
-------------------------------
La "marea tranquila" que se sospechaba (zona quieta, equilibrada, con volumen
seco) no aporta nada medible por encima de esto: +1.6, +2.1 y +0.1 puntos
segun el ingrediente, con signo inconsistente entre ventanas y n~400, mientras
corta la muestra a la cuarta parte. La quietud SIN caida previa rinde POR
DEBAJO del azar (9.1% contra 10.5%): las zonas tranquilas estan en todas
partes, asi que no discriminan.

Aviso: son 2.7 dias de un solo regimen alcista. El patron hay que revalidarlo
segun se acumulen datos.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.config.settings import get_settings


@dataclass
class Retroceso:
    detectado: bool = False
    caida_pct: Optional[float] = None       # del pico previo al suelo de la zona
    suelo: Optional[float] = None
    pico_previo: Optional[float] = None
    minutos_desde_suelo: int = 0            # cuanto hace que marco ese suelo
    rebote_pct: Optional[float] = None      # cuanto lleva recuperado desde el suelo
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "detectado": self.detectado,
            "caida_pct": self.caida_pct,
            "suelo": self.suelo,
            "pico_previo": self.pico_previo,
            "minutos_desde_suelo": self.minutos_desde_suelo,
            "rebote_pct": self.rebote_pct,
            "reason": self.reason,
        }


def detectar_retroceso(candles_1m: list) -> Retroceso:
    """
    candles_1m: buffer de velas 1m cerradas, la ultima es la actual.

    Replica exactamente la medicion del estudio: el suelo se busca en las
    ultimas `retroceso_velas_zona` velas y el pico en las
    `retroceso_lookback` que las preceden.
    """
    s = get_settings()
    res = Retroceso()

    zona = s.retroceso_velas_zona
    atras = s.retroceso_lookback
    if len(candles_1m) < zona + atras:
        res.reason = "datos insuficientes"
        return res

    v = list(candles_1m)
    seg = v[-zona:]
    prev = v[-(zona + atras):-zona]

    pico = max(c.h for c in prev)
    if pico <= 0:
        return res
    suelo = min(c.l for c in seg)
    res.pico_previo = pico
    res.suelo = suelo
    res.caida_pct = round((suelo - pico) / pico * 100.0, 2)

    # Cuanto hace que se marco ese suelo: distingue "acaba de caer" de
    # "cayo y lleva rato aguantando". Solo informativo, no filtra: el estudio
    # no encontro que la espera cambiara el resultado.
    for i, c in enumerate(reversed(seg)):
        if c.l <= suelo * 1.0001:
            res.minutos_desde_suelo = i
            break

    precio = float(v[-1].c)
    if suelo > 0:
        res.rebote_pct = round((precio - suelo) / suelo * 100.0, 2)

    if res.caida_pct > -s.retroceso_caida_min:
        res.reason = (f"caida previa {res.caida_pct}% insuficiente "
                      f"(minimo {-s.retroceso_caida_min}%)")
        return res

    res.detectado = True
    res.reason = (f"cayo {res.caida_pct}% desde {pico} | suelo {suelo} hace "
                  f"{res.minutos_desde_suelo}min | rebotado {res.rebote_pct}%")
    return res


# --- Probabilidad medida de llegar a la meta segun lo que falte -------------
#
# Tabla del grupo de control de research/cascada.py: instantes al azar sobre
# senales abiertas, horizonte 6h, meta +3.2% sobre el entry congelado. NO es
# un modelo: es la frecuencia observada, con su n al lado.
#
#     le faltaba      llego en 6h        n
#       < 0.5%           87.3%           55     <- pocas, tomar con pinzas
#       0.5-1%           69.7%          198
#         1-2%           42.3%        1,075
#         2-3%           22.0%        2,824
#         3-5%           12.3%        5,771
#         > 5%            4.4%        2,077
#
_TABLA_META = (
    (0.5, 87.0, 55),
    (1.0, 70.0, 198),
    (2.0, 42.0, 1075),
    (3.0, 22.0, 2824),
    (5.0, 12.0, 5771),
    (float("inf"), 4.0, 2077),
)


def prob_llegar_meta(dist_pct: float) -> tuple:
    """
    dist_pct: cuanto le falta al precio actual para la meta, en %.
    Devuelve (probabilidad_observada, n_de_la_banda). Si ya la paso, 100.
    """
    if dist_pct <= 0:
        return 100.0, 0
    for limite, p, n in _TABLA_META:
        if dist_pct < limite:
            return p, n
    return 4.0, 2077
