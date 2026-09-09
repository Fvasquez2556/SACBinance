# -*- coding: utf-8 -*-
"""
El hoyo, pero solo en la PRIMERA señal de cada par.

Las dos lineas que quedaron en pie el 9-sep tiran en sentidos opuestos:

  - La primera señal de cada moneda es mucho mejor que las repetidas, y
    aguantada con stop ancho es lo unico cuyo intervalo no esta en negativo.
  - Entrar en el hoyo pierde, porque la orden solo se llena en las monedas que
    caen: el 13.5% que nunca baja hasta su stop es el unico grupo con media
    positiva, y esa regla renuncia a el entero.

La pregunta obvia es si la seleccion se comporta igual dentro del subconjunto
bueno. Puede que en las primeras señales bajar al hoyo signifique otra cosa —
o puede que el mismo mecanismo se repita y no haya nada que rascar.

Se comparan, sobre los MISMOS pares y la MISMA ventana:

    ENTRAR EN LA SEÑAL    lo que hace el sistema hoy
    ENTRAR EN EL HOYO     esperar a SL + margen, con varios stops y objetivos
    LAS QUE NO BAJARON    el grupo al que la regla del hoyo renuncia

Todo con bootstrap agrupado por par, que aqui coincide con agrupar por
operacion porque hay una sola por par.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
VENTANA_H = 24
META = 3.2
MARGENES = (0.5, 0.6, 1.0)


def u(ms):
    return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%d/%m %H:%M")


def pct(n, d):
    return f"{100*n/d:4.1f}%" if d else "   -"


def boot_ci(x, pares, rng, n=2000):
    if len(x) < 8:
        return float("nan"), float("nan")
    g = defaultdict(list)
    for v, p in zip(x, pares):
        g[p].append(v)
    arrs = [np.array(v, dtype=float) for v in g.values()]
    m = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(arrs), len(arrs))
        m[i] = np.concatenate([arrs[j] for j in pick]).mean()
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def simular(hi, lo, cl, desde, entry, stop, techo):
    h, l, c = hi[desde:], lo[desde:], cl[desde:]
    if len(h) < 30:
        return None
    mfe = float((h.max() - entry) / entry * 100)
    mae = float((l.min() - entry) / entry * 100)
    t_sl = t_tp = None
    if stop:
        x = l <= stop
        t_sl = int(np.argmax(x)) if x.any() else None
    if techo:
        x = h >= techo
        t_tp = int(np.argmax(x)) if x.any() else None
    if t_sl is not None and (t_tp is None or t_sl <= t_tp):
        return ("SL", (stop - entry) / entry * 100, mfe, mae)
    if t_tp is not None:
        return ("TP", (techo - entry) / entry * 100, mfe, mae)
    return ("ABIERTA", float((c[-1] - entry) / entry * 100), mfe, mae)


def linea(nombre, out, pares, rng, extra=""):
    res = np.array([o[1] for o in out], dtype=float)
    if len(res) < 15:
        print(f"  {nombre:<36} {len(res):>5}   (pocas)")
        return
    lo, hi = boot_ci(res, pares, rng)
    tp = sum(1 for o in out if o[0] == "TP")
    sl = sum(1 for o in out if o[0] == "SL")
    m32 = sum(1 for o in out if o[2] >= META)
    print(f"  {nombre:<36} {len(res):>5} {pct(tp,len(out)):>8} {pct(sl,len(out)):>8} "
          f"{pct(m32,len(out)):>9} {100*(res>0).mean():>8.1f}% {res.mean():>7.2f}% "
          f"[{lo:>6.2f},{hi:>6.2f}] {np.median(res):>7.2f}%{extra}")


def main():
    rng = np.random.default_rng(20260909)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    prim = con.execute("SELECT MIN(open_time) FROM klines WHERE tf='1m'").fetchone()[0]

    series = {}
    for sym, in con.execute("SELECT DISTINCT symbol FROM klines WHERE tf='1m'"):
        f = con.execute("SELECT open_time,h,l,c FROM klines WHERE symbol=? AND tf='1m' "
                        "ORDER BY open_time", (sym,)).fetchall()
        if len(f) < 200:
            continue
        series[sym] = {
            "t": np.array([r[0] for r in f], dtype=np.int64),
            "h": np.array([r[1] for r in f], dtype=float),
            "l": np.array([r[2] for r in f], dtype=float),
            "c": np.array([r[3] for r in f], dtype=float),
        }

    por_par = defaultdict(list)
    for r in con.execute(
            "SELECT * FROM outcomes WHERE sombra=0 AND ts_open>=? AND stop_loss>0 "
            "AND sl_pct<0 AND tp_pct IS NOT NULL ORDER BY ts_open", (prim,)):
        por_par[r["symbol"]].append(dict(r))

    minutos = VENTANA_H * 60
    casos = []
    for sym, lista in por_par.items():
        s = series.get(sym)
        if s is None:
            continue
        p = lista[0]
        i0 = int(np.searchsorted(s["t"], p["ts_open"], side="right")) - 1
        if i0 < 0 or i0 + minutos > len(s["t"]):
            continue
        hi = s["h"][i0:i0 + minutos]
        lo = s["l"][i0:i0 + minutos]
        cl = s["c"][i0:i0 + minutos]
        c = {"symbol": sym, "ts": p["ts_open"], "entry": p["entry"],
             "tp": p["take_profit"], "sl": p["stop_loss"],
             "tp_pct": p["tp_pct"], "sl_pct": p["sl_pct"],
             "hi": hi, "lo": lo, "cl": cl, "n_senales": len(lista)}
        c["base"] = simular(hi, lo, cl, 0, p["entry"], p["stop_loss"], p["take_profit"])
        for m in MARGENES:
            disparo = p["stop_loss"] * (1 + m / 100.0)
            toca = lo <= disparo
            c[m] = int(np.argmax(toca)) if toca.any() else None
        if c["base"]:
            casos.append(c)

    print(f"{len(casos)} pares con su primera señal y {VENTANA_H}h completas\n")
    cab = (f"  {'':36} {'n':>5} {'TP':>8} {'SL':>8} {'a +3.2%':>9} "
           f"{'gana':>9} {'media':>8} {'IC 95%':>17} {'mediana':>8}")

    # ==================================================================
    print("=" * 116)
    print("1. ¿TAMBIEN AQUI EL QUE NO BAJA ES EL BUENO?")
    print("=" * 116)
    print(cab)
    linea("TODAS, entrando en la señal", [c["base"] for c in casos],
          [c["symbol"] for c in casos], rng)
    for etq, f in (("  las que BAJARON al hoyo", lambda c: c[0.5] is not None),
                   ("  las que NO bajaron", lambda c: c[0.5] is None)):
        sub = [c for c in casos if f(c)]
        linea(etq, [c["base"] for c in sub], [c["symbol"] for c in sub], rng)
    nob = [c for c in casos if c[0.5] is None]
    print(f"\n  El {100*len(nob)/len(casos):.1f}% de las primeras señales nunca baja hasta")
    print(f"  el hoyo. En el conjunto entero de señales era el 13.5%.")

    # ==================================================================
    print()
    print("=" * 116)
    print(f"2. ENTRAR EN EL HOYO, SOLO EN LA PRIMERA SEÑAL")
    print("=" * 116)
    for m in MARGENES:
        ent = [c for c in casos if c[m] is not None]
        if len(ent) < 20:
            continue
        print(f"\n  DISPARO EN SL +{m}%   ({len(ent)} entradas de {len(casos)} primeras señales)")
        print(cab)
        # referencia: esas mismas, entrando en la señal
        linea("  entrando en la SEÑAL (referencia)", [c["base"] for c in ent],
              [c["symbol"] for c in ent], rng)
        for setq, sfun in (("stop del sistema", lambda c, f: f * (1 + c["sl_pct"] / 100)),
                           ("stop -3%", lambda c, f: f * 0.97),
                           ("stop -5%", lambda c, f: f * 0.95),
                           ("sin stop", lambda c, f: None)):
            for tetq, tfun in (("TP del sistema", lambda c, f: c["tp"]),
                               ("+3.2% desde el hoyo", lambda c, f: f * 1.032)):
                out, par = [], []
                for c in ent:
                    fill = c["sl"] * (1 + m / 100.0)
                    techo = tfun(c, fill)
                    if techo is not None and techo <= fill:
                        continue
                    o = simular(c["hi"], c["lo"], c["cl"], c[m], fill,
                                sfun(c, fill), techo)
                    if o:
                        out.append(o)
                        par.append(c["symbol"])
                linea(f"  hoyo · {setq} · {tetq}", out, par, rng)

    # ==================================================================
    print()
    print("=" * 116)
    print("3. ¿CUANTO TARDA EN BAJAR AL HOYO? (primera señal, disparo 0.5%)")
    print("=" * 116)
    ent = [c for c in casos if c[0.5] is not None]
    print(cab)
    for etq, f in (("  baja en menos de 15 min", lambda c: c[0.5] < 15),
                   ("  baja entre 15 min y 1 h", lambda c: 15 <= c[0.5] < 60),
                   ("  baja entre 1 y 4 h", lambda c: 60 <= c[0.5] < 240),
                   ("  baja despues de 4 h", lambda c: c[0.5] >= 240)):
        sub = [c for c in ent if f(c)]
        if len(sub) < 15:
            print(f"  {etq:<36} {len(sub):>5}   (pocas)")
            continue
        out, par = [], []
        for c in sub:
            fill = c["sl"] * 1.005
            o = simular(c["hi"], c["lo"], c["cl"], c[0.5], fill,
                        fill * 0.95, fill * 1.032)
            if o:
                out.append(o)
                par.append(c["symbol"])
        linea(etq + " (stop -5%, +3.2%)", out, par, rng)


if __name__ == "__main__":
    main()
