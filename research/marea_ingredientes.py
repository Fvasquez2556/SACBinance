# -*- coding: utf-8 -*-
"""
Cual de los ingredientes lleva la senal.

El primer barrido (marea_tranquila.py) dio un resultado sospechoso: TODAS las
combinaciones de arriba exigian caida previa, y en cambio los parametros de
quietud (rango maximo, equilibrio 1:1) casi no cambiaban el resultado. El
rango que ganaba era 3.0%, el mas FLOJO de los probados, y el equilibrio
0.50 rendia casi igual que 0.15.

Cuando el filtro mas flojo gana, el filtro no esta filtrando. La hipotesis a
descartar es que lo unico que el barrido encontro fue "comprar despues de una
caida del 2%", y que la marea tranquila no aportaba nada.

Este estudio lo separa. Cuatro ingredientes, encendidos y apagados por
separado, para ver cuanto aporta cada uno POR ENCIMA de los demas:

    A  caida previa      el precio venia de caer >= caida_min
    B  quietud RELATIVA  rango de la zona <= q x el rango normal DE ESE PAR
    C  equilibrio 1:1    |deriva| / rango <= e   (sube tanto como baja)
    D  secado de volumen volumen de la zona <= d x el volumen de la caida

B es la correccion importante del primer barrido: alli el rango era un % fijo
igual para todos, y 3% en 8 minutos es normal en una alt volatil y enorme en
una tranquila. "Quieto" solo significa algo comparado con lo que ese par hace
normalmente.
"""
from __future__ import annotations

import itertools
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
OBJETIVO = 3.2
STOP_REF = 1.2
HORIZONTE = 180          # el que mejor salio en el primer barrido
MIN_N = 50
DEDUP_MIN = 60

N_VELAS = (8, 15, 30)    # 1m
CAIDA_MIN = 2.0
CAIDA_LOOKBACK = 40
BASE_VOL = 500           # velas para el "normal" del par
Q_QUIETUD = 0.6          # rango <= 0.6 x rango tipico del par
E_EQUIL = 0.30
D_VOL = 0.7


def cargar(con) -> dict:
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


def futuro(a, h_min):
    n = len(a)
    sube = np.zeros(n, dtype=bool)
    cobra = np.zeros(n, dtype=bool)
    if n <= h_min + 1:
        return sube, cobra
    vh = np.lib.stride_tricks.sliding_window_view(a[1:, 2], h_min)
    vl = np.lib.stride_tricks.sliding_window_view(a[1:, 3], h_min)
    m = len(vh)
    c0 = a[:m, 4]
    hu = vh >= (c0 * (1 + OBJETIVO / 100.0))[:, None]
    hd = vl <= (c0 * (1 - STOP_REF / 100.0))[:, None]
    au, ad = hu.any(axis=1), hd.any(axis=1)
    iu = np.where(au, hu.argmax(axis=1), h_min + 1)
    idn = np.where(ad, hd.argmax(axis=1), h_min + 1)
    sube[:m] = au
    cobra[:m] = au & (iu < idn)
    return sube, cobra


