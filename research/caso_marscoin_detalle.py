# -*- coding: utf-8 -*-
"""
El caso MARSCOIN, segunda parte: el minuto del pico, y que tan comun es.

La senal de las 01:52 GT del 9-sep toco su stop a los 32 minutos y 48 minutos
despues supero su propio take profit. Este script hace tres cosas:

  1. Imprime el minuto a minuto de esa hora y media, para ver la forma exacta.
  2. Mira el registro de analisis: que dijo el sistema entre el stop y el pico,
     y por que no volvio a avisar.
  3. Cuenta cuantas senales de toda la base hicieron lo mismo — tocar el stop
     y despues alcanzar su TP dentro de la misma ventana de 24h. Si es raro,
     MARSCOIN fue mala suerte; si es frecuente, el stop esta mal puesto.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

import numpy as np

DB = "data/sacbinance.db"
SYM = "MARSCOINUSDT"
TZ = -6


def gt(ms):
    return (dt.datetime.utcfromtimestamp(ms / 1000)
            + dt.timedelta(hours=TZ)).strftime("%d/%m %H:%M")


def a_ms(txt):
    d = dt.datetime.strptime("2026/" + txt, "%Y/%d/%m %H:%M:%S")
    d = d - dt.timedelta(hours=TZ)
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def dur(ms):
    m = int(ms / 60000)
    return f"{m//60}h{m%60:02d}m" if m >= 60 else f"{m}m"


def pct(n, d):
    return f"{100*n/d:.1f}%" if d else "-"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    s = dict(con.execute(
        "SELECT * FROM outcomes WHERE symbol=? AND ts_open>=? ORDER BY ts_open DESC LIMIT 1",
        (SYM, a_ms("09/09 00:00:00"))).fetchone())
    e, tp, sl = s["entry"], s["take_profit"], s["stop_loss"]

    # ==================================================================
    print("=" * 92)
    print("1. EL MINUTO A MINUTO: 01:50 -> 03:30 GT del 9-sep")
    print("=" * 92)
    print(f"  entrada {e:.5f}   TP {tp:.5f}   SL {sl:.5f}")
    print()
    print(f"  {'hora':<6} {'max':>9} {'min':>9} {'cierra':>9} {'desde entrada':>14} "
          f"{'volumen':>10}  ")
    ini, fin = a_ms("09/09 01:50:00"), a_ms("09/09 03:30:00")
    vmax = 0.0
    filas = list(con.execute(
        "SELECT open_time,o,h,l,c,v FROM klines WHERE symbol=? AND tf='1m' "
        "AND open_time BETWEEN ? AND ? ORDER BY open_time", (SYM, ini, fin)))
    for v in filas:
        vmax = max(vmax, v["v"])
    stop_visto = False
    for v in filas:
        h = (v["h"] - e) / e * 100
        l = (v["l"] - e) / e * 100
        nota = ""
        if not stop_visto and v["l"] <= sl:
            nota = "  <<< STOP"
            stop_visto = True
        elif v["h"] >= tp:
            nota = "  <<< pasa su TP"
        barra = "#" * int(24 * v["v"] / max(vmax, 1e-9))
        rango = f"{l:+.2f}% a {h:+.2f}%"
        print(f"  {gt(v['open_time'])[6:]:<6} {v['h']:>9.5f} {v['l']:>9.5f} "
              f"{v['c']:>9.5f} {rango:>14} {barra:<24}{nota}")

    # ==================================================================
    print()
    print("=" * 92)
    print("2. QUE HIZO EL SISTEMA ENTRE EL STOP Y EL PICO")
    print("=" * 92)
    cols = [r[1] for r in con.execute("PRAGMA table_info(analysis_log)")]
    print(f"  columnas del registro: {cols}")
    print()
    tcol = "ts_ms" if "ts_ms" in cols else "ts"
    reg = list(con.execute(
        f"SELECT * FROM analysis_log WHERE symbol=? AND {tcol} BETWEEN ? AND ? "
        f"ORDER BY {tcol}", (SYM, a_ms("09/09 01:40:00"), a_ms("09/09 04:00:00"))))
    if not reg:
        print("  Sin registro de analisis en esa franja.")
    for r in reg:
        d = dict(r)
        t = d.pop(tcol)
        resto = "  ".join(f"{k}={v}" for k, v in d.items()
                          if k != "symbol" and v not in (None, "", 0))
        print(f"  {gt(t)} GT  {resto}")

    # ==================================================================
    print()
    print("=" * 92)
    print("3. ¿CUANTAS SENALES TOCAN EL STOP Y DESPUES ALCANZAN SU TP?")
    print("=" * 92)
    print("  Sobre todas las senales cerradas y reales (sin sombra).")
    print("  'rescatada' = el stop salto, pero dentro de las mismas 24h el precio")
    print("  llego igual al take profit que la senal habia fijado.")
    print()
    filas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND cerrado=1")]
    n = len(filas)
    con_sl = [f for f in filas if f["ms_sl"] is not None
              and (f["ms_tp"] is None or f["ms_sl"] < f["ms_tp"])]
    rescatadas = [f for f in con_sl if f["ms_tp"] is not None]
    llego_meta = [f for f in con_sl if f["ms_up_32"] is not None
                  and f["ms_up_32"] > (f["ms_sl"] or 0)]
    print(f"  senales cerradas               {n:>6}")
    print(f"  tocaron su stop primero        {len(con_sl):>6}   {pct(len(con_sl), n)}")
    print(f"    y aun asi llegaron a su TP   {len(rescatadas):>6}   "
          f"{pct(len(rescatadas), len(con_sl))} de las que pararon")
    print(f"    y llegaron al +3.2% de Felix {len(llego_meta):>6}   "
          f"{pct(len(llego_meta), len(con_sl))} de las que pararon")
    if rescatadas:
        d = np.array([f["ms_tp"] - f["ms_sl"] for f in rescatadas]) / 60000.0
        print()
        print(f"  cuanto tardo el TP en llegar DESPUES del stop:")
        print(f"     mediana {np.median(d):.0f} min   p25 {np.percentile(d,25):.0f} min"
              f"   p75 {np.percentile(d,75):.0f} min")
        rapidas = int((d <= 60).sum())
        print(f"     en menos de 1 hora: {rapidas} de {len(d)} ({pct(rapidas, len(d))})")
        print()
        print("  las 10 mas rapidas en darse la vuelta:")
        orden = sorted(rescatadas, key=lambda f: f["ms_tp"] - f["ms_sl"])[:10]
        print(f"     {'par':<16} {'emitida':<14} {'SL':>8} {'TP':>8} "
              f"{'stop a los':>11} {'TP a los':>10} {'hueco':>8}")
        for f in orden:
            print(f"     {f['symbol']:<16} {gt(f['ts_open']):<14} "
                  f"{f['sl_pct']:>7.2f}% {f['tp_pct']:>7.2f}% "
                  f"{dur(f['ms_sl']):>11} {dur(f['ms_tp']):>10} "
                  f"{dur(f['ms_tp']-f['ms_sl']):>8}")

    # cuanto mas abajo habria hecho falta poner el stop
    print()
    print("  Si el stop hubiera estado mas abajo, ¿cuantas se salvaban?")
    print(f"     {'stop en':<10} {'sobreviven':>11} {'de las que hoy paran':>22}")
    for extra in (1.0, 1.5, 2.0, 3.0, 5.0):
        salvadas = sum(1 for f in rescatadas
                       if (f["mae_pct"] or 0) > f["sl_pct"] - extra)
        print(f"     {f'-{extra:.1f}% mas':<10} {salvadas:>11} {pct(salvadas, len(con_sl)):>22}")


if __name__ == "__main__":
    main()
