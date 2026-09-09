# -*- coding: utf-8 -*-
"""
Las dos caras: MARSCOIN bajo al stop y despues subio; KAT no bajo, subio.

Felix lo pregunto asi: "¿como es que empeoraria la entrada? son las dos caras
de la misma moneda". La respuesta esta en QUE MONEDAS TE TOCAN.

Entrar en el hoyo solo se ejecuta si el precio baja hasta ahi. Las que suben
sin bajar —las KAT— nunca te llenan la orden. Asi que la estrategia no elige
entre "entrar arriba" y "entrar abajo" sobre las mismas señales: se queda con
un SUBCONJUNTO, el de las que caen. Y si ese subconjunto es peor que el resto,
entrar mas abajo puede salir peor aunque cada entrada individual sea mejor.

Este script parte las señales en dos, por si el precio llego o no al disparo,
y mira que hizo cada grupo con los niveles del PROPIO sistema. Si el grupo que
nunca baja es mucho mejor, la seleccion esta demostrada.

Segunda parte: la primera señal de cada par, aguantada, con varios anchos de
stop. Es la unica linea que seguia en pie al final del 9-sep.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
VENTANA_MS = 24 * 3600 * 1000
META = 3.2
MARGEN = 0.5
MIN_VELAS = 60


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
    """(desenlace, resultado_pct, mfe, mae) desde el indice `desde`."""
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


def main():
    rng = np.random.default_rng(20260909)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    prim = con.execute("SELECT MIN(open_time) FROM klines WHERE tf='1m'").fetchone()[0]
    ult = con.execute("SELECT MAX(open_time) FROM klines WHERE tf='1m'").fetchone()[0]

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

    seniales = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND ts_open>=? AND stop_loss>0 "
        "AND sl_pct<0 AND tp_pct IS NOT NULL ORDER BY ts_open", (prim,))]

    casos = []
    for s in seniales:
        ser = series.get(s["symbol"])
        if ser is None:
            continue
        i0 = int(np.searchsorted(ser["t"], s["ts_open"], side="right")) - 1
        i1 = int(np.searchsorted(ser["t"], s["ts_open"] + VENTANA_MS, side="right"))
        if i0 < 0 or i1 - i0 < MIN_VELAS:
            continue
        hi, lo, cl = ser["h"][i0:i1], ser["l"][i0:i1], ser["c"][i0:i1]
        disparo = s["stop_loss"] * (1 + MARGEN / 100.0)
        toca = lo <= disparo
        idx = int(np.argmax(toca)) if toca.any() else None
        prop = simular(hi, lo, cl, 0, s["entry"], s["stop_loss"], s["take_profit"])
        if prop is None:
            continue
        casos.append({"symbol": s["symbol"], "ts": s["ts_open"],
                      "bajo": idx is not None, "ms_bajo": idx,
                      "prop": prop, "sl_pct": s["sl_pct"], "tp_pct": s["tp_pct"],
                      "up32": prop[2] >= META})

    print(f"{len(casos)} señales, {len({c['symbol'] for c in casos})} pares\n")
    print("=" * 100)
    print("1. LAS DOS CARAS: ¿el precio llego a bajar hasta el hoyo?")
    print("=" * 100)
    print(f"  El hoyo = stop del sistema + {MARGEN}%. Todo se mide con los niveles")
    print("  del PROPIO sistema, iguales para los dos grupos.\n")
    print(f"  {'grupo':<32} {'n':>5} {'cumple TP':>10} {'la paran':>9} "
          f"{'llega a +3.2%':>14} {'MFE medio':>10} {'media':>8} {'IC 95%':>17}")
    for nombre, sub in (("BAJARON al hoyo", [c for c in casos if c["bajo"]]),
                        ("NO bajaron (las KAT)", [c for c in casos if not c["bajo"]])):
        if len(sub) < 20:
            continue
        res = [c["prop"][1] for c in sub]
        par = [c["symbol"] for c in sub]
        tp = sum(1 for c in sub if c["prop"][0] == "TP")
        sl = sum(1 for c in sub if c["prop"][0] == "SL")
        m32 = sum(1 for c in sub if c["up32"])
        mfe = np.mean([c["prop"][2] for c in sub])
        lo_, hi_ = boot_ci(res, par, rng)
        print(f"  {nombre:<32} {len(sub):>5} {pct(tp,len(sub)):>10} {pct(sl,len(sub)):>9} "
              f"{pct(m32,len(sub)):>14} {mfe:>9.2f}% {np.mean(res):>7.2f}% "
              f"[{lo_:>6.2f},{hi_:>6.2f}]")

    baj = [c for c in casos if c["bajo"]]
    nob = [c for c in casos if not c["bajo"]]
    if baj and nob:
        print(f"\n  El grupo que NO baja es el {100*len(nob)/len(casos):.1f}% de las señales.")
        print(f"  Entrar en el hoyo renuncia a ese grupo entero: la orden nunca se llena.")
        d_m32 = 100*sum(c['up32'] for c in nob)/len(nob) - 100*sum(c['up32'] for c in baj)/len(baj)
        print(f"  Diferencia en llegar a +3.2%: {d_m32:+.1f} puntos a favor de las que no bajan.")

    print()
    print("  ¿Y cuanto tarda en bajar al hoyo? (solo las que bajaron)")
    print(f"  {'tarda':<20} {'n':>5} {'cumple TP':>10} {'llega a +3.2%':>14} {'media':>8}")
    for etq, f in (("menos de 15 min", lambda c: c["ms_bajo"] < 15),
                   ("15-60 min", lambda c: 15 <= c["ms_bajo"] < 60),
                   ("1-4 h", lambda c: 60 <= c["ms_bajo"] < 240),
                   ("mas de 4 h", lambda c: c["ms_bajo"] >= 240)):
        sub = [c for c in baj if f(c)]
        if len(sub) < 20:
            continue
        tp = sum(1 for c in sub if c["prop"][0] == "TP")
        m32 = sum(1 for c in sub if c["up32"])
        print(f"  {etq:<20} {len(sub):>5} {pct(tp,len(sub)):>10} {pct(m32,len(sub)):>14} "
              f"{np.mean([c['prop'][1] for c in sub]):>7.2f}%")

    # ==================================================================
    print()
    print("=" * 100)
    print("2. LA PRIMERA SEÑAL DE CADA PAR, AGUANTADA, CON VARIOS STOPS")
    print("=" * 100)
    por_par = defaultdict(list)
    for s in seniales:
        por_par[s["symbol"]].append(s)

    for horas in (24, 48):
        minutos = horas * 60
        filas = []
        for sym, lista in por_par.items():
            ser = series.get(sym)
            if ser is None:
                continue
            p = lista[0]
            i0 = int(np.searchsorted(ser["t"], p["ts_open"], side="right")) - 1
            if i0 < 0 or i0 + minutos > len(ser["t"]):
                continue
            hi = ser["h"][i0:i0 + minutos]
            lo = ser["l"][i0:i0 + minutos]
            cl = ser["c"][i0:i0 + minutos]
            filas.append({"symbol": sym, "hi": hi, "lo": lo, "cl": cl,
                          "entry": p["entry"], "tp": p["take_profit"],
                          "sl": p["stop_loss"], "sl_pct": p["sl_pct"],
                          "tp_pct": p["tp_pct"]})
        if len(filas) < 30:
            continue
        print(f"\n  HORIZONTE {horas}h — {len(filas)} pares con su primera señal\n")
        print(f"  {'stop':<14} {'objetivo':<10} {'ops':>5} {'aciertos':>9} "
              f"{'media':>8} {'IC 95%':>17} {'mediana':>8} {'peor':>8}")
        for setq, sfun in (("el del sistema", lambda f: f["sl"]),
                           ("-1.5%", lambda f: f["entry"] * 0.985),
                           ("-2%", lambda f: f["entry"] * 0.98),
                           ("-3%", lambda f: f["entry"] * 0.97),
                           ("-5%", lambda f: f["entry"] * 0.95),
                           ("-8%", lambda f: f["entry"] * 0.92),
                           ("sin stop", lambda f: None)):
            for tetq, tfun in (("su TP", lambda f: f["tp"]),
                               ("+3.2%", lambda f: f["entry"] * 1.032),
                               ("aguantar", lambda f: None)):
                out = [simular(f["hi"], f["lo"], f["cl"], 0, f["entry"],
                               sfun(f), tfun(f)) for f in filas]
                pares = [f["symbol"] for f, o in zip(filas, out) if o]
                res = np.array([o[1] for o in out if o])
                maes = np.array([o[3] for o in out if o])
                if len(res) < 30:
                    continue
                lo_, hi_ = boot_ci(res, pares, rng)
                print(f"  {setq:<14} {tetq:<10} {len(res):>5} "
                      f"{100*(res>0).mean():>8.1f}% {res.mean():>7.2f}% "
                      f"[{lo_:>6.2f},{hi_:>6.2f}] {np.median(res):>7.2f}% "
                      f"{np.median(maes):>7.2f}%")
            print()


if __name__ == "__main__":
    main()
