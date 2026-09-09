# -*- coding: utf-8 -*-
"""
¿Las señales nuevas del mismo par ensucian el analisis?

La sospecha de Felix, en sus palabras: un par da senal a 0.00987, cae un 2.4%
sin recuperarse, y horas despues vuelve a dar senal —ya mas abajo— y esa
segunda si llega a su TP. En la tabla la segunda cuenta como ganadora, pero
quien actuo sobre la primera sigue en perdida. Y la subida que "gana" la
segunda es en parte la recuperacion de la caida de la primera.

Es una critica metodologica real y tiene nombre: ventanas solapadas. Tres
formas distintas de contaminar:

  1. INDEPENDENCIA. Dos senales del mismo par con ventanas que se pisan no son
     dos observaciones independientes. n=1391 no son 1391 datos.
  2. SESGO DE ENTRADA MAS BAJA. Tras una caida, la senal nueva nace a un precio
     menor, asi que subir 3.2% desde ahi es mecanicamente mas facil. Parte de
     lo que se cuenta como acierto es rebote de la caida anterior.
  3. DOBLE CONTEO DEL MISMO MOVIMIENTO. Un solo tramo alcista puede cumplir el
     objetivo de tres senales a la vez, y se cuenta tres veces.

Se mide cada una, y al final se calcula la version DEDUPLICADA: una senal por
par a la vez, que es lo que un operador con capital limitado vive de verdad.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
VENTANA_MS = 24 * 3600_000
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

    # Precios 1m para saber donde estaba la senal anterior cuando nace la nueva
    kl = defaultdict(list)
    for s, t, c in con.execute(
            "SELECT symbol, open_time, c FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        kl[s].append((t, c))
    kl = {s: np.array(v, dtype=np.float64) for s, v in kl.items()}

    def precio_en(sym, ts):
        a = kl.get(sym)
        if a is None:
            return None
        i = int(np.searchsorted(a[:, 0], ts, side="right")) - 1
        if i < 0 or ts - a[i, 0] > 5 * 60_000:
            return None
        return float(a[i, 1])

    por_par = defaultdict(list)
    for f in filas:
        f["gano"] = (f["mfe_pct"] or 0) >= META
        por_par[f["symbol"]].append(f)
    for sym, lista in por_par.items():
        for k, f in enumerate(lista, 1):
            f["orden"] = k
    n = len(filas)
    base = 100 * sum(1 for f in filas if f["gano"]) / n
    print(f"{n} senales cerradas, {len(por_par)} pares, base {base:.1f}%\n")

    # ==================================================================
    print("=" * 96)
    print("1. ¿CUANTO SE PISAN LAS VENTANAS?")
    print("=" * 96)
    for f in filas:
        prev = [g for g in por_par[f["symbol"]]
                if g["ts_open"] < f["ts_open"]
                and g["ts_open"] + VENTANA_MS > f["ts_open"]]
        f["solapa"] = len(prev)
        f["anterior"] = prev[-1] if prev else None
        f["bajo_agua"] = None
        if f["anterior"]:
            p = precio_en(f["symbol"], f["ts_open"])
            if p and f["anterior"]["entry"]:
                f["bajo_agua"] = (p / f["anterior"]["entry"] - 1) * 100.0

    solapadas = [f for f in filas if f["solapa"] > 0]
    print(f"  senales con OTRA del mismo par aun en ventana: "
          f"{len(solapadas)} ({pct(len(solapadas), n)})")
    d = [f["solapa"] for f in solapadas]
    print(f"  cuantas se pisan a la vez: mediana {np.median(d):.0f}, "
          f"maximo {max(d)}")
    print(f"\n  {'senales solapadas':<22} {'n':>6} {'llega a meta':>14} {'vs base':>9}")
    for lo, hi, lab in [(0, 1, "ninguna (limpia)"), (1, 2, "1 encima"),
                        (2, 4, "2-3"), (4, 99, "4 o mas")]:
        sub = [f for f in filas if lo <= f["solapa"] < hi]
        if len(sub) < MIN_N:
            print(f"  {lab:<22} (pocas: {len(sub)})")
            continue
        w = sum(1 for f in sub if f["gano"])
        print(f"  {lab:<22} {len(sub):>6} {pct(w, len(sub)):>14} "
              f"{100*w/len(sub) - base:>+8.1f}")

    # ==================================================================
    print("\n" + "=" * 96)
    print("2. EL CASO EXACTO QUE DESCRIBES: senal nueva con la anterior BAJO AGUA")
    print("=" * 96)
    print("  (donde estaba el precio respecto al entry de la senal anterior)")
    print(f"\n  {'la anterior iba':<22} {'n':>6} {'llega a meta':>14} {'vs base':>9} "
          f"{'MFE med':>9}")
    for lo, hi, lab in [(-100, -3, "peor de -3%"), (-3, -1.5, "-3 a -1.5%"),
                        (-1.5, -0.5, "-1.5 a -0.5%"), (-0.5, 0.5, "cerca de 0"),
                        (0.5, 100, "en verde")]:
        sub = [f for f in filas if f["bajo_agua"] is not None
               and lo <= f["bajo_agua"] < hi]
        if len(sub) < MIN_N:
            print(f"  {lab:<22} (pocas: {len(sub)})")
            continue
        w = sum(1 for f in sub if f["gano"])
        mfe = np.median([f["mfe_pct"] for f in sub])
        print(f"  {lab:<22} {len(sub):>6} {pct(w, len(sub)):>14} "
              f"{100*w/len(sub) - base:>+8.1f} {mfe:>+8.2f}%")

    hondas = [f for f in filas if f["bajo_agua"] is not None and f["bajo_agua"] <= -2]
    if hondas:
        print(f"\n  Senales nacidas con la anterior a -2% o peor: {len(hondas)}")
        w = sum(1 for f in hondas if f["gano"])
        print(f"    llegan a la meta: {pct(w, len(hondas))} "
              f"({100*w/len(hondas) - base:+.1f} vs base)")
        print(f"    ...pero quien entro en la ANTERIOR seguia perdiendo.")
        recup = [f for f in hondas if f["anterior"]["gano"]]
        print(f"    de esas anteriores, acabaron llegando a la meta: "
              f"{len(recup)} de {len(hondas)}  ({pct(len(recup), len(hondas))})")

    # ==================================================================
    print("\n" + "=" * 96)
    print("3. LA VERSION DEDUPLICADA: una senal por par a la vez")
    print("=" * 96)
    print("  Es lo que vive un operador con capital limitado: si ya esta dentro")
    print("  de un par, la siguiente senal de ese par no la puede tomar.")
    ocupado: dict = {}
    dedup = []
    for f in filas:
        libre_desde = ocupado.get(f["symbol"], 0)
        if f["ts_open"] >= libre_desde:
            dedup.append(f)
            ocupado[f["symbol"]] = f["ts_open"] + VENTANA_MS
    w = sum(1 for f in dedup if f["gano"])
    print(f"\n  {'':<26} {'n':>6} {'llega a meta':>14}")
    print(f"  {'TODAS (como se mide hoy)':<26} {n:>6} {pct(sum(1 for f in filas if f['gano']), n):>14}")
    print(f"  {'DEDUPLICADA':<26} {len(dedup):>6} {pct(w, len(dedup)):>14}")
    print(f"\n  diferencia: {100*w/len(dedup) - base:+.1f} puntos")
    print(f"  se descartan {n - len(dedup)} senales ({pct(n-len(dedup), n)}) por "
          f"solaparse con una anterior del mismo par")

    # ==================================================================
    print("\n" + "=" * 96)
    print("4. LAS 217 QUE SUBIERON >=2.2% Y DESPUES CAYERON AL SL")
    print("=" * 96)
    sub22 = [f for f in filas if f["ms_up_2"] is not None
             and f["ms_sl"] is not None and f["ms_sl"] > f["ms_up_2"]]
    print(f"  son {len(sub22)}. ¿de que numero de senal del par son?\n")
    print(f"  {'orden de la senal':<22} {'n':>6} {'% de las 217':>14}")
    for lo, hi, lab in [(1, 2, "1a del par"), (2, 4, "2a-3a"),
                        (4, 8, "4a-7a"), (8, 999, "8a o mas")]:
        k = sum(1 for f in sub22 if lo <= f["orden"] < hi)
        print(f"  {lab:<22} {k:>6} {pct(k, len(sub22)):>14}")
    solap = sum(1 for f in sub22 if f["solapa"] > 0)
    print(f"\n  de las 217, {solap} ({pct(solap, len(sub22))}) nacieron con otra "
          f"del mismo par aun viva")

    print(f"\n  Las 25 mas recientes:")
    print(f"  {'hora GT':<14} {'par':<12} {'nº':>3} {'entry':<11} {'TP':>7} {'SL':>7} "
          f"{'MFE':>7} {'MAE':>7} {'subio 2.2% en':>14} {'SL en':>9}")
    for f in sorted(sub22, key=lambda x: -x["ts_open"])[:25]:
        print(f"  {gt(f['ts_open']):%d/%m %H:%M}  {f['symbol'].replace('USDT',''):<12} "
              f"{f['orden']:>3} {f['entry']:<11.6g} {f['tp_pct']:>+6.2f}% "
              f"{f['sl_pct']:>+6.2f}% {f['mfe_pct']:>+6.2f}% {f['mae_pct']:>+6.2f}% "
              f"{f['ms_up_2']/60000:>13.0f}m {f['ms_sl']/60000:>8.0f}m")


if __name__ == "__main__":
    main()
