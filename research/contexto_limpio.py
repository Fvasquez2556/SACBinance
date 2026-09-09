# -*- coding: utf-8 -*-
"""
Las dos variables de contexto, recalculadas SIN mirar al futuro.

En anatomia.py cole dos sesgos de look-ahead y hay que arreglarlos antes de
usar nada de eso:

  CLIMA. Miraba cuantas senales de hace 1-3h "llegaron a +3.2%", pero eso se
  sabe con la ventana de 24h cumplida, no en el instante en que nace la nueva
  senal. La version honesta es: cuantas de esas YA habian llegado en ese
  momento. Es lo unico que se sabria en vivo.

  HISTORIAL DEL PAR. Igual: para saber si un par "nunca funciona" hay que usar
  solo las senales suyas que ya habian cerrado sus 24h antes de que naciera
  esta. Si se usan todas, se esta prediciendo el pasado con el futuro.

Las dos versiones se comparan aqui, para ver cuanto del efecto era real y
cuanto era el sesgo.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
VENTANA_MS = 24 * 3600_000
TZ = -6
MIN_N = 30


def pct(n, d):
    return f"{100*n/d:.1f}%" if d else "—"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    filas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND cerrado=1 ORDER BY ts_open")]
    for f in filas:
        f["gano"] = (f["mfe_pct"] or 0) >= META
        # instante absoluto en que toco la meta (si la toco)
        f["t_meta"] = (f["ts_open"] + f["ms_up_32"]) if f["ms_up_32"] else None
    n = len(filas)
    base = 100 * sum(1 for f in filas if f["gano"]) / n
    ts = np.array([f["ts_open"] for f in filas], dtype=float)
    print(f"{n} senales cerradas, base {base:.1f}%\n")

    def tabla(nombre, clave, bandas):
        print(f"  {nombre}")
        for lo, hi, lab in bandas:
            sub = [f for f in filas if f.get(clave) is not None
                   and lo <= f[clave] < hi]
            if len(sub) < MIN_N:
                print(f"     {lab:<22} (pocas: {len(sub)})")
                continue
            w = sum(1 for f in sub if f["gano"])
            print(f"     {lab:<22} n={len(sub):>5}  llega {pct(w, len(sub)):>6}  "
                  f"({100*w/len(sub) - base:+5.1f})")
        print()

    # ------------------------------------------------------------------
    print("=" * 92)
    print("CLIMA: como iban las senales de hace 1-3h")
    print("=" * 92)
    for f in filas:
        t = f["ts_open"]
        i = np.searchsorted(ts, t - 180 * 60_000, side="left")
        j = np.searchsorted(ts, t - 60 * 60_000, side="right")
        prev = filas[i:j]
        if len(prev) < 5:
            f["clima_sucio"] = f["clima_limpio"] = None
            continue
        # sucio: usa el desenlace final, que en ese momento no se conoce
        f["clima_sucio"] = sum(1 for p in prev if p["gano"]) / len(prev)
        # limpio: solo las que YA habian tocado la meta en ese instante
        f["clima_limpio"] = sum(
            1 for p in prev if p["t_meta"] and p["t_meta"] <= t) / len(prev)

    bandas_c = [(0, 0.35, "bajo (<35%)"), (0.35, 0.5, "35-50%"),
                (0.5, 0.65, "50-65%"), (0.65, 1.01, "alto (>65%)")]
    tabla("CON look-ahead (INVALIDO, solo para comparar)", "clima_sucio", bandas_c)
    tabla("SIN look-ahead (lo que se sabria en vivo)", "clima_limpio",
          [(0, 0.15, "bajo (<15%)"), (0.15, 0.30, "15-30%"),
           (0.30, 0.45, "30-45%"), (0.45, 1.01, "alto (>45%)")])

    # ------------------------------------------------------------------
    print("=" * 92)
    print("HISTORIAL DEL PAR: ¿su racha pasada predice la siguiente?")
    print("=" * 92)
    print("  Solo cuentan las senales del par cuyas 24h ya habian cerrado")
    print("  ANTES de que naciera esta. Es lo unico que se sabria en vivo.\n")
    por_par: dict = {}
    for f in filas:
        hist = por_par.setdefault(f["symbol"], [])
        # resueltas antes de que esta naciera
        pasadas = [h for h in hist if h["ts_open"] + VENTANA_MS <= f["ts_open"]]
        f["n_hist"] = len(pasadas)
        f["tasa_hist"] = (sum(1 for h in pasadas if h["gano"]) / len(pasadas)
                          if pasadas else None)
        hist.append(f)

    for min_hist, etq in ((3, "con >=3 senales previas resueltas"),
                          (5, "con >=5 senales previas resueltas")):
        sub_all = [f for f in filas if f["n_hist"] >= min_hist]
        print(f"  {etq}: {len(sub_all)} senales")
        for lo, hi, lab in [(0, 0.25, "el par iba <25%"), (0.25, 0.5, "25-50%"),
                            (0.5, 0.75, "50-75%"), (0.75, 1.01, ">=75%")]:
            sub = [f for f in sub_all if lo <= f["tasa_hist"] < hi]
            if len(sub) < MIN_N:
                print(f"     {lab:<22} (pocas: {len(sub)})")
                continue
            w = sum(1 for f in sub if f["gano"])
            print(f"     {lab:<22} n={len(sub):>5}  llega {pct(w, len(sub)):>6}  "
                  f"({100*w/len(sub) - base:+5.1f})")
        print()

    print("  ¿Y una lista negra? Pares que fallaron TODAS sus previas:")
    negra = [f for f in filas if f["n_hist"] >= 3 and f["tasa_hist"] == 0.0]
    if len(negra) >= MIN_N:
        w = sum(1 for f in negra if f["gano"])
        print(f"     0 de >=3 previas   n={len(negra):>5}  llega {pct(w, len(negra)):>6}  "
              f"({100*w/len(negra) - base:+5.1f})")
    else:
        print(f"     (pocas: {len(negra)})")
    blanca = [f for f in filas if f["n_hist"] >= 3 and f["tasa_hist"] == 1.0]
    if len(blanca) >= MIN_N:
        w = sum(1 for f in blanca if f["gano"])
        print(f"     TODAS las >=3 previas  n={len(blanca):>5}  "
              f"llega {pct(w, len(blanca)):>6}  ({100*w/len(blanca) - base:+5.1f})")
    else:
        print(f"     (blanca, pocas: {len(blanca)})")

    # ------------------------------------------------------------------
    print("\n" + "=" * 92)
    print("LO QUE SI AGUANTA: repeticion y hora, con su n")
    print("=" * 92)
    vistos: dict = {}
    for f in filas:
        f["rep"] = vistos.get(f["symbol"], 0) + 1
        vistos[f["symbol"]] = f["rep"]
        f["hora"] = (dt.datetime.utcfromtimestamp(f["ts_open"] / 1000)
                     + dt.timedelta(hours=TZ)).hour
    tabla("por numero de senal del par", "rep",
          [(1, 2, "1a"), (2, 3, "2a"), (3, 5, "3a-4a"), (5, 999, "5a o mas")])
    tabla("por hora (Guatemala)", "hora",
          [(0, 6, "00-06"), (6, 12, "06-12"), (12, 18, "12-18"), (18, 24, "18-24")])

    print("  COMBINADAS (1a o 2a del par, y fuera de 12-18h):")
    sub = [f for f in filas if f["rep"] <= 2 and not (12 <= f["hora"] < 18)]
    w = sum(1 for f in sub if f["gano"])
    print(f"     n={len(sub)}  llega {pct(w, len(sub))}  "
          f"({100*w/len(sub) - base:+.1f} vs base)  "
          f"retiene {pct(len(sub), n)} de las senales")


if __name__ == "__main__":
    main()
