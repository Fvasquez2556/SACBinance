# -*- coding: utf-8 -*-
"""
La idea de Felix: fijar la PRIMERA señal de cada moneda y comprar contra ella.

Su argumento, dicho el 9-sep a raiz de IOST: el sistema reevalua cada minuto y
acaba vetando para siempre a la moneda que se mueve, asi que en el dia grande
no emite nada. Si en vez de eso se congelara la primera señal de cada par y se
mantuviera como referencia, IOST habria quedado bien — su ultima señal fue del
7-sep a 0.000874, y el 9-sep el precio llego a 0.002448.

Es una critica de arquitectura, no de umbral, y se puede medir.

Las tres formas de operar que se comparan
-----------------------------------------
    SISTEMA    cada señal es una operacion, con su propio TP y su propio SL.
               Es lo que hace hoy: 450 señales al dia.
    PRIMERA    solo la primera señal de cada par. Entrada congelada, y se
               aguanta hasta TP, SL o fin del horizonte.
    PRIMERA+   igual, pero sin stop: se aguanta pase lo que pase.

Todas sobre los MISMOS pares y la MISMA ventana, para que la comparacion
signifique algo. Se prueban tres horizontes, porque "aguantar" sin decir
cuanto no es una estrategia.

El sesgo que hay que vigilar
----------------------------
Aguantar sin stop siempre gana si la ventana acaba en un buen momento. Por eso
solo entran las primeras señales con el horizonte COMPLETO de velas por
delante, y se reporta tambien el peor momento por el que paso cada una: una
media bonita con un -40% de por medio no es aguantable con dinero prestado.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
HORIZONTES = ((24, "24h"), (48, "48h"), (72, "72h"))


def u(ms):
    return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%d/%m %H:%M")


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


def simular(s, i0, entry, tp, sl, minutos):
    """Devuelve (resultado_pct, mfe, mae, desenlace) aguantando `minutos`."""
    fin = min(i0 + minutos, len(s["h"]))
    hi, lo, cl = s["h"][i0:fin], s["l"][i0:fin], s["c"][i0:fin]
    if len(hi) < 60:
        return None
    mfe = float((hi.max() - entry) / entry * 100)
    mae = float((lo.min() - entry) / entry * 100)
    t_tp = t_sl = None
    if tp:
        cruz = hi >= tp
        t_tp = int(np.argmax(cruz)) if cruz.any() else None
    if sl:
        cruz = lo <= sl
        t_sl = int(np.argmax(cruz)) if cruz.any() else None
    if t_sl is not None and (t_tp is None or t_sl <= t_tp):
        return ((sl - entry) / entry * 100, mfe, mae, "SL")
    if t_tp is not None:
        return ((tp - entry) / entry * 100, mfe, mae, "TP")
    return (float((cl[-1] - entry) / entry * 100), mfe, mae, "ABIERTA")


def main():
    rng = np.random.default_rng(20260909)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

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
    t_max = int(max(s["t"][-1] for s in series.values()))
    t_min = int(min(s["t"][0] for s in series.values()))
    print(f"{len(series)} pares, velas de {u(t_min)} a {u(t_max)} UTC "
          f"({(t_max-t_min)/86400000:.1f} dias)\n")

    senales = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND ts_open>=? ORDER BY ts_open",
        (t_min,))]
    por_par = defaultdict(list)
    for x in senales:
        por_par[x["symbol"]].append(x)

    for horas, etq in HORIZONTES:
        minutos = horas * 60
        print("=" * 96)
        print(f"HORIZONTE {etq}")
        print("=" * 96)

        primeras, sistema = [], []
        for sym, lista in por_par.items():
            s = series.get(sym)
            if s is None:
                continue
            p = lista[0]
            i0 = int(np.searchsorted(s["t"], p["ts_open"], side="right")) - 1
            # solo si cabe el horizonte entero: si no, aguantar seria trampa
            if i0 < 0 or i0 + minutos > len(s["t"]):
                continue
            con_stop = simular(s, i0, p["entry"], p["take_profit"], p["stop_loss"], minutos)
            sin_stop = simular(s, i0, p["entry"], p["take_profit"], None, minutos)
            libre = simular(s, i0, p["entry"], None, None, minutos)
            if not con_stop:
                continue
            primeras.append({"symbol": sym, "ts": p["ts_open"], "entry": p["entry"],
                             "con": con_stop, "sin": sin_stop, "libre": libre,
                             "n_senales": len(lista)})
            # el sistema: todas las señales de ese par dentro del horizonte
            tope = p["ts_open"] + minutos * 60000
            for x in lista:
                if x["ts_open"] > tope:
                    continue
                tp, sl = x["ms_tp"], x["ms_sl"]
                if sl is not None and (tp is None or sl <= tp):
                    r = x["sl_pct"]
                elif tp is not None:
                    r = x["tp_pct"]
                else:
                    continue          # sin resolver: no se cuenta
                sistema.append({"symbol": sym, "res": r})

        if len(primeras) < 20:
            print("  (pocos pares con el horizonte completo)\n")
            continue

        print(f"  {len(primeras)} pares con su primera señal y {etq} de velas por delante")
        print(f"  {len(sistema)} operaciones del sistema en esos mismos pares y ventana\n")
        print(f"  {'estrategia':<34} {'ops':>5} {'aciertos':>9} {'media':>8} "
              f"{'IC 95%':>18} {'mediana':>8} {'peor momento':>13}")

        def fila(nombre, vals, pares, maes=None):
            v = np.array(vals, dtype=float)
            lo, hi = boot_ci(v, pares, rng)
            gan = 100 * (v > 0).mean()
            peor = f"{np.median(maes):+.2f}%" if maes else "—"
            print(f"  {nombre:<34} {len(v):>5} {gan:>8.1f}% {v.mean():>7.2f}% "
                  f"[{lo:>6.2f},{hi:>6.2f}] {np.median(v):>7.2f}% {peor:>13}")

        fila("SISTEMA (cada señal, su TP y SL)",
             [x["res"] for x in sistema], [x["symbol"] for x in sistema])
        fila("PRIMERA (con su TP y su SL)",
             [x["con"][0] for x in primeras], [x["symbol"] for x in primeras],
             [x["con"][2] for x in primeras])
        fila("PRIMERA sin stop, hasta su TP",
             [x["sin"][0] for x in primeras], [x["symbol"] for x in primeras],
             [x["sin"][2] for x in primeras])
        fila(f"PRIMERA a pelo, cerrar a las {etq}",
             [x["libre"][0] for x in primeras], [x["symbol"] for x in primeras],
             [x["libre"][2] for x in primeras])
        m32 = sum(1 for x in primeras if x["libre"][1] >= META)
        print(f"\n  de las {len(primeras)} primeras señales, {m32} "
              f"({100*m32/len(primeras):.1f}%) llegaron a +{META}% en algun momento")
        print()

    # ---- el caso IOST -----------------------------------------------
    print("=" * 96)
    print("EL CASO QUE LO MOTIVA: IOST")
    print("=" * 96)
    s = series.get("IOSTUSDT")
    lista = por_par.get("IOSTUSDT", [])
    if s is not None and lista:
        p = lista[0]
        i0 = int(np.searchsorted(s["t"], p["ts_open"], side="right")) - 1
        print(f"\n  primera señal: {u(p['ts_open'])} UTC  entry {p['entry']:.6g}  "
              f"TP {p['take_profit']:.6g} (+{p['tp_pct']:.1f}%)  SL {p['stop_loss']:.6g} "
              f"({p['sl_pct']:.1f}%)")
        print(f"  el par dio {len(lista)} señales en total\n")
        print(f"  {'aguantando':<16} {'con su TP y SL':>16} {'sin stop':>12} {'a pelo':>10} "
              f"{'peor momento':>14}")
        for horas, etq in ((24, "24h"), (48, "48h"), (72, "72h"), (96, "96h")):
            m = horas * 60
            a = simular(s, i0, p["entry"], p["take_profit"], p["stop_loss"], m)
            b = simular(s, i0, p["entry"], p["take_profit"], None, m)
            c = simular(s, i0, p["entry"], None, None, m)
            if not a:
                continue
            print(f"  {etq:<16} {a[0]:>14.2f}% {b[0]:>11.2f}% {c[0]:>9.2f}% "
                  f"{c[2]:>13.2f}%")
        fin = min(i0 + 96 * 60, len(s["h"]))
        print(f"\n  maximo alcanzado: {s['h'][i0:fin].max():.6g}  "
              f"({(s['h'][i0:fin].max()-p['entry'])/p['entry']*100:+.1f}% sobre la entrada)")


if __name__ == "__main__":
    main()
