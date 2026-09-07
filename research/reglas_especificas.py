# -*- coding: utf-8 -*-
"""
¿Reglas por moneda, o reglas normalizadas por el caracter de la moneda?

La idea de Felix: reglas globales que filtren y reglas especificas por moneda
que confirmen. El instinto es correcto —una caida del 2% no significa lo mismo
en un par que se mueve 0.5% al dia que en uno que se mueve 5%— pero hay dos
formas muy distintas de implementarlo y solo una es viable:

  (a) POR MONEDA: aprender el umbral de cada par con su propio historial.
      Requiere suficientes senales POR PAR. Esto es lo que se mide aqui.

  (b) NORMALIZADA: un solo umbral global, expresado en unidades del propio par
      (multiplos de su ATR, de su rango tipico). No necesita historial de
      senales: el normalizador sale de las velas recientes de ese par.

Este estudio responde tres cosas:
  1. ¿Cuantas senales hay por par? Decide si (a) es siquiera posible.
  2. ¿El umbral optimo de caida cambia segun la volatilidad del par? Si no
     cambia, la idea entera sobra.
  3. ¿Normalizar por ATR bate al umbral fijo del 2%?
"""
from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict

import numpy as np

DB = "data/sacbinance.db"
OBJETIVO = 3.2
STOP_REF = 1.2
HORIZONTE = 180
DEDUP_MIN = 60
ZONA = 8
LOOKBACK = 40
MIN_N = 60


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
    con.row_factory = sqlite3.Row

    # --- 1. ¿Hay senales suficientes por par? ---
    print("=" * 88)
    print("1. ¿ES POSIBLE UNA REGLA POR MONEDA?")
    print("=" * 88)
    cnt = Counter(r[0] for r in con.execute(
        "SELECT symbol FROM outcomes WHERE sombra=0"))
    n_pares = len(cnt)
    total = sum(cnt.values())
    vals = sorted(cnt.values(), reverse=True)
    print(f"  {total} senales repartidas en {n_pares} pares")
    print(f"  mediana por par: {vals[len(vals)//2]}   "
          f"el que mas: {vals[0]}   el que menos: {vals[-1]}")
    for umbral in (10, 20, 30, 50):
        n = sum(1 for v in vals if v >= umbral)
        print(f"  pares con >= {umbral:>2} senales: {n:>3} de {n_pares} "
              f"({100*n/n_pares:.0f}%)")
    print("\n  Para estimar un porcentaje por par hacen falta ~30 casos. Con la")
    print("  mediana actual, una regla por moneda ajustaria ruido, no la moneda.")

    # --- 2 y 3: sobre velas ---
    pares = cargar(con)
    print(f"\n{len(pares)} pares con velas utilizables\n")

    fut, tot, cob = {}, 0, 0
    for sym, a in pares.items():
        s, c = futuro(a, HORIZONTE)
        fut[sym] = (s, c)
        v = len(a) - HORIZONTE - 1
        if v > 0:
            tot += v
            cob += int(c[:v].sum())
    base = cob / tot
    print(f"CONTROL: {100*base:.2f}% cobra desde un instante cualquiera\n")

    # metricas por par + su volatilidad tipica
    datos, atr_par = {}, {}
    for sym, a in pares.items():
        hi, lo, cl = a[:, 2], a[:, 3], a[:, 4]
        mn = rolling(lo, ZONA, np.min)
        pico = rolling(hi, LOOKBACK, np.max)
        pico_prev = np.concatenate((np.full(ZONA, np.nan),
                                    pico[: len(pico) - ZONA]))
        with np.errstate(invalid="ignore", divide="ignore"):
            caida = (mn - pico_prev) / pico_prev * 100.0
            rebote = (cl - mn) / mn * 100.0
            # rango tipico del par en ventanas de 48 velas: su "caracter"
            rango48 = (rolling(hi, 48, np.max) - rolling(lo, 48, np.min)) / \
                      rolling(lo, 48, np.min) * 100.0
        tip = float(np.nanmedian(rango48))
        atr_par[sym] = tip
        datos[sym] = (caida, rebote, rango48, tip)

    tips = np.array([v for v in atr_par.values() if np.isfinite(v)])
    q = np.percentile(tips, [33, 66])
    print("=" * 88)
    print("2. ¿EL UMBRAL OPTIMO CAMBIA SEGUN EL CARACTER DEL PAR?")
    print("=" * 88)
    print(f"  Pares partidos por su rango tipico de 48min: "
          f"tranquilos <{q[0]:.2f}%, medios, movidos >{q[1]:.2f}%\n")

    def evalua(syms, umbral_fijo=None, mult_atr=None):
        det = cb = 0
        for sym in syms:
            a = pares.get(sym)
            if a is None:
                continue
            caida, rebote, rango48, tip = datos[sym]
            if umbral_fijo is not None:
                ok = caida <= -umbral_fijo
            else:
                ok = caida <= -(mult_atr * tip)
            ok = ok & (rebote >= 1.0)
            ok = np.where(np.isfinite(ok.astype(float)), ok, False)
            pos = np.flatnonzero(ok)
            pos = pos[pos < len(a) - HORIZONTE - 1]
            if len(pos) == 0:
                continue
            keep = [pos[0]]
            for p in pos[1:]:
                if p - keep[-1] >= DEDUP_MIN:
                    keep.append(p)
            k = np.array(keep)
            _, c = fut[sym]
            det += len(k)
            cb += int(c[k].sum())
        return det, cb

    grupos = {
        "tranquilos": [s for s, t in atr_par.items() if t < q[0]],
        "medios": [s for s, t in atr_par.items() if q[0] <= t < q[1]],
        "movidos": [s for s, t in atr_par.items() if t >= q[1]],
    }
    print(f"  {'grupo':>12} {'pares':>6} " +
          " ".join(f"{'caida ' + str(u) + '%':>14}" for u in (1.0, 1.5, 2.0, 3.0)))
    for g, syms in grupos.items():
        celdas = []
        for u in (1.0, 1.5, 2.0, 3.0):
            det, cb = evalua(syms, umbral_fijo=u)
            celdas.append(f"{100*cb/det:5.1f}% n={det:<5}" if det >= MIN_N
                          else f"(pocas n={det})")
        print(f"  {g:>12} {len(syms):>6} " + " ".join(f"{c:>14}" for c in celdas))

    print("\n" + "=" * 88)
    print("3. ¿NORMALIZAR POR EL CARACTER DEL PAR BATE AL UMBRAL FIJO?")
    print("=" * 88)
    todos = list(pares)
    print(f"  {'regla':>34} {'n':>7} {'cobra':>8} {'lift':>7}")
    for u in (1.5, 2.0, 3.0):
        det, cb = evalua(todos, umbral_fijo=u)
        if det >= MIN_N:
            print(f"  {'caida fija >= ' + str(u) + '%':>34} {det:>7} "
                  f"{100*cb/det:>7.1f}% {100*(cb/det - base):>+6.1f}")
    for m in (0.4, 0.6, 0.8, 1.0):
        det, cb = evalua(todos, mult_atr=m)
        if det >= MIN_N:
            print(f"  {'caida >= ' + str(m) + ' x rango tipico':>34} {det:>7} "
                  f"{100*cb/det:>7.1f}% {100*(cb/det - base):>+6.1f}")


if __name__ == "__main__":
    main()
