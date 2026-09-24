"""
Que le pasa a una trayectoria simulada frente a la meta y el stop. Puro.

`KronosPredictor.predict()` PROMEDIA las muestras antes de devolverlas: una
media de trayectorias no es una distribucion y no sirve para contar quien toca
primero (la media de un camino que sube y otro que baja no toca nada). Por eso
el adaptador pide cada trayectoria por separado y este modulo las cuenta una a
una. Mismas reglas que el evaluador comun:

- Si una misma vela toca meta y stop, no se sabe el orden: `AMBIGUA`, y en la
  frecuencia de meta no cuenta como acierto.
- Kronos predice cada campo por separado y a veces da un maximo por debajo del
  cierre (medido el 24-sep: 1,5 % de las velas, 13,8 % de las trayectorias,
  violacion mediana 0,08 %). Tirar esas trayectorias NO es neutral: un cierre
  por encima del maximo aparece justo en los caminos que suben, asi que
  descartarlas bajaria la frecuencia de meta. En vez de eso se usa el rango que
  la propia vela afirma haber recorrido: la apertura y el cierre son precios
  tocados, asi que maximo = max(o, h, c) y minimo = min(o, l, c). No se inventa
  un extremo ni se reordena nada; se cuenta cuantas velas hubo que ensanchar.
- Solo es `INVALIDA` una trayectoria con precios no finitos o no positivos. Si
  hay demasiadas, el adaptador se abstiene.
- La primera vela predicha empieza ANTES del aviso (es la vela en curso
  del marco de Kronos): su maximo y su minimo mezclan pasado y futuro, asi que se descarta.
"""
from __future__ import annotations

import math
from typing import Sequence

META, STOP, NINGUNA, AMBIGUA, INVALIDA = "META", "STOP", "NINGUNA", "AMBIGUA", "INVALIDA"


def vela_valida(o: float, h: float, l: float, c: float) -> bool:
    return (all(isinstance(x, (int, float)) and math.isfinite(x) for x in (o, h, l, c))
            and min(o, h, l, c) > 0 and l <= min(o, c) and max(o, c) <= h)


def precios_validos(o: float, h: float, l: float, c: float) -> bool:
    return (all(isinstance(x, (int, float)) and math.isfinite(x) for x in (o, h, l, c))
            and min(o, h, l, c) > 0)


def rango(o: float, h: float, l: float, c: float) -> tuple[float, float, float, float]:
    """La vela con el rango que ella misma dice haber tocado: o y c son precios del camino."""
    return o, max(o, h, c), min(o, l, c), c


def ensanchada(o: float, h: float, l: float, c: float) -> bool:
    return h < max(o, c) or l > min(o, c)


def clasificar(trayectoria: Sequence[Sequence[float]], meta: float, stop: float) -> str:
    """`trayectoria`: velas (o, h, l, c) YA sin la vela solapada con el pasado."""
    if not trayectoria or not all(precios_validos(*v) for v in trayectoria):
        return INVALIDA
    for vela in trayectoria:
        o, h, l, c = rango(*vela)
        toca_stop, toca_meta = l <= stop, h >= meta
        if toca_stop and toca_meta:
            return AMBIGUA
        if toca_stop:
            return STOP
        if toca_meta:
            return META
    return NINGUNA


def _cuantil(valores: list[float], q: float):
    if not valores:
        return None
    v = sorted(valores)
    pos = (len(v) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return round(v[lo] + (v[hi] - v[lo]) * (pos - lo), 4)


def resumir(trayectorias: Sequence[Sequence[Sequence[float]]], entrada: float,
            meta: float, stop: float, max_invalidas_frac: float) -> dict:
    """Frecuencias y cuantiles. `p_meta` es una frecuencia, no una probabilidad."""
    clases = [clasificar(t, meta, stop) for t in trayectorias]
    validas = [t for t, k in zip(trayectorias, clases) if k != INVALIDA]
    n, nv = len(trayectorias), len(validas)
    cuenta = {k: clases.count(k) for k in (META, STOP, NINGUNA, AMBIGUA, INVALIDA)}
    abstiene = n == 0 or (n - nv) / n > max_invalidas_frac

    def pct(x):
        return (x / entrada - 1) * 100

    ret_final = [pct(t[-1][3]) for t in validas]
    max_sube = [pct(max(rango(*v)[1] for v in t)) for t in validas]
    max_baja = [pct(min(rango(*v)[2] for v in t)) for t in validas]
    return {
        "n_trayectorias": n,
        "n_validas": nv,
        "velas_ensanchadas": sum(ensanchada(*v) for t in validas for v in t),
        "cuenta": cuenta,
        "abstiene": abstiene,
        "p_meta_antes_que_stop": None if abstiene else round(cuenta[META] / nv, 4),
        "p_stop_antes_que_meta": None if abstiene else round(cuenta[STOP] / nv, 4),
        "p_ninguna": None if abstiene else round(cuenta[NINGUNA] / nv, 4),
        "p_ambigua": None if abstiene else round(cuenta[AMBIGUA] / nv, 4),
        "retorno_final_pct": {"p10": _cuantil(ret_final, 0.1), "p50": _cuantil(ret_final, 0.5),
                              "p90": _cuantil(ret_final, 0.9)},
        "max_subida_pct_p50": _cuantil(max_sube, 0.5),
        "max_bajada_pct_p50": _cuantil(max_baja, 0.5),
        "nota": "frecuencias sobre trayectorias simuladas, sin calibrar",
    }
