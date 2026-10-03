"""Análisis de 7 meses según REGLAS.md (fijadas antes de ver resultados).

Lee data/binance_vision/escaneo7.npz y escribe analisis7.json con:
- cada idea x geometría x plazo: exploración (mar-jun), comprobación (jul-1 oct) y cada mes;
- el criterio de candidata aplicado tal cual;
- el modelo combinado (logística sobre décimos) entrenado solo con la exploración;
- el resultado de comprar al azar por día y su relación con el mercado del día anterior.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
Z = np.load(AQUI.parents[2] / "data" / "binance_vision" / ("escaneo7_prueba.npz" if "--prueba" in sys.argv else "escaneo7.npz"))
X, minuto, sym = Z["X"], Z["minuto"].astype(np.int64), Z["sym"].astype(np.int64)
cols = [str(c) for c in Z["cols"]]
C = {c: i for i, c in enumerate(cols)}
col = lambda n: X[:, C[n]].astype(np.float64)
dia = minuto // 1440
CORTE = int(dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc).timestamp() // 60)
mes = np.array([dt.datetime.fromtimestamp(int(m) * 60, dt.timezone.utc).strftime("%Y-%m") for m in
                np.unique(minuto // 1440) * 1440])
_mes_de_dia = dict(zip(np.unique(minuto // 1440), mes))
mes_fila = np.array([_mes_de_dia[d_] for d_ in dia])
mes_fila[mes_fila == "2026-10"] = "2026-09"                 # el 1-oct va con septiembre
MESES = sorted(set(mes_fila))
PERIODOS = {"exploracion": minuto < CORTE - 720, "comprobacion": minuto >= CORTE}
COSTES = (0.2, 0.3, 0.4, 0.5)
COSTE = 0.4
print("filas", len(X), "monedas", len(np.unique(sym)), "meses", MESES, file=sys.stderr, flush=True)

tu = lambda x: col(f"t_up_{x}")
td = lambda x: col(f"t_dn_{x}")


def pnl(lado, tp, sl, H):
    ret = col("ret_180" if H == 180 else "ret_720") * 100
    if lado == "largo":
        tg, tpi, fin = tu(tp), td(sl), ret
    else:
        tg, tpi, fin = td(tp), tu(sl), -ret
    gana = (tg <= H) & (tg < tpi)
    pierde = (tpi <= H) & ~gana
    return np.where(gana, tp, np.where(pierde, -sl, fin)), gana, pierde


ORDEN = np.lexsort((minuto, sym))


def una_por_moneda(m, espera=720):
    sel = np.zeros(len(X), bool)
    cand = ORDEN[m[ORDEN]]
    ultimo_sym, ultimo_min = -1, -10 ** 12
    s_, mi = sym[cand], minuto[cand]
    for k in range(len(cand)):
        if s_[k] != ultimo_sym:
            ultimo_sym, ultimo_min = s_[k], -10 ** 12
        if mi[k] - ultimo_min >= espera:
            sel[cand[k]] = True
            ultimo_min = mi[k]
    return sel


def ic_dias(p, m, coste, reps=2000, semilla=11):
    """IC 95 % del neto medio remuestreando días enteros."""
    if m.sum() == 0:
        return None
    u, inv = np.unique(dia[m], return_inverse=True)
    if len(u) < 5:
        return None
    sums = np.bincount(inv, weights=p[m]); cnts = np.bincount(inv).astype(float)
    rng = np.random.default_rng(semilla)
    k = rng.integers(0, len(u), size=(reps, len(u)))
    medias = sums[k].sum(1) / cnts[k].sum(1) - coste
    return [round(float(np.percentile(medias, 2.5)), 3), round(float(np.percentile(medias, 97.5)), 3)]


def stats(p, g, q, m):
    n = int(m.sum())
    if n == 0:
        return {"n": 0}
    return {"n": n, "monedas": int(len(np.unique(sym[m]))), "dias": int(len(np.unique(dia[m]))),
            "aciertos_pct": round(100 * float(g[m].sum()) / max(1, float(g[m].sum() + q[m].sum())), 1),
            "bruto": round(float(p[m].mean()), 3),
            **{f"neto_{c_}": round(float(p[m].mean() - c_), 3) for c_ in COSTES}}


# ---------------------------------------------------------------- ideas (definiciones de la revisión + L8-L10)
r15, r60, r1440 = col("r15"), col("r60"), col("r1440")
dmax, volr15, volr60 = col("dmax1440"), col("volr15"), col("volr60")
amp, amp24, btc60, btc24 = col("amplitud"), col("amplitud24"), col("btc_r60"), col("btc_r1440")
mecha, dmin60 = col("mecha15"), col("dmin60")
zr, vel, tb1, tb2, sma7 = col("zrise"), col("vel"), col("tbr1"), col("tbr2"), col("btc_sma7")
todo = np.ones(len(X), bool)
disparo = (zr >= 2.0) & (vel > 0) & (dmin60 <= 0.035)
IDEAS = {
    "L0 cualquier momento (referencia)": ("largo", todo),
    "L1 rompe el máximo de 24 h con volumen (x3)": ("largo", (dmax >= -0.002) & (volr15 >= 3)),
    "L2 volumen x3 sin mover precio (acumulación)": ("largo", (volr60 >= 3) & (np.abs(r60) < 0.01)),
    "L3 caída de −3 % en 1 h en moneda que sube +10 % en 24 h": ("largo", (r1440 >= 0.10) & (r60 <= -0.03)),
    "L4 mercado a favor (60 % de monedas arriba en 24 h y BTC arriba)": ("largo", (amp24 >= 0.6) & (btc24 > 0)),
    "L5 mercado a favor ahora + impulso corto (+0,5 a +2 % en 15 min)": ("largo", (amp >= 0.6) & (btc60 > 0) & (r15 >= 0.005) & (r15 <= 0.02)),
    "L6 rebote tras desplome (−3 % en 15 min)": ("largo", r15 <= -0.03),
    "L7 muy lejos del máximo de 24 h (−10 % o más)": ("largo", dmax <= -0.10),
    "L8 como SAC: subida de 3 min >= 2 sigmas con compras dominantes": ("largo", disparo & (tb1 >= 0.58) & (tb2 >= 0.54)),
    "L9 como SAC pero sin mirar las compras": ("largo", disparo),
    "L10 BTC sobre su media de 7 días y la moneda sube en 24 h": ("largo", (sma7 > 0) & (r1440 > 0)),
    "S0 cualquier momento (referencia)": ("corto", todo),
    "S1 subió de golpe: +3 % en 15 min": ("corto", r15 >= 0.03),
    "S2 subió de golpe: +5 % en 1 h": ("corto", r60 >= 0.05),
    "S3 subió de golpe: +10 % en 1 h": ("corto", r60 >= 0.10),
    "S4 cerca del máximo de 24 h sin haber subido (<3 % en 24 h)": ("corto", (dmax >= -0.005) & (r1440 < 0.03)),
    "S5 cae de golpe (−2 % en 15 min) cerca del máximo de 24 h": ("corto", (r15 <= -0.02) & (dmax >= -0.05)),
    "S6 subió +5 % en 1 h y deja mecha arriba (rechazo)": ("corto", (r60 >= 0.05) & (mecha >= 0.5)),
}
GEOS = [(2.67, 1.8), (2.67, 3.0), (2.67, 5.0), (2.67, 8.0), (1.5, 1.5), (5.0, 2.67)]

res = {"filas": int(len(X)), "monedas": int(len(np.unique(sym))), "meses": MESES, "coste_principal": COSTE,
       "ideas": {}, "candidatas": []}
for nombre, (lado, cond) in IDEAS.items():
    sel = una_por_moneda(cond)
    res["ideas"][nombre] = {}
    for H in (180, 720):
        for tp, sl in GEOS:
            p, g, q = pnl(lado, tp, sl, H)
            fila = {k: stats(p, g, q, sel & m) for k, m in PERIODOS.items()}
            fila["meses"] = {mm: stats(p, g, q, sel & (mes_fila == mm)).get(f"neto_{COSTE}") for mm in MESES}
            pos_meses = sum(1 for v in fila["meses"].values() if v is not None and v > 0)
            fila["meses_positivos"] = pos_meses
            fila["ic95_comprobacion"] = ic_dias(p, sel & PERIODOS["comprobacion"], COSTE)
            e, c_ = fila["exploracion"], fila["comprobacion"]
            ok = (e.get("n", 0) > 0 and c_.get("n", 0) > 0 and e[f"neto_{COSTE}"] > 0 and c_[f"neto_{COSTE}"] > 0
                  and pos_meses >= 5 and fila["ic95_comprobacion"] is not None
                  and fila["ic95_comprobacion"][0] > -0.10 and c_["n"] >= 300 and c_["monedas"] >= 50)
            clave = f"{H // 60}h|TP{tp}|SL{sl}"
            fila["candidata"] = ok
            fila["solida"] = ok and fila["ic95_comprobacion"][0] > 0
            res["ideas"][nombre][clave] = fila
            if ok:
                res["candidatas"].append({"idea": nombre, "geometria": clave, "solida": fila["solida"],
                                          "exploracion": e, "comprobacion": c_, "meses": fila["meses"],
                                          "ic95": fila["ic95_comprobacion"]})
    print("hecho:", nombre, file=sys.stderr, flush=True)

# ---------------------------------------------------------------- modelo combinado (largo, +2,67 / −1,8, 12 h)
RASGOS = [c for c in cols if not (c.startswith("t_up") or c.startswith("t_dn") or c.startswith("ret_")
                                  or c in ("max_720", "min_720"))]
expl = PERIODOS["exploracion"]
# Cada rasgo en 10 tramos (cortes de la exploración). El modelo suma un peso por tramo de cada rasgo:
# es una logística sobre los 0/1 de cada tramo, calculada sin armar la matriz entera.
B = np.zeros((len(X), len(RASGOS)), np.int8)
for j, r in enumerate(RASGOS):
    x = col(r)
    ok = np.isfinite(x)
    cortes = np.unique(np.nanpercentile(x[expl & ok], np.arange(10, 100, 10)))
    B[:, j] = np.digitize(np.where(ok, x, np.nanmedian(x[expl & ok])), cortes)
p_l, g_l, q_l = pnl("largo", 2.67, 1.8, 720)
y = g_l.astype(np.float64)
rng = np.random.default_rng(5)
filas_e = np.nonzero(expl)[0]
muestra = rng.choice(filas_e, size=min(len(filas_e), 1_500_000), replace=False)
Be, ye = B[muestra], y[muestra]
W = np.zeros((len(RASGOS), 10)); b0 = 0.0


def logit(Bm):
    z = np.full(len(Bm), b0)
    for j in range(len(RASGOS)):
        z += W[j][Bm[:, j]]
    return z


for _ in range(300):
    pr = 1 / (1 + np.exp(-logit(Be)))
    err = pr - ye
    b0 -= 0.5 * err.mean()
    for j in range(len(RASGOS)):
        gj = np.bincount(Be[:, j], weights=err, minlength=10) / len(ye) + W[j] / len(ye)
        W[j] -= 0.5 * gj
nombres = [f"{r}>{k}" for r in RASGOS for k in range(10)]
w = np.concatenate([W.ravel(), [b0]])
prob = 1 / (1 + np.exp(-logit(B)))
modelo = {}
for top in (20, 10, 5, 2, 1):
    corte = np.percentile(prob[expl], 100 - top)
    sel = una_por_moneda(prob >= corte)
    modelo[f"top{top}%"] = {k: stats(p_l, g_l, q_l, sel & m) for k, m in PERIODOS.items()}
    modelo[f"top{top}%"]["meses"] = {mm: stats(p_l, g_l, q_l, sel & (mes_fila == mm)).get(f"neto_{COSTE}") for mm in MESES}
modelo["pesos_mayores"] = [(nombres[i], round(float(w[i]), 3)) for i in np.argsort(-np.abs(w[:-1]))[:12]]
res["modelo"] = modelo

# ---------------------------------------------------------------- comprar al azar por día vs mercado del día anterior
azar = una_por_moneda(todo, espera=1440)
por_dia = {}
for d_ in np.unique(dia):
    m = azar & (dia == d_)
    if m.sum() < 30:
        continue
    por_dia[int(d_)] = (float(p_l[m].mean()), float(np.nanmedian(amp24[m])), float(np.nanmedian(btc24[m])))
dd = sorted(por_dia)
pares = [(por_dia[d_][0], por_dia[d_ - 1][1], por_dia[d_ - 1][2]) for d_ in dd if d_ - 1 in por_dia]
a = np.array(pares)
res["regimen"] = {
    "dias": len(a),
    "bruto_medio_dia": round(float(a[:, 0].mean()), 3),
    "dias_positivos_pct": round(100 * float((a[:, 0] > 0).mean()), 1),
    "correlacion_con_amplitud_del_dia_anterior": round(float(np.corrcoef(a[:, 0], a[:, 1])[0, 1]), 3),
    "correlacion_con_btc_del_dia_anterior": round(float(np.corrcoef(a[:, 0], a[:, 2])[0, 1]), 3),
    "bruto_si_ayer_amplitud>=0.6": round(float(a[a[:, 1] >= 0.6, 0].mean()), 3) if (a[:, 1] >= 0.6).any() else None,
    "dias_ayer_amplitud>=0.6": int((a[:, 1] >= 0.6).sum()),
    "bruto_si_ayer_amplitud<0.4": round(float(a[a[:, 1] < 0.4, 0].mean()), 3) if (a[:, 1] < 0.4).any() else None,
    "dias_ayer_amplitud<0.4": int((a[:, 1] < 0.4).sum()),
    "por_mes_bruto": {mm: round(float(np.mean([por_dia[d_][0] for d_ in dd if _mes_de_dia.get(d_, "") .startswith(mm)])), 3)
                      for mm in MESES},
}

(AQUI / ("analisis7_prueba.json" if "--prueba" in sys.argv else "analisis7.json")).write_bytes(json.dumps(res, indent=1, ensure_ascii=False).encode())

# ---------------------------------------------------------------- resumen en pantalla
print(f"\nCANDIDATAS (coste {COSTE}): {len(res['candidatas'])}")
for c_ in res["candidatas"]:
    print(" ", c_["idea"], c_["geometria"], "sólida" if c_["solida"] else "", c_["ic95"],
          "expl", c_["exploracion"][f"neto_{COSTE}"], "comp", c_["comprobacion"][f"neto_{COSTE}"], c_["meses"])
print("\nidea | geometría | expl n acierto neto0.4 | comp n acierto neto0.4 | meses+ | neto0.2 expl/comp")
for nombre, g in res["ideas"].items():
    for geo, f in g.items():
        e, c_ = f["exploracion"], f["comprobacion"]
        if not e.get("n") or not c_.get("n"):
            continue
        print(f"{nombre[:60]:60s} {geo:16s} | {e['n']:6d} {e['aciertos_pct']:5.1f}% {e['neto_0.4']:+.3f} | "
              f"{c_['n']:6d} {c_['aciertos_pct']:5.1f}% {c_['neto_0.4']:+.3f} | {f['meses_positivos']}/7 | "
              f"{e['neto_0.2']:+.3f} {c_['neto_0.2']:+.3f}")
print("\nMODELO:", json.dumps(modelo, ensure_ascii=False)[:3000])
print("\nRÉGIMEN:", json.dumps(res["regimen"], ensure_ascii=False))
