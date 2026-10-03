"""¿Cuántos avisos salen justo después de un hueco de velas (la moneda volvía al universo o el stream se cortó)?"""
import json
import numpy as np
from collections import Counter
from comun import AQUI, Serie, cargar

d = cargar()
series = {s: Serie(*a) for s, a in d["velas"].items()}
tot = Counter(); tras = Counter(); ejemplos = []
for a in d["avisos"]:
    s = series.get(a["symbol"])
    if s is None:
        continue
    i = s.i(a["ts_ms"] // 60000)
    if i < 61 or i > s.n:
        continue
    faltan = int(np.isnan(s.c[i - 60:i]).sum())
    tot[a["tier"]] += 1
    if faltan >= 15:
        tras[a["tier"]] += 1
        if len(ejemplos) < 8:
            ejemplos.append((a["symbol"], a["ts_ms"], a["tier"], faltan))
res = {t: {"avisos": tot[t], "con_15+_minutos_sin_vela_en_la_hora_previa": tras[t],
           "pct": round(100 * tras[t] / max(1, tot[t]), 1)} for t in tot}
res["ejemplos"] = ejemplos
(AQUI / "avisos_tras_hueco.json").write_bytes(json.dumps(res, indent=1).encode())
print(json.dumps(res, indent=1))
