# -*- coding: utf-8 -*-
"""
KAT contra TAO: por que una subio y la otra no, y que vio el sistema.

Felix recuerda una "señal" de KAT con entrada 0.00617 que subio dos veces. El
sistema NO emitio ninguna señal de KATUSDT — ni una en toda su historia. Lo
que hubo fueron alertas de BASE Y REBOTE en el tablero y doce vetos seguidos
por "movimiento ya consumido". TAO, en cambio, si dio señales.

Este script pone las dos monedas en la misma linea de tiempo y compara lo que
el sistema medio en cada una, para responder tres cosas:

  1. ¿La forma que recuerda Felix en KAT es la que tuvo de verdad?
  2. ¿Que separo a KAT de TAO, si las dos aparecieron casi a la vez?
  3. ¿KAT tiene el patron de MARSCOIN, o es otro distinto?
"""
from __future__ import annotations

import datetime as dt
import sqlite3

DB = "data/sacbinance.db"
TZ = -6


def u(ms):
    return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%d/%m %H:%M")


def gt(ms):
    return (dt.datetime.utcfromtimestamp(ms / 1000)
            + dt.timedelta(hours=TZ)).strftime("%d/%m %H:%M")


def velas(con, sym, desde, hasta, tf="1m"):
    return list(con.execute(
        "SELECT open_time,o,h,l,c,v FROM klines WHERE symbol=? AND tf=? "
        "AND open_time BETWEEN ? AND ? ORDER BY open_time",
        (sym, tf, desde, hasta)))


