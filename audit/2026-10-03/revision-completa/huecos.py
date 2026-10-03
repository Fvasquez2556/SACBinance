"""Minutos de 1m que faltan en la base, por día y por moneda (entre su primera y última vela)."""
import json
from collections import defaultdict
import numpy as np
from comun import AQUI, Serie, cargar

d = cargar()
por_dia = defaultdict(lambda: [0, 0])     # dia -> [faltan, esperados]
por_moneda = {}
for sym, a in d["velas"].items():
    s = Serie(*a)
    falta = np.isnan(s.c)
    por_moneda[sym] = float(round(100 * falta.mean(), 2))
    dias = (np.arange(s.n) + s.base) // 1440
    for dia in np.unique(dias):
        m = dias == dia
        por_dia[int(dia)][0] += int(falta[m].sum()); por_dia[int(dia)][1] += int(m.sum())
import datetime as dt
tabla = {dt.datetime.utcfromtimestamp(k * 86400).strftime("%Y-%m-%d"): round(100 * v[0] / v[1], 2) for k, v in sorted(por_dia.items())}
# huecos simultáneos (todas las monedas a la vez = caída del servidor) vs sueltos
cuantas = defaultdict(int); presentes = defaultdict(int)
for sym, a in d["velas"].items():
    s = Serie(*a)
    for j in np.nonzero(np.isnan(s.c))[0]:
        cuantas[s.base + int(j)] += 1
mins = sorted(cuantas)
masivos = sum(1 for m in mins if cuantas[m] >= 200)
res = {"por_dia_pct": tabla, "monedas_pct_p50": float(np.median(list(por_moneda.values()))),
       "monedas_con_mas_de_20pct": sum(v > 20 for v in por_moneda.values()),
       "minutos_con_200+_monedas_sin_vela": int(masivos),
       "peores": sorted(por_moneda.items(), key=lambda x: -x[1])[:15]}
(AQUI / "huecos.json").write_bytes(json.dumps(res, indent=1, default=float).encode())
print(json.dumps(res, indent=1, default=float))
