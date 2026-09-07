# -*- coding: utf-8 -*-
"""
¿El rebote necesita un TECHO, ademas del suelo?

De donde sale la pregunta
-------------------------
research/suelo_maduro.py encontro que exigir >=1% de rebote desde el suelo
sube el acierto cobrable de 19.5% a 24.4%. Se implemento como umbral minimo.
Pero ACEUSDT aparecio primero en el tablero con 3.26% ya rebotado: la mayor
parte del movimiento hecho. El estudio puso un SUELO al rebote, nunca un
techo, asi que ese caso no esta cubierto por nada medido.

El sistema si aplica esa logica en otro sitio — `alerta_consumido_max = 3.5%`
veta emitir cuando el movimiento ya se gasto — pero el patron de retroceso la
ignora porque nadie la midio aqui.

Que se mide
-----------
El objetivo se cuenta SIEMPRE desde el precio actual: un par que ya reboto 3%
necesita otro 3.2% mas desde donde esta. Asi que la pregunta es limpia: dado
que cayo >=2% y lleva X% recuperado, ¿que probabilidad hay de +3.2% MAS?

Dos formas de medir "cuanto lleva recuperado":
    absoluta   rebote %  desde el suelo
    relativa   rebote / |caida|  — que fraccion de la caida ya deshizo

La relativa deberia ser mejor: recuperar 2% de una caida del 2% (todo) no es
lo mismo que recuperar 2% de una caida del 8% (un cuarto).
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
N = 8
LOOKBACK = 40
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
    mfe = np.full(n, np.nan)
    if n <= h + 1:
        return sube, cobra, mfe
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
    mfe[:m] = (vh.max(axis=1) / c0 - 1) * 100.0
    return sube, cobra, mfe


def main():
    con = sqlite3.connect(DB)
    pares = cargar(con)
    print(f"{len(pares)} pares\n")

    fut, tot, sub, cob = {}, 0, 0, 0
    for sym, a in pares.items():
        s, c, m = futuro(a, HORIZONTE)
        fut[sym] = (s, c, m)
        v = len(a) - HORIZONTE - 1
        if v > 0:
            tot += v
            sub += int(s[:v].sum())
            cob += int(c[:v].sum())
    b_sube, b_cobra = sub / tot, cob / tot
    print(f"CONTROL (instante cualquiera): llega {100*b_sube:.2f}%   "
          f"cobra {100*b_cobra:.2f}%   n={tot:,}\n")

    datos = {}
    for sym, a in pares.items():
        hi, lo, cl = a[:, 2], a[:, 3], a[:, 4]
        mn = rolling(lo, N, np.min)
        pico = rolling(hi, LOOKBACK, np.max)
        pico_prev = np.concatenate((np.full(N, np.nan), pico[: len(pico) - N]))
        with np.errstate(invalid="ignore", divide="ignore"):
            caida = (mn - pico_prev) / pico_prev * 100.0
            rebote = (cl - mn) / mn * 100.0
            # fraccion de la caida ya deshecha: 0 = en el suelo, 1 = pico otra vez
            frac = rebote / np.abs(caida)
        datos[sym] = (caida <= -CAIDA_MIN, rebote, frac)

    def mide(filtro):
        det = up = cb = 0
        mfes = []
        for sym, a in pares.items():
            ok, rebote, frac = datos[sym]
            m = ok & filtro(rebote, frac)
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
            s, c, mf = fut[sym]
            det += len(k)
            up += int(s[k].sum())
            cb += int(c[k].sum())
            mfes.append(mf[k])
        mm = np.concatenate(mfes) if mfes else np.array([])
        return det, up, cb, (np.nanmedian(mm) if len(mm) else float("nan"))

    def tabla(titulo, pruebas):
        print("=" * 92)
        print(titulo)
        print("=" * 92)
        print(f"  {'banda':>28} {'n':>7} {'llega':>8} {'lift':>7} "
              f"{'cobra':>8} {'lift':>7} {'MFE med':>9}")
        for etq, f in pruebas:
            det, up, cb, mfe = mide(f)
            if det < MIN_N:
                print(f"  {etq:>28} {det:>7}   (pocas)")
                continue
            print(f"  {etq:>28} {det:>7} {100*up/det:>7.1f}% "
                  f"{100*(up/det - b_sube):>+6.1f} {100*cb/det:>7.1f}% "
                  f"{100*(cb/det - b_cobra):>+6.1f} {mfe:>+8.2f}%")
        print()

    tabla("REBOTE ABSOLUTO desde el suelo", [
        ("sin filtro (todo el patron)", lambda r, f: r >= -99),
        ("  0 - 0.5%", lambda r, f: (r >= 0) & (r < 0.5)),
        ("0.5 - 1.0%", lambda r, f: (r >= 0.5) & (r < 1.0)),
        ("1.0 - 1.5%", lambda r, f: (r >= 1.0) & (r < 1.5)),
        ("1.5 - 2.0%", lambda r, f: (r >= 1.5) & (r < 2.0)),
        ("2.0 - 3.0%", lambda r, f: (r >= 2.0) & (r < 3.0)),
        ("3.0 - 5.0%", lambda r, f: (r >= 3.0) & (r < 5.0)),
        ("     > 5.0%", lambda r, f: r >= 5.0),
        ("--- acumulado >= 1.0%", lambda r, f: r >= 1.0),
        ("--- con techo: 1.0 - 3.0%", lambda r, f: (r >= 1.0) & (r < 3.0)),
        ("--- con techo: 1.0 - 2.0%", lambda r, f: (r >= 1.0) & (r < 2.0)),
    ])

    tabla("FRACCION DE LA CAIDA YA DESHECHA (rebote / |caida|)", [
        ("      < 0.25  (aun en el suelo)", lambda r, f: f < 0.25),
        ("  0.25 - 0.50", lambda r, f: (f >= 0.25) & (f < 0.50)),
        ("  0.50 - 0.75", lambda r, f: (f >= 0.50) & (f < 0.75)),
        ("  0.75 - 1.00", lambda r, f: (f >= 0.75) & (f < 1.00)),
        ("      > 1.00  (ya paso el pico)", lambda r, f: f >= 1.00),
        ("--- 0.25 - 0.75", lambda r, f: (f >= 0.25) & (f < 0.75)),
        ("--- 0.25 - 1.00", lambda r, f: (f >= 0.25) & (f < 1.00)),
    ])

    tabla("COMBINADO: rebote >=1% Y fraccion controlada", [
        ("reb>=1% (regla actual)", lambda r, f: r >= 1.0),
        ("reb>=1% y frac < 0.75", lambda r, f: (r >= 1.0) & (f < 0.75)),
        ("reb>=1% y frac < 1.00", lambda r, f: (r >= 1.0) & (f < 1.00)),
        ("reb 1-3% y frac < 1.00", lambda r, f: (r >= 1.0) & (r < 3.0) & (f < 1.0)),
    ])


if __name__ == "__main__":
    main()
