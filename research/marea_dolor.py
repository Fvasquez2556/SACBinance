# -*- coding: utf-8 -*-
"""
Si la marea tranquila no cambia la probabilidad, cambia el dolor?

El estudio de ingredientes dejo claro que la caida previa (A) lleva casi toda
la senal y que la quietud (B), el equilibrio 1:1 (C) y el secado de volumen (D)
aportan 1-2 puntos, dentro del ruido. Pero "probabilidad de llegar" no es lo
unico que importa: dos entradas con la misma probabilidad pueden exigir stops
muy distintos. Si entrar en la zona tranquila reduce el retroceso que hay que
aguantar, sirve igual — no para acertar mas, sino para arriesgar menos.

Mide, para cada conjunto de detecciones, lo que pasa en los 180 minutos
siguientes: el retroceso maximo (MAE), la subida maxima (MFE) y cuanto tarda.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
OBJETIVO = 3.2
HORIZONTE = 180
DEDUP_MIN = 60
N = 8
CAIDA_MIN = 2.0
CAIDA_LOOKBACK = 40
BASE_VOL = 500
Q_QUIETUD = 0.6
E_EQUIL = 0.30
D_VOL = 0.7


def cargar(con):
    datos = defaultdict(list)
    q = ("SELECT symbol, open_time, o, h, l, c, v FROM klines "
         "WHERE tf='1m' ORDER BY symbol, open_time")
    for row in con.execute(q):
        datos[row[0]].append(row[1:])
    out = {}
    for sym, filas in datos.items():
        if len(filas) < 1200:
            continue
        a = np.array(filas, dtype=np.float64)
        d = np.diff(a[:, 0])
        if len(d) and (d > 5 * 60_000).sum() > len(d) * 0.02:
            continue
        out[sym] = a
    return out


def rolling(x, n, func):
    if len(x) < n:
        return np.full(len(x), np.nan)
    v = np.lib.stride_tricks.sliding_window_view(x, n)
    return np.concatenate((np.full(n - 1, np.nan), func(v, axis=1)))


def main():
    con = sqlite3.connect(DB)
    pares = cargar(con)
    print(f"{len(pares)} pares, zona de {N} velas 1m, horizonte {HORIZONTE}min\n")

    # ventanas hacia delante: MFE, MAE y minuto en que se toca el objetivo
    fw = {}
    for sym, a in pares.items():
        n = len(a)
        if n <= HORIZONTE + 1:
            continue
        vh = np.lib.stride_tricks.sliding_window_view(a[1:, 2], HORIZONTE)
        vl = np.lib.stride_tricks.sliding_window_view(a[1:, 3], HORIZONTE)
        m = len(vh)
        c0 = a[:m, 4]
        mfe = (vh.max(axis=1) / c0 - 1) * 100.0
        mae = (vl.min(axis=1) / c0 - 1) * 100.0
        hu = vh >= (c0 * (1 + OBJETIVO / 100.0))[:, None]
        au = hu.any(axis=1)
        tmin = np.where(au, hu.argmax(axis=1) + 1, -1)
        # retroceso ANTES de tocar el objetivo: lo que hay que aguantar
        prev = np.full(m, np.nan)
        idx = np.flatnonzero(au)
        for i in idx:
            t = tmin[i]
            prev[i] = (vl[i, :t].min() / c0[i] - 1) * 100.0
        fw[sym] = (mfe, mae, au, tmin, prev, m)

    ing = {}
    for sym, a in pares.items():
        if sym not in fw:
            continue
        hi, lo, cl, vo, op = a[:, 2], a[:, 3], a[:, 4], a[:, 5], a[:, 1]
        mx, mn = rolling(hi, N, np.max), rolling(lo, N, np.min)
        with np.errstate(invalid="ignore", divide="ignore"):
            rango = (mx - mn) / mn * 100.0
            quietud = rango / rolling(rango, BASE_VOL, np.nanmedian)
            o_ini = np.concatenate((np.full(N - 1, np.nan), op[: len(op) - N + 1]))
            equil = np.abs((cl - o_ini) / o_ini * 100.0) / np.where(rango > 0, rango, np.nan)
            pico = rolling(hi, CAIDA_LOOKBACK, np.max)
            pico_prev = np.concatenate((np.full(N, np.nan), pico[: len(pico) - N]))
            caida = (mn - pico_prev) / pico_prev * 100.0
            vz = rolling(vo, N, np.mean)
            va = rolling(vo, CAIDA_LOOKBACK, np.mean)
            vprev = np.concatenate((np.full(N, np.nan), va[: len(va) - N]))
            dry = vz / np.where(vprev > 0, vprev, np.nan)
        ing[sym] = {"A": caida <= -CAIDA_MIN, "B": quietud <= Q_QUIETUD,
                    "C": equil <= E_EQUIL, "D": dry <= D_VOL}

    def recoge(letras):
        MFE, MAE, PREV, TMIN, hits, tot = [], [], [], [], 0, 0
        for sym, a in pares.items():
            if sym not in fw:
                continue
            mfe, mae, au, tmin, prev, m = fw[sym]
            mask = np.ones(len(a), dtype=bool)
            for L in letras:
                v = ing[sym][L]
                mask &= np.where(np.isfinite(v.astype(float)), v, False)
            pos = np.flatnonzero(mask)
            pos = pos[pos < m]
            if len(pos) == 0:
                continue
            keep = [pos[0]]
            for p in pos[1:]:
                if p - keep[-1] >= DEDUP_MIN:
                    keep.append(p)
            k = np.array(keep)
            MFE.append(mfe[k]); MAE.append(mae[k])
            tot += len(k); hits += int(au[k].sum())
            kk = k[au[k]]
            if len(kk):
                TMIN.append(tmin[kk]); PREV.append(prev[kk])
        j = lambda L: np.concatenate(L) if L else np.array([])
        return j(MFE), j(MAE), j(PREV), j(TMIN), hits, tot

    print(f"  {'conjunto':>26} {'n':>6} {'cobra':>7} {'MFE med':>9} {'MAE med':>9} "
          f"{'MAE p90':>9} {'aguantar':>9} {'tarda':>8}")
    for letras, etq in [((), "cualquier instante"),
                        (("A",), "A  solo caida"),
                        (("A", "B"), "AB caida + quietud"),
                        (("A", "C"), "AC caida + 1:1"),
                        (("A", "D"), "AD caida + vol seco"),
                        (("A", "B", "C"), "ABC caida+quiet+1:1"),
                        (("A", "B", "C", "D"), "ABCD los cuatro"),
                        (("B", "C"), "BC quietud + 1:1 sin caida")]:
        mfe, mae, prev, tmin, hits, tot = recoge(letras)
        if tot < 50:
            print(f"  {etq:>26} {tot:>6}   (pocas)")
            continue
        med = lambda x: np.median(x) if len(x) else float("nan")
        p90 = np.percentile(mae, 10) if len(mae) else float("nan")  # el 10% peor
        print(f"  {etq:>26} {tot:>6} {100*hits/tot:>6.1f}% {med(mfe):>+8.2f}% "
              f"{med(mae):>+8.2f}% {p90:>+8.2f}% {med(prev):>+8.2f}% "
              f"{med(tmin):>7.0f}m")
    print("\n  'aguantar' = retroceso maximo ANTES de tocar el objetivo, solo en")
    print("  las que lo tocaron. Es el stop minimo que habria hecho falta.")
    print("  'MAE p90'   = el 10% de casos peores.")


if __name__ == "__main__":
    main()
