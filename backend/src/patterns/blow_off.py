"""Detector de techo parabolico / blow-off top (portado de v2)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from src.config.settings import get_settings


@dataclass
class BlowOffResult:
    detected: bool = False
    reason: str = ""


def detect_blow_off(candles) -> BlowOffResult:
    s = get_settings()
    if len(candles) < 25:
        return BlowOffResult()

    recent = list(candles)[-25:]
    last = recent[-1]

    body = abs(last.c - last.o)
    upper_shadow = last.h - max(last.c, last.o)
    if body <= 0 or upper_shadow < 2.0 * body:
        return BlowOffResult()

    closes = np.array([c.c for c in recent[:-1]], dtype=float)
    vols = np.array([c.v for c in recent], dtype=float)
    vol_sma20 = vols[:-1].mean() if len(vols) > 1 else 0.0
    vol_ratio = last.v / vol_sma20 if vol_sma20 > 0 else 0.0
    if vol_ratio < s.blowoff_vol_ratio:
        return BlowOffResult()

    if len(closes) < 4:
        return BlowOffResult()
    move_3 = (last.c - closes[-3]) / closes[-3] * 100.0 if closes[-3] > 0 else 0.0
    moves = []
    for i in range(3, len(closes)):
        if closes[i - 3] > 0:
            moves.append((closes[i] - closes[i - 3]) / closes[i - 3] * 100.0)
    if not moves:
        return BlowOffResult()
    p90 = float(np.percentile(moves, 90))
    if move_3 < p90:
        return BlowOffResult()

    reason = (
        f"sombra={upper_shadow/body:.1f}x cuerpo | "
        f"vol={vol_ratio:.1f}x SMA20 | mov3={move_3:.1f}%>P90({p90:.1f}%)"
    )
    return BlowOffResult(detected=True, reason=reason)
