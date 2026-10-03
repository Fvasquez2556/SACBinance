"""Compara las velas de 1 m de la base de SAC con las oficiales de Binance (8-sep a 1-oct).

Para cada moneda que está en las dos fuentes: qué parte de los minutos de Binance falta en SAC,
y si los precios de los minutos que sí están coinciden.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "revision-completa"))
from comun import cargar  # noqa: E402

NPZ = AQUI.parents[2] / "data" / "binance_vision" / "npz"
FIN = int(dt.datetime(2026, 10, 2, tzinfo=dt.timezone.utc).timestamp() // 60)   # hasta el 1-oct inclusive

sac = cargar()["velas"]
por_dia = defaultdict(lambda: [0, 0])
monedas, distintos, comparados = {}, 0, 0
for f in sorted(NPZ.glob("*.npz")):
    sym = f.stem
    if sym not in sac:
        continue
    b = np.load(f)
    t_s, o_s, h_s, l_s, c_s, v_s = sac[sym]
    t_s = t_s.astype(np.int64)
    ini = max(int(t_s[0]), int(b["t"][0]))
    m = (b["t"] >= ini) & (b["t"] < FIN)
    tb, cb = b["t"][m].astype(np.int64), b["c"][m]
    if len(tb) == 0:
        continue
    pos = np.searchsorted(t_s, tb)
    pos_ok = np.minimum(pos, len(t_s) - 1)
    esta = t_s[pos_ok] == tb
    falta = ~esta
    monedas[sym] = {"minutos_binance": int(len(tb)), "faltan_en_sac": int(falta.sum()),
                    "pct": round(100 * float(falta.mean()), 2)}
    # precios de los minutos presentes en las dos fuentes
    cs = c_s[pos_ok[esta]].astype(np.float64)
    rel = np.abs(cs / cb[esta] - 1)
    distintos += int((rel > 1e-6).sum()); comparados += int(esta.sum())
    for d_, fa in zip(tb // 1440, falta):
        por_dia[int(d_)][0] += int(fa); por_dia[int(d_)][1] += 1

tot_b = sum(v["minutos_binance"] for v in monedas.values())
tot_f = sum(v["faltan_en_sac"] for v in monedas.values())
res = {
    "monedas_comparadas": len(monedas),
    "minutos_binance": tot_b, "faltan_en_sac": tot_f, "pct_faltan": round(100 * tot_f / max(1, tot_b), 2),
    "cierres_comparados": comparados, "cierres_distintos_mas_de_1ppm": distintos,
    "por_dia_pct_faltan": {dt.datetime.fromtimestamp(k * 86400, dt.timezone.utc).strftime("%Y-%m-%d"):
                           round(100 * v[0] / v[1], 2) for k, v in sorted(por_dia.items())},
    "peores": sorted(((k, v["pct"]) for k, v in monedas.items()), key=lambda x: -x[1])[:10],
}
(AQUI / "comparar_sac.json").write_bytes(json.dumps(res, indent=1).encode())
print(json.dumps(res, indent=1))
