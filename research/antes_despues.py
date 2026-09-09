# -*- coding: utf-8 -*-
"""
¿Han mejorado las senales desde los cambios del 7-sep?

El 7 de septiembre por la tarde se ensancho el stop: min_risk_atr paso de 0.5
a 1.5 y se anadio un suelo medido sobre el ruido real del par en 1m. Ese
cambio afecta a los NIVELES que el sistema ofrece, no al precio.

Distinguir eso es la clave de leer bien esta comparacion:

  la tasa de ACIERTO (llegar a +3.2%) NO deberia moverse por el cambio de
  stop. El precio hace lo que hace, este el stop donde este. Si se mueve, es
  el mercado, no la mejora.

  la tasa COBRABLE (llegar antes de que salte el stop) SI deberia mejorar,
  porque el stop ya no vive dentro del ruido. Ahi es donde hay que mirar.

Y sobre todo: el regimen del mercado se reporta en cada tramo. Sin eso,
cualquier subida se puede confundir con habilidad.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
TZ = -6
# El despliegue del stop nuevo, en UTC
CORTE = dt.datetime(2026, 9, 7, 18, 14)
MIN_N = 40


def ms(d: dt.datetime) -> int:
    return int((d - dt.datetime(1970, 1, 1)).total_seconds() * 1000)


def gt(ts):
    return dt.datetime.utcfromtimestamp(ts / 1000) + dt.timedelta(hours=TZ)


def pct(n, d):
    return f"{100*n/d:.1f}%" if d else "—"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    kl = defaultdict(list)
    for s, t, c in con.execute(
            "SELECT symbol, open_time, c FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        kl[s].append((t, c))
    kl = {s: np.array(v, dtype=np.float64) for s, v in kl.items()}

    filas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND cerrado=1 ORDER BY ts_open")]
    for f in filas:
        f["gano"] = (f["mfe_pct"] or 0) >= META
        # cobrable: llego a la meta ANTES de que saltara su propio stop
        f["cobro"] = bool(f["ms_up_32"] is not None
                          and (f["ms_sl"] is None or f["ms_sl"] > f["ms_up_32"]))

    tramos = [
        ("finde 5-6 sep", dt.datetime(2026, 9, 5), dt.datetime(2026, 9, 7)),
        ("7 sep, antes", dt.datetime(2026, 9, 7), CORTE),
        ("7 sep, despues", CORTE, dt.datetime(2026, 9, 8)),
        ("8 sep", dt.datetime(2026, 9, 8), dt.datetime(2026, 9, 9)),
        ("9 sep", dt.datetime(2026, 9, 9), dt.datetime(2026, 9, 10)),
    ]

    def regimen(t0, t1):
        subs = []
        for s, a in kl.items():
            i = int(np.searchsorted(a[:, 0], ms(t0), side="left"))
            j = int(np.searchsorted(a[:, 0], ms(t1), side="right")) - 1
            if j - i > 60 and a[i, 1] > 0:
                subs.append((a[j, 1] / a[i, 1] - 1) * 100.0)
        if len(subs) < 20:
            return None, None
        return float(np.median(subs)), 100.0 * float((np.array(subs) > 0).mean())

    print("=" * 100)
    print("  ANTES Y DESPUES DEL STOP NUEVO (7-sep 18:14 UTC)")
    print("=" * 100)
    print(f"  {'tramo':<16} {'n':>5} {'SL ofrecido':>12} {'llega a meta':>13} "
          f"{'lo COBRA':>10} {'mercado':>16}")
    print("  " + "-" * 96)
    for etq, t0, t1 in tramos:
        sub = [f for f in filas if ms(t0) <= f["ts_open"] < ms(t1)]
        if len(sub) < MIN_N:
            print(f"  {etq:<16} {len(sub):>5}   (pocas, aun sin ventana cumplida)")
            continue
        sl = np.median([abs(f["sl_pct"]) for f in sub if f.get("sl_pct")])
        w = sum(1 for f in sub if f["gano"])
        c = sum(1 for f in sub if f["cobro"])
        med, up = regimen(t0, t1)
        merc = f"{med:+.2f}% ({up:.0f}% suben)" if med is not None else "—"
        print(f"  {etq:<16} {len(sub):>5} {sl:>11.2f}% {pct(w,len(sub)):>13} "
              f"{pct(c,len(sub)):>10} {merc:>16}")

    # --- Lo que de verdad debia cambiar ---
    print("\n" + "=" * 100)
    print("  LO QUE EL CAMBIO SI DEBIA MOVER")
    print("=" * 100)
    antes = [f for f in filas if f["ts_open"] < ms(CORTE)]
    desp = [f for f in filas if f["ts_open"] >= ms(CORTE)]
    print(f"  antes: {len(antes)} senales   despues: {len(desp)}\n")
    if len(desp) < MIN_N:
        print("  Aun no hay bastantes senales cerradas despues del cambio.")
    else:
        print(f"  {'medida':<38} {'antes':>10} {'despues':>10} {'dif':>9}")
        def cmp(nombre, fn, sufijo="%"):
            a, b = fn(antes), fn(desp)
            print(f"  {nombre:<38} {a:>9.1f}{sufijo} {b:>9.1f}{sufijo} "
                  f"{b-a:>+8.1f}")
        cmp("SL mediano ofrecido",
            lambda L: float(np.median([abs(f["sl_pct"]) for f in L if f.get("sl_pct")])))
        cmp("senales con SL < 1% (dentro del ruido)",
            lambda L: 100*sum(1 for f in L if f.get("sl_pct") and abs(f["sl_pct"]) < 1)/len(L))
        cmp("saltan el stop",
            lambda L: 100*sum(1 for f in L if f["ms_sl"] is not None)/len(L))
        cmp("llegan a la meta (no deberia moverse)",
            lambda L: 100*sum(1 for f in L if f["gano"])/len(L))
        cmp("la COBRAN (deberia subir)",
            lambda L: 100*sum(1 for f in L if f["cobro"])/len(L))
        gan_a = [f for f in antes if f["gano"]]
        gan_d = [f for f in desp if f["gano"]]
        if gan_a and gan_d:
            cmp("de las ganadoras, el stop las saco antes",
                lambda L: 100*sum(1 for f in L if f["gano"] and f["ms_sl"] is not None
                                  and f["ms_sl"] < f["ms_up_32"])
                / max(sum(1 for f in L if f["gano"]), 1))

    # --- Y la advertencia ---
    print("\n" + "=" * 100)
    print("  EL MERCADO, QUE EXPLICA MAS QUE CUALQUIER CAMBIO NUESTRO")
    print("=" * 100)
    for etq, t0, t1 in tramos:
        med, up = regimen(t0, t1)
        if med is None:
            continue
        r = "ALCISTA" if med > 0.5 else "BAJISTA" if med < -0.5 else "PLANO"
        print(f"  {etq:<16} mediana {med:>+6.2f}%   suben {up:>3.0f}%   {r}")


if __name__ == "__main__":
    main()
