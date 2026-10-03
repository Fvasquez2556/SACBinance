"""Comprueba con los avisos reales el error del ajuste por BTC (engine.py:702-707)."""
import json
from collections import Counter
from comun import cargar, AQUI

d = cargar()
res = {}
for tier in ("VIGILANCIA", "MODERADA", "FUERTE", "EXTRA-FUERTE"):
    g = [a for a in d["avisos"] if a["tier"] == tier and a["display_state"] == "SUBIENDO" and a.get("o_btc_regime")]
    flujo_ok = [a for a in g if (a.get("o_flow_trades_30s") or 0) >= 8]
    res[tier] = {
        "con_rasgos": len(g),
        "flujo_confirmable(>=8 trades)": len(flujo_ok),
        "btc": dict(Counter(a["o_btc_regime"] for a in g)),
        "macro": dict(Counter(a["o_macro"] for a in g)),
        "score": dict(sorted(Counter(a["score"] for a in g).items())),
        "macro_neutral_score<75": sum(1 for a in g if a["o_macro"] == "NEUTRAL" and a["score"] < 75),
        "sin_flujo_y_score>=80": sum(1 for a in g if (a.get("o_flow_trades_30s") or 0) < 8 and a["score"] >= 80),
    }
# del total de avisos FUERTE (todas las filas, con o sin rasgos), qué fracción tiene score 80-86 (79*1.1=86)
f = [a for a in d["avisos"] if a["tier"] == "FUERTE"]
res["FUERTE_score_80_86"] = sum(1 for a in f if 80 <= (a["score"] or 0) <= 86)
res["FUERTE_total"] = len(f)
(AQUI / "verificar_btc.json").write_bytes(json.dumps(res, indent=1, ensure_ascii=False).encode())
print(json.dumps(res, indent=1, ensure_ascii=False))
