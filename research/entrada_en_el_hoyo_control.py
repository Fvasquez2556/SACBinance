# -*- coding: utf-8 -*-
"""
Dos controles sobre la simulacion de "entrar en el hoyo".

1. VALIDACION. La simulacion vuelve a recorrer las velas de 1m para decidir
   si cada senal toco su TP o su SL. Pero el sistema ya lo habia decidido en
   vivo y lo guardo en ms_tp / ms_sl. Si los dos no coinciden, la simulacion
   no vale nada. Aqui se comparan senal por senal y se explica cada
   diferencia.

2. LA COMBINACION. Las dos variables que separaron mejor fueron el tiempo que
   tarda el precio en bajar hasta el hoyo y el ancho del stop que pidio el
   sistema. Aqui se cruzan, con intervalo por bootstrap agrupado por par,
   para ver si el efecto sobrevive cuando se miran juntas.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

import entrada_en_el_hoyo as base

DB = base.DB
VENTANA_MS = base.VENTANA_MS


def pct(n, d):
    return f"{100*n/d:4.1f}%" if d else "   -"


def cargar(con, ult):
    seniales = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND ts_open >= "
        "(SELECT MIN(open_time) FROM klines WHERE tf='1m') ORDER BY ts_open")]
    datos = []
    for s in seniales:
        fin = min(s["ts_open"] + VENTANA_MS, ult)
        velas = list(con.execute(
            "SELECT open_time,o,h,l,c FROM klines WHERE symbol=? AND tf='1m' "
            "AND open_time BETWEEN ? AND ? ORDER BY open_time",
            (s["symbol"], s["ts_open"], fin)))
        if len(velas) < base.MIN_VELAS:
            continue
        o = base.evaluar(s, velas)
        o["completa"] = (fin - s["ts_open"]) >= VENTANA_MS * 0.95
        o["cerrado"] = s["cerrado"]
        # lo que el sistema decidio en vivo
        tp, sl = s["ms_tp"], s["ms_sl"]
        if tp is not None and (sl is None or tp < sl):
            o["vivo"] = "TP"
        elif sl is not None:
            o["vivo"] = "SL"
        else:
            o["vivo"] = "ABIERTA"
        datos.append(o)
    return datos


def validar(datos):
    print("=" * 96)
    print("1. ¿COINCIDE LA SIMULACION CON LO QUE EL SISTEMA MIDIO EN VIVO?")
    print("=" * 96)
    print()
    completas = [o for o in datos if o["completa"] and o["cerrado"]]
    print(f"  {len(datos)} senales simuladas, de las cuales {len(completas)} tienen")
    print(f"  la ventana de 24h entera y ya cerrada. Solo esas son comparables.")
    print()
    m = defaultdict(int)
    for o in completas:
        m[(o["vivo"], o["sistema"]["des"])] += 1
    print(f"  {'en vivo \\ simulado':<22} {'TP':>8} {'SL':>8} {'ABIERTA':>9}")
    for v in ("TP", "SL", "ABIERTA"):
        fila = f"  {v:<22}"
        for sm in ("TP", "SL", "ABIERTA"):
            fila += f"{m[(v, sm)]:>8}"
        print(fila)
    ok = sum(m[(v, v)] for v in ("TP", "SL", "ABIERTA"))
    print()
    print(f"  coinciden: {ok} de {len(completas)}  ({pct(ok, len(completas))})")

    disc = [o for o in completas if o["vivo"] != o["sistema"]["des"]]
    if disc:
        print()
        print(f"  las {len(disc)} discrepancias, por tipo:")
        tip = defaultdict(int)
        for o in disc:
            tip[f"{o['vivo']} en vivo -> {o['sistema']['des']} simulado"] += 1
        for k, v in sorted(tip.items(), key=lambda x: -x[1]):
            print(f"     {k:<34} {v:>5}")
        print()
        print("  muestra de 8:")
        print(f"     {'par':<16} {'emitida':<14} {'SL%':>7} {'TP%':>7} "
              f"{'vivo':>8} {'simulado':>10}")
        for o in disc[:8]:
            print(f"     {o['symbol']:<16} {base.gt(o['ts_open']):<14} "
                  f"{o['sl_pct']:>6.2f}% {o['tp_pct']:>6.2f}% "
                  f"{o['vivo']:>8} {o['sistema']['des']:>10}")

    # el efecto de las ventanas truncadas
    parciales = [o for o in datos if not o["completa"]]
    print()
    print(f"  ventanas truncadas (la senal aun no cumple 24h): {len(parciales)}")
    if parciales:
        tp = sum(1 for o in parciales if o["sistema"]["des"] == "TP")
        print(f"     de esas, {tp} ya tocaron el TP; el resto podria tocarlo aun.")
        print(f"     Por eso los grupos del 8-9 de sep subestiman los TP.")


def combinacion(datos, rng):
    entraron = [o for o in datos if o.get("entro")]
    print()
    print("=" * 96)
    print("2. LA COMBINACION: velocidad de la bajada x ancho del stop")
    print("=" * 96)
    print("  Se mide la media por operacion, con intervalo por bootstrap agrupado")
    print("  por par. Si el intervalo cruza el cero, no hay nada demostrado.")

    vel = [
        ("se desploma  <1h", lambda o: o["ms_disparo"] < 3600000),
        ("baja despacio >1h", lambda o: o["ms_disparo"] >= 3600000),
    ]
    anc = [
        ("stop estrecho <2%", lambda o: o["sl_pct"] > -2.0),
        ("stop ancho    >2%", lambda o: o["sl_pct"] <= -2.0),
    ]
    for regla in ("A", "C3"):
        print()
        print(f"  REGLA {regla}")
        print(f"     {'celda':<40} {'n':>5} {'TP':>7} {'media':>8} {'IC 95%':>20}")
        for ev, fv in vel:
            for ea, fa in anc:
                sub = [o for o in entraron if fv(o) and fa(o)]
                if len(sub) < 15:
                    print(f"     {ev+' + '+ea:<40} {len(sub):>5}   (pocas)")
                    continue
                res = [o[regla]["res"] for o in sub]
                par = [o["symbol"] for o in sub]
                tp = sum(1 for o in sub if o[regla]["des"] == "TP")
                lo, hi = base.boot_ci(res, par, rng)
                print(f"     {ev+' + '+ea:<40} {len(sub):>5} {pct(tp, len(sub)):>7} "
                      f"{np.mean(res):>7.2f}% [{lo:>6.2f}, {hi:>6.2f}]")

    # la mejor celda contra el resto, con la regla que gano
    print()
    print("  LA CELDA MEJOR CONTRA TODO LO DEMAS (regla C3)")
    buena = [o for o in entraron
             if o["ms_disparo"] >= 3600000 and o["sl_pct"] <= -2.0]
    resto = [o for o in entraron if o not in buena]
    for etq, grupo in (("celda buena", buena), ("todo lo demas", resto)):
        if len(grupo) < 15:
            continue
        res = [o["C3"]["res"] for o in grupo]
        par = [o["symbol"] for o in grupo]
        lo, hi = base.boot_ci(res, par, rng)
        m32 = sum(1 for o in grupo if o["C3"]["mfe"] >= base.META)
        print(f"     {etq:<20} n={len(grupo):>5}  media {np.mean(res):>6.2f}% "
              f"[{lo:>6.2f}, {hi:>6.2f}]   llegan a +3.2%: {pct(m32, len(grupo))}")

    # cuantas senales al dia serian
    if buena:
        dias = (max(o["ts_open"] for o in entraron)
                - min(o["ts_open"] for o in entraron)) / 86400000.0
        print()
        print(f"     eso son {len(buena)/max(dias,1e-9):.1f} operaciones al dia "
              f"sobre {dias:.1f} dias de datos")


def main():
    rng = np.random.default_rng(20260909)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    ult = con.execute("SELECT MAX(open_time) FROM klines WHERE tf='1m'").fetchone()[0]
    datos = cargar(con, ult)
    validar(datos)
    combinacion(datos, rng)


if __name__ == "__main__":
    main()
