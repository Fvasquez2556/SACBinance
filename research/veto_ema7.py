# -*- coding: utf-8 -*-
"""
¿Acierta el veto de la EMA7? Medido sobre toda la base, con control.

En IOST el 9-sep, el veto "precio bajo la EMA7 en N TFs" salto 20 veces y en
el 65% de ellas el precio habria llegado a +3.2% antes que a un stop del 2%.
Eso es una moneda y un dia. Aqui se mide sobre todos los vetos guardados.

Como se mide, y por que asi
---------------------------
Un veto no se juzga por lo que hizo el precio despues — se juzga contra lo que
habria pasado en un instante CUALQUIERA de esa misma moneda. Los vetos saltan
en monedas nerviosas y en momentos agitados; sin control, cualquier motivo
parece que "acierta" o "falla" solo por la volatilidad del par.

Por eso, por cada veto conservado se sortea un minuto al azar del MISMO par
dentro de la misma ventana de datos, y se le aplica la misma prueba. La
diferencia entre los dos es lo unico que dice algo.

Tres decisiones mas, todas para no engañarse:

  - Los vetos llegan en rafagas: veinte seguidos del mismo par en veinte
    minutos no son veinte observaciones. Se conserva uno por par, motivo y
    tramo de 30 minutos.
  - El intervalo se calcula con bootstrap agrupado POR PAR, no por veto.
  - Solo cuentan los vetos con velas de 1m suficientes por delante.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2               # el objetivo de Felix
HORIZONTE_MIN = 360      # 6 horas
STOPS = (1.5, 2.0, 3.0)
DEDUP_MIN = 30           # un veto por par, motivo y tramo de 30 min
MIN_N = 25


def u(ms):
    return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%d/%m %H:%M")


def motivo_normal(msg: str) -> str:
    """El motivo sin sus numeros, para poder agrupar."""
    m = msg.split("—", 1)[-1].strip()
    m = re.sub(r"[\d.]+", "N", m)
    return m[:44]


# Los vetos de contabilidad no juzgan la calidad de la señal: dicen que ya hay
# una alerta viva del par o que esta en cooldown. Mezclarlos con los de calidad
# hunde cualquier medicion, porque son la mayoria.
CONTABLES = ("ya hay una alerta viva", "cooldown", "STALE", "expirada")


def familia(m: str) -> str:
    if any(x in m for x in CONTABLES):
        return "(contable)"
    if "EMA" in m:
        return "EMA7"
    if "consumido" in m:
        return "consumido"
    if "ya recorrido" in m:
        return "ya recorrido"
    if "maximos planos" in m:
        return "maximos planos"
    if "RSI" in m:
        return "RSI+MACD"
    if "DESACELERANDO" in m:
        return "desacelerando"
    return "otros"


def evaluar(hi, lo, cl, i, stop_pct):
    n = len(hi)
    fin = min(i + 1 + HORIZONTE_MIN, n)
    if fin - (i + 1) < 60:
        return None
    p = cl[i]
    if p <= 0:
        return None
    techo = p * (1 + META / 100.0)
    suelo = p * (1 - stop_pct / 100.0)
    seg_hi = hi[i + 1:fin]
    seg_lo = lo[i + 1:fin]
    t_up = np.argmax(seg_hi >= techo) if (seg_hi >= techo).any() else None
    t_dn = np.argmax(seg_lo <= suelo) if (seg_lo <= suelo).any() else None
    if t_up is None and t_dn is None:
        return 0                     # ni una cosa ni otra: no cobra
    if t_dn is None:
        return 1
    if t_up is None:
        return 0
    return 1 if t_up < t_dn else 0


def boot_dif(v, a, pares, rng, n=2000):
    """
    Intervalo sobre la DIFERENCIA veto - azar, emparejada caso a caso.

    Comparar dos intervalos por separado y ver si se solapan no responde la
    pregunta: lo que hay que acotar es la diferencia. Cada caso lleva su propio
    control del mismo par, asi que la resta se hace dentro del par y el
    remuestreo va por par, que es la unidad que se repite.
    """
    d = np.asarray(v, dtype=float) - np.asarray(a, dtype=float)
    g = defaultdict(list)
    for x, p in zip(d, pares):
        g[p].append(x)
    arrs = [np.array(x) for x in g.values()]
    if len(arrs) < 5:
        return float("nan"), float("nan")
    m = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(arrs), len(arrs))
        m[i] = np.concatenate([arrs[j] for j in pick]).mean()
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def boot_ci(x, pares, rng, n=2000):
    if len(x) < 10:
        return float("nan"), float("nan")
    g = defaultdict(list)
    for v, p in zip(x, pares):
        g[p].append(v)
    arrs = [np.array(v, dtype=float) for v in g.values()]
    m = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(arrs), len(arrs))
        m[i] = np.concatenate([arrs[j] for j in pick]).mean()
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def main():
    rng = np.random.default_rng(20260909)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # --- velas de 1m, por par ---------------------------------------
    series = {}
    for sym, in con.execute("SELECT DISTINCT symbol FROM klines WHERE tf='1m'"):
        filas = con.execute(
            "SELECT open_time,h,l,c FROM klines WHERE symbol=? AND tf='1m' "
            "ORDER BY open_time", (sym,)).fetchall()
        if len(filas) < 120:
            continue
        series[sym] = {
            "t": np.array([r[0] for r in filas], dtype=np.int64),
            "h": np.array([r[1] for r in filas], dtype=float),
            "l": np.array([r[2] for r in filas], dtype=float),
            "c": np.array([r[3] for r in filas], dtype=float),
        }
    # int() a proposito: sqlite3 enlaza un numpy.int64 sin protestar y devuelve
    # CERO filas en vez de lanzar. La primera version de este script decia
    # "0 vetos" con 12.048 en la tabla.
    t0 = int(min(s["t"][0] for s in series.values()))
    t1 = int(max(s["t"][-1] for s in series.values()))
    print(f"{len(series)} pares con velas de 1m, de {u(t0)} a {u(t1)} UTC")

    # --- vetos --------------------------------------------------------
    vetos = con.execute(
        "SELECT ts_ms, symbol, message FROM analysis_log "
        "WHERE level='VETO_ALERTA' AND ts_ms>=? ORDER BY ts_ms", (t0,)).fetchall()
    print(f"{len(vetos)} vetos con velas que los cubren\n")

    vistos = set()
    casos = []
    for r in vetos:
        s = series.get(r["symbol"])
        if s is None:
            continue
        m = motivo_normal(r["message"])
        fam = familia(m)
        clave = (r["symbol"], fam, r["ts_ms"] // (DEDUP_MIN * 60000))
        if clave in vistos:
            continue
        i = int(np.searchsorted(s["t"], r["ts_ms"], side="right")) - 1
        if i < 0 or i >= len(s["t"]) - 1:
            continue
        res = {st: evaluar(s["h"], s["l"], s["c"], i, st) for st in STOPS}
        if res[2.0] is None:
            continue
        vistos.add(clave)
        # control: un minuto al azar del MISMO par
        j = int(rng.integers(0, len(s["t"]) - HORIZONTE_MIN - 2))
        ctrl = {st: evaluar(s["h"], s["l"], s["c"], j, st) for st in STOPS}
        casos.append({"symbol": r["symbol"], "fam": fam, "motivo": m,
                      "ts": r["ts_ms"], "res": res, "ctrl": ctrl})

    print(f"{len(casos)} vetos tras deduplicar por par/motivo/{DEDUP_MIN}min")
    print(f"   pares distintos: {len({c['symbol'] for c in casos})}\n")

    # --- resultado por familia ---------------------------------------
    print("=" * 100)
    print(f"¿HABRIA LLEGADO A +{META}% ANTES QUE AL STOP? — veto contra azar del mismo par")
    print("=" * 100)
    for st in STOPS:
        print(f"\n  STOP -{st}%")
        print(f"  {'motivo del veto':<20} {'n':>5} {'el veto':>9} {'el azar':>9} "
              f"{'dif':>8} {'IC 95% de la dif':>16}  lectura")
        fams = defaultdict(list)
        for c in casos:
            if c["res"][st] is not None and c["ctrl"][st] is not None:
                fams[c["fam"]].append(c)
        orden = sorted(fams.items(), key=lambda x: -len(x[1]))
        todos = [c for v in fams.values() for c in v]
        for nombre, sub in [("TODOS", todos)] + orden:
            if len(sub) < MIN_N:
                print(f"  {nombre:<20} {len(sub):>5}   (pocas)")
                continue
            v = [c["res"][st] for c in sub]
            a = [c["ctrl"][st] for c in sub]
            par = [c["symbol"] for c in sub]
            pv, pa = 100 * np.mean(v), 100 * np.mean(a)
            dlo, dhi = boot_dif(v, a, par, rng)
            dif = pv - pa
            # Solo se afirma algo si el intervalo de la DIFERENCIA no toca cero.
            if dlo != dlo:
                lec = "sin intervalo"
            elif dlo > 0:
                lec = "TIRA señales buenas"
            elif dhi < 0:
                lec = "protege de verdad"
            else:
                lec = "no distingue"
            print(f"  {nombre:<20} {len(sub):>5} {pv:>8.1f}% {pa:>8.1f}% "
                  f"{dif:>+8.1f} [{100*dlo:>+6.1f},{100*dhi:>+6.1f}]  {lec}")

    # --- ¿lo arrastra un solo par? -----------------------------------
    print()
    print("=" * 100)
    print("EL VETO DE LA EMA7, PAR POR PAR (stop -2%)")
    print("=" * 100)
    ema = [c for c in casos if c["fam"] == "EMA7" and c["res"][2.0] is not None]
    porpar = defaultdict(list)
    for c in ema:
        porpar[c["symbol"]].append(c)
    print(f"  {len(ema)} vetos de EMA7 en {len(porpar)} pares\n")
    print(f"  {'par':<16} {'n':>4} {'el veto':>9} {'el azar':>9} {'diferencia':>11}")
    for sym, sub in sorted(porpar.items(), key=lambda x: -len(x[1]))[:12]:
        if len(sub) < 4:
            continue
        pv = 100 * np.mean([c["res"][2.0] for c in sub])
        pa = 100 * np.mean([c["ctrl"][2.0] for c in sub])
        print(f"  {sym.replace('USDT',''):<16} {len(sub):>4} {pv:>8.1f}% {pa:>8.1f}% {pv-pa:>+10.1f}")
    if len(porpar) > 3:
        cuantos = [len(v) for v in porpar.values()]
        print(f"\n  el par mas repetido aporta {max(cuantos)} de {len(ema)} "
              f"({100*max(cuantos)/len(ema):.0f}%)")

    # --- el detalle de los mensajes de EMA7 ---------------------------
    print()
    print("  variantes del mensaje:")
    var = defaultdict(list)
    for c in ema:
        var[c["motivo"]].append(c["res"][2.0])
    for m, v in sorted(var.items(), key=lambda x: -len(x[1])):
        if len(v) >= 8:
            print(f"     {m:<46} {len(v):>4} {100*np.mean(v):>7.1f}%")


if __name__ == "__main__":
    main()
