"""
Indicadores tecnicos (portado de v2, numpy vectorizado).
Funciona sobre cualquier TF — el caller pasa los arrays correctos.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from src.utils.fastmath import ema as _fast_ema

EMA_SHORT, EMA_MEDIUM, EMA_LONG = 7, 25, 99
RSI_SLOW, RSI_FAST = 14, 5
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BB_PERIOD, BB_STD = 20, 2.0
ATR_PERIOD = 20
VOL_MA = 20
ALMA_OFFSET, ALMA_SIGMA = 0.85, 6.0
_MIN_CANDLES = EMA_LONG + 5


@dataclass
class IndSnap:
    valid: bool = False
    ema7: float = 0.0
    ema25: float = 0.0
    ema99: float = 0.0
    rsi14: float = 50.0
    rsi5: float = 50.0
    macd_hist: float = 0.0
    macd_hist_prev: float = 0.0
    bb_position: float = 0.5
    bb_width: float = 0.0
    atr_pct: float = 0.0
    vol_ratio: float = 1.0
    alma25: float = 0.0
    trend_up: bool = False
    macd_rising: bool = False


def _ema(x: np.ndarray, period: int) -> np.ndarray:
    return _fast_ema(x, period)


def _rsi(close: np.ndarray, period: int) -> float:
    if len(close) <= period:
        return 50.0
    d = np.diff(close)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag = _ema(gain, 2 * period - 1)[-1]
    al = _ema(loss, 2 * period - 1)[-1]
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def _alma_last(close: np.ndarray, window: int) -> float:
    if len(close) < window:
        return float(close[-1])
    m = ALMA_OFFSET * (window - 1)
    s = window / ALMA_SIGMA
    i = np.arange(window)
    w = np.exp(-((i - m) ** 2) / (2 * s * s))
    w /= w.sum()
    return float(np.dot(close[-window:], w))


def compute_indicators(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
) -> Optional[IndSnap]:
    n = len(closes)
    if n < _MIN_CANDLES:
        return None
    c = np.asarray(closes, dtype=float)
    h = np.asarray(highs, dtype=float)
    low = np.asarray(lows, dtype=float)
    v = np.asarray(volumes, dtype=float)
    if np.any(c <= 0):
        return None

    snap = IndSnap(valid=True)
    ema7 = _ema(c, EMA_SHORT)
    ema25 = _ema(c, EMA_MEDIUM)
    ema99 = _ema(c, EMA_LONG)
    snap.ema7 = float(ema7[-1])
    snap.ema25 = float(ema25[-1])
    snap.ema99 = float(ema99[-1])
    snap.rsi14 = float(_rsi(c, RSI_SLOW))
    snap.rsi5 = float(_rsi(c, RSI_FAST))

    macd_line = _ema(c, MACD_FAST) - _ema(c, MACD_SLOW)
    signal = _ema(macd_line, MACD_SIGNAL)
    hist = macd_line - signal
    snap.macd_hist = float(hist[-1])
    snap.macd_hist_prev = float(hist[-2]) if len(hist) >= 2 else 0.0
    snap.macd_rising = bool(snap.macd_hist > snap.macd_hist_prev and snap.macd_hist > 0)

    if n >= BB_PERIOD:
        seg = c[-BB_PERIOD:]
        mid = seg.mean()
        sd = seg.std()
        up, lo = mid + BB_STD * sd, mid - BB_STD * sd
        rng = up - lo
        if rng > 0 and mid > 0:
            snap.bb_position = float((c[-1] - lo) / rng)
            snap.bb_width = float(rng / mid)

    if n >= ATR_PERIOD + 1:
        prev_c = c[:-1]
        tr = np.maximum(
            h[1:] - low[1:],
            np.maximum(np.abs(h[1:] - prev_c), np.abs(low[1:] - prev_c)),
        )
        atr = _ema(tr, 2 * ATR_PERIOD - 1)[-1]
        snap.atr_pct = float(atr / c[-1] * 100.0) if c[-1] > 0 else 0.0

    if n >= VOL_MA:
        vsma = v[-VOL_MA:].mean()
        snap.vol_ratio = float(v[-1] / vsma) if vsma > 0 else 1.0

    snap.alma25 = float(_alma_last(c, EMA_MEDIUM))
    snap.trend_up = bool(snap.ema7 > snap.ema25 > snap.ema99 and float(c[-1]) > snap.ema99)
    return snap


def indicators_from_candles(candles) -> Optional[IndSnap]:
    if not candles or len(candles) < _MIN_CANDLES:
        return None
    cl, hi, lo, vo = [], [], [], []
    for k in candles:
        cl.append(k.c)
        hi.append(k.h)
        lo.append(k.l)
        vo.append(k.v)
    return compute_indicators(cl, hi, lo, vo)