def tramos(con, sym, desde, hasta, minutos=15):
    """Agrupa las velas de 1m en tramos, para poder leer 12 horas de un vistazo."""
    vs = velas(con, sym, desde, hasta)
    paso = minutos * 60000
    grupos = {}
    for v in vs:
        grupos.setdefault(v["open_time"] // paso, []).append(v)
    out = []
    for k in sorted(grupos):
        g = grupos[k]
        out.append({
            "t": k * paso, "o": g[0]["o"], "c": g[-1]["c"],
            "h": max(x["h"] for x in g), "l": min(x["l"] for x in g),
            "v": sum(x["v"] for x in g),
        })
    return out


def recorrido(con, sym, desde, hasta, umbral=3.0):
    """
    Los giros del precio: cada vez que se da la vuelta mas de `umbral` %.

    Un zigzag clasico. Se lleva un extremo movil y un sentido; cuando el precio
    retrocede `umbral` desde ese extremo, se apunta el giro y se cambia de
    sentido. La primera version tenia la comprobacion de vuelta guardada tras
    `modo != sentido_actual`, asi que no podia dispararse nunca y el recorrido
    salia con dos puntos.
    """
    vs = velas(con, sym, desde, hasta)
    if not vs:
        return []
    u_ = 1.0 + umbral / 100.0
    d_ = 1.0 - umbral / 100.0
    puntos = [(vs[0]["open_time"], vs[0]["o"], "inicio")]
    modo = None
    ext_t, ext_p = vs[0]["open_time"], vs[0]["o"]
    for v in vs:
        if modo != "baja":
            if v["h"] > ext_p:
                ext_t, ext_p = v["open_time"], v["h"]
                modo = "sube"
            elif modo == "sube" and v["l"] <= ext_p * d_:
                puntos.append((ext_t, ext_p, "techo"))
                modo = "baja"
                ext_t, ext_p = v["open_time"], v["l"]
        if modo != "sube":
            if v["l"] < ext_p:
                ext_t, ext_p = v["open_time"], v["l"]
                modo = "baja"
            elif modo == "baja" and v["h"] >= ext_p * u_:
                puntos.append((ext_t, ext_p, "suelo"))
                modo = "sube"
                ext_t, ext_p = v["open_time"], v["h"]
    puntos.append((ext_t, ext_p, "ultimo extremo"))
    return puntos


CONTEXTO = [
    ("retro_confirmado", "retroceso confirmado"),
    ("retro_caida_pct", "  caida previa"),
    ("retro_rebote_pct", "  rebote desde el suelo"),
    ("consumido_pct", "movimiento ya consumido"),
    ("fase_impulso", "fase del impulso"),
    ("fuerza_impulso", "fuerza del impulso"),
    ("atr_pct", "ATR"),
    ("ruido_1m_pct", "ruido 1m del par"),
    ("rango_1h_pct", "rango de la ultima hora"),
    ("pos_en_rango", "posicion en su rango"),
    ("dist_resistencia_pct", "distancia a resistencia"),
    ("rsi5", "RSI 5"),
    ("vol_ratio", "volumen vs mediana"),
    ("z_rise", "z de subida"),
    ("velocity", "velocidad"),
    ("btc_regime", "regimen BTC"),
    ("macro_gate_mult", "multiplicador macro"),
]


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    hoy = int(dt.datetime(2026, 9, 9, 6, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
    fin = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)

    # ==================================================================
    print("=" * 94)
    print("1. LO QUE EL SISTEMA HIZO CON CADA UNA")
    print("=" * 94)
    for sym in ("KATUSDT", "TAOUSDT"):
        n_out = con.execute("SELECT COUNT(*) FROM outcomes WHERE symbol=?",
                            (sym,)).fetchone()[0]
        vetos = con.execute(
            "SELECT COUNT(*) FROM analysis_log WHERE symbol=? AND level='VETO_ALERTA' "
            "AND ts_ms>?", (sym, hoy)).fetchone()[0]
        bases = con.execute(
            "SELECT COUNT(*) FROM analysis_log WHERE symbol=? AND level='BASE' "
            "AND ts_ms>?", (sym, hoy)).fetchone()[0]
        print(f"\n  {sym}")
        print(f"     señales emitidas en toda su historia : {n_out}")
        print(f"     vetos de alerta hoy                  : {vetos}")
        print(f"     alertas de BASE Y REBOTE hoy         : {bases}")
        if vetos:
            print("     motivos de los vetos:")
            for r in con.execute(
                    "SELECT message, COUNT(*) FROM analysis_log WHERE symbol=? "
                    "AND level='VETO_ALERTA' AND ts_ms>? GROUP BY "
                    "substr(message, instr(message,'—')) ORDER BY 2 DESC LIMIT 4",
                    (sym, hoy)):
                motivo = r[0].split("—", 1)[-1].strip()
                print(f"        {r[1]:>3}x  {motivo[:70]}")

    # ==================================================================
    print()
    print("=" * 94)
    print("2. EL RECORRIDO REAL DE KAT (giros de mas del 3%)")
    print("=" * 94)
    pts = recorrido(con, "KATUSDT", hoy, fin)
    if pts:
        base = pts[0][1]
        print(f"\n  {'hora UTC':<12} {'precio':>10} {'desde el anterior':>18} "
              f"{'desde el inicio':>16}  que fue")
        ant = None
        for t, p, etq in pts:
            d = f"{(p-ant)/ant*100:+.2f}%" if ant else "—"
            print(f"  {u(t):<12} {p:>10.6g} {d:>18} "
                  f"{(p-base)/base*100:>15.2f}%  {etq}")
            ant = p

    print()
    print("=" * 94)
    print("3. EL RECORRIDO REAL DE TAO (giros de mas del 3%)")
    print("=" * 94)
    pts = recorrido(con, "TAOUSDT", hoy, fin)
    if pts:
        base = pts[0][1]
        print(f"\n  {'hora UTC':<12} {'precio':>10} {'desde el anterior':>18} "
              f"{'desde el inicio':>16}  que fue")
        ant = None
        for t, p, etq in pts:
            d = f"{(p-ant)/ant*100:+.2f}%" if ant else "—"
            print(f"  {u(t):<12} {p:>10.6g} {d:>18} "
                  f"{(p-base)/base*100:>15.2f}%  {etq}")
            ant = p

    # ==================================================================
    print()
    print("=" * 94)
    print("4. EL CONTEXTO QUE MIDIO EL SISTEMA — TAO contra MARSCOIN")
    print("=" * 94)
    print("  KAT no aparece: sin señal, no hay fila de contexto que comparar.")
    print()
    filas = {}
    for etq, sql, args in (
        ("TAO 08:09", "SELECT * FROM outcomes WHERE symbol='TAOUSDT' AND ts_open>? "
                      "AND ts_open<? ORDER BY ts_open LIMIT 1",
         (hoy, hoy + 4 * 3600000)),
        ("TAO 20:33", "SELECT * FROM outcomes WHERE symbol='TAOUSDT' "
                      "ORDER BY ts_open DESC LIMIT 1", ()),
        ("MARSCOIN 07:52", "SELECT * FROM outcomes WHERE symbol='MARSCOINUSDT' "
                           "ORDER BY ts_open DESC LIMIT 1", ()),
    ):
        r = con.execute(sql, args).fetchone()
        if r:
            filas[etq] = dict(r)
    if filas:
        cab = f"  {'variable':<26}" + "".join(f"{k:>17}" for k in filas)
        print(cab)
        print("  " + "-" * (len(cab) - 2))
        for campo, nombre in CONTEXTO:
            linea = f"  {nombre:<26}"
            hay = False
            for k, f in filas.items():
                v = f.get(campo)
                if v is None:
                    linea += f"{'—':>17}"
                else:
                    hay = True
                    linea += f"{(f'{v:.2f}' if isinstance(v, float) else str(v)):>17}"
            if hay:
                print(linea)
        print()
        linea = f"  {'RESULTADO: MFE':<26}"
        for f in filas.values():
            linea += f"{f['mfe_pct']:>16.2f}%"
        print(linea)
        linea = f"  {'RESULTADO: MAE':<26}"
        for f in filas.values():
            linea += f"{f['mae_pct']:>16.2f}%"
        print(linea)


if __name__ == "__main__":
    main()
