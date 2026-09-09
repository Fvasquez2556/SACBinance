# -*- coding: utf-8 -*-
"""
Entrar en el hoyo: las variantes exactas que pidio Felix.

Se entra cuando el precio baja a un pelo POR ENCIMA del stop que el sistema
calculo, y desde esa entrada nueva se colocan los niveles. Lo que cambia entre
variantes es a que distancia se pone el disparo y donde se pone el objetivo.

El disparo — cuanto por encima del SL del sistema se entra:
    0.5%   la que ya esta midiendose en sombra desde el 9-sep
    0.6%
    1.0%

El stop, igual en todas: el MISMO PORCENTAJE que el sistema pedia, pero medido
desde la entrada nueva. Si el sistema dijo -1.4% desde su entrada, aqui va
-1.4% desde el hoyo. Es la unica forma de que el riesgo sea el que el sistema
calculo para ese par y no un numero inventado.

El objetivo — cuatro formas, y no dan lo mismo:
    TP%     el porcentaje de TP del sistema, desde la entrada nueva
    +3.2%   el objetivo de Felix, desde la entrada nueva
    TPprec  el TP del sistema como PRECIO, el que fijo al dar la señal.
            Como se entra mas abajo, ese precio queda mas lejos en % — es el
            objetivo mas ambicioso de los tres.
    sin TP  aguantar las 24h y cerrar donde este, para ver cuanto del
            resultado viene del objetivo y cuanto de la deriva.

Como se lee cada tasa de acierto
--------------------------------
Un % de acierto no significa nada sin su linea base geometrica. Para un paseo
aleatorio, P(tocar +A antes que -B) = B/(A+B). Cada variante tiene su propia
A y su propia B, asi que cada una tiene su propia linea base — y comparar dos
variantes por su % de acierto sin corregir eso es comparar dos geometrias, no
dos estrategias.

Supuestos, todos del lado malo: el fill se anota al precio del disparo (nunca
mejor); si una vela contiene el disparo y el stop, se cuenta parada; si
contiene el stop y el objetivo, se cuenta parada.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
VENTANA_MS = 24 * 3600 * 1000
META = 3.2
MARGENES = (0.5, 0.6, 1.0)
MIN_VELAS = 60


def u(ms):
    return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%d/%m %H:%M")


def pct(n, d):
    return f"{100*n/d:4.1f}%" if d else "   -"


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


def simular(velas, desde, fill, stop, techo):
    """(desenlace, resultado_pct, mfe, mae). techo None = aguantar la ventana."""
    mfe = mae = 0.0
    for k in range(desde, len(velas)):
        v = velas[k]
        mfe = max(mfe, (v["h"] - fill) / fill * 100.0)
        mae = min(mae, (v["l"] - fill) / fill * 100.0)
        if v["l"] <= stop:
            return "SL", (stop - fill) / fill * 100.0, mfe, mae
        if techo is not None and v["h"] >= techo:
            return "TP", (techo - fill) / fill * 100.0, mfe, mae
    fin = velas[-1]["c"]
    return "ABIERTA", (fin - fill) / fill * 100.0, mfe, mae


def objetivos(fill, s):
    """Los cuatro techos, en precio. None = sin objetivo."""
    return {
        "TP%": fill * (1 + s["tp_pct"] / 100.0) if s["tp_pct"] else None,
        "+3.2%": fill * (1 + META / 100.0),
        "TPprec": s["take_profit"],
        "sin TP": None,
    }


def main():
    rng = np.random.default_rng(20260909)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    prim = con.execute("SELECT MIN(open_time) FROM klines WHERE tf='1m'").fetchone()[0]
    ult = con.execute("SELECT MAX(open_time) FROM klines WHERE tf='1m'").fetchone()[0]
    print(f"velas de 1m: {u(prim)} -> {u(ult)} UTC\n")

    seniales = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND ts_open>=? AND stop_loss>0 "
        "AND tp_pct IS NOT NULL AND sl_pct<0 ORDER BY ts_open", (prim,))]

    datos = []
    for s in seniales:
        fin = min(s["ts_open"] + VENTANA_MS, ult)
        velas = list(con.execute(
            "SELECT open_time,h,l,c FROM klines WHERE symbol=? AND tf='1m' "
            "AND open_time BETWEEN ? AND ? ORDER BY open_time",
            (s["symbol"], s["ts_open"], fin)))
        if len(velas) < MIN_VELAS:
            continue
        fila = {"symbol": s["symbol"], "ts": s["ts_open"], "tp_pct": s["tp_pct"],
                "sl_pct": s["sl_pct"], "entry": s["entry"],
                "completa": (fin - s["ts_open"]) >= VENTANA_MS * 0.95}
        # el sistema tal cual, como referencia
        d, r, mfe, mae = simular(velas, 0, s["entry"], s["stop_loss"], s["take_profit"])
        fila["sistema"] = {"des": d, "res": r}
        for m in MARGENES:
            disparo = s["stop_loss"] * (1 + m / 100.0)
            idx = next((k for k, v in enumerate(velas) if v["l"] <= disparo), None)
            if idx is None:
                fila[m] = None
                continue
            fill = disparo
            stop = fill * (1 + s["sl_pct"] / 100.0)
            res = {}
            for nom, techo in objetivos(fill, s).items():
                if techo is not None and techo <= fill:
                    res[nom] = None          # objetivo ya rebasado: no aplica
                    continue
                d, r, mfe, mae = simular(velas, idx, fill, stop, techo)
                dist_tp = (techo - fill) / fill * 100.0 if techo else None
                res[nom] = {"des": d, "res": r, "mfe": mfe, "mae": mae,
                            "dist_tp": dist_tp}
            fila[m] = {"fill": fill, "idx": idx, "stop_pct": s["sl_pct"], "obj": res,
                       "ms": velas[idx]["open_time"] - s["ts_open"]}
        datos.append(fila)

    print(f"{len(datos)} señales simuladas, {len({d['symbol'] for d in datos})} pares\n")

    # ---- cuantas entran con cada disparo ----------------------------
    print("=" * 104)
    print("1. ¿CUANTAS VECES SE LLEGA A ENTRAR?")
    print("=" * 104)
    print(f"\n  {'disparo':<26} {'entran':>8} {'%':>8} {'tarda (mediana)':>18}")
    for m in MARGENES:
        ent = [d for d in datos if d.get(m)]
        t = np.median([d[m]["ms"] for d in ent]) / 60000 if ent else 0
        print(f"  SL +{m:.1f}%{'':<18} {len(ent):>8} {pct(len(ent), len(datos)):>8} "
              f"{t:>15.0f} min")

    # ---- el cuerpo del analisis -------------------------------------
    print()
    print("=" * 104)
    print("2. CADA COMBINACION: DISPARO x OBJETIVO   (stop = el % del sistema, desde la entrada)")
    print("=" * 104)
    print("  'azar' es la linea base geometrica B/(A+B) de ESA combinacion: lo que")
    print("  daria una moneda que se moviera al azar con esos mismos niveles.")
    print()
    ref = [d["sistema"]["res"] for d in datos]
    lo, hi = boot_ci(ref, [d["symbol"] for d in datos], rng)
    print(f"  {'REFERENCIA':<14} {'objetivo':<8} {'ops':>5} {'TP':>7} {'SL':>7} "
          f"{'abierta':>8} {'acierto':>8} {'azar':>7} {'ventaja':>8} "
          f"{'media':>8} {'IC 95%':>17}")
    gan = sum(1 for r in ref if r > 0)
    print(f"  {'el sistema':<14} {'su TP':<8} {len(ref):>5} "
          f"{'':>7} {'':>7} {'':>8} {pct(gan, len(ref)):>8} {'':>7} {'':>8} "
          f"{np.mean(ref):>7.2f}% [{lo:>6.2f},{hi:>6.2f}]")
    print()
    for m in MARGENES:
        ent = [d for d in datos if d.get(m)]
        if len(ent) < 20:
            continue
        for nom in ("TP%", "+3.2%", "TPprec", "sin TP"):
            sub = [d for d in ent if d[m]["obj"].get(nom)]
            if len(sub) < 20:
                continue
            res = [d[m]["obj"][nom]["res"] for d in sub]
            par = [d["symbol"] for d in sub]
            des = [d[m]["obj"][nom]["des"] for d in sub]
            tp = des.count("TP"); sl = des.count("SL"); ab = des.count("ABIERTA")
            resueltas = tp + sl
            acierto = 100 * tp / resueltas if resueltas else float("nan")
            # linea base geometrica, señal por señal
            geos = []
            for d in sub:
                a = d[m]["obj"][nom]["dist_tp"]
                b = abs(d[m]["stop_pct"])
                if a and a > 0:
                    geos.append(100 * b / (a + b))
            geo = np.mean(geos) if geos else float("nan")
            lo, hi = boot_ci(res, par, rng)
            print(f"  SL +{m:<10.1f} {nom:<8} {len(sub):>5} {pct(tp, len(sub)):>7} "
                  f"{pct(sl, len(sub)):>7} {pct(ab, len(sub)):>8} "
                  f"{acierto:>7.1f}% {geo:>6.1f}% {acierto-geo:>+7.1f} "
                  f"{np.mean(res):>7.2f}% [{lo:>6.2f},{hi:>6.2f}]")
        print()

    # ---- los cubos de Felix -----------------------------------------
    print("=" * 104)
    print("3. LOS GRUPOS, CON EL DISPARO A 0.6% Y A 1.0%")
    print("=" * 104)
    for m in (0.6, 1.0):
        ent = [d for d in datos if d.get(m)]
        print(f"\n  DISPARO EN SL +{m}%   ({len(ent)} entradas de {len(datos)} señales)")
        print(f"  {'objetivo':<10} {'cumple obj':>12} {'llega a +3.2%':>15} "
              f"{'la paran':>10} {'se hunde':>10} {'ni una cosa':>12}")
        for nom in ("TP%", "+3.2%", "TPprec"):
            sub = [d for d in ent if d[m]["obj"].get(nom)]
            if len(sub) < 20:
                continue
            o = [d[m]["obj"][nom] for d in sub]
            cumple = sum(1 for x in o if x["des"] == "TP")
            m32 = sum(1 for x in o if x["mfe"] >= META)
            paran = sum(1 for x in o if x["des"] == "SL")
            hunde = sum(1 for x, d in zip(o, sub)
                        if x["des"] == "SL" and x["mae"] <= 2 * d[m]["stop_pct"])
            nada = sum(1 for x in o if x["des"] == "ABIERTA")
            print(f"  {nom:<10} {cumple:>5} {pct(cumple,len(sub)):>6} "
                  f"{m32:>7} {pct(m32,len(sub)):>7} {paran:>4} {pct(paran,len(sub)):>5} "
                  f"{hunde:>4} {pct(hunde,len(sub)):>5} {nada:>5} {pct(nada,len(sub)):>6}")

    # ---- de donde sale el dinero ------------------------------------
    print()
    print("=" * 104)
    print("4. DE DONDE SALE EL RESULTADO  (disparo 1.0%)")
    print("=" * 104)
    ent = [d for d in datos if d.get(1.0)]
    for nom in ("TP%", "+3.2%", "TPprec", "sin TP"):
        sub = [d for d in ent if d[1.0]["obj"].get(nom)]
        if len(sub) < 20:
            continue
        g = defaultdict(list)
        for d in sub:
            o = d[1.0]["obj"][nom]
            g[o["des"]].append(o["res"])
        tot = sum(len(v) for v in g.values())
        trozos = []
        for k in ("TP", "SL", "ABIERTA"):
            if g[k]:
                a = np.array(g[k])
                trozos.append(f"{k} {len(a):>4} ({pct(len(a),tot)}) media {a.mean():>+6.2f}% "
                              f"aporta {a.sum()/tot:>+6.3f}")
        print(f"\n  objetivo {nom}")
        for t in trozos:
            print(f"     {t}")
        todos = np.concatenate([np.array(v) for v in g.values() if len(v)])
        if len(todos) > 5:
            print(f"     media {todos.mean():+.2f}%   mediana {np.median(todos):+.2f}%   "
                  f"sin las 5 mejores {np.sort(todos)[:-5].mean():+.2f}%")


if __name__ == "__main__":
    main()
