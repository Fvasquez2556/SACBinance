"""
Detector de breakout incipiente.

Un breakout valido (segun el plan v3):
  - El precio cruza por encima de la MA99 del 1h (sale del rango macro)
  - Volumen de la vela actual > breakout_vol_mult × SMA20 de volumen
  - Score del par >= breakout_score_min

Es el unico estado "detonante visual" del dashboard, por eso el filtro es
estricto: cruce estructural + volumen real + score alto, los tres a la vez.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import get_settings


@dataclass
class BreakoutResult:
    detected: bool = False
    reason: str = ""


def detectar_breakout(
    candles_1m: list,
    ma99_1h: float,
    score: int,
) -> BreakoutResult:
    """
    candles_1m: buffer de velas 1m (.c, .v)
    ma99_1h: valor actual de la MA99 del timeframe 1h
    score: score actual del par (ya con gate macro aplicado)
    """
    s = get_settings()
    res = BreakoutResult()

    if not ma99_1h or ma99_1h <= 0:
        return res
    if score < s.breakout_score_min:
        return res
    if len(candles_1m) < 25:
        return res

    closes = [c.c for c in candles_1m]
    vols = [c.v for c in candles_1m]

    # Cruce: ahora por encima de la MA99 1h, pero hace pocas velas estaba debajo
    price_now = closes[-1]
    lookback = s.breakout_cross_lookback
    estaba_debajo = any(c <= ma99_1h for c in closes[-(lookback + 1):-1])
    cruzo = price_now > ma99_1h and estaba_debajo
    if not cruzo:
        return res

    # Volumen: ultima vela vs SMA20 de las 20 previas
    sma20 = sum(vols[-21:-1]) / 20.0 if len(vols) >= 21 else 0.0
    vol_ratio = vols[-1] / sma20 if sma20 > 0 else 0.0
    if vol_ratio < s.breakout_vol_mult:
        return res

    dist_pct = (price_now - ma99_1h) / ma99_1h * 100.0
    res.detected = True
    res.reason = (
        f"cruce MA99-1h (+{dist_pct:.2f}%) | vol={vol_ratio:.1f}× SMA20 | score={score}"
    )
    return res
