"""Elige las ~150 monedas más líquidas del universo de SAC (mediana del volumen diario en USDT, 8-sep a 2-oct).

Se excluyen las que no se mueven por sí mismas: estables, oro y envoltorios de BTC/ETH.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "revision-completa"))
from comun import cargar  # noqa: E402

EXCLUIR = {"USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "USDPUSDT", "DAIUSDT", "EURUSDT", "EURIUSDT", "AEURUSDT",
           "USD1USDT", "BFUSDUSDT", "XUSDUSDT", "RLUSDUSDT", "PYUSDUSDT", "USDEUSDT", "GBPUSDT", "UUSDT",
           "PAXGUSDT", "XAUTUSDT", "WBTCUSDT", "WBETHUSDT", "BNSOLUSDT", "USDSUSDT", "USDTUSDT"}
d = cargar()
filas = []
for sym, (t, o, h, l, c, v) in d["velas"].items():
    if sym in EXCLUIR:
        continue
    dias = (t // 1440)
    vol_dia = {}
    for dd, vv in zip(dias, v):
        vol_dia[int(dd)] = vol_dia.get(int(dd), 0.0) + float(vv)
    completos = [x for k, x in vol_dia.items() if np.sum(dias == k) >= 1300]   # días con >= 1300 minutos
    if len(completos) < 10:
        continue
    filas.append((sym, float(np.median(completos)), len(completos)))
filas.sort(key=lambda x: -x[1])
elegidas = [f[0] for f in filas[:150]]
if "BTCUSDT" not in elegidas:
    elegidas.append("BTCUSDT")
out = {"criterio": "top 150 por mediana de volumen diario (USDT) en días con >=1300 minutos, 8-sep a 2-oct; sin estables/oro/envoltorios",
       "monedas": elegidas,
       "detalle": [{"symbol": s, "vol_mediano_usdt": round(v_), "dias": n} for s, v_, n in filas[:150]],
       "candidatas": len(filas)}
Path("monedas.json").write_bytes(json.dumps(out, indent=1).encode())
print(len(elegidas), "monedas de", len(filas), "candidatas")
print("más líquida:", filas[0][0], round(filas[0][1] / 1e6), "M USDT/día | la 150:", filas[149][0], round(filas[149][1] / 1e6, 1), "M")
print(", ".join(elegidas[:40]), "...")
