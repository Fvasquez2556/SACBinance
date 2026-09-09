# -*- coding: utf-8 -*-
"""
El caso MARSCOIN: reconstruccion minuto a minuto.

Felix recuerda dos cosas de esa noche pero sin hora exacta: una senal del
sistema cuyo stop se cumplio, y cinco alertas que el mismo puso en Binance.
Este script pone las dos series en la misma linea de tiempo, sobre las velas
de 1m que el sistema ya tenia guardadas, y comprueba si la memoria cuadra
con lo que realmente paso.

Todas las horas se imprimen en GT (UTC-6), que es lo que muestra su telefono.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys

DB = "data/sacbinance.db"
SYM = "MARSCOINUSDT"
TZ = -6

# Lo que Felix recuerda haber puesto en Binance, en hora GT del 9-sep.
# (hora, precio, sentido)
ALERTAS_FELIX = [
    ("09/09 02:25:16", 0.1345, "baja"),
    ("09/09 03:12:09", None, "sube +3.2%"),
    ("09/09 05:39:36", 0.1305, "baja"),
    ("09/09 09:28:48", 0.1246, "baja"),
    ("09/09 10:04:00", 0.1280, "sube"),
]


def gt(ms):
    return (dt.datetime.utcfromtimestamp(ms / 1000)
            + dt.timedelta(hours=TZ)).strftime("%d/%m %H:%M")


def gt_largo(ms):
    return (dt.datetime.utcfromtimestamp(ms / 1000)
            + dt.timedelta(hours=TZ)).strftime("%d/%m/%Y %H:%M GT")


def a_ms(txt):
    """'09/09 02:25:16' en GT -> epoch ms."""
    d = dt.datetime.strptime("2026/" + txt, "%Y/%d/%m %H:%M:%S")
    d = d - dt.timedelta(hours=TZ)
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def dur(ms):
    m = int(ms / 60000)
    return f"{m//60}h{m%60:02d}m" if m >= 60 else f"{m}m"


def velas(con, desde, hasta):
    return list(con.execute(
        "SELECT open_time, o, h, l, c, v FROM klines "
        "WHERE symbol=? AND tf='1m' AND open_time BETWEEN ? AND ? "
        "ORDER BY open_time", (SYM, desde, hasta)))


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    seniales = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE symbol=? ORDER BY ts_open", (SYM,))]

    # ==================================================================
    print("=" * 96)
    print(f"1. TODAS LAS SENALES QUE EL SISTEMA LANZO SOBRE {SYM}")
    print("=" * 96)
    print()
    cab = (f"  {'#':>2} {'emitida (GT)':<14} {'tier':<11} {'sc':>3} {'entrada':>9} "
           f"{'TP':>9} {'':>7} {'SL':>9} {'':>7} {'desenlace':<24} {'MFE':>7} {'MAE':>7}")
    print(cab)
    for i, s in enumerate(seniales, 1):
        tp, sl = s["ms_tp"], s["ms_sl"]
        if tp is not None and (sl is None or tp < sl):
            fin = f"TP {gt(s['ts_open']+tp)} ({dur(tp)})"
        elif sl is not None:
            fin = f"SL {gt(s['ts_open']+sl)} ({dur(sl)})"
        elif s["cerrado"]:
            fin = "ni TP ni SL en 24h"
        else:
            fin = "ventana aun abierta"
        marca = "   (sombra)" if s["sombra"] else ""
        tpp = "+%.2f%%" % s["tp_pct"]
        slp = "%.2f%%" % s["sl_pct"]
        print(f"  {i:>2} {gt(s['ts_open']):<14} {str(s['tier']):<11} {s['score']:>3.0f} "
              f"{s['entry']:>9.5f} {s['take_profit']:>9.5f} {tpp:>7} "
              f"{s['stop_loss']:>9.5f} {slp:>7} {fin:<24} "
              f"{(s['mfe_pct'] or 0):>6.2f}% {(s['mae_pct'] or 0):>6.2f}%{marca}")

    # ==================================================================
    print()
    print("=" * 96)
    print("2. LA SENAL QUE FELIX RECUERDA: 'entrada 0.198, TP +8%, SL +4%'")
    print("=" * 96)
    cand = [s for s in seniales if 7.5 <= s["tp_pct"] <= 9.0
            and -5.0 <= s["sl_pct"] <= -3.5]
    for s in cand:
        print()
        print(f"  Emitida el {gt_largo(s['ts_open'])}")
        print(f"     entrada  {s['entry']:.5f}")
        print(f"     TP       {s['take_profit']:.5f}   (+{s['tp_pct']:.2f}%)"
              f"   <-- el 0.198 que recordabas es ESTE, no la entrada")
        print(f"     SL       {s['stop_loss']:.5f}   ({s['sl_pct']:.2f}%)")
        if s["ms_sl"] is not None:
            print(f"     el stop se toco a los {dur(s['ms_sl'])}"
                  f"  ({gt_largo(s['ts_open']+s['ms_sl'])})")
        if s["ms_mae"]:
            print(f"     lo peor que llego a caer: {s['mae_pct']:.2f}% "
                  f"a los {dur(s['ms_mae'])}")
        print(f"     lo mejor que llego a subir: {s['mfe_pct']:.2f}%")

    # ==================================================================
    print()
    print("=" * 96)
    print("3. LO QUE PASO DE VERDAD, HORA POR HORA (8-sep 00:00 -> 9-sep 18:00 GT)")
    print("=" * 96)
    ini, fin = a_ms("08/09 00:00:00"), a_ms("09/09 18:00:00")
    vs = velas(con, ini, fin)
    if not vs:
        print("  Sin velas de 1m en esa ventana.")
        return
    marcas = {}
    for i, s in enumerate(seniales, 1):
        if ini <= s["ts_open"] <= fin:
            etq = f"SENAL {i}{' (sombra)' if s['sombra'] else ''} entrada {s['entry']:.5f}"
            marcas.setdefault(s["ts_open"] // 3600000, []).append(etq)
    for h, p, sentido in ALERTAS_FELIX:
        etq = f"alerta tuya {sentido}" + (f" {p:.4f}" if p else "")
        marcas.setdefault(a_ms(h) // 3600000, []).append(etq)

    porhora = {}
    for v in vs:
        porhora.setdefault(v["open_time"] // 3600000, []).append(v)
    print()
    print(f"  {'hora GT':<12} {'abre':>9} {'max':>9} {'min':>9} {'cierra':>9} "
          f"{'rango':>7}  eventos")
    for hh in sorted(porhora):
        g = porhora[hh]
        o, c = g[0]["o"], g[-1]["c"]
        hi = max(x["h"] for x in g)
        lo = min(x["l"] for x in g)
        rng = (hi - lo) / lo * 100
        ev = "  |  ".join(marcas.get(hh, []))
        print(f"  {gt(hh*3600000):<12} {o:>9.5f} {hi:>9.5f} {lo:>9.5f} {c:>9.5f} "
              f"{rng:>6.2f}%  {ev}")

    hi_v = max(vs, key=lambda v: v["h"])
    lo_v = min(vs, key=lambda v: v["l"])
    print()
    print(f"  techo de la ventana: {hi_v['h']:.5f} el {gt(hi_v['open_time'])}")
    print(f"  suelo de la ventana: {lo_v['l']:.5f} el {gt(lo_v['open_time'])}")
    print(f"  caida techo->suelo:  {(lo_v['l']-hi_v['h'])/hi_v['h']*100:.2f}%")

    # ==================================================================
    print()
    print("=" * 96)
    print("4. TUS CINCO ALERTAS, CONTRASTADAS CONTRA LAS VELAS")
    print("=" * 96)
    print("  Busco la vela del minuto que recuerdas, y ademas el primer cruce")
    print("  de ese nivel en toda la ventana.")
    print()
    for h, p, sentido in ALERTAS_FELIX:
        t = a_ms(h)
        v = [x for x in vs if x["open_time"] <= t < x["open_time"] + 60000]
        real = v[0] if v else None
        niv = f"nivel {p:.4f}" if p else "nivel relativo"
        print(f"  {h} GT   {sentido:<11} {niv}")
        if real:
            print(f"     vela de ese minuto:  max {real['h']:.5f}   "
                  f"min {real['l']:.5f}   cierra {real['c']:.5f}")
            if p:
                dentro = real["l"] <= p <= real["h"]
                print(f"     el nivel {p:.4f} {'SI' if dentro else 'NO'} estaba dentro "
                      f"del rango de ese minuto")
        else:
            print("     no hay vela guardada de ese minuto")
        if p:
            if sentido.startswith("baja"):
                cruce = next((x for x in vs if x["l"] <= p), None)
            else:
                cruce = next((x for x in vs if x["h"] >= p), None)
            if cruce:
                print(f"     primer cruce de {p:.4f} en la ventana: "
                      f"{gt(cruce['open_time'])} GT")
        print()

    # ==================================================================
    print("=" * 96)
    print("5. LAS SENALES DE ESA NOCHE, MINUTO A MINUTO")
    print("=" * 96)
    viva = [s for s in seniales if s["ts_open"] >= ini]
    for s in viva:
        s0 = s["ts_open"]
        vv = velas(con, s0, s0 + 24 * 3600000)
        if not vv:
            continue
        e, tp, sl = s["entry"], s["take_profit"], s["stop_loss"]
        print()
        sombra = "   (SOMBRA: no se aviso por Telegram)" if s["sombra"] else ""
        print(f"  --- Senal del {gt_largo(s0)}{sombra} ---")
        print(f"      entrada {e:.5f}   TP {tp:.5f} (+{s['tp_pct']:.2f}%)   "
              f"SL {sl:.5f} ({s['sl_pct']:.2f}%)")
        print(f"      tier {s['tier']}   score {s['score']:.0f}   "
              f"estado {s['display_state']}")
        hitos = [(-0.4, "baja -0.4%"), (-0.9, "baja -0.9%"), (-1.8, "baja -1.8%"),
                 (2.2, "sube +2.2%"), (3.2, "META +3.2%"), (4.2, "SUPERA +4.2%")]
        vistos = []
        pend = list(hitos)
        for v in vv:
            for hh in list(pend):
                pc, etq = hh
                if pc < 0:
                    golpe = (v["l"] - e) / e * 100 <= pc
                else:
                    golpe = (v["h"] - e) / e * 100 >= pc
                if golpe:
                    vistos.append((v["open_time"], etq))
                    pend.remove(hh)
            if v["l"] <= sl:
                vistos.append((v["open_time"], f"*** STOP {sl:.5f} ***"))
                break
            if v["h"] >= tp:
                vistos.append((v["open_time"], f"*** TP {tp:.5f} ***"))
                break
        for t, etq in vistos:
            print(f"      {gt(t)} GT   +{dur(t-s0):>7}   {etq}")
        if not vistos:
            print("      no cruzo ningun hito")


if __name__ == "__main__":
    sys.exit(main())
