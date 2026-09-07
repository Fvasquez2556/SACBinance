# -*- coding: utf-8 -*-
"""
Cuantos avisos al dia saldrian con cada criterio, y si valdria la pena recibirlos.

Una notificacion que suena 40 veces al dia se silencia el primer dia. La
pregunta no es solo "¿que criterio acierta mas?" sino "¿cuantas veces suena?".
Las dos cosas juntas, o la funcion no sirve.

Para cada señal real emitida se reconstruye, con las velas 1m de ese instante,
si cumplia el patron validado (caida >=2%) y si el rebote estaba confirmado
(>=1% desde el suelo). Eso no esta guardado en la base porque el detector es
de hoy, asi que hay que recalcularlo hacia atras.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
ZONA = 8           # velas 1m donde se busca el suelo
LOOKBACK = 40      # velas previas donde se busca el pico
CAIDA_MIN = 2.0
REBOTE_MIN = 1.0
MIN_N = 15


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    kl = defaultdict(list)
    for sym, t, h, l, c in con.execute(
            "SELECT symbol, open_time, h, l, c FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        kl[sym].append((t, h, l, c))
    kl = {s: np.array(v, dtype=np.float64) for s, v in kl.items()}

    filas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND entry IS NOT NULL "
        "ORDER BY ts_open")]
    if not filas:
        print("sin datos")
        return

    span_h = (filas[-1]["ts_open"] - filas[0]["ts_open"]) / 3600_000
    dias = max(span_h / 24.0, 0.01)
    print(f"{len(filas)} señales reales en {span_h:.1f}h ({dias:.2f} dias)")
    print(f"ritmo actual: {len(filas)/dias:.0f} señales al dia\n")

    # Reconstruir el patron en el instante de cada emision
    for f in filas:
        a = kl.get(f["symbol"])
        f["patron"] = f["confirmado"] = False
        if a is None:
            continue
        i = int(np.searchsorted(a[:, 0], f["ts_open"], side="right")) - 1
        if i < ZONA + LOOKBACK:
            continue
        seg = a[i - ZONA + 1:i + 1]
        prev = a[i - ZONA - LOOKBACK + 1:i - ZONA + 1]
        pico = prev[:, 1].max()
        suelo = seg[:, 2].min()
        if pico <= 0 or suelo <= 0:
            continue
        caida = (suelo - pico) / pico * 100.0
        rebote = (a[i, 3] - suelo) / suelo * 100.0
        f["patron"] = caida <= -CAIDA_MIN
        f["confirmado"] = f["patron"] and rebote >= REBOTE_MIN

    def evalua(nombre, cond):
        sel = [f for f in filas if cond(f)]
        n = len(sel)
        if n == 0:
            print(f"  {nombre:<44}   0 avisos")
            return
        cerr = [f for f in sel if f["cerrado"]]
        v = sum(1 for f in cerr if f["ms_up_32"] is not None)
        # cobrable: llega a la meta antes de caer -1.2%
        cob = sum(1 for f in cerr
                  if f["ms_up_32"] is not None
                  and (f["ms_dn_12"] is None or f["ms_dn_12"] > f["ms_up_32"]))
        por_dia = n / dias
        if len(cerr) < MIN_N:
            print(f"  {nombre:<44} {por_dia:5.1f}/dia   "
                  f"(pocas cerradas: {len(cerr)})")
            return
        print(f"  {nombre:<44} {por_dia:5.1f}/dia   "
              f"llega {100*v/len(cerr):5.1f}%   cobra {100*cob/len(cerr):5.1f}%   "
              f"n={len(cerr)}")

    print("=" * 100)
    print("VOLUMEN DE AVISOS Y CALIDAD, POR CRITERIO")
    print("=" * 100)
    print(f"  {'criterio':<44} {'ritmo':>9}   {'llega a +3.2%':>13}   "
          f"{'lo cobra':>10}")
    evalua("todas las señales", lambda f: True)
    evalua("tier FUERTE o EXTRA-FUERTE",
           lambda f: f["tier"] in ("FUERTE", "EXTRA-FUERTE"))
    evalua("score >= 75", lambda f: (f["score"] or 0) >= 75)
    evalua("patron: viene de caer >=2%", lambda f: f["patron"])
    evalua("patron CONFIRMADO (rebote >=1%)", lambda f: f["confirmado"])
    evalua("TP ofrecido >= 3.2% (llega a tu meta)",
           lambda f: (f["tp_pct"] or 0) >= META)
    print()
    evalua("confirmado + tier fuerte",
           lambda f: f["confirmado"] and f["tier"] in ("FUERTE", "EXTRA-FUERTE"))
    evalua("confirmado + score>=75",
           lambda f: f["confirmado"] and (f["score"] or 0) >= 75)
    evalua("confirmado + TP>=3.2%",
           lambda f: f["confirmado"] and (f["tp_pct"] or 0) >= META)
    evalua("confirmado + score>=75 + vol24h>=2M",
           lambda f: (f["confirmado"] and (f["score"] or 0) >= 75
                      and (f["vol_24h"] or 0) >= 2e6))
    evalua("confirmado + score>=75 + TP>=3.2% + vol>=2M",
           lambda f: (f["confirmado"] and (f["score"] or 0) >= 75
                      and (f["tp_pct"] or 0) >= META
                      and (f["vol_24h"] or 0) >= 2e6))
    print()
    evalua("score>=75 + TP>=3.2% + vol24h>=2M (sin patron)",
           lambda f: ((f["score"] or 0) >= 75 and (f["tp_pct"] or 0) >= META
                      and (f["vol_24h"] or 0) >= 2e6))

    print("\n  'llega' = el precio alcanzo +3.2% en las 24h de seguimiento.")
    print("  'cobra' = lo alcanzo ANTES de caer a -1.2%, que es lo que")
    print("  distingue un aviso util de uno que te mete en un retroceso.")


if __name__ == "__main__":
    main()
