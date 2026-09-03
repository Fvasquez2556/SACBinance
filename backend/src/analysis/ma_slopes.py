"""
Calculo de pendiente de Medias Moviles por timeframe.

La pendiente (slope) es la variacion porcentual de la MA en los ultimos N
periodos. Es la metrica central del v3 para determinar la "gravedad
direccional" del mercado en cada TF.
"""
from __future__ import annotations
from typing import List, Optional, Sequence

import numpy as np

from src.config.settings import get_settings


def _ema(closes: np.ndarray, period: int) -> np.ndarray:
    a = 2.0 / (period + 1.0)
    out = np.empty_like(closes)
    out[0] = closes[0]
    for i in range(1, len(closes)):
        out[i] = a * closes[i] + (1.0 - a) * out[i - 1]
    return out


def calcular_slope(ma_series: Sequence[float], periodos: int) -> float:
    """
    Variacion porcentual de la MA en los ultimos N periodos.
    Positivo = subiendo, negativo = bajando.
    """
    if len(ma_series) < periodos + 1:
        return 0.0
    actual = ma_series[-1]
    anterior = ma_series[-(periodos + 1)]
    if anterior <= 0:
        return 0.0
    return (actual - anterior) / anterior * 100.0


def tendencia_timeframe(
    slope_ma7: float,
    slope_ma25: float,
    slope_ma99: float,
    alcista: float,
    bajista: float,
) -> str:
    """
    Promedio ponderado de pendientes -> 'ALCISTA' / 'NEUTRAL' / 'BAJISTA'.
    MA7 pesa mas porque reacciona antes; MA99 es el ancla macro.
    """
    promedio = slope_ma7 * 0.5 + slope_ma25 * 0.3 + slope_ma99 * 0.2
    if promedio > alcista:
        return "ALCISTA"
    if promedio < bajista:
        return "BAJISTA"
    return "NEUTRAL"


def analizar_tf(candles: list, lookback: Optional[int] = None) -> dict:
    """
    Calcula MA7/25/99, sus slopes y la tendencia resultante de un buffer de velas.
    Devuelve un dict con 'ma7', 'ma25', 'ma99', 'slope_ma7', ..., 'tendencia'.
    Devuelve None si no hay suficientes velas.
    """
    s = get_settings()
    lb = lookback or s.slope_lookback
    min_needed = 99 + lb + 1

    if not candles or len(candles) < min_needed:
        return {"tendencia": "NEUTRAL", "valid": False}

    closes = np.array([c.c for c in candles], dtype=float)
    ema7 = _ema(closes, 7)
    ema25 = _ema(closes, 25)
    ema99 = _ema(closes, 99)

    slope7 = calcular_slope(ema7, lb)
    slope25 = calcular_slope(ema25, lb)
    slope99 = calcular_slope(ema99, lb)

    tendencia = tendencia_timeframe(
        slope7, slope25, slope99,
        s.slope_alcista, s.slope_bajista
    )

    return {
        "valid": True,
        "tendencia": tendencia,
        "ma7": float(ema7[-1]),
        "ma25": float(ema25[-1]),
        "ma99": float(ema99[-1]),
        "slope_ma7": round(float(slope7), 4),
        "slope_ma25": round(float(slope25), 4),
        "slope_ma99": round(float(slope99), 4),
        "n_candles": len(candles),
    }


def calcular_atr_pct(candles: list, period: int = 14) -> Optional[float]:
    """ATR% = ATR / precio_cierre * 100. Normalizado y comparable entre pares."""
    if len(candles) < period + 2:
        return None
    h = np.array([c.h for c in candles], dtype=float)
    lo = np.array([c.l for c in candles], dtype=float)
    c_arr = np.array([c.c for c in candles], dtype=float)
    prev_c = c_arr[:-1]
    tr = np.maximum(
        h[1:] - lo[1:],
        np.maximum(np.abs(h[1:] - prev_c), np.abs(lo[1:] - prev_c)),
    )
    # Wilder smoothing
    atr = float(np.mean(tr[:period]))
    for t in tr[period:]:
        atr = (atr * (period - 1) + float(t)) / period
    last_close = float(c_arr[-1])
    if last_close <= 0:
        return None
    return atr / last_close * 100.0
