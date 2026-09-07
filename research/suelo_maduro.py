# -*- coding: utf-8 -*-
"""
¿Importa cuanto hace que se marco el suelo?

Motivo: con el orden nuevo, REZUSDT aparecio SEGUNDO en el tablero con score 0,
estado CAYENDO y el suelo marcado hace 0 minutos. El patron valida "viene de
caer", pero no exige que la caida haya PARADO. Antes de dejar eso arriba hay
que medir si esperar a que el suelo tenga unos minutos cambia el resultado.

El estudio original no lo separo: media cualquier instante tras una caida >=2%.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
OBJETIVO = 3.2
STOP_REF = 1.2
HORIZONTE = 180
DEDUP_MIN = 60
N = 8               # velas donde se busca el suelo
LOOKBACK = 40       # velas previas donde se busca el pico
CAIDA_MIN = 2.0
MIN_N = 50


def cargar(con):
    d = defaultdict(list)
    for row in con.execute("SELECT symbol, open_time, o, h, l, c FROM klines "
                           "WHERE tf='1m' ORDER BY symbol, open_time"):
        d[row[0]].append(row[1:])
    out = {}
    for sym, filas in d.items():
        if len(filas) < 1200:
            continue
        a = np.array(filas, dtype=np.float64)
        dd = np.diff(a[:, 0])
        if len(dd) and (dd > 5 * 60_000).sum() > len(dd) * 0.02:
            continue
        out[sym] = a
    return out


def rolling(x, n, func):
    if len(x) < n:
        return np.full(len(x), np.nan)
    v = np.lib.stride_tricks.sliding_window_view(x, n)
    return np.concatenate((np.full(n - 1, np.nan), func(v, axis=1)))


def futuro(a, h):
    n = len(a)
    sube = np.zeros(n, dtype=bool)
    cobra = np.zeros(n, dtype=bool)
    if n <= h + 1:
        return sube, cobra
    vh = np.lib.stride_tricks.sliding_window_view(a[1:, 2], h)
    vl = np.lib.stride_tricks.sliding_window_view(a[1:, 3], h)
    m = len(vh)
    c0 = a[:m, 4]
    hu = vh >= (c0 * (1 + OBJETIVO / 100.0))[:, None]
    hd = vl <= (c0 * (1 - STOP_REF / 100.0))[:, None]
    au, ad = hu.any(axis=1), hd.any(axis=1)
    iu = np.where(au, hu.argmax(axis=1), h + 1)
    idn = np.where(ad, hd.argmax(axis=1), h + 1)
    sube[:m] = au
    cobra[:m] = au & (iu < idn)
    return sube, cobra


def main():
    con = sqlite3.connect(DB)
    pares = cargar(con)
    print(f"{len(pares)} pares\n")

    fut, tot, sub, cob = {}, 0, 0, 0
    for sym, a in pares.items():
        s, c = futuro(a, HORIZONTE)
        fut[sym] = (s, c)
        v = len(a) - HORIZONTE - 1
        if v > 0:
            tot += v
            sub += int(s[:v].sum())
            cob += int(c[:v].sum())
    b_sube, b_cobra = sub / tot, cob / tot
    print(f"CONTROL: llega {100*b_sube:.2f}%   cobra {100*b_cobra:.2f}%   n={tot:,}\n")

    # metricas por par
    datos = {}
    for sym, a in pares.items():
        hi, lo, cl = a[:, 2], a[:, 3], a[:, 4]
        mn = rolling(lo, N, np.min)
        pico = rolling(hi, LOOKBACK, np.max)
        pico_prev = np.concatenate((np.full(N, np.nan), pico[: len(pico) - N]))
        with np.errstate(invalid="ignore", divide="ignore"):
            caida = (mn - pico_prev) / pico_prev * 100.0
            rebote = (cl - mn) / mn * 100.0
        # minutos desde el suelo: cuantas velas atras esta el minimo de la ventana
        edad = np.full(len(a), -1.0)
        v = np.lib.stride_tricks.sliding_window_view(lo, N)
        arg = v.argmin(axis=1)               # 0 = la mas antigua de la ventana
        edad[N - 1:] = (N - 1) - arg         # velas desde el minimo hasta ahora
        datos[sym] = (caida <= -CAIDA_MIN, edad, rebote)

    def mide(filtro):
        det = up = cb = 0
        for sym, a in pares.items():
            ok, edad, rebote = datos[sym]
            m = ok & filtro(edad, rebote)
            m = np.where(np.isfinite(m.astype(float)), m, False)
            pos = np.flatnonzero(m)
            pos = pos[pos < len(a) - HORIZONTE - 1]
            if len(pos) == 0:
                continue
            keep = [pos[0]]
            for p in pos[1:]:
                if p - keep[-1] >= DEDUP_MIN:
                    keep.append(p)
            k = np.array(keep)
            s, c = fut[sym]
            det += len(k)
            up += int(s[k].sum())
            cb += int(c[k].sum())
        return det, up, cb

    print("=" * 88)
    print("EDAD DEL SUELO: ¿conviene esperar a que la caida pare?")
    print("=" * 88)
    print(f"  {'filtro':>34} {'n':>7} {'llega':>8} {'lift':>7} {'cobra':>8} {'lift':>7}")
    pruebas = [
        ("patron solo (como esta ahora)", lambda e, r: e >= 0),
        ("suelo hace >= 1 vela", lambda e, r: e >= 1),
        ("suelo hace >= 2 velas", lambda e, r: e >= 2),
        ("suelo hace >= 3 velas", lambda e, r: e >= 3),
        ("suelo hace >= 5 velas", lambda e, r: e >= 5),
        ("suelo en la vela actual (e=0)", lambda e, r: e == 0),
        ("ya rebotado >= 0.5% del suelo", lambda e, r: r >= 0.5),
        ("ya rebotado >= 1.0% del suelo", lambda e, r: r >= 1.0),
        ("rebotado >=0.5% y suelo >=2 velas", lambda e, r: (r >= 0.5) & (e >= 2)),
    ]
    for etq, f in pruebas:
        det, up, cb = mide(f)
        if det < MIN_N:
            print(f"  {etq:>34} {det:>7}   (pocas)")
            continue
        print(f"  {etq:>34} {det:>7} {100*up/det:>7.1f}% "
              f"{100*(up/det - b_sube):>+6.1f} {100*cb/det:>7.1f}% "
              f"{100*(cb/det - b_cobra):>+6.1f}")


if __name__ == "__main__":
    main()
