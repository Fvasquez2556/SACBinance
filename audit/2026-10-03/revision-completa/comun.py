"""Carga de la fuente congelada y utilidades comunes (velas densas por minuto)."""
from __future__ import annotations

import gzip
import pickle
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
FUENTE = AQUI / "fuente.pkl.gz"
COSTE = 0.5          # puntos porcentuales por operación (ida y vuelta), supuesto del proyecto
TP, SL = 2.67, 1.8   # meta bruta y stop fijo que pidió Felix
CORTE_MIN = 1790121600000 // 60000   # 2026-09-24 00:00 UTC: separa exploración y comprobación


def cargar():
    with gzip.open(FUENTE, "rb") as g:
        return pickle.load(g)


class Serie:
    """Velas de 1 minuto de una moneda en arreglos densos (NaN donde falta el minuto)."""

    def __init__(self, t, o, h, l, c, v):
        self.base = int(t[0])
        n = int(t[-1]) - self.base + 1
        idx = (t - self.base).astype(np.int64)
        self.o = np.full(n, np.nan); self.h = np.full(n, np.nan)
        self.l = np.full(n, np.nan); self.c = np.full(n, np.nan); self.v = np.full(n, np.nan)
        self.o[idx] = o; self.h[idx] = h; self.l[idx] = l; self.c[idx] = c; self.v[idx] = v
        self.n = n

    def i(self, minuto: int) -> int:
        return int(minuto) - self.base


def primer_alcance(h, l, entrada, tp_pct, sl_pct):
    """Recorre velas desde la entrada: 'TP', 'SL' o None. Misma vela con los dos -> SL."""
    arriba = entrada * (1 + tp_pct / 100)
    abajo = entrada * (1 - sl_pct / 100)
    toca_sl = l <= abajo
    toca_tp = h >= arriba
    i_sl = np.argmax(toca_sl) if toca_sl.any() else None
    i_tp = np.argmax(toca_tp) if toca_tp.any() else None
    if i_sl is None and i_tp is None:
        return None, None
    if i_tp is None or (i_sl is not None and i_sl <= i_tp):
        return "SL", int(i_sl)
    return "TP", int(i_tp)
