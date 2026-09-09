# -*- coding: utf-8 -*-
"""
MARSCOIN, solo la ventana que importa: 8-sep 20:00 GT -> 9-sep 11:00 GT.

Nada de dias anteriores. Quince horas, en tramos de 15 minutos, con todo lo
que ocurrio dentro marcado en su sitio: la senal del sistema, sus hitos, los
vetos, y las cinco alertas que Felix puso en Binance.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

DB = "data/sacbinance.db"
SYM = "MARSCOINUSDT"
TZ = -6

DESDE = "08/09 20:00:00"
HASTA = "09/09 11:00:00"

ALERTAS_FELIX = [
    ("09/09 02:25:16", "tu alerta  baja a 0.1345"),
    ("09/09 03:12:09", "tu alerta  sube +3.2%"),
    ("09/09 05:39:36", "tu alerta  baja a 0.1305"),
    ("09/09 09:28:48", "tu alerta  baja a 0.1246"),
    ("09/09 10:04:00", "tu alerta  sube a 0.1280"),
]


def gt(ms):
    return (dt.datetime.utcfromtimestamp(ms / 1000)
            + dt.timedelta(hours=TZ)).strftime("%d/%m %H:%M")


def hh(ms):
    return gt(ms)[6:]


def a_ms(txt):
    d = dt.datetime.strptime("2026/" + txt, "%Y/%d/%m %H:%M:%S")
    d = d - dt.timedelta(hours=TZ)
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    ini, fin = a_ms(DESDE), a_ms(HASTA)

    velas = list(con.execute(
        "SELECT open_time,o,h,l,c,v FROM klines WHERE symbol=? AND tf='1m' "
        "AND open_time BETWEEN ? AND ? ORDER BY open_time", (SYM, ini, fin)))

    # ---- eventos dentro de la ventana --------------------------------
    ev = []
    for a, txt in ALERTAS_FELIX:
        ev.append((a_ms(a), txt))
    for s in con.execute(
            "SELECT * FROM outcomes WHERE symbol=? ORDER BY ts_open", (SYM,)):
        s = dict(s)
        s0 = s["ts_open"]
        et = "sombra" if s["sombra"] else "REAL"
        if ini <= s0 <= fin:
            ev.append((s0, f"SENAL {et} entrada {s['entry']:.5f}  "
                           f"TP {s['take_profit']:.5f}  SL {s['stop_loss']:.5f}"))
        for k, nom in (("ms_sl", "STOP"), ("ms_tp", "TP del sistema"),
                       ("ms_up_32", "+3.2%"), ("ms_up_42", "+4.2%"),
                       ("ms_mfe", "PICO"), ("ms_mae", "FONDO")):
            if s[k] is not None and ini <= s0 + s[k] <= fin:
                ev.append((s0 + s[k], f"{nom} de la senal {et} de las {hh(s0)}"))
    for r in con.execute(
            "SELECT ts_ms, level, message FROM analysis_log WHERE symbol=? "
            "AND ts_ms BETWEEN ? AND ? AND level='VETO_ALERTA' ORDER BY ts_ms",
            (SYM, ini, fin)):
        ev.append((r["ts_ms"], f"VETO — {r['message']}"))

    porslot = {}
    for t, txt in ev:
        porslot.setdefault(t // 900000, []).append((t, txt))

    # ---- la tabla ----------------------------------------------------
    ref = velas[0]["o"]
    print("=" * 104)
    print(f"MARSCOIN — {DESDE[:5]} 20:00 GT  ->  {HASTA[:5]} 11:00 GT   "
          f"(precio de partida {ref:.5f})")
    print("=" * 104)
    print()
    print(f"  {'tramo':<7} {'abre':>9} {'max':>9} {'min':>9} {'cierra':>9} "
          f"{'vs 20:00':>9} {'vol':<14} eventos")

    slots = {}
    for v in velas:
        slots.setdefault(v["open_time"] // 900000, []).append(v)
    vmax = max(sum(x["v"] for x in g) for g in slots.values())

    for sl in sorted(slots):
        g = slots[sl]
        o, c = g[0]["o"], g[-1]["c"]
        hi = max(x["h"] for x in g)
        lo = min(x["l"] for x in g)
        vol = sum(x["v"] for x in g)
        barra = "#" * int(13 * vol / vmax)
        cab = f"  {hh(sl*900000):<7} {o:>9.5f} {hi:>9.5f} {lo:>9.5f} {c:>9.5f} " \
              f"{(c-ref)/ref*100:>8.2f}% {barra:<14}"
        lineas = porslot.get(sl, [])
        if not lineas:
            print(cab)
        else:
            for k, (t, txt) in enumerate(sorted(lineas)):
                pref = cab if k == 0 else " " * len(cab)
                print(f"{pref}{gt(t)[6:]}  {txt}")

    # ---- lo esencial -------------------------------------------------
    alto = max(velas, key=lambda v: v["h"])
    bajo = min(velas, key=lambda v: v["l"])
    print()
    print("=" * 104)
    print("  RESUMEN DE LA VENTANA")
    print("=" * 104)
    print(f"  precio a las 20:00 del 8 : {ref:.5f}")
    print(f"  minimo                   : {bajo['l']:.5f}  el {gt(bajo['open_time'])} GT"
          f"   ({(bajo['l']-ref)/ref*100:+.2f}% desde las 20:00)")
    print(f"  maximo                   : {alto['h']:.5f}  el {gt(alto['open_time'])} GT"
          f"   ({(alto['h']-ref)/ref*100:+.2f}% desde las 20:00)")
    print(f"  precio a las 11:00 del 9 : {velas[-1]['c']:.5f}"
          f"   ({(velas[-1]['c']-ref)/ref*100:+.2f}% desde las 20:00)")
    print()
    print(f"  del minimo al maximo     : "
          f"{(alto['h']-bajo['l'])/bajo['l']*100:+.2f}%   "
          f"en {int((alto['open_time']-bajo['open_time'])/60000)} minutos")
    print(f"  del maximo al cierre     : "
          f"{(velas[-1]['c']-alto['h'])/alto['h']*100:+.2f}%")


if __name__ == "__main__":
    main()
