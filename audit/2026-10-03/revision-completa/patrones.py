"""¿Hay algún patrón, visible ANTES, que lleve a +2,67 % antes de −1,8 %?

Se aprende con la exploración (antes del 24-sep) y se comprueba con lo que vino después.
Operación simulada en cada momento: compra al cierre, meta +2,67 %, stop −1,8 %, cierre forzoso a las 12 h.
"""
from __future__ import annotations

import json
import sys

import numpy as np

from comun import AQUI, CORTE_MIN, COSTE, SL, TP

z = np.load(AQUI / "escaneo.npz")
X, cols = z["X"], [str(c) for c in z["cols"]]
C = {c: i for i, c in enumerate(cols)}
col = lambda n: X[:, C[n]]
minuto = col("minuto")
dia = (minuto // 1440).astype(int)
sym = col("sym").astype(int)
expl = minuto < CORTE_MIN - 720            # sin solaparse con la comprobación
comp = minuto >= CORTE_MIN
bruto = col("neto_720")                    # % bruto de la operación
tpsl = col("tp_sl_720")
RASGOS = ["r5", "r15", "r60", "r240", "r1440", "rng60", "rng240", "pos60", "pos1440", "dmax1440", "dmin60",
          "volr15", "volr60", "verdes15", "mecha15", "vol24h", "btc_r60", "btc_r15", "amplitud", "hora"]
EMPATE = (SL + COSTE) / (TP + SL)           # % de aciertos (sobre resueltas) para no perder
out = {"filas": int(len(X)), "monedas": int(len(np.unique(sym))), "exploracion": int(expl.sum()),
       "comprobacion": int(comp.sum()), "empate_aciertos_pct": round(100 * EMPATE, 1)}


def resumen(m, coste=COSTE):
    n = int(m.sum())
    if n == 0:
        return {"n": 0}
    g, p = (tpsl[m] == 1).sum(), (tpsl[m] == -1).sum()
    return {"n": n, "monedas": int(len(np.unique(sym[m]))), "dias": int(len(np.unique(dia[m]))),
            "aciertos_pct": round(100 * g / max(1, g + p), 1),
            "llega267_12h_pct": round(100 * col("llega267_720")[m].mean(), 1),
            "bruto_medio": round(float(bruto[m].mean()), 3),
            "neto_medio": round(float(bruto[m].mean() - coste), 3)}


def ic_por_dia(m, reps=2000, semilla=7):
    """IC 95 % del neto medio remuestreando DÍAS enteros (los días mueven a todas las monedas a la vez)."""
    dias = np.unique(dia[m])
    if len(dias) < 3:
        return None
    sumas = {d_: (bruto[m & (dia == d_)].sum(), (m & (dia == d_)).sum()) for d_ in dias}
    rng = np.random.default_rng(semilla)
    medias = []
    for _ in range(reps):
        tome = rng.choice(dias, len(dias))
        s_, n_ = sum(sumas[t][0] for t in tome), sum(sumas[t][1] for t in tome)
        medias.append(s_ / n_ - COSTE)
    return [round(float(np.percentile(medias, 2.5)), 3), round(float(np.percentile(medias, 97.5)), 3)]


def una_por_moneda(m, espera=720):
    """Quita solapes: después de una entrada, esa moneda no vuelve a entrar en 12 h."""
    sel = np.zeros(len(X), bool)
    orden = np.lexsort((minuto, sym))
    ultimo = {}
    for i in orden[m[orden]]:
        s_ = sym[i]
        if minuto[i] - ultimo.get(s_, -10 ** 9) >= espera:
            sel[i] = True
            ultimo[s_] = minuto[i]
    return sel


out["base"] = {"exploracion": resumen(expl), "comprobacion": resumen(comp),
               "exploracion_una_por_moneda": resumen(una_por_moneda(expl)),
               "comprobacion_una_por_moneda": resumen(una_por_moneda(comp))}

# ---------------------------------------------------------------- 1. un rasgo a la vez, por décimos
deciles = {}
for r in RASGOS:
    x = col(r)
    ok = np.isfinite(x)
    cortes = np.unique(np.nanpercentile(x[expl & ok], np.arange(10, 100, 10)))
    b = np.digitize(x, cortes)
    filas = []
    for k in range(len(cortes) + 1):
        m = ok & (b == k)
        filas.append({"decimo": k, "desde": None if k == 0 else round(float(cortes[k - 1]), 5),
                      "exploracion": resumen(m & expl), "comprobacion": resumen(m & comp)})
    mejor = max(filas, key=lambda f: f["exploracion"].get("neto_medio", -9))
    deciles[r] = {"filas": filas, "mejor_en_exploracion": mejor["decimo"],
                  "neto_exploracion": mejor["exploracion"].get("neto_medio"),
                  "neto_comprobacion": mejor["comprobacion"].get("neto_medio"),
                  "aciertos_exploracion": mejor["exploracion"].get("aciertos_pct"),
                  "aciertos_comprobacion": mejor["comprobacion"].get("aciertos_pct")}
out["deciles"] = deciles

# ---------------------------------------------------------------- 2. las ideas de Felix
r15, r60, dmax, r1440 = col("r15"), col("r60"), col("dmax1440"), col("r1440")
cae = col("cae2_antes_sube2_180")


def caida(m):
    n = int(m.sum())
    if n == 0:
        return {"n": 0}
    c_, s_ = (cae[m] == 1).sum(), (cae[m] == -1).sum()
    return {"n": n, "monedas": int(len(np.unique(sym[m]))),
            "cae2_antes_que_sube2_pct": round(100 * c_ / max(1, c_ + s_), 1),
            "ret_3h_mediana": round(100 * float(np.nanmedian(col("ret_180")[m])), 2),
            "min_3h_mediana": round(100 * float(np.nanmedian(col("min_180")[m])), 2),
            "max_3h_mediana": round(100 * float(np.nanmedian(col("max_180")[m])), 2),
            "long_neto_medio": round(float(bruto[m].mean() - COSTE), 3)}


todos = np.ones(len(X), bool)
ideas = {
    "todas (referencia)": todos,
    "subió de golpe: +3 % o más en 15 min": r15 >= 0.03,
    "subió de golpe: +5 % o más en 60 min": r60 >= 0.05,
    "subió de golpe: +10 % o más en 60 min": r60 >= 0.10,
    "bajó de golpe: −3 % o más en 15 min": r15 <= -0.03,
    "cerca del máximo de 24 h (a <0,5 %) sin haber subido (<3 % en 24 h)": (dmax >= -0.005) & (r1440 < 0.03),
    "cerca del máximo de 24 h (a <0,5 %) habiendo subido 10 % o más en 24 h": (dmax >= -0.005) & (r1440 >= 0.10),
    "lejos del máximo de 24 h (−10 % o más)": dmax <= -0.10,
}
out["ideas"] = {k: {"exploracion": caida(m & expl), "comprobacion": caida(m & comp)} for k, m in ideas.items()}

# ---------------------------------------------------------------- 3. todos los rasgos juntos (regresión logística)
# Cada rasgo se parte en décimos (cortes de la exploración) y se codifica en 0/1: el modelo puede
# aprender formas raras (en U, umbrales), no solo "más es mejor".
bloques, nombres = [], []
for r in RASGOS:
    x = col(r)
    cortes = np.unique(np.nanpercentile(x[expl & np.isfinite(x)], np.arange(10, 100, 10)))
    b = np.digitize(np.nan_to_num(x, nan=np.nanmedian(x[expl])), cortes)
    for k in range(1, len(cortes) + 1):
        bloques.append((b == k).astype(np.float32)); nombres.append(f"{r}>{k}")
Z = np.column_stack(bloques + [np.ones(len(X), np.float32)])
y = (tpsl == 1).astype(np.float32)          # gana (TP antes que SL en 12 h)


def entrenar(Z, y, m, l2=1.0, pasos=300, lr=0.5):
    w = np.zeros(Z.shape[1], np.float32)
    Zm, ym = Z[m], y[m]
    for _ in range(pasos):
        p = 1 / (1 + np.exp(-(Zm @ w)))
        g = Zm.T @ (p - ym) / len(ym) + l2 * w / len(ym)
        w -= lr * g
    return w


w = entrenar(Z, y, expl)
prob = 1 / (1 + np.exp(-(Z @ w)))
modelo = {}
for nombre, m in (("exploracion", expl), ("comprobacion", comp)):
    p = prob[m]
    filas = {}
    for top in (50, 20, 10, 5, 2, 1):
        corte = np.percentile(prob[expl], 100 - top)    # umbral fijado con la exploración
        sel = m & (prob >= corte)
        uno = una_por_moneda(sel)
        filas[f"top{top}%"] = {"todas": resumen(sel), "una_por_moneda_12h": resumen(uno),
                               "ic95_neto_por_dia": ic_por_dia(uno)}
    modelo[nombre] = filas
orden = np.argsort(-np.abs(w[:-1]))[:15]
modelo["pesos_mayores"] = [(nombres[i], round(float(w[i]), 3)) for i in orden]
out["modelo"] = modelo

# ---------------------------------------------------------------- 4. sensibilidad al coste (todas las monedas, al azar)
out["coste"] = {f"{c_}": {"exploracion": resumen(una_por_moneda(expl), c_)["neto_medio"],
                          "comprobacion": resumen(una_por_moneda(comp), c_)["neto_medio"]}
                for c_ in (0.0, 0.1, 0.2, 0.3, 0.5)}

(AQUI / "patrones.json").write_bytes(json.dumps(out, indent=1, ensure_ascii=False).encode())
print(json.dumps({k: v for k, v in out.items() if k != "deciles"}, indent=1, ensure_ascii=False))
print("\n== mejor décimo de cada rasgo (aprendido en exploración) ==")
for r, v in deciles.items():
    print(f"{r:10s} decimo {v['mejor_en_exploracion']}: neto expl {v['neto_exploracion']:+.3f} aciertos {v['aciertos_exploracion']}% "
          f"| comprobación neto {v['neto_comprobacion']:+.3f} aciertos {v['aciertos_comprobacion']}%")
