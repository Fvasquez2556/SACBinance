# -*- coding: utf-8 -*-
"""
La tabla de probabilidad que muestra el tablero, calibrada por distancia Y edad.

El fallo que se arregla
-----------------------
`prob_meta` usaba una tabla solo por distancia, con la banda "3-5%" en 12%. Una
senal RECIEN EMITIDA esta siempre a 3.2% de su meta (precio = entry en ese
instante), asi que el tablero le ponia 12%. Medido directamente sobre las 767
senales con ventana cumplida, desde su entry y a 6h vista: 27.5%.

Afinar las bandas no bastaba: con bandas finas, "3.0-3.5%" da 15.5% sobre
16,919 muestras. Y sin embargo las 656 muestras de esa banda que son senales
RECIEN emitidas dan 24.8%. La banda mezcla dos poblaciones distintas:

    recien emitida a 3.2%        acaba de pasar las puertas del sistema
    diez horas viva a 3.2%       lleva medio dia sin ir a ninguna parte

La distancia sola no las distingue. La edad si.

Metodo
------
Muestreo sistematico de la vida de cada senal (cada 5 min de sus 24h), que es
el mismo universo al que se aplica la tabla en produccion. Para cada muestra:
lo que falta para la meta, la edad de la senal, y si llego en las 6h
siguientes. Nada de porcentajes por debajo de MIN_N.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
SEGUIMIENTO = 360        # min hacia delante
MIN_N = 60
PASO = 5                 # min entre muestras

# La edad se corta fina al principio porque es donde mas cambia todo.
EDADES = [(0, 15, "0-15min"), (15, 60, "15-60min"),
          (60, 360, "1-6h"), (360, 10**9, ">6h")]
BANDAS = [(0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 2.5),
          (2.5, 3.0), (3.0, 3.5), (3.5, 4.0), (4.0, 5.0), (5.0, 7.0),
          (7.0, 999)]


def cargar_klines(con):
    d = defaultdict(list)
    for sym, t, h, c in con.execute(
            "SELECT symbol, open_time, h, c FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        d[sym].append((t, h, c))
    return {s: np.array(v, dtype=np.float64) for s, v in d.items()}


def precio_en(a, ts):
    i = np.searchsorted(a[:, 0], ts, side="right") - 1
    if i < 0 or i >= len(a) or ts - a[i, 0] > 5 * 60_000:
        return None
    return float(a[i, 2])


def llega(a, t0, t1, nivel):
    i = np.searchsorted(a[:, 0], t0, side="left")
    j = np.searchsorted(a[:, 0], t1, side="right")
    if j <= i:
        return None
    seg = a[i:j]
    k = np.flatnonzero(seg[:, 1] >= nivel)
    return int(seg[k[0], 0]) if len(k) else None


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    kl = cargar_klines(con)
    filas = [dict(r) for r in con.execute(
        "SELECT symbol, ts_open, entry FROM outcomes WHERE entry IS NOT NULL")]
    for f in filas:
        f["nivel"] = f["entry"] * (1 + META / 100.0)
    t_fin = max(a[-1, 0] for a in kl.values())
    print(f"{len(filas)} senales, {len(kl)} pares\n")

    D, R, E = [], [], []
    for g in filas:
        a = kl.get(g["symbol"])
        if a is None:
            continue
        for off in range(0, 24 * 60, PASO):
            T = g["ts_open"] + off * 60_000
            if T + SEGUIMIENTO * 60_000 > t_fin:
                break
            p = precio_en(a, T)
            if p is None or p <= 0:
                continue
            falta = (g["nivel"] / p - 1) * 100.0
            if falta <= 0:
                continue
            D.append(falta)
            E.append(off)
            R.append(llega(a, T, T + SEGUIMIENTO * 60_000, g["nivel"]) is not None)
    D, R, E = np.array(D), np.array(R, dtype=float), np.array(E)
    print(f"muestras: {len(D):,}   tasa global {100*R.mean():.1f}%\n")

    print("=" * 88)
    print(f"PROBABILIDAD DE LLEGAR A LA META EN {SEGUIMIENTO//60}h")
    print("=" * 88)
    print(f"  {'le falta':>12} " + " ".join(f"{lab:>17}" for _, _, lab in EDADES))
    tabla = {}
    for lo, hi in BANDAS:
        md = (D >= lo) & (D < hi)
        celdas = []
        for e0, e1, lab in EDADES:
            m = md & (E >= e0) & (E < e1)
            n = int(m.sum())
            if n < MIN_N:
                celdas.append(f"(pocas n={n})")
                tabla[(hi, e1)] = None
            else:
                p = 100 * R[m].mean()
                celdas.append(f"{p:5.1f}%  n={n:<6}")
                tabla[(hi, e1)] = (round(p), n)
        print(f"  {f'{lo}-{hi}%':>12} " + " ".join(f"{c:>17}" for c in celdas))

    print("\n  La fila 3.0-3.5% es donde cae una senal recien emitida.")
    print("  Compara su primera columna con lo que el tablero mostraba: 12%.")

    print("\n" + "=" * 88)
    print("TABLA PARA PEGAR EN retroceso.py")
    print("=" * 88)
    print("# (limite_distancia, {edad_max_min: (prob, n)})")
    print("_TABLA_META = (")
    for lo, hi in BANDAS:
        lim = 'float("inf")' if hi >= 999 else f"{hi}"
        celdas = []
        for e0, e1, lab in EDADES:
            v = tabla.get((hi, e1))
            celdas.append("None" if v is None else f"({v[0]}.0, {v[1]})")
        e_lims = ", ".join(
            f"{'float(\"inf\")' if e1 >= 10**8 else e1}: {c}"
            for (_, e1, _), c in zip(EDADES, celdas))
        print(f"    ({lim}, {{{e_lims}}}),")
    print(")")


if __name__ == "__main__":
    main()
