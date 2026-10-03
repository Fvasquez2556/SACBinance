"""Ideas concretas, escritas ANTES de ver su resultado, en largo y en corto, con varias metas y stops.

Cada idea se mide en las dos mitades por separado (exploración: hasta el 23-sep; comprobación: desde el 24-sep).
Unidad principal: una entrada por moneda cada 12 h (sin solapes). Coste 0,5 pp por operación (y 0,2 pp como
sensibilidad, por si Felix paga menos comisión).
"""
from __future__ import annotations

import json
import sys

import numpy as np

from comun import AQUI, CORTE_MIN

z = np.load(AQUI / "escaneo.npz")
X, cols = z["X"], [str(c) for c in z["cols"]]
C = {c: i for i, c in enumerate(cols)}
col = lambda n: X[:, C[n]]
minuto, sym = col("minuto"), col("sym").astype(int)
dia = (minuto // 1440).astype(int)
mitades = {"exploracion": minuto < CORTE_MIN - 720, "comprobacion": minuto >= CORTE_MIN}
tu = lambda x: col(f"t_up_{x}")
td = lambda x: col(f"t_dn_{x}")


def pnl(lado, tp, sl, H):
    """% bruto de cada operación: meta, stop o cierre al vencer H minutos. Misma vela -> stop."""
    ret = col("ret_180" if H == 180 else "ret_720") * 100
    if lado == "largo":
        t_gana, t_pierde, fin = tu(tp), td(sl), ret
    else:
        t_gana, t_pierde, fin = td(tp), tu(sl), -ret
    gana = (t_gana <= H) & (t_gana < t_pierde)
    pierde = (t_pierde <= H) & ~gana
    return np.where(gana, tp, np.where(pierde, -sl, fin)), gana, pierde


def una_por_moneda(m, espera=720):
    sel = np.zeros(len(X), bool)
    orden = np.lexsort((minuto, sym))
    ultimo = {}
    for i in orden[m[orden]]:
        if minuto[i] - ultimo.get(sym[i], -10 ** 9) >= espera:
            sel[i] = True
            ultimo[sym[i]] = minuto[i]
    return sel


def ic_dias(p, m, coste, reps=2000):
    dias = np.unique(dia[m])
    if len(dias) < 4:
        return None
    s_ = {d_: (p[m & (dia == d_)].sum(), (m & (dia == d_)).sum()) for d_ in dias}
    rng = np.random.default_rng(11)
    med = []
    for _ in range(reps):
        t = rng.choice(dias, len(dias))
        med.append(sum(s_[k][0] for k in t) / sum(s_[k][1] for k in t) - coste)
    return [round(float(np.percentile(med, 2.5)), 3), round(float(np.percentile(med, 97.5)), 3)]


r15, r60, r1440 = col("r15"), col("r60"), col("r1440")
dmax, volr15, volr60 = col("dmax1440"), col("volr15"), col("volr60")
amp, amp24, btc60, btc24 = col("amplitud"), col("amplitud24"), col("btc_r60"), col("btc_r1440")
mecha = col("mecha15")

IDEAS = {
    # --- largo
    "L0 cualquier momento (referencia)": ("largo", np.ones(len(X), bool)),
    "L1 rompe el máximo de 24 h con volumen (x3)": ("largo", (dmax >= -0.002) & (volr15 >= 3)),
    "L2 volumen x3 sin mover precio (acumulación)": ("largo", (volr60 >= 3) & (np.abs(r60) < 0.01)),
    "L3 caída de −3 % en 1 h en moneda que sube +10 % en 24 h": ("largo", (r1440 >= 0.10) & (r60 <= -0.03)),
    "L4 mercado a favor (60 % de monedas arriba en 24 h y BTC arriba)": ("largo", (amp24 >= 0.6) & (btc24 > 0)),
    "L5 mercado a favor ahora + impulso corto (+0,5 a +2 % en 15 min)": ("largo", (amp >= 0.6) & (btc60 > 0) & (r15 >= 0.005) & (r15 <= 0.02)),
    "L6 rebote tras desplome (−3 % en 15 min)": ("largo", r15 <= -0.03),
    "L7 muy lejos del máximo de 24 h (−10 % o más)": ("largo", dmax <= -0.10),
    # --- corto (las ideas de Felix sobre caídas)
    "S0 cualquier momento (referencia)": ("corto", np.ones(len(X), bool)),
    "S1 subió de golpe: +3 % en 15 min": ("corto", r15 >= 0.03),
    "S2 subió de golpe: +5 % en 1 h": ("corto", r60 >= 0.05),
    "S3 subió de golpe: +10 % en 1 h": ("corto", r60 >= 0.10),
    "S4 cerca del máximo de 24 h sin haber subido (<3 % en 24 h)": ("corto", (dmax >= -0.005) & (r1440 < 0.03)),
    "S5 cae de golpe (−2 % en 15 min) cerca del máximo de 24 h": ("corto", (r15 <= -0.02) & (dmax >= -0.05)),
    "S6 subió +5 % en 1 h y deja mecha arriba (rechazo)": ("corto", (r60 >= 0.05) & (mecha >= 0.5)),
}
GEOMETRIAS = [(2.67, 1.8), (2.67, 3.0), (2.67, 5.0), (2.67, 8.0), (1.5, 1.5), (5.0, 2.67)]

res = {}
for nombre, (lado, cond) in IDEAS.items():
    res[nombre] = {}
    sel = {k: una_por_moneda(cond & m) for k, m in mitades.items()}
    for H in (180, 720):
        for tp, sl in GEOMETRIAS:
            p, g, q = pnl(lado, tp, sl, H)
            fila = {}
            for k, m in sel.items():
                n = int(m.sum())
                if n == 0:
                    fila[k] = {"n": 0}
                    continue
                fila[k] = {"n": n, "monedas": int(len(np.unique(sym[m]))), "dias": int(len(np.unique(dia[m]))),
                           "aciertos_pct": round(100 * g[m].sum() / max(1, g[m].sum() + q[m].sum()), 1),
                           "bruto": round(float(p[m].mean()), 3),
                           "neto_0.5": round(float(p[m].mean() - 0.5), 3),
                           "neto_0.2": round(float(p[m].mean() - 0.2), 3)}
            positivo = all(fila[k].get("neto_0.5", -1) > 0 for k in mitades)
            if positivo:
                fila["ic95_comprobacion"] = ic_dias(p, sel["comprobacion"], 0.5)
            res[nombre][f"{H // 60}h|TP{tp}|SL{sl}"] = fila

# régimen por día: lo que da comprar al azar (una por moneda) cada día, y cómo venía BTC
p, _, _ = pnl("largo", 2.67, 1.8, 720)
azar = una_por_moneda(np.ones(len(X), bool), espera=1440)
dias = {}
for d_ in np.unique(dia):
    m = azar & (dia == d_)
    if m.sum() < 30:
        continue
    import datetime as dt
    dias[dt.datetime.utcfromtimestamp(int(d_) * 86400).strftime("%Y-%m-%d")] = {
        "n": int(m.sum()), "bruto_largo": round(float(p[m].mean()), 3),
        "btc_24h_previo": round(100 * float(np.nanmedian(btc24[m])), 2),
        "amplitud24_previa": round(float(np.nanmedian(amp24[m])), 2)}
res["_por_dia_largo_al_azar"] = dias

(AQUI / "hipotesis.json").write_bytes(json.dumps(res, indent=1, ensure_ascii=False).encode())

print("idea | geometría | EXPLORACIÓN n, aciertos, neto0.5 | COMPROBACIÓN n, aciertos, neto0.5 | neto0.2 en las dos")
for nombre, g in res.items():
    if nombre.startswith("_"):
        continue
    for geo, f in g.items():
        e, c = f["exploracion"], f["comprobacion"]
        if not e.get("n") or not c.get("n"):
            continue
        marca = " <== POSITIVA EN LAS DOS" if "ic95_comprobacion" in f else ""
        print(f"{nombre[:58]:58s} {geo:16s} | {e['n']:5d} {e['aciertos_pct']:5.1f}% {e['neto_0.5']:+.3f} | "
              f"{c['n']:5d} {c['aciertos_pct']:5.1f}% {c['neto_0.5']:+.3f} | {e['neto_0.2']:+.3f} {c['neto_0.2']:+.3f}{marca}"
              + (f" IC{f['ic95_comprobacion']}" if marca else ""))
print()
for k, v in dias.items():
    print(k, v)
