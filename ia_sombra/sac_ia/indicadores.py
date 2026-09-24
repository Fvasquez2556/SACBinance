"""
Indicadores recalculados sobre velas CERRADAS. Funciones puras, sin numpy.

El snapshot que SAC guarda en `planes` es plano: los indicadores por marco
(RSI, ATR, EMA de 15m, 1h, 4h) viven anidados y se pierden al guardarlo. Aqui
se recalculan desde las velas, con formulas versionadas. No son la lectura
intravela que vio SAC; por eso el contexto los marca como `recalculado`.

Cada vela es una tupla (open_time, o, h, l, c, v).
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

VERSION = "ind-v1"


def _finito(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def valida(vela: Sequence) -> bool:
    _, o, h, l, c, v = vela
    return (all(_finito(x) for x in (o, h, l, c)) and min(o, h, l, c) > 0
            and l <= min(o, c) and max(o, c) <= h and (v is None or v >= 0))


def continuas(velas: Sequence[Sequence], paso_ms: int) -> bool:
    return all(b[0] - a[0] == paso_ms for a, b in zip(velas, velas[1:]))


def rsi(cierres: Sequence[float], n: int = 14) -> Optional[float]:
    """RSI de Wilder. Necesita al menos 2n cierres para que el suavizado asiente."""
    if len(cierres) < 2 * n:
        return None
    subidas, bajadas = [], []
    for a, b in zip(cierres, cierres[1:]):
        subidas.append(max(b - a, 0.0))
        bajadas.append(max(a - b, 0.0))
    media_s = sum(subidas[:n]) / n
    media_b = sum(bajadas[:n]) / n
    for s, b in zip(subidas[n:], bajadas[n:]):
        media_s = (media_s * (n - 1) + s) / n
        media_b = (media_b * (n - 1) + b) / n
    if media_b == 0:
        return 100.0
    return round(100 - 100 / (1 + media_s / media_b), 2)


def atr_pct(velas: Sequence[Sequence], n: int = 14) -> Optional[float]:
    """ATR de Wilder como porcentaje del ultimo cierre."""
    if len(velas) < n + 1:
        return None
    rangos = []
    for prev, v in zip(velas, velas[1:]):
        _, _, h, l, _, _ = v
        c_prev = prev[4]
        rangos.append(max(h - l, abs(h - c_prev), abs(l - c_prev)))
    atr = sum(rangos[:n]) / n
    for r in rangos[n:]:
        atr = (atr * (n - 1) + r) / n
    return round(atr / velas[-1][4] * 100, 4)


def ema(valores: Sequence[float], n: int) -> Optional[float]:
    if len(valores) < n:
        return None
    k = 2 / (n + 1)
    e = sum(valores[:n]) / n
    for x in valores[n:]:
        e = x * k + e * (1 - k)
    return e


def retorno_pct(cierres: Sequence[float], n: int) -> Optional[float]:
    if len(cierres) <= n or cierres[-1 - n] <= 0:
        return None
    return round((cierres[-1] / cierres[-1 - n] - 1) * 100, 4)


def posicion_en_rango(velas: Sequence[Sequence], n: int) -> Optional[float]:
    """0 = en el minimo de las ultimas n velas, 1 = en el maximo."""
    if len(velas) < n:
        return None
    tramo = velas[-n:]
    alto = max(v[2] for v in tramo)
    bajo = min(v[3] for v in tramo)
    if alto <= bajo:
        return None
    return round((velas[-1][4] - bajo) / (alto - bajo), 4)


def ratio_volumen(velas: Sequence[Sequence], n_base: int = 20) -> Optional[float]:
    """Volumen de la ultima vela frente a la media de las n_base anteriores."""
    if len(velas) < n_base + 1:
        return None
    base = [v[5] for v in velas[-n_base - 1:-1] if v[5] is not None]
    if len(base) < n_base or sum(base) <= 0 or velas[-1][5] is None:
        return None
    return round(velas[-1][5] / (sum(base) / len(base)), 3)


def resumen_marco(velas: Sequence[Sequence], paso_ms: int) -> dict:
    """
    Lo que se le enseña al modelo de un marco. Si faltan velas o hay huecos,
    se dice, en vez de calcular sobre una serie rota.
    """
    velas = [v for v in velas if valida(v)]
    cierres = [v[4] for v in velas]
    e25 = ema(cierres, 25)
    e99 = ema(cierres, 99)
    ultimo = cierres[-1] if cierres else None
    return {
        "n_velas": len(velas),
        "continuas": continuas(velas[-50:], paso_ms) if len(velas) > 1 else False,
        "rsi14": rsi(cierres[-100:], 14),
        "atr_pct": atr_pct(velas[-100:], 14),
        "ret_4_velas_pct": retorno_pct(cierres, 4),
        "ret_24_velas_pct": retorno_pct(cierres, 24),
        "pos_en_rango_50": posicion_en_rango(velas, 50),
        "dist_ema25_pct": round((ultimo / e25 - 1) * 100, 4) if e25 and ultimo else None,
        "dist_ema99_pct": round((ultimo / e99 - 1) * 100, 4) if e99 and ultimo else None,
        "ratio_volumen_20": ratio_volumen(velas, 20),
    }
