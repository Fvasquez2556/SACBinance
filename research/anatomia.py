# -*- coding: utf-8 -*-
"""
Anatomia de los grupos: que tienen en comun las que fallan y las que llegan.

Cuatro preguntas, tres de Felix y una mia:

  1. ¿Que comparten las 372 de AL_STOP?
  2. De las que llegaron a +3.2%: ¿bajaron antes? ¿cuanto, de media, en el
     peor caso y en el mejor?
  3. ¿Cuanto tiempo pasa entre una senal ganadora y la siguiente?
  4. (mia) ¿Que mas podria ayudar a elegir mejor?

La 4 se ataca por donde ninguna variable del sistema ha mirado todavia: no lo
que pasa DENTRO de una senal, sino el CONTEXTO en que nace — cuantas senales
hay a la vez, si el par ya venia dando senales, y si las ganadoras se agrupan
en el tiempo. Si se agrupan, lo que decide no es la moneda sino el momento, y
eso cambia donde hay que buscar.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import Counter, defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
TZ = -6
MIN_N = 30


def gt(ts):
    return dt.datetime.utcfromtimestamp(ts / 1000) + dt.timedelta(hours=TZ)


def pct(n, d):
    return f"{100*n/d:.1f}%" if d else "—"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    filas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND cerrado=1 ORDER BY ts_open")]
    for f in filas:
        f["gano"] = (f["mfe_pct"] or 0) >= META
        f["al_stop"] = (not f["gano"]) and (f["mfe_pct"] or 0) < 2.2 \
            and f["ms_sl"] is not None
    n = len(filas)
    gan = [f for f in filas if f["gano"]]
    stop = [f for f in filas if f["al_stop"]]
    base = 100 * len(gan) / n
    print(f"{n} senales cerradas | {len(gan)} llegaron ({base:.1f}%) | "
          f"{len(stop)} AL_STOP\n")

    # ==================================================================
    print("=" * 94)
    print("1. QUE COMPARTEN LAS DE AL_STOP")
    print("=" * 94)

    print("\n  a) ¿se repiten los mismos pares?")
    c_stop = Counter(f["symbol"] for f in stop)
    c_gan = Counter(f["symbol"] for f in gan)
    print(f"     {len(stop)} senales en {len(c_stop)} pares distintos "
          f"(mediana {np.median(list(c_stop.values())):.0f} por par)")
    print(f"     los que mas fallaron:")
    for sym, k in c_stop.most_common(8):
        tot = sum(1 for f in filas if f["symbol"] == sym)
        print(f"       {sym.replace('USDT',''):<12} {k:>3} al stop de {tot:>3} "
              f"senales   ganaron {c_gan.get(sym,0):>3}")

    print("\n  b) ¿el ancho de su stop?")
    for etq, sub in (("AL_STOP", stop), ("ganadoras", gan), ("todas", filas)):
        sl = [abs(f["sl_pct"]) for f in sub if f.get("sl_pct")]
        print(f"     {etq:<10} SL mediana {np.median(sl):.2f}%   "
              f"p25 {np.percentile(sl,25):.2f}%   p75 {np.percentile(sl,75):.2f}%")

    print("\n  c) ¿cuanto aguantaron antes de saltar?")
    t = np.array([f["ms_sl"] for f in stop if f["ms_sl"]]) / 60000.0
    print(f"     mediana {np.median(t):.0f}min   p25 {np.percentile(t,25):.0f}   "
          f"p75 {np.percentile(t,75):.0f}   "
          f"menos de 15min: {pct((t<15).sum(), len(t))}")

    print("\n  d) ¿y despues del stop, se recuperaron?")
    subio_luego = [f for f in stop if (f["mfe_pct"] or 0) > 0]
    print(f"     MFE mediana del grupo: {np.median([f['mfe_pct'] for f in stop]):+.2f}%")
    print(f"     MAE mediana: {np.median([f['mae_pct'] for f in stop]):+.2f}%")
    print(f"     nunca subieron nada: "
          f"{pct(sum(1 for f in stop if (f['mfe_pct'] or 0) <= 0.5), len(stop))}")

    print("\n  e) ¿se agrupan en el tiempo? (huecos entre una y la siguiente)")
    for etq, sub in (("AL_STOP", stop), ("ganadoras", gan)):
        ts = sorted(f["ts_open"] for f in sub)
        d = np.diff(ts) / 60000.0
        print(f"     {etq:<10} hueco mediana {np.median(d):>5.1f}min   "
              f"p25 {np.percentile(d,25):>5.1f}   p75 {np.percentile(d,75):>5.1f}   "
              f"seguidas (<2min): {pct((d<2).sum(), len(d))}")

    # ==================================================================
    print("\n" + "=" * 94)
    print("2. LAS QUE LLEGARON: ¿BAJARON ANTES DE SUBIR?")
    print("=" * 94)
    dips = [f["dip_antes_obj"] for f in gan if f.get("dip_antes_obj") is not None]
    d = np.array(dips)
    sin_dip = [f for f in gan if not f.get("dip_antes_obj")]
    print(f"\n  de {len(gan)} ganadoras, {len(d)} tienen medido el retroceso previo")
    print(f"\n  {'':>22} {'valor':>9}")
    print(f"  {'media':>22} {d.mean():>+8.2f}%")
    print(f"  {'mediana':>22} {np.median(d):>+8.2f}%")
    print(f"  {'el MEJOR (menos cayo)':>22} {d.max():>+8.2f}%")
    print(f"  {'el PEOR (mas cayo)':>22} {d.min():>+8.2f}%")
    print(f"  {'p25 (1 de cada 4 peor)':>22} {np.percentile(d,25):>+8.2f}%")
    print(f"  {'p10 (1 de cada 10 peor)':>22} {np.percentile(d,10):>+8.2f}%")
    print(f"\n  reparto del retroceso previo:")
    for lo, hi, lab in [(-0.5, 0.1, "casi nada (>-0.5%)"), (-1.2, -0.5, "-0.5 a -1.2%"),
                        (-2.0, -1.2, "-1.2 a -2%"), (-3.2, -2.0, "-2 a -3.2%"),
                        (-5.0, -3.2, "-3.2 a -5%"), (-100, -5.0, "peor de -5%")]:
        k = ((d > lo) & (d <= hi)).sum()
        print(f"     {lab:<22} {k:>4}  {pct(k, len(d))}")
    print(f"\n  Lo que esto significa para el stop: un stop mas estrecho que")
    print(f"  {abs(np.percentile(d,25)):.2f}% saca a 1 de cada 4 ganadoras, y uno mas")
    print(f"  estrecho que {abs(np.percentile(d,10)):.2f}% saca a 1 de cada 10.")

    # ==================================================================
    print("\n" + "=" * 94)
    print("3. TIEMPO ENTRE SENALES GANADORAS")
    print("=" * 94)
    ts = sorted(f["ts_open"] for f in gan)
    hue = np.diff(ts) / 60000.0
    print(f"\n  {len(gan)} ganadoras en {(ts[-1]-ts[0])/3600000:.1f}h")
    print(f"  hueco entre una y la siguiente:")
    print(f"     mediana {np.median(hue):.1f}min   media {hue.mean():.1f}min")
    print(f"     p25 {np.percentile(hue,25):.1f}   p75 {np.percentile(hue,75):.1f}   "
          f"el mayor {hue.max():.0f}min ({hue.max()/60:.1f}h)")
    print(f"\n  reparto:")
    for lo, hi, lab in [(0, 1, "menos de 1min"), (1, 5, "1-5min"), (5, 15, "15min"),
                        (15, 60, "15-60min"), (60, 1e9, "mas de 1h")]:
        k = ((hue >= lo) & (hue < hi)).sum()
        print(f"     {lab:<16} {k:>4}  {pct(k, len(hue))}")
    print(f"\n  ritmo: {len(gan)/((ts[-1]-ts[0])/3600000):.1f} ganadoras por hora")

    # ==================================================================
    print("\n" + "=" * 94)
    print("4. EL CONTEXTO EN QUE NACE LA SENAL  (lo que nadie ha mirado)")
    print("=" * 94)

    orden = sorted(filas, key=lambda f: f["ts_open"])
    tiempos = np.array([f["ts_open"] for f in orden], dtype=float)

    print("\n  a) ¿cuantas senales hay a la vez? (emitidas en los 10min previos)")
    for f in orden:
        i = np.searchsorted(tiempos, f["ts_open"] - 10 * 60_000, side="left")
        j = np.searchsorted(tiempos, f["ts_open"], side="right")
        f["rafaga"] = int(j - i)
    for lo, hi, lab in [(1, 3, "1-2 (sola)"), (3, 6, "3-5"), (6, 11, "6-10"),
                        (11, 21, "11-20"), (21, 999, "mas de 20")]:
        sub = [f for f in orden if lo <= f["rafaga"] < hi]
        if len(sub) < MIN_N:
            print(f"     {lab:<14} (pocas: {len(sub)})")
            continue
        w = sum(1 for f in sub if f["gano"])
        print(f"     {lab:<14} n={len(sub):>5}  llega {pct(w, len(sub)):>6}  "
              f"({100*w/len(sub) - base:+5.1f} vs base)")

    print("\n  b) ¿es la primera senal de ese par, o ya venia dando?")
    vistos: dict = {}
    for f in orden:
        f["repeticion"] = vistos.get(f["symbol"], 0) + 1
        f["desde_anterior"] = ((f["ts_open"] - vistos[f["symbol"] + "_ts"]) / 60000.0
                               if f["symbol"] + "_ts" in vistos else None)
        vistos[f["symbol"]] = f["repeticion"]
        vistos[f["symbol"] + "_ts"] = f["ts_open"]
    for lo, hi, lab in [(1, 2, "1a del par"), (2, 3, "2a"), (3, 5, "3a-4a"),
                        (5, 999, "5a o mas")]:
        sub = [f for f in orden if lo <= f["repeticion"] < hi]
        if len(sub) < MIN_N:
            print(f"     {lab:<14} (pocas: {len(sub)})")
            continue
        w = sum(1 for f in sub if f["gano"])
        print(f"     {lab:<14} n={len(sub):>5}  llega {pct(w, len(sub)):>6}  "
              f"({100*w/len(sub) - base:+5.1f} vs base)")

    print("\n  c) ¿cuanto hacia de la anterior senal DEL MISMO par?")
    for lo, hi, lab in [(0, 60, "menos de 1h"), (60, 240, "1-4h"),
                        (240, 720, "4-12h"), (720, 1e9, "mas de 12h")]:
        sub = [f for f in orden if f["desde_anterior"] is not None
               and lo <= f["desde_anterior"] < hi]
        if len(sub) < MIN_N:
            print(f"     {lab:<14} (pocas: {len(sub)})")
            continue
        w = sum(1 for f in sub if f["gano"])
        print(f"     {lab:<14} n={len(sub):>5}  llega {pct(w, len(sub)):>6}  "
              f"({100*w/len(sub) - base:+5.1f} vs base)")

    print("\n  d) ¿como iban las senales de la hora anterior? "
          "(¿el momento es bueno o malo?)")
    # De las senales emitidas 60-180min antes, cuantas acabaron llegando.
    # Es informacion que YA se sabe cuando nace la nueva.
    for f in orden:
        i = np.searchsorted(tiempos, f["ts_open"] - 180 * 60_000, side="left")
        j = np.searchsorted(tiempos, f["ts_open"] - 60 * 60_000, side="right")
        prev = orden[i:j]
        f["clima"] = (sum(1 for p in prev if p["gano"]) / len(prev)) if len(prev) >= 5 else None
    for lo, hi, lab in [(0, 0.35, "mal (<35% llego)"), (0.35, 0.5, "35-50%"),
                        (0.5, 0.65, "50-65%"), (0.65, 1.01, "bien (>65%)")]:
        sub = [f for f in orden if f["clima"] is not None and lo <= f["clima"] < hi]
        if len(sub) < MIN_N:
            print(f"     {lab:<18} (pocas: {len(sub)})")
            continue
        w = sum(1 for f in sub if f["gano"])
        print(f"     {lab:<18} n={len(sub):>5}  llega {pct(w, len(sub)):>6}  "
              f"({100*w/len(sub) - base:+5.1f} vs base)")

    print("\n  e) por hora del dia (Guatemala)")
    for f in orden:
        f["hora"] = gt(f["ts_open"]).hour
    for h0, h1, lab in [(0, 6, "00-06"), (6, 12, "06-12"),
                        (12, 18, "12-18"), (18, 24, "18-24")]:
        sub = [f for f in orden if h0 <= f["hora"] < h1]
        if len(sub) < MIN_N:
            continue
        w = sum(1 for f in sub if f["gano"])
        print(f"     {lab:<14} n={len(sub):>5}  llega {pct(w, len(sub)):>6}  "
              f"({100*w/len(sub) - base:+5.1f} vs base)")


if __name__ == "__main__":
    main()
