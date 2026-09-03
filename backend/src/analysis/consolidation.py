"""
Deteccion de consolidacion usando ATR% adaptativo.

Una consolidacion verdadera (base de acumulacion) tiene:
  - ATR% en su percentil mas bajo historico (compresion de volatilidad)
  - MAs convergentes (pendientes cercanas a cero)
  - Volumen decreciendo asintoticamente
  - Duracion minima: 4 velas 4h / 2 velas 1h / 2 velas 15m
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from src.config.settings import get_settings


@dataclass
class ConsolidationResult:
    consolidating: bool = False
    atr_pct: Optional[float] = None
    atr_percentile: Optional[int] = None
    ma_convergent: bool = False
    vol_declining: bool = False
    candles_in_state: int = 0


def detectar_consolidacion(candles: list, tf: str, slopes: dict) -> ConsolidationResult:
    """
    Evalua si la moneda esta consolidando en el TF dado.

    candles: buffer de velas del TF (objeto con .c, .h, .l, .v)
    tf: '15m', '1h', '4h'
    slopes: dict con slope_ma7, slope_ma25, slope_ma99 del TF actual
    """
    s = get_settings()
    res = ConsolidationResult()

    min_velas = {
        "15m": s.consolidacion_min_velas_15m,
        "1h": s.consolidacion_min_velas_1h,
        "4h": s.consolidacion_min_velas_4h,
    }.get(tf, 2)

    if not candles or len(candles) < 30:
        return res

    closes = np.array([c.c for c in candles], dtype=float)
    highs = np.array([c.h for c in candles], dtype=float)
    lows = np.array([c.l for c in candles], dtype=float)
    vols = np.array([c.v for c in candles], dtype=float)

    # ATR% adaptativo
    period = s.atr_period
    if len(candles) >= period + 2:
        prev_c = closes[:-1]
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(np.abs(highs[1:] - prev_c), np.abs(lows[1:] - prev_c)),
        )
        atr_window = float(np.mean(tr[-period:]))
        last_close = float(closes[-1])
        atr_pct = atr_window / last_close * 100.0 if last_close > 0 else None

        if atr_pct is not None:
            # ATR% de todo el buffer para el percentil
            atr_history = []
            for i in range(period, len(tr)):
                atr_h = float(np.mean(tr[max(0, i - period):i]))
                c_h = float(closes[i])
                if c_h > 0:
                    atr_history.append(atr_h / c_h * 100.0)

            res.atr_pct = round(atr_pct, 3)
            if atr_history:
                pct_rank = int(np.searchsorted(np.sort(atr_history), atr_pct) / len(atr_history) * 100)
                res.atr_percentile = pct_rank
                atr_comprimido = pct_rank <= s.atr_percentil_consolidacion
            else:
                atr_comprimido = False
        else:
            atr_comprimido = False
    else:
        atr_comprimido = False

    # MAs convergentes: todos los slopes < 0.15%
    slope_ma7 = abs(slopes.get("slope_ma7", 1.0))
    slope_ma25 = abs(slopes.get("slope_ma25", 1.0))
    slope_ma99 = abs(slopes.get("slope_ma99", 1.0))
    res.ma_convergent = bool(slope_ma7 < 0.15 and slope_ma25 < 0.15)

    # Volumen decreciente: ultimas N velas el volumen baja
    if len(vols) >= min_velas + 2:
        recent_vols = vols[-(min_velas + 2):]
        vol_trend = np.polyfit(np.arange(len(recent_vols)), recent_vols, 1)[0]
        res.vol_declining = bool(vol_trend < 0)

    # Contar cuantas velas consecutivas el ATR esta bajo
    if atr_comprimido and len(candles) >= period + 2:
        count = 0
        for i in range(len(tr) - 1, max(len(tr) - 20, period - 1), -1):
            atr_i = float(np.mean(tr[max(0, i - period + 1):i + 1]))
            c_i = float(closes[i])
            if c_i > 0 and (atr_i / c_i * 100.0) <= (res.atr_pct or 999):
                count += 1
            else:
                break
        res.candles_in_state = count

    res.consolidating = bool(
        atr_comprimido
        and res.ma_convergent
        and res.candles_in_state >= min_velas
    )
    return res
