# -*- coding: utf-8 -*-
"""
El pico exacto de cada senal de MARSCOIN, y que hizo despues.

Felix recuerda que la senal del 0.198 "cumplio el 3.2 y cumplio el TP del
sistema, y despues bajo". Este script traza el recorrido completo de cada
senal desde su entrada hasta el cierre de su ventana de 24h y responde tres
cosas con precision: hasta donde subio, a que hora, y cuanto se cayo despues.

Usa la mejor resolucion de vela disponible en cada tramo (1m si la hay, si no
5m, 15m o 1h), porque las velas de 1m no cubren los primeros dias. Los hitos
(-1%, +3.2%, TP, SL...) vienen del propio registro del sistema, que los midio
en vivo, no de las velas.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

DB = "data/sacbinance.db"
SYM = "MARSCOINUSDT"
TZ = -6


def gt(ms):
    return (dt.datetime.utcfromtimestamp(ms / 1000)
            + dt.timedelta(hours=TZ)).strftime("%d/%m %H:%M")


def dur(ms):
    m = int(round(ms / 60000))
    return f"{m//60}h{m%60:02d}m" if m >= 60 else f"{m}m"


HITOS = [
    ("ms_dn_1", "bajo -1%"), ("ms_dn_2", "bajo -2%"), ("ms_dn_32", "bajo -3.2%"),
    ("ms_dn_5", "bajo -5%"), ("ms_dn_10", "bajo -10%"),
    ("ms_up_1", "subio +1%"), ("ms_up_2", "subio +2%"),
    ("ms_up_32", "subio +3.2%  <- tu meta"), ("ms_up_42", "subio +4.2%"),
    ("ms_up_5", "subio +5%"), ("ms_up_10", "subio +10%"),
    ("ms_sl", "*** STOP ***"), ("ms_tp", "*** TP DEL SISTEMA ***"),
]


def mejor_max(con, desde, hasta):
    """Maximo real en la ventana, usando la vela mas fina disponible."""
    for tf in ("1m", "5m", "15m", "1h"):
        filas = list(con.execute(
            "SELECT open_time, h, l FROM klines WHERE symbol=? AND tf=? "
            "AND open_time BETWEEN ? AND ? ORDER BY open_time",
            (SYM, tf, desde, hasta)))
        # exigimos que la vela cubra al menos el 80% de la ventana
        if filas:
            paso = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}[tf] * 1000
            cubierto = len(filas) * paso
            if cubierto >= 0.8 * (hasta - desde):
                alto = max(filas, key=lambda r: r["h"])
                bajo = min(filas, key=lambda r: r["l"])
                return tf, alto, bajo, filas
    return None, None, None, []


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    seniales = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE symbol=? ORDER BY ts_open", (SYM,))]

    for i, s in enumerate(seniales, 1):
        # solo las que interesan: la del 0.198 y la de la madrugada
        if i not in (1, 4, 9, 10):
            continue
        s0 = s["ts_open"]
        e, tp, sl = s["entry"], s["take_profit"], s["stop_loss"]
        marca = "  (SOMBRA)" if s["sombra"] else ""
        print("=" * 88)
        print(f"SENAL {i} — {gt(s0)} GT{marca}")
        print("=" * 88)
        print(f"  entrada {e:.5f}   TP {tp:.5f} (+{s['tp_pct']:.2f}%)   "
              f"SL {sl:.5f} ({s['sl_pct']:.2f}%)")
        print()

        # --- la secuencia real, en orden cronologico -------------------
        print("  RECORRIDO (lo que el sistema midio en vivo)")
        eventos = [(s[k], etq) for k, etq in HITOS if s.get(k) is not None]
        eventos.append((s["ms_mfe"], f"PICO  {e*(1+s['mfe_pct']/100):.5f}  "
                                     f"({s['mfe_pct']:+.2f}%)"))
        eventos.append((s["ms_mae"], f"FONDO {e*(1+s['mae_pct']/100):.5f}  "
                                     f"({s['mae_pct']:+.2f}%)"))
        for t, etq in sorted(eventos):
            print(f"     {gt(s0+t)} GT   +{dur(t):>7}   {etq}")
        print()

        # --- el pico contra el TP -------------------------------------
        pico = e * (1 + s["mfe_pct"] / 100)
        falta = (tp - pico) / pico * 100
        print("  EL PICO CONTRA EL TAKE PROFIT")
        print(f"     lo mas alto que llego : {pico:.5f}   ({s['mfe_pct']:+.2f}%)")
        print(f"     el TP que pedia       : {tp:.5f}   (+{s['tp_pct']:.2f}%)")
        if s["ms_tp"] is not None:
            print(f"     -> LO PASO por {-falta:.2f}%")
        else:
            print(f"     -> SE QUEDO CORTO por {falta:.2f}%  "
                  f"({tp-pico:.5f} de diferencia). NO cumplio su TP.")
        print()

        # --- que hizo despues del pico --------------------------------
        t_pico = s0 + s["ms_mfe"]
        t_fin = s["ts_last"]
        tf, alto, bajo, filas = mejor_max(con, t_pico, t_fin)
        print("  DESPUES DEL PICO")
        if bajo is not None:
            caida = (bajo["l"] - pico) / pico * 100
            print(f"     desde el pico hasta el cierre de la ventana ({dur(t_fin-t_pico)}):")
            print(f"     cayo hasta {bajo['l']:.5f} el {gt(bajo['open_time'])} GT"
                  f"   =  {caida:.2f}% desde el pico")
            print(f"     (medido con velas de {tf})")
        else:
            print("     sin velas guardadas de ese tramo")
        print()

    # =================================================================
    print("=" * 88)
    print("RESUMEN: EL PICO DE CADA SENAL DE MARSCOIN")
    print("=" * 88)
    print(f"  {'#':>2} {'emitida':<14} {'entrada':>9} {'pico':>9} {'%':>8} "
          f"{'TP pedido':>10} {'?':>4} {'llego a +3.2%':>14}")
    for i, s in enumerate(seniales, 1):
        pico = s["entry"] * (1 + s["mfe_pct"] / 100)
        cumplio = "SI" if s["ms_tp"] is not None else "no"
        meta = dur(s["ms_up_32"]) if s["ms_up_32"] is not None else "nunca"
        print(f"  {i:>2} {gt(s['ts_open']):<14} {s['entry']:>9.5f} {pico:>9.5f} "
              f"{s['mfe_pct']:>7.2f}% {s['take_profit']:>10.5f} {cumplio:>4} "
              f"{meta:>14}")


if __name__ == "__main__":
    main()
