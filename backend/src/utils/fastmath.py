"""
Primitivas numericas rapidas compartidas.

`ema()` reemplaza los bucles Python de indicators/calculator.py y
analysis/ma_slopes.py. Es identica bit a bit al bucle original pero delega la
recursion a scipy.signal.lfilter (implementado en C), ~50x mas rapida sobre
buffers de 300+ velas. Si scipy no esta instalado cae al bucle original.

Motivo: al segundo 0 de cada minuto cierran las velas 1m de los ~250 pares a la
vez. Con el bucle Python eso son ~2.5M iteraciones en rafaga sobre el event
loop, que durante ese tiempo no lee del WebSocket.
"""
from __future__ import annotations

import numpy as np

try:
    from scipy.signal import lfilter as _lfilter
    HAS_SCIPY = True
except ImportError:  # pragma: no cover
    HAS_SCIPY = False


def ema(x, period: int) -> np.ndarray:
    """
    EMA recursiva: y[0] = x[0], y[i] = a*x[i] + (1-a)*y[i-1], a = 2/(period+1).
    Devuelve la serie completa (mismo shape que x).
    """
    arr = np.asarray(x, dtype=float)
    n = arr.size
    if n == 0:
        return arr.copy()
    a = 2.0 / (period + 1.0)
    b = 1.0 - a

    if HAS_SCIPY:
        # zi elegido para que y[0] == x[0] exactamente
        zi = np.array([b * arr[0]], dtype=float)
        y, _ = _lfilter([a], [1.0, -b], arr, zi=zi)
        return y

    out = np.empty_like(arr)
    out[0] = arr[0]
    for i in range(1, n):
        out[i] = a * arr[i] + b * out[i - 1]
    return out
