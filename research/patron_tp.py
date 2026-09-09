# -*- coding: utf-8 -*-
"""
Las que tocaron su TP: ¿que patron tienen, y cuantas llegaron a +3.2%?

Hay un confundido que hay que desmontar antes de leer nada: tocar el TP es
MAS FACIL cuanto mas cerca esta. Una senal con TP de +1.5% lo toca mucho mas
que una con TP de +8%, sin que eso diga nada de la calidad de la senal.

Asi que "toco su TP" mezcla dos cosas:
    la senal acerto
    el TP era corto

Y hay una consecuencia practica que importa mas: si el TP esta por debajo de
+3.2%, tocarlo NO te lleva a tu objetivo. El sistema cumple su promesa y aun
asi te quedas corto.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import Counter, defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
TZ = -6
MIN_N = 25


def gt(ts):
    return dt.datetime.utcfromtimestamp(ts / 1000) + dt.timedelta(hours=TZ)


def pct(n, d):
    return f"{100*n/d:.1f}%" if d else "—"


def desenlace(f):
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
        f["llego32"] = f["ms_up_32"] is not None
        por_par[f["symbol"]].append(f)
    for lista in por_par.values():
        for k, f in enumerate(lista, 1):
            f["orden"] = k

    n = len(filas)
    conTP = [f for f in filas if f["des"] == "TP"]
    print(f"{n} senales cerradas. {len(conTP)} tocaron su TP ({pct(len(conTP), n)})\n")

    # ==================================================================
    print("=" * 92)
    print("1. EL CONFUNDIDO: tocar el TP es mas facil cuanto mas corto es")
    print("=" * 92)
    print(f"\n  {'TP ofrecido':<14} {'n':>6} {'toca su TP':>12} {'toca su SL':>12} "
          f"{'llega a +3.2%':>15}")
    bandas = [(0, 1.5, "< 1.5%"), (1.5, 2.5, "1.5-2.5%"), (2.5, 3.2, "2.5-3.2%"),
              (3.2, 5.0, "3.2-5%"), (5.0, 8.0, "5-8%"), (8.0, 99, "> 8%")]
    for lo, hi, lab in bandas:
        sub = [f for f in filas if f.get("tp_pct") is not None
               and lo <= f["tp_pct"] < hi]
        if len(sub) < MIN_N:
            print(f"  {lab:<14} (pocas: {len(sub)})")
            continue
        c = Counter(f["des"] for f in sub)
        g = sum(1 for f in sub if f["llego32"])
        print(f"  {lab:<14} {len(sub):>6} {pct(c['TP'], len(sub)):>12} "
              f"{pct(c['SL'], len(sub)):>12} {pct(g, len(sub)):>15}")
    print("\n  Con TP corto se cumple mas y se llega menos a tu objetivo.")
    print("  Son medidas distintas y conviene no confundirlas.")

    # ==================================================================
    print("\n" + "=" * 92)
    print("2. ¿QUE TP TENIAN LAS QUE CUMPLIERON?")
    print("=" * 92)
    tps = np.array([f["tp_pct"] for f in conTP if f.get("tp_pct") is not None])
    otras = np.array([f["tp_pct"] for f in filas
                      if f["des"] != "TP" and f.get("tp_pct") is not None])
    print(f"\n  {'':<22} {'cumplieron':>12} {'las demas':>12}")
    print(f"  {'TP mediano':<22} {np.median(tps):>+11.2f}% {np.median(otras):>+11.2f}%")
    print(f"  {'p25':<22} {np.percentile(tps,25):>+11.2f}% "
          f"{np.percentile(otras,25):>+11.2f}%")
    print(f"  {'p75':<22} {np.percentile(tps,75):>+11.2f}% "
          f"{np.percentile(otras,75):>+11.2f}%")
    print(f"\n  reparto del TP entre las {len(conTP)} que cumplieron:")
    for lo, hi, lab in bandas:
        k = int(((tps >= lo) & (tps < hi)).sum())
        barra = "#" * int(44 * k / max(len(tps), 1))
        print(f"     {lab:<12} {k:>4} {pct(k, len(tps)):>7}  {barra}")

    # ==================================================================
    print("\n" + "=" * 92)
    print("3. DE LAS QUE CUMPLIERON SU TP, ¿CUANTAS LLEGARON A +3.2%?")
    print("=" * 92)
    g = [f for f in conTP if f["llego32"]]
    corto = [f for f in conTP if (f.get("tp_pct") or 0) < META]
    corto_g = [f for f in corto if f["llego32"]]
    largo = [f for f in conTP if (f.get("tp_pct") or 0) >= META]
    print(f"\n  de las {len(conTP)} que tocaron su TP:")
    print(f"    llegaron a +{META}%:      {len(g):>4}  {pct(len(g), len(conTP))}")
    print(f"    se quedaron cortas:   {len(conTP)-len(g):>4}  "
          f"{pct(len(conTP)-len(g), len(conTP))}")
    print(f"\n  partido por el TP que ofrecian:")
    print(f"    TP >= {META}% (tocarlo YA es llegar):  {len(largo):>4}  "
          f"{pct(len(largo), len(conTP))}")
    print(f"    TP <  {META}% (tocarlo NO basta):      {len(corto):>4}  "
          f"{pct(len(corto), len(conTP))}")
    if corto:
        print(f"       de esas, aun asi llegaron a +{META}%: {len(corto_g):>4}  "
              f"{pct(len(corto_g), len(corto))}")
        print(f"       se quedaron cortas de verdad:      "
              f"{len(corto)-len(corto_g):>4}  "
              f"{pct(len(corto)-len(corto_g), len(corto))}")
    print(f"\n  Sobre el total de {n} senales, las que cumplieron su TP Y ademas")
    print(f"  llegaron a tu objetivo son {len(g)}  ({pct(len(g), n)}).")

    # ==================================================================
    print("\n" + "=" * 92)
    print("4. EL PATRON: en que se diferencian de las que no cumplieron")
    print("=" * 92)
    noTP = [f for f in filas if f["des"] != "TP"]
    print(f"\n  {'variable':<20} {'cumplieron':>12} {'no':>12} {'dif':>10}")
    def med(L, c):
        v = [x[c] for x in L if x.get(c) is not None]
        return np.median(v) if v else float("nan")
    for c, fmt in (("tp_pct", "{:+.2f}"), ("sl_pct", "{:+.2f}"), ("score", "{:.0f}"),
                   ("orden", "{:.0f}"), ("vol_24h", "{:.2e}"),
                   ("vol_1m_medio", "{:.0f}"), ("mfe_pct", "{:+.2f}"),
                   ("mae_pct", "{:+.2f}")):
        a, b = med(conTP, c), med(noTP, c)
        d = (a - b) / abs(b) * 100 if b else 0
        print(f"  {c:<20} {fmt.format(a):>12} {fmt.format(b):>12} {d:>+9.1f}%")

    print(f"\n  reparto por tier y por orden de senal:")
    for campo, vals in (("tier", ["EXTRA-FUERTE", "FUERTE", "MODERADA", "VIGILANCIA"]),):
        for v in vals:
            sub = [f for f in filas if f["tier"] == v]
            if len(sub) < MIN_N:
                continue
            k = sum(1 for f in sub if f["des"] == "TP")
            tp_med = med(sub, "tp_pct")
            print(f"     {v:<14} n={len(sub):>4}  cumple {pct(k, len(sub)):>6}  "
                  f"TP mediano {tp_med:+.2f}%")
    print()
    for lo, hi, lab in [(1, 2, "1a del par"), (2, 4, "2a-3a"),
                        (4, 7, "4a-6a"), (7, 999, "7a o mas")]:
        sub = [f for f in filas if lo <= f["orden"] < hi]
        k = sum(1 for f in sub if f["des"] == "TP")
        g2 = sum(1 for f in sub if f["llego32"])
        print(f"     {lab:<14} n={len(sub):>4}  cumple {pct(k, len(sub)):>6}  "
              f"TP mediano {med(sub,'tp_pct'):+.2f}%   llega a +3.2% {pct(g2, len(sub)):>6}")

    # ==================================================================
    print("\n" + "=" * 92)
    print("5. CUANTO TARDARON EN CUMPLIR")
    print("=" * 92)
    t = np.array([f["ms_tp"] for f in conTP]) / 60000.0
    print(f"  mediana {np.median(t):.0f}min   p25 {np.percentile(t,25):.0f}   "
          f"p75 {np.percentile(t,75):.0f}   max {t.max():.0f}")
    print(f"\n  {'tramo':<16} {'n':>6} {'%':>8}")
    for lo, hi, lab in [(0, 15, "< 15min"), (15, 60, "15-60min"),
                        (60, 240, "1-4h"), (240, 720, "4-12h"), (720, 1e9, "> 12h")]:
        k = int(((t >= lo) & (t < hi)).sum())
        print(f"  {lab:<16} {k:>6} {pct(k, len(t)):>8}")


    # ==================================================================
    print("\n" + "=" * 92)
    print("6. LA 1a Y LA 2a: cuanto pasa entre ellas, y si la 1a ya se resolvio")
    print("=" * 92)
    print("  Distingue dos cosas muy distintas: que la 2a llegue DESPUES de que")
    print("  la 1a cerrara (senal nueva legitima) o que llegue con la 1a todavia")
    print("  abierta (doblar la apuesta sobre el mismo movimiento).\n")
    parejas = []
    for sym, lista in por_par.items():
        if len(lista) < 2:
            continue
        a1, a2 = lista[0], lista[1]
        hueco = (a2["ts_open"] - a1["ts_open"]) / 60000.0
        # ¿la 1a ya se habia resuelto cuando nacio la 2a?
        t_tp = a1["ts_open"] + a1["ms_tp"] if a1["ms_tp"] else None
        t_sl = a1["ts_open"] + a1["ms_sl"] if a1["ms_sl"] else None
        antes = [t for t in (t_tp, t_sl) if t is not None and t <= a2["ts_open"]]
        if t_tp is not None and t_tp <= a2["ts_open"] and (
                t_sl is None or t_tp < t_sl):
            estado = "la 1a ya habia cumplido su TP"
        elif t_sl is not None and t_sl <= a2["ts_open"]:
            estado = "la 1a ya habia tocado su SL"
        else:
            estado = "la 1a seguia abierta"
        parejas.append({"sym": sym, "hueco": hueco, "estado": estado,
                        "d1": a1["des"], "d2": a2["des"],
                        "g1": a1["llego32"], "g2": a2["llego32"]})

    h = np.array([p["hueco"] for p in parejas])
    print(f"  {len(parejas)} pares con al menos dos senales")
    print(f"  hueco entre la 1a y la 2a: mediana {np.median(h):.0f}min "
          f"({np.median(h)/60:.1f}h)   p25 {np.percentile(h,25):.0f}   "
          f"p75 {np.percentile(h,75):.0f}   max {h.max():.0f}")
    print(f"\n  {'hueco':<16} {'n':>6} {'%':>8}")
    for lo, hi, lab in [(0, 60, "< 1h"), (60, 240, "1-4h"), (240, 720, "4-12h"),
                        (720, 1440, "12-24h"), (1440, 1e9, "mas de 24h")]:
        k = int(((h >= lo) & (h < hi)).sum())
        print(f"  {lab:<16} {k:>6} {pct(k, len(h)):>8}")

    print(f"\n  ¿en que estado estaba la 1a cuando nacio la 2a?")
    c = Counter(p["estado"] for p in parejas)
    for k, v in c.most_common():
        print(f"     {k:<34} {v:>4}  {pct(v, len(parejas))}")

    print(f"\n  y segun ese estado, ¿como le fue a la 2a?")
    print(f"     {'estado de la 1a':<34} {'n':>5} {'la 2a cumple':>14} "
          f"{'la 2a llega a +3.2%':>21}")
    for est in c:
        sub = [p for p in parejas if p["estado"] == est]
        if len(sub) < MIN_N:
            print(f"     {est:<34} (pocas: {len(sub)})")
            continue
        k = sum(1 for p in sub if p["d2"] == "TP")
        g2 = sum(1 for p in sub if p["g2"])
        print(f"     {est:<34} {len(sub):>5} {pct(k, len(sub)):>14} "
              f"{pct(g2, len(sub)):>21}")

    print(f"\n  por hueco de tiempo:")
    print(f"     {'hueco':<16} {'n':>5} {'la 2a cumple':>14} {'la 1a ya estaba resuelta':>26}")
    for lo, hi, lab in [(0, 60, "< 1h"), (60, 240, "1-4h"), (240, 720, "4-12h"),
                        (720, 1e9, "mas de 12h")]:
        sub = [p for p in parejas if lo <= p["hueco"] < hi]
        if len(sub) < MIN_N:
            print(f"     {lab:<16} (pocas: {len(sub)})")
            continue
        k = sum(1 for p in sub if p["d2"] == "TP")
        r = sum(1 for p in sub if p["estado"] != "la 1a seguia abierta")
        print(f"     {lab:<16} {len(sub):>5} {pct(k, len(sub)):>14} "
              f"{pct(r, len(sub)):>26}")


if __name__ == "__main__":
    main()
