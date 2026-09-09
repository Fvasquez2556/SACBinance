# -*- coding: utf-8 -*-
"""
Las ganadoras que primero se hundieron: ¿se podian ver venir?

De las 697 que llegaron a +3.2%, el retroceso previo tuvo mediana -1.03% pero
la peor cayo -8.45%. Felix pregunta por esas: si se puede evitar entrar en
ellas, o al menos reconocerlas.

La pregunta se parte en dos, y solo la segunda es util:

  a) ¿Se distinguen DESPUES? Trivial: cayeron mas. No sirve de nada.
  b) ¿Se distinguian EN EL MOMENTO DE LA SENAL? Eso es lo unico accionable, y
     es lo que se mide aqui.

Ojo con el reves de la moneda: quien cae -8% y luego llega a +3.2% ofrece,
desde el suelo, una subida enorme. Evitarlas no es gratis.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
TZ = -6
MIN_N = 25
ZONA, LOOKBACK = 8, 40


def pct(n, d):
    return f"{100*n/d:.1f}%" if d else "—"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    kl = defaultdict(list)
    for s, t, h, l, c, v in con.execute(
            "SELECT symbol, open_time, h, l, c, v FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        kl[s].append((t, h, l, c, v))
    kl = {s: np.array(x, dtype=np.float64) for s, x in kl.items()}

    filas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND cerrado=1 "
        "AND mfe_pct >= ? ORDER BY ts_open", (META,))]

    for f in filas:
        f["dip"] = f.get("dip_antes_obj") or 0.0
        f["hora"] = (dt.datetime.utcfromtimestamp(f["ts_open"] / 1000)
                     + dt.timedelta(hours=TZ)).hour
        f["caida_prev"] = f["rebote"] = f["vol_ratio"] = f["rango_1h"] = None
        a = kl.get(f["symbol"])
        if a is None:
            continue
        i = int(np.searchsorted(a[:, 0], f["ts_open"], side="right")) - 1
        if i < 120:
            continue
        seg, prev = a[i - ZONA + 1:i + 1], a[i - ZONA - LOOKBACK + 1:i - ZONA + 1]
        pico, suelo = prev[:, 1].max(), seg[:, 2].min()
        if pico > 0 and suelo > 0:
            f["caida_prev"] = (suelo - pico) / pico * 100.0
            f["rebote"] = (a[i, 3] - suelo) / suelo * 100.0
        # contexto de la hora previa, todo conocido en el instante de la senal
        h1 = a[i - 59:i + 1]
        if len(h1) == 60 and h1[:, 2].min() > 0:
            f["rango_1h"] = (h1[:, 1].max() - h1[:, 2].min()) / h1[:, 2].min() * 100.0
        v1, v0 = a[i - 14:i + 1, 4].mean(), a[i - 119:i - 14, 4].mean()
        if v0 > 0:
            f["vol_ratio"] = v1 / v0

    n = len(filas)
    d = np.array([f["dip"] for f in filas])
    print(f"{n} ganadoras. Retroceso previo: mediana {np.median(d):+.2f}%, "
          f"peor {d.min():+.2f}%\n")

    HONDO = -3.0
    hondas = [f for f in filas if f["dip"] <= HONDO]
    suaves = [f for f in filas if f["dip"] > HONDO]
    print("=" * 92)
    print(f"LAS QUE SE HUNDIERON (<= {HONDO}%) CONTRA LAS DEMAS")
    print("=" * 92)
    print(f"  hondas: {len(hondas)} ({pct(len(hondas), n)})   suaves: {len(suaves)}")

    print(f"\n  ¿se distinguian EN EL MOMENTO DE LA SENAL?")
    print(f"  {'variable':<20} {'hondas':>10} {'suaves':>10} {'dif':>9}")
    for c, fmt in (("score", "{:.0f}"), ("tp_pct", "{:+.2f}"), ("sl_pct", "{:+.2f}"),
                   ("vol_24h", "{:.2e}"), ("vol_1m_medio", "{:.0f}"),
                   ("caida_prev", "{:+.2f}"), ("rebote", "{:+.2f}"),
                   ("rango_1h", "{:.2f}"), ("vol_ratio", "{:.2f}"),
                   ("hora", "{:.0f}")):
        h = [x[c] for x in hondas if x.get(c) is not None]
        s = [x[c] for x in suaves if x.get(c) is not None]
        if len(h) < 10 or len(s) < 10:
            continue
        mh, ms = np.median(h), np.median(s)
        dif = (mh - ms) / abs(ms) * 100 if ms else 0
        print(f"  {c:<20} {fmt.format(mh):>10} {fmt.format(ms):>10} {dif:>+8.1f}%")

    print(f"\n  ¿y que recompensa dieron? (evitarlas no es gratis)")
    for etq, sub in (("hondas", hondas), ("suaves", suaves)):
        mfe = [x["mfe_pct"] for x in sub]
        t = [x["ms_up_32"] / 60000.0 for x in sub if x["ms_up_32"]]
        print(f"     {etq:<8} MFE mediana {np.median(mfe):>+6.2f}%   "
              f"tardo {np.median(t):>5.0f}min   "
              f"desde su suelo hasta la meta: "
              f"{np.median([META - x['dip'] for x in sub]):>+5.2f}%")

    print("\n" + "=" * 92)
    print("EL RANGO DE LA HORA PREVIA — la unica que separa algo")
    print("=" * 92)
    print("  (cuanto se movio el par en los 60 minutos anteriores a la senal)")
    print(f"  {'rango 1h':<16} {'n':>6} {'retroceso mediano':>19} "
          f"{'se hunde <-3%':>15}")
    for lo, hi, lab in [(0, 1.0, "< 1%"), (1.0, 2.0, "1-2%"), (2.0, 3.5, "2-3.5%"),
                        (3.5, 6.0, "3.5-6%"), (6.0, 999, "> 6%")]:
        sub = [f for f in filas if f.get("rango_1h") is not None
               and lo <= f["rango_1h"] < hi]
        if len(sub) < MIN_N:
            print(f"  {lab:<16} (pocas: {len(sub)})")
            continue
        dd = np.array([x["dip"] for x in sub])
        print(f"  {lab:<16} {len(sub):>6} {np.median(dd):>18.2f}% "
              f"{pct((dd <= HONDO).sum(), len(sub)):>15}")

    print("\n" + "=" * 92)
    print("Y LA COMPROBACION QUE IMPORTA: ¿el rango 1h predice el resultado?")
    print("=" * 92)
    print("  Aqui sobre TODAS las senales cerradas, no solo las ganadoras.")
    todas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND cerrado=1 ORDER BY ts_open")]
    for f in todas:
        f["gano"] = (f["mfe_pct"] or 0) >= META
        f["rango_1h"] = None
        a = kl.get(f["symbol"])
        if a is None:
            continue
        i = int(np.searchsorted(a[:, 0], f["ts_open"], side="right")) - 1
        if i < 120:
            continue
        h1 = a[i - 59:i + 1]
        if len(h1) == 60 and h1[:, 2].min() > 0:
            f["rango_1h"] = (h1[:, 1].max() - h1[:, 2].min()) / h1[:, 2].min() * 100.0
    base = 100 * sum(1 for f in todas if f["gano"]) / len(todas)
    print(f"  base {base:.1f}%")
    print(f"  {'rango 1h':<16} {'n':>6} {'llega a meta':>14} {'vs base':>9} "
          f"{'MAE mediano':>13}")
    for lo, hi, lab in [(0, 1.0, "< 1%"), (1.0, 2.0, "1-2%"), (2.0, 3.5, "2-3.5%"),
                        (3.5, 6.0, "3.5-6%"), (6.0, 999, "> 6%")]:
        sub = [f for f in todas if f.get("rango_1h") is not None
               and lo <= f["rango_1h"] < hi]
        if len(sub) < MIN_N:
            print(f"  {lab:<16} (pocas: {len(sub)})")
            continue
        w = sum(1 for f in sub if f["gano"])
        mae = np.median([f["mae_pct"] for f in sub])
        print(f"  {lab:<16} {len(sub):>6} {pct(w, len(sub)):>14} "
              f"{100*w/len(sub) - base:>+8.1f} {mae:>12.2f}%")


if __name__ == "__main__":
    main()
