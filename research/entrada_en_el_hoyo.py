# -*- coding: utf-8 -*-
"""
La idea de Felix: no entrar en la senal, sino esperar al hoyo.

En vez de comprar al precio de la senal, se pone una alerta de bajada 0.5%
POR ENCIMA del stop que el sistema calculo. Si el precio baja hasta ahi, se
entra, y se apunta al mismo take profit que el sistema habia fijado.

La intuicion viene del caso MARSCOIN del 9-sep: el sistema predijo suelo
0.13254 y techo 0.15192; el precio toco 0.13100 y luego 0.15200. Clavo los
dos extremos. Quien hubiera entrado abajo se habria llevado el tramo entero.

La pregunta es si eso pasa a menudo o fue una noche afortunada. Aqui se
simulan cuatro reglas sobre las mismas senales:

    SISTEMA  entrar al precio de la senal, con su TP y su SL   (lo de hoy)
    A        entrar en SL*1.005, y poner el stop al MISMO % por debajo
             de la nueva entrada que el sistema pedia desde la suya
    B        entrar en SL*1.005 y dejar el stop en el SL del sistema
             (solo 0.5% de riesgo, pero el ruido te saca)
    C-x      entrar en SL*1.005 con un stop fijo de x% bajo la entrada

Todo se simula sobre las velas de 1m guardadas, dentro de la misma ventana
de 24h que usa el sistema. Cuando una vela contiene a la vez el disparo de
entrada y el stop, no se puede saber el orden: se cuenta como parada, que es
el supuesto pesimista, y se reporta aparte cuantas veces pasa.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
TZ = -6
VENTANA_MS = 24 * 3600 * 1000
DISPARO = 1.005          # 0.5% por encima del SL del sistema
META = 3.2               # el objetivo de Felix
MUCHO = 10.0             # "subio muchisimo mas", como MARSCOIN
MIN_VELAS = 60           # cobertura minima para simular


def gt(ms):
    return (dt.datetime.utcfromtimestamp(ms / 1000)
            + dt.timedelta(hours=TZ)).strftime("%d/%m %H:%M")


def a_ms(txt):
    d = dt.datetime.strptime("2026/" + txt, "%Y/%d/%m %H:%M:%S")
    d = d - dt.timedelta(hours=TZ)
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def pct(n, d):
    return f"{100*n/d:4.1f}%" if d else "   -"


# ----------------------------------------------------------------------
# simulacion
# ----------------------------------------------------------------------
def simular(velas, entrada, stop, techo, desde_idx=0):
    """Recorre las velas y devuelve (desenlace, resultado_pct, ms, mfe, mae)."""
    mfe = mae = 0.0
    for k in range(desde_idx, len(velas)):
        v = velas[k]
        mfe = max(mfe, (v["h"] - entrada) / entrada * 100)
        mae = min(mae, (v["l"] - entrada) / entrada * 100)
        toca_sl = v["l"] <= stop
        toca_tp = v["h"] >= techo
        if toca_sl and toca_tp:
            return "SL", (stop - entrada) / entrada * 100, v["open_time"], mfe, mae
        if toca_sl:
            return "SL", (stop - entrada) / entrada * 100, v["open_time"], mfe, mae
        if toca_tp:
            return "TP", (techo - entrada) / entrada * 100, v["open_time"], mfe, mae
    fin = velas[-1]["c"]
    return "ABIERTA", (fin - entrada) / entrada * 100, velas[-1]["open_time"], mfe, mae


def evaluar(s, velas):
    """Devuelve un dict con el desenlace de cada regla para una senal."""
    e = s["entry"]
    sl_sys = s["stop_loss"]
    tp_sys = s["take_profit"]
    sl_pct = s["sl_pct"]          # negativo
    out = {"symbol": s["symbol"], "ts_open": s["ts_open"], "tier": s["tier"],
           "score": s["score"], "sl_pct": sl_pct, "tp_pct": s["tp_pct"]}

    # --- referencia: el sistema tal cual --------------------------------
    d, r, t, mfe, mae = simular(velas, e, sl_sys, tp_sys)
    out["sistema"] = {"des": d, "res": r, "mfe": mfe, "mae": mae}

    # --- el disparo de entrada -----------------------------------------
    disparo = sl_sys * DISPARO
    idx = None
    for k, v in enumerate(velas):
        if v["l"] <= disparo:
            idx = k
            break
    if idx is None:
        out["entro"] = False
        return out
    out["entro"] = True
    v0 = velas[idx]
    fill = min(disparo, v0["o"]) if v0["o"] <= disparo else disparo
    out["fill"] = fill
    out["ms_disparo"] = v0["open_time"] - s["ts_open"]
    out["tp_desde_fill"] = (tp_sys - fill) / fill * 100

    reglas = {
        "A": fill * (1 + sl_pct / 100.0),
        "B": sl_sys,
    }
    for x in (1.5, 2.0, 3.0):
        reglas[f"C{x:g}"] = fill * (1 - x / 100.0)

    for nom, stop in reglas.items():
        # ambiguedad dentro de la vela de entrada
        ambiguo = v0["l"] <= stop
        d, r, t, mfe, mae = simular(velas, fill, stop, tp_sys, desde_idx=idx)
        out[nom] = {"des": d, "res": r, "mfe": mfe, "mae": mae,
                    "ambiguo": ambiguo, "stop_pct": (stop - fill) / fill * 100}
    return out


# ----------------------------------------------------------------------
def boot_ci(x, pares, rng, n=2000):
    """Bootstrap agrupado por par: la unidad que se remuestrea es el par."""
    if len(x) < 10:
        return float("nan"), float("nan")
    x = np.asarray(x, dtype=float)
    grupos = defaultdict(list)
    for v, p in zip(x, pares):
        grupos[p].append(v)
    claves = list(grupos)
    arrs = [np.array(grupos[k]) for k in claves]
    medias = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(arrs), len(arrs))
        medias[i] = np.concatenate([arrs[j] for j in pick]).mean()
    return float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5))


def clasificar(o, nom):
    """Los cubos que pidio Felix."""
    if not o.get("entro"):
        return "NO_ENTRO"
    d = o[nom]
    if d["des"] == "TP":
        return "SUBIO_MUCHO" if d["mfe"] >= MUCHO else "TP"
    if d["des"] == "SL":
        return "HUNDIO" if d["mae"] <= 2 * d["stop_pct"] else "STOP"
    return "PLANA"


CUBOS = ["SUBIO_MUCHO", "TP", "PLANA", "STOP", "HUNDIO", "NO_ENTRO"]
ETIQ = {
    "SUBIO_MUCHO": "cumplio el TP y subio >=10%",
    "TP":          "cumplio el TP del sistema",
    "PLANA":       "entro, ni TP ni stop en 24h",
    "STOP":        "entro y la pararon",
    "HUNDIO":      "entro y se hundio (>2x el stop)",
    "NO_ENTRO":    "nunca bajo hasta el disparo",
}


def informe(titulo, datos, rng):
    print()
    print("=" * 100)
    print(titulo)
    print("=" * 100)
    n = len(datos)
    entraron = [o for o in datos if o.get("entro")]
    print(f"  {n} senales simuladas   |   el precio bajo hasta el disparo en "
          f"{len(entraron)} ({pct(len(entraron), n)})")
    if not entraron:
        return

    reglas = ["sistema", "A", "B", "C1.5", "C2", "C3"]
    nombres = {
        "sistema": "SISTEMA (entrar en la senal)",
        "A": "A  stop al mismo % bajo la entrada",
        "B": "B  stop en el SL del sistema",
        "C1.5": "C  stop fijo -1.5%",
        "C2": "C  stop fijo -2.0%",
        "C3": "C  stop fijo -3.0%",
    }

    # --- los cubos ----------------------------------------------------
    print()
    print("  LOS GRUPOS QUE PEDISTE  (sobre las que SI entraron)")
    print()
    cab = f"  {'regla':<36}" + "".join(f"{c[:11]:>13}" for c in CUBOS[:5])
    print(cab)
    for nom in reglas:
        base = datos if nom == "sistema" else entraron
        cont = defaultdict(int)
        for o in base:
            if nom == "sistema":
                d = o["sistema"]
                if d["des"] == "TP":
                    c = "SUBIO_MUCHO" if d["mfe"] >= MUCHO else "TP"
                elif d["des"] == "SL":
                    c = "HUNDIO" if d["mae"] <= 2 * o["sl_pct"] else "STOP"
                else:
                    c = "PLANA"
            else:
                c = clasificar(o, nom)
            cont[c] += 1
        tot = sum(cont[c] for c in CUBOS[:5])
        linea = f"  {nombres[nom]:<36}"
        for c in CUBOS[:5]:
            linea += f"{cont[c]:>6} {pct(cont[c], tot):>6}"
        print(linea)
    print()
    for c in CUBOS[:5]:
        print(f"     {c:<14} {ETIQ[c]}")

    # --- el dinero ----------------------------------------------------
    print()
    print("  EL RESULTADO POR OPERACION  (intervalo con bootstrap por par)")
    print()
    print(f"  {'regla':<36} {'ops':>5} {'aciertos':>9} {'media':>8} "
          f"{'IC 95%':>20} {'mediana':>8}")
    for nom in reglas:
        base = datos if nom == "sistema" else entraron
        res = [o[nom]["res"] for o in base]
        par = [o["symbol"] for o in base]
        gan = sum(1 for r in res if r > 0)
        lo, hi = boot_ci(res, par, rng)
        print(f"  {nombres[nom]:<36} {len(res):>5} {pct(gan, len(res)):>9} "
              f"{np.mean(res):>7.2f}% [{lo:>6.2f}, {hi:>6.2f}] "
              f"{np.median(res):>7.2f}%")

    # --- la meta de Felix ---------------------------------------------
    print()
    print(f"  ¿LLEGO A TU +{META}% DESDE EL PRECIO DE ENTRADA?")
    print()
    print(f"  {'regla':<36} {'ops':>5} {'llego a +3.2%':>15} {'llego a +10%':>14}")
    for nom in reglas:
        base = datos if nom == "sistema" else entraron
        m = sum(1 for o in base if o[nom]["mfe"] >= META)
        g = sum(1 for o in base if o[nom]["mfe"] >= MUCHO)
        print(f"  {nombres[nom]:<36} {len(base):>5} "
              f"{m:>6} {pct(m, len(base)):>8} {g:>6} {pct(g, len(base)):>7}")

    amb = sum(1 for o in entraron if o["A"]["ambiguo"])
    ambB = sum(1 for o in entraron if o["B"]["ambiguo"])
    print()
    print(f"  velas ambiguas (entrada y stop en el mismo minuto, contadas como")
    print(f"  paradas): regla A {amb} de {len(entraron)} ({pct(amb, len(entraron))}), "
          f"regla B {ambB} ({pct(ambB, len(entraron))})")


def patron(datos):
    """Que distingue a las que se hunden de las que cumplen."""
    entraron = [o for o in datos if o.get("entro")]
    if len(entraron) < 40:
        print("\n  (muy pocas entradas para buscar patron)")
        return
    print()
    print("=" * 100)
    print("BUSCANDO PATRON — regla A, que separa a las buenas de las malas")
    print("=" * 100)

    def tabla(nombre, clave, cortes):
        print()
        print(f"  {nombre}")
        print(f"     {'tramo':<18} {'n':>5} {'TP':>8} {'+3.2%':>8} "
              f"{'hundio':>8} {'media':>9}")
        for etq, f in cortes:
            sub = [o for o in entraron if f(o)]
            if len(sub) < 8:
                print(f"     {etq:<18} {len(sub):>5}   (pocas)")
                continue
            tp = sum(1 for o in sub if o["A"]["des"] == "TP")
            m = sum(1 for o in sub if o["A"]["mfe"] >= META)
            hu = sum(1 for o in sub if clasificar(o, "A") == "HUNDIO")
            med = np.mean([o["A"]["res"] for o in sub])
            print(f"     {etq:<18} {len(sub):>5} {pct(tp, len(sub)):>8} "
                  f"{pct(m, len(sub)):>8} {pct(hu, len(sub)):>8} {med:>8.2f}%")

    tabla("cuanto tardo en bajar hasta el disparo", "ms_disparo", [
        ("< 15 min", lambda o: o["ms_disparo"] < 15 * 60000),
        ("15 min - 1 h", lambda o: 15 * 60000 <= o["ms_disparo"] < 3600000),
        ("1 - 4 h", lambda o: 3600000 <= o["ms_disparo"] < 4 * 3600000),
        ("4 - 12 h", lambda o: 4 * 3600000 <= o["ms_disparo"] < 12 * 3600000),
        ("mas de 12 h", lambda o: o["ms_disparo"] >= 12 * 3600000),
    ])
    tabla("ancho del stop que pidio el sistema", "sl_pct", [
        ("menos de 1%", lambda o: o["sl_pct"] > -1.0),
        ("1 - 2%", lambda o: -2.0 < o["sl_pct"] <= -1.0),
        ("2 - 4%", lambda o: -4.0 < o["sl_pct"] <= -2.0),
        ("mas de 4%", lambda o: o["sl_pct"] <= -4.0),
    ])
    tabla("distancia al TP desde el hoyo", "tp_desde_fill", [
        ("menos de 3%", lambda o: o["tp_desde_fill"] < 3),
        ("3 - 6%", lambda o: 3 <= o["tp_desde_fill"] < 6),
        ("6 - 10%", lambda o: 6 <= o["tp_desde_fill"] < 10),
        ("mas de 10%", lambda o: o["tp_desde_fill"] >= 10),
    ])
    tabla("score de la senal", "score", [
        ("menos de 65", lambda o: o["score"] < 65),
        ("65 - 75", lambda o: 65 <= o["score"] < 75),
        ("75 - 85", lambda o: 75 <= o["score"] < 85),
        ("85 o mas", lambda o: o["score"] >= 85),
    ])
    tabla("hora GT de la senal", "ts_open", [
        ("00-06h", lambda o: 0 <= int(gt(o["ts_open"])[6:8]) < 6),
        ("06-12h", lambda o: 6 <= int(gt(o["ts_open"])[6:8]) < 12),
        ("12-18h", lambda o: 12 <= int(gt(o["ts_open"])[6:8]) < 18),
        ("18-24h", lambda o: 18 <= int(gt(o["ts_open"])[6:8]) < 24),
    ])


def main():
    rng = np.random.default_rng(20260909)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    ult = con.execute("SELECT MAX(open_time) FROM klines WHERE tf='1m'").fetchone()[0]
    prim = con.execute("SELECT MIN(open_time) FROM klines WHERE tf='1m'").fetchone()[0]
    print(f"velas de 1m disponibles: {gt(prim)} -> {gt(ult)} GT")

    seniales = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND ts_open >= ? ORDER BY ts_open",
        (prim,))]
    print(f"{len(seniales)} senales reales con velas de 1m que las cubran")

    datos = []
    sin_velas = 0
    for s in seniales:
        fin = min(s["ts_open"] + VENTANA_MS, ult)
        velas = list(con.execute(
            "SELECT open_time,o,h,l,c FROM klines WHERE symbol=? AND tf='1m' "
            "AND open_time BETWEEN ? AND ? ORDER BY open_time",
            (s["symbol"], s["ts_open"], fin)))
        if len(velas) < MIN_VELAS:
            sin_velas += 1
            continue
        o = evaluar(s, velas)
        o["completa"] = (fin - s["ts_open"]) >= VENTANA_MS * 0.95
        datos.append(o)
    print(f"{len(datos)} simuladas   ({sin_velas} descartadas por falta de velas)")

    corte = a_ms("08/09 00:00:00")
    recientes = [o for o in datos if o["ts_open"] >= corte]

    informe("GRUPO 1 — SENALES DEL 8 Y 9 DE SEPTIEMBRE", recientes, rng)
    informe("GRUPO 2 (CONTROL) — TODAS LAS SENALES CON VELAS DE 1m", datos, rng)
    patron(datos)


if __name__ == "__main__":
    main()
