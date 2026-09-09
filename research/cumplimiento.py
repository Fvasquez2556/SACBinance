# -*- coding: utf-8 -*-
"""
¿Cumple el sistema lo que dicta en la PRIMERA senal?

Hasta ahora todo se ha medido contra un objetivo externo de +3.2%. Esta mide
otra cosa: si la senal hace lo que el propio sistema prometio — tocar SU TP o
SU SL. Es la promesa que el sistema firma, y hay que puntuarla contra si misma.

Tres desenlaces posibles, excluyentes:
    TP     toco su take profit antes que su stop
    SL     toco su stop antes que su take profit
    NADA   ni uno ni otro en 24h

Y la pregunta de Felix: si un par dio cuatro senales, ¿en cual se cumplio? Si
casi siempre es la tercera o la cuarta, quiere decir que las primeras estan
llegando pronto y sirven de poco; si es la primera, las repeticiones sobran.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import Counter, defaultdict

import numpy as np

DB = "data/sacbinance.db"
TZ = -6
MIN_N = 25


def gt(ts):
    return dt.datetime.utcfromtimestamp(ts / 1000) + dt.timedelta(hours=TZ)


def pct(n, d):
    return f"{100*n/d:.1f}%" if d else "—"


def desenlace(f: dict) -> str:
    tp, sl = f.get("ms_tp"), f.get("ms_sl")
    if tp is not None and (sl is None or tp < sl):
        return "TP"
    if sl is not None and (tp is None or sl < tp):
        return "SL"
    return "NADA"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    filas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND cerrado=1 ORDER BY ts_open")]

    por_par = defaultdict(list)
    for f in filas:
        f["des"] = desenlace(f)
        por_par[f["symbol"]].append(f)
    for lista in por_par.values():
        for k, f in enumerate(lista, 1):
            f["orden"] = k
            f["total_par"] = len(lista)

    n = len(filas)
    print(f"{n} senales cerradas en {len(por_par)} pares\n")

    # ==================================================================
    print("=" * 90)
    print("1. ¿CUMPLE LO QUE DICTA? — desenlace contra su PROPIO TP/SL")
    print("=" * 90)
    print(f"\n  {'grupo':<24} {'n':>6} {'toco su TP':>12} {'toco su SL':>12} "
          f"{'ninguno':>10}")
    def fila(etq, sub):
        if len(sub) < MIN_N:
            print(f"  {etq:<24} (pocas: {len(sub)})")
            return
        c = Counter(f["des"] for f in sub)
        print(f"  {etq:<24} {len(sub):>6} {pct(c['TP'], len(sub)):>12} "
              f"{pct(c['SL'], len(sub)):>12} {pct(c['NADA'], len(sub)):>10}")

    fila("TODAS", filas)
    print()
    fila("solo la 1a del par", [f for f in filas if f["orden"] == 1])
    fila("2a", [f for f in filas if f["orden"] == 2])
    fila("3a", [f for f in filas if f["orden"] == 3])
    fila("4a-6a", [f for f in filas if 4 <= f["orden"] <= 6])
    fila("7a o mas", [f for f in filas if f["orden"] >= 7])
    print()
    for t in ("EXTRA-FUERTE", "FUERTE", "MODERADA", "VIGILANCIA"):
        fila(f"tier {t}", [f for f in filas if f["tier"] == t])

    # ==================================================================
    print("\n" + "=" * 90)
    print("2. SI UN PAR DIO VARIAS, ¿EN CUAL SE CUMPLIO?")
    print("=" * 90)
    print("  Solo pares con al menos 3 senales cerradas.\n")
    ordenes_tp = []
    pares_con_tp = 0
    pares_sin = 0
    detalle = []
    for sym, lista in por_par.items():
        if len(lista) < 3:
            continue
        con_tp = [f for f in lista if f["des"] == "TP"]
        if con_tp:
            pares_con_tp += 1
            primero = min(f["orden"] for f in con_tp)
            ordenes_tp.append(primero)
            detalle.append((sym, len(lista), primero, len(con_tp)))
        else:
            pares_sin += 1
    if ordenes_tp:
        o = np.array(ordenes_tp)
        print(f"  pares evaluados: {pares_con_tp + pares_sin}")
        print(f"    con al menos un TP: {pares_con_tp} ({pct(pares_con_tp, pares_con_tp+pares_sin)})")
        print(f"    sin ningun TP:      {pares_sin}")
        print(f"\n  la PRIMERA senal que cumplio fue la numero:")
        print(f"     media {o.mean():.2f}   mediana {np.median(o):.0f}   "
              f"moda {Counter(o.tolist()).most_common(1)[0][0]}")
        print(f"\n  {'fue la':<12} {'pares':>7} {'%':>8}")
        for k in range(1, 7):
            c = int((o == k).sum())
            if c:
                print(f"  {str(k)+'a':<12} {c:>7} {pct(c, len(o)):>8}")
        c = int((o > 6).sum())
        if c:
            print(f"  {'7a o mas':<12} {c:>7} {pct(c, len(o)):>8}")
        print(f"\n  En {pct(int((o==1).sum()), len(o))} de los pares, la PRIMERA")
        print(f"  senal ya cumplio. Las repeticiones no aportaron nada nuevo ahi.")

    # ==================================================================
    print("\n" + "=" * 90)
    print("3. LA HORA EN QUE SE CUMPLE")
    print("=" * 90)
    con_tp = [f for f in filas if f["des"] == "TP"]
    print(f"  {len(con_tp)} senales tocaron su TP.\n")
    print("  a) hora en que se EMITIO la senal")
    print(f"     {'franja':<10} {'n':>6} {'toco su TP':>12} {'toco su SL':>12}")
    for h0, h1 in ((0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)):
        sub = [f for f in filas if h0 <= gt(f["ts_open"]).hour < h1]
        if len(sub) < MIN_N:
            continue
        c = Counter(f["des"] for f in sub)
        print(f"     {f'{h0:02d}-{h1:02d}h':<10} {len(sub):>6} "
              f"{pct(c['TP'], len(sub)):>12} {pct(c['SL'], len(sub)):>12}")

    print("\n  b) hora en que se TOCO el TP (el momento del cobro)")
    horas = Counter(gt(f["ts_open"] + f["ms_tp"]).hour for f in con_tp)
    total = sum(horas.values())
    print(f"     {'franja':<10} {'n':>6} {'% de los TP':>13}   grafico")
    for h0, h1 in ((0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)):
        k = sum(horas.get(h, 0) for h in range(h0, h1))
        barra = "#" * int(40 * k / max(total, 1))
        print(f"     {f'{h0:02d}-{h1:02d}h':<10} {k:>6} {pct(k, total):>13}   {barra}")
    pico = horas.most_common(3)
    print(f"\n     horas punta: " + ", ".join(f"{h:02d}h ({k})" for h, k in pico))

    print("\n  c) cuanto tardo en cumplirse, por franja de emision")
    print(f"     {'franja':<10} {'n':>6} {'mediana':>10} {'p25':>8} {'p75':>8}")
    for h0, h1 in ((0, 8), (8, 16), (16, 24)):
        sub = [f for f in con_tp if h0 <= gt(f["ts_open"]).hour < h1]
        if len(sub) < MIN_N:
            continue
        t = np.array([f["ms_tp"] for f in sub]) / 60000.0
        print(f"     {f'{h0:02d}-{h1:02d}h':<10} {len(sub):>6} "
              f"{np.median(t):>9.0f}m {np.percentile(t,25):>7.0f}m "
              f"{np.percentile(t,75):>7.0f}m")


if __name__ == "__main__":
    main()
