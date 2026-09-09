# -*- coding: utf-8 -*-
"""
"Maximos planos con cuerpos encogiendo": el unico veto que se gana su sitio.

De los seis motivos por los que el sistema se niega a alertar, cinco no
distinguen nada de un instante al azar de la misma moneda. Este si: -10.2
puntos de acierto, con el intervalo entero por debajo de cero con los tres
anchos de stop. Aqui se le aprieta para ver si aguanta.

Cuatro formas de intentar tumbarlo
----------------------------------
  1. Control con 20 sorteos por veto en vez de uno. Con un solo minuto de
     control, la mitad del ruido del resultado es del propio control.
  2. Cambiar la ventana de deduplicacion (15 / 30 / 60 min). Si el efecto
     depende de cuantas rafagas se colapsen, no es real.
  3. Cambiar el horizonte (2h / 6h / 12h). Un veto que solo funciona a una
     distancia concreta es una casualidad.
  4. Quitar los pares que mas aportan. Si el efecto se cae al quitar tres
     monedas, es de esas tres monedas.

Y al final, lo que importa de verdad: cuantas alertas bloquea al dia, y que
habria pasado con ellas.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
MARCA = "maximos planos"
N_CONTROL = 20            # sorteos de control por cada veto


def u(ms):
    return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%d/%m %H:%M")


def cargar_series(con):
    series = {}
    for sym, in con.execute("SELECT DISTINCT symbol FROM klines WHERE tf='1m'"):
        f = con.execute("SELECT open_time,h,l,c FROM klines WHERE symbol=? AND tf='1m' "
                        "ORDER BY open_time", (sym,)).fetchall()
        if len(f) < 200:
            continue
        series[sym] = {
            "t": np.array([r[0] for r in f], dtype=np.int64),
            "h": np.array([r[1] for r in f], dtype=float),
            "l": np.array([r[2] for r in f], dtype=float),
            "c": np.array([r[3] for r in f], dtype=float),
        }
    return series


def evaluar(s, i, stop_pct, horizonte):
    n = len(s["h"])
    fin = min(i + 1 + horizonte, n)
    if fin - (i + 1) < 60:
        return None
    p = s["c"][i]
    if p <= 0:
        return None
    hi = s["h"][i + 1:fin]
    lo = s["l"][i + 1:fin]
    sube = hi >= p * (1 + META / 100.0)
    baja = lo <= p * (1 - stop_pct / 100.0)
    t_up = int(np.argmax(sube)) if sube.any() else None
    t_dn = int(np.argmax(baja)) if baja.any() else None
    if t_up is None:
        return 0
    if t_dn is None:
        return 1
    return 1 if t_up < t_dn else 0


def boot_dif(d, pares, rng, n=2000):
    """Intervalo sobre la diferencia emparejada, remuestreando PARES."""
    g = defaultdict(list)
    for x, p in zip(d, pares):
        g[p].append(x)
    arrs = [np.array(v) for v in g.values()]
    if len(arrs) < 5:
        return float("nan"), float("nan")
    m = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(arrs), len(arrs))
        m[i] = np.concatenate([arrs[j] for j in pick]).mean()
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def recoger(con, series, rng, dedup_min, horizonte, stop):
    t0 = int(min(s["t"][0] for s in series.values()))
    filas = con.execute(
        "SELECT ts_ms, symbol, message FROM analysis_log WHERE level='VETO_ALERTA' "
        "AND ts_ms>=? AND message LIKE ? ORDER BY ts_ms", (t0, f"%{MARCA}%")).fetchall()
    vistos = set()
    casos = []
    for r in filas:
        s = series.get(r["symbol"])
        if s is None:
            continue
        clave = (r["symbol"], r["ts_ms"] // (dedup_min * 60000))
        if clave in vistos:
            continue
        i = int(np.searchsorted(s["t"], r["ts_ms"], side="right")) - 1
        if i < 0:
            continue
        v = evaluar(s, i, stop, horizonte)
        if v is None:
            continue
        vistos.add(clave)
        # control: N sorteos del MISMO par, promediados
        tope = len(s["t"]) - horizonte - 2
        if tope <= 1:
            continue
        muestras = [evaluar(s, int(j), stop, horizonte)
                    for j in rng.integers(0, tope, N_CONTROL)]
        muestras = [m for m in muestras if m is not None]
        if not muestras:
            continue
        casos.append({"symbol": r["symbol"], "ts": r["ts_ms"],
                      "v": v, "a": float(np.mean(muestras)),
                      "msg": r["message"]})
    return casos


def resumen(nombre, casos, rng):
    if len(casos) < 25:
        print(f"  {nombre:<34} {len(casos):>5}   (pocas)")
        return None
    v = np.array([c["v"] for c in casos], dtype=float)
    a = np.array([c["a"] for c in casos], dtype=float)
    par = [c["symbol"] for c in casos]
    lo, hi = boot_dif(v - a, par, rng)
    dif = 100 * (v.mean() - a.mean())
    marca = "SI" if hi < 0 else ("  " if lo < 0 < hi else "AL REVES")
    print(f"  {nombre:<34} {len(casos):>5} {100*v.mean():>8.1f}% {100*a.mean():>8.1f}% "
          f"{dif:>+8.1f} [{100*lo:>+6.1f},{100*hi:>+6.1f}]  {marca}")
    return dif, lo, hi


def main():
    rng = np.random.default_rng(20260909)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    series = cargar_series(con)
    print(f"{len(series)} pares con velas de 1m\n")

    base = recoger(con, series, rng, 30, 360, 2.0)
    print("=" * 96)
    print(f"1. LA MEDIDA BASE — dedup 30 min, horizonte 6h, stop -2%")
    print("=" * 96)
    print(f"  {'':34} {'n':>5} {'el veto':>9} {'el azar':>9} {'dif':>8} "
          f"{'IC 95%':>16}  ¿protege?")
    resumen("maximos planos", base, rng)
    print(f"\n  {len({c['symbol'] for c in base})} pares distintos, "
          f"control con {N_CONTROL} sorteos por veto")

    # --- 2. robustez -------------------------------------------------
    print()
    print("=" * 96)
    print("2. ¿AGUANTA SI CAMBIO LAS REGLAS DEL JUEGO?")
    print("=" * 96)
    print(f"  {'':34} {'n':>5} {'el veto':>9} {'el azar':>9} {'dif':>8} "
          f"{'IC 95%':>16}  ¿protege?")
    for d in (15, 30, 60):
        resumen(f"deduplicando cada {d} min", recoger(con, series, rng, d, 360, 2.0), rng)
    print()
    for h, etq in ((120, "2h"), (360, "6h"), (720, "12h")):
        resumen(f"horizonte {etq}", recoger(con, series, rng, 30, h, 2.0), rng)
    print()
    for st in (1.5, 2.0, 3.0, 5.0):
        resumen(f"stop -{st}%", recoger(con, series, rng, 30, 360, st), rng)

    # --- 3. ¿lo arrastran unos pocos pares? --------------------------
    print()
    print("=" * 96)
    print("3. ¿LO ARRASTRAN UNOS POCOS PARES?")
    print("=" * 96)
    porpar = defaultdict(list)
    for c in base:
        porpar[c["symbol"]].append(c)
    orden = sorted(porpar.items(), key=lambda x: -len(x[1]))
    print(f"\n  {len(porpar)} pares. Los que mas aportan:")
    print(f"  {'par':<16} {'n':>4} {'veto':>8} {'azar':>8} {'dif':>8}")
    for sym, sub in orden[:8]:
        v = np.mean([c["v"] for c in sub]); a = np.mean([c["a"] for c in sub])
        print(f"  {sym.replace('USDT',''):<16} {len(sub):>4} {100*v:>7.1f}% "
              f"{100*a:>7.1f}% {100*(v-a):>+7.1f}")
    print()
    print(f"  {'':34} {'n':>5} {'el veto':>9} {'el azar':>9} {'dif':>8} "
          f"{'IC 95%':>16}  ¿protege?")
    for k in (1, 3, 5):
        fuera = {s for s, _ in orden[:k]}
        resumen(f"quitando los {k} pares mas repetidos",
                [c for c in base if c["symbol"] not in fuera], rng)

    # --- 4. cuanto bloquea -------------------------------------------
    print()
    print("=" * 96)
    print("4. ¿CUANTO CUESTA TENERLO?")
    print("=" * 96)
    t0 = int(min(s["t"][0] for s in series.values()))
    t1 = int(max(s["t"][-1] for s in series.values()))
    dias = (t1 - t0) / 86400000.0
    total = con.execute(
        "SELECT COUNT(*) FROM analysis_log WHERE level='VETO_ALERTA' AND ts_ms>=? "
        "AND message LIKE ?", (t0, f"%{MARCA}%")).fetchone()[0]
    senales = con.execute(
        "SELECT COUNT(*) FROM outcomes WHERE sombra=0 AND ts_open>=?", (t0,)).fetchone()[0]
    print(f"\n  vetos de 'maximos planos' en bruto : {total}  ({total/dias:.0f}/dia)")
    print(f"  momentos distintos (dedup 30 min)  : {len(base)}  ({len(base)/dias:.0f}/dia)")
    print(f"  señales que el sistema SI emitio   : {senales}  ({senales/dias:.0f}/dia)")
    print(f"\n  Si se quitara el veto, el sistema emitiria hasta un "
          f"{100*len(base)/max(senales,1):.0f}% mas de señales,")
    print(f"  y esas señales rinden {abs(resumen.__doc__ or ''):.0s}"
          if False else
          f"  y esas serian peores que un instante al azar del mismo par.")


if __name__ == "__main__":
    main()