def main() -> None:
    con = sqlite3.connect(DB)
    print("cargando...", flush=True)
    pares = cargar(con)
    print(f"{len(pares)} pares\n", flush=True)

    fut = {}
    tot = subio = cobro = 0
    for sym, a in pares.items():
        s, c = futuro(a, HORIZONTE)
        fut[sym] = (s, c)
        val = len(a) - HORIZONTE - 1
        if val > 0:
            tot += val
            subio += int(s[:val].sum())
            cobro += int(c[:val].sum())
    base_sube, base_cobra = subio / tot, cobro / tot
    print(f"CONTROL (cualquier instante, {HORIZONTE}min): llega a +{OBJETIVO}% "
          f"{100*base_sube:.2f}%   lo cobra antes de -{STOP_REF}% "
          f"{100*base_cobra:.2f}%   n={tot:,}\n", flush=True)

    for N in N_VELAS:
        print("=" * 96)
        print(f"ZONA DE {N} VELAS DE 1m")
        print("=" * 96)

        # --- ingredientes por par ---
        ing = {}
        for sym, a in pares.items():
            hi, lo, cl, vo, op = a[:, 2], a[:, 3], a[:, 4], a[:, 5], a[:, 1]
            mx = rolling(hi, N, np.max)
            mn = rolling(lo, N, np.min)
            with np.errstate(invalid="ignore", divide="ignore"):
                rango = (mx - mn) / mn * 100.0
                # rango "normal" del par: mediana de los rangos de N velas
                normal = rolling(rango, BASE_VOL, np.nanmedian)
                quietud = rango / normal
                o_ini = np.concatenate((np.full(N - 1, np.nan), op[: len(op) - N + 1]))
                deriv = (cl - o_ini) / o_ini * 100.0
                equil = np.abs(deriv) / np.where(rango > 0, rango, np.nan)
                pico = rolling(hi, CAIDA_LOOKBACK, np.max)
                pico_prev = np.concatenate((np.full(N, np.nan), pico[: len(pico) - N]))
                caida = (mn - pico_prev) / pico_prev * 100.0
                vol_zona = rolling(vo, N, np.mean)
                vol_antes = rolling(vo, CAIDA_LOOKBACK, np.mean)
                vol_prev = np.concatenate((np.full(N, np.nan),
                                           vol_antes[: len(vol_antes) - N]))
                dryup = vol_zona / np.where(vol_prev > 0, vol_prev, np.nan)
            ing[sym] = {
                "A": caida <= -CAIDA_MIN,
                "B": quietud <= Q_QUIETUD,
                "C": equil <= E_EQUIL,
                "D": dryup <= D_VOL,
            }

        def evalua(letras):
            det = up = cb = 0
            for sym, a in pares.items():
                m = np.ones(len(a), dtype=bool)
                for L in letras:
                    v = ing[sym][L]
                    m &= np.where(np.isfinite(v.astype(float)), v, False)
                pos = np.flatnonzero(m)
                pos = pos[pos < len(a) - HORIZONTE - 1]
                if len(pos) == 0:
                    continue
                keep = [pos[0]]
                for p in pos[1:]:
                    if p - keep[-1] >= DEDUP_MIN:
                        keep.append(p)
                keep = np.array(keep)
                s, c = fut[sym]
                det += len(keep)
                up += int(s[keep].sum())
                cb += int(c[keep].sum())
            return det, up, cb

        print(f"  {'ingredientes':>14} {'n':>7} {'llega':>8} {'lift':>7} "
              f"{'cobra':>8} {'lift':>7}")
        resultados = {}
        for r in range(0, 5):
            for combo in itertools.combinations("ABCD", r):
                det, up, cb = evalua(combo)
                if det < MIN_N:
                    continue
                resultados[combo] = (det, up / det, cb / det)
                etq = "".join(combo) if combo else "(ninguno)"
                print(f"  {etq:>14} {det:>7} {100*up/det:>7.1f}% "
                      f"{100*(up/det - base_sube):>+6.1f} {100*cb/det:>7.1f}% "
                      f"{100*(cb/det - base_cobra):>+6.1f}")

        # aporte marginal de cada ingrediente sobre el resto
        print(f"\n  Aporte MARGINAL de cada ingrediente (anadirlo a los otros tres):")
        base3 = tuple(sorted(set("ABCD")))
        for L in "ABCD":
            sin = tuple(sorted(set("ABCD") - {L}))
            con_ = base3
            if sin in resultados and con_ in resultados:
                d = 100 * (resultados[con_][2] - resultados[sin][2])
                print(f"    {L}: {d:+.1f} puntos de 'cobra'   "
                      f"(n pasa de {resultados[sin][0]} a {resultados[con_][0]})")
            else:
                print(f"    {L}: muestra insuficiente para medirlo")
        print()


if __name__ == "__main__":
    main()
