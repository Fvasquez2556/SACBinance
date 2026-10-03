"""¿El sistema marca FUERTE cuando la moneda ya subió?

Parte 1 — por aviso: cuánto había subido la moneda ANTES del aviso y cuánto sube DESPUÉS, por nivel.
Parte 2 — por subida grande: en cada subida de +5 % o más (desde un mínimo, en <= 3 h),
           cuándo apareció el primer aviso y qué parte de la subida ya se había hecho.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import numpy as np

from comun import AQUI, SL, TP, Serie, cargar, primer_alcance

d = cargar()
print(d["meta"], file=sys.stderr)
series = {s: Serie(*a) for s, a in d["velas"].items()}
avisos = d["avisos"]

NIVELES = ["VIGILANCIA", "MODERADA", "FUERTE", "EXTRA-FUERTE"]


def med(x):
    x = [v for v in x if v is not None and np.isfinite(v)]
    return round(float(np.median(x)), 2) if x else None


def pct(x, q):
    x = [v for v in x if v is not None and np.isfinite(v)]
    return round(float(np.percentile(x, q)), 2) if x else None


# ---------------------------------------------------------------- parte 1
filas = []
for a in avisos:
    s = series.get(a["symbol"])
    if s is None or not a.get("entry"):
        continue
    m = a["ts_ms"] // 60000            # minuto en curso al emitir; la última vela cerrada es m-1
    i = s.i(m)
    if i - 241 < 0 or i + 720 > s.n:
        continue
    R = float(a["entry"])
    c, h, l = s.c, s.h, s.l
    pasado = slice(i - 240, i)
    if np.isnan(c[pasado]).sum() > 5 or np.isnan(h[i:i + 720]).sum() > 5:
        continue
    f = {"tier": a["tier"], "estado": a["display_state"], "symbol": a["symbol"], "m": m,
         "telegram": a["telegram"] == "enviado", "score": a["score"]}
    for k in (5, 15, 30, 60, 240):
        ref = c[i - 1 - k]
        f[f"sube_{k}"] = (R / ref - 1) * 100 if np.isfinite(ref) and ref > 0 else None
    lo60 = np.nanmin(l[i - 60:i]); lo240 = np.nanmin(l[i - 240:i])
    f["desde_min60"] = (R / lo60 - 1) * 100
    f["desde_min240"] = (R / lo240 - 1) * 100
    f["min_desde_min240"] = 240 - int(np.nanargmin(l[i - 240:i]))
    hi240 = np.nanmax(h[i - 240:i])
    f["bajo_max240"] = (R / hi240 - 1) * 100
    for W in (60, 180, 720):
        hh, ll = h[i:i + W], l[i:i + W]
        f[f"max_{W}"] = (np.nanmax(hh) / R - 1) * 100
        f[f"min_{W}"] = (np.nanmin(ll) / R - 1) * 100
    res, _ = primer_alcance(np.nan_to_num(h[i:i + 720], nan=0), np.nan_to_num(l[i:i + 720], nan=np.inf), R, TP, SL)
    f["tp_antes_sl_12h"] = res
    filas.append(f)

# primera del movimiento: 12 h sin avisos de esa moneda (cualquier nivel)
ultimo = {}
for f in sorted(filas, key=lambda x: x["m"]):
    f["primera"] = f["m"] - ultimo.get(f["symbol"], -10 ** 9) >= 720
    ultimo[f["symbol"]] = f["m"]

out = {"parte1": {}, "parte2": {}}
for modo in ("todas", "primera"):
    for niv in NIVELES + ["TELEGRAM"]:
        g = [f for f in filas if (f["telegram"] if niv == "TELEGRAM" else f["tier"] == niv)
             and f["estado"] in ("SUBIENDO", "BREAKOUT_INCIPIENTE") and (modo == "todas" or f["primera"])]
        if not g:
            continue
        tp = sum(1 for f in g if f["tp_antes_sl_12h"] == "TP")
        sl = sum(1 for f in g if f["tp_antes_sl_12h"] == "SL")
        out["parte1"][f"{modo}|{niv}"] = {
            "n": len(g), "monedas": len({f["symbol"] for f in g}),
            "sube_5": med([f["sube_5"] for f in g]), "sube_15": med([f["sube_15"] for f in g]),
            "sube_30": med([f["sube_30"] for f in g]), "sube_60": med([f["sube_60"] for f in g]),
            "desde_min60": med([f["desde_min60"] for f in g]), "desde_min60_p75": pct([f["desde_min60"] for f in g], 75),
            "desde_min240": med([f["desde_min240"] for f in g]),
            "pct_desde_min60_3_o_mas": round(100 * np.mean([f["desde_min60"] >= 3 for f in g]), 1),
            "bajo_max240": med([f["bajo_max240"] for f in g]),
            "max_60": med([f["max_60"] for f in g]), "max_180": med([f["max_180"] for f in g]),
            "max_720": med([f["max_720"] for f in g]),
            "min_60": med([f["min_60"] for f in g]), "min_180": med([f["min_180"] for f in g]),
            "min_720": med([f["min_720"] for f in g]),
            "tp_antes_sl_12h_pct": round(100 * tp / max(1, tp + sl), 1), "resueltas": tp + sl,
        }

# rasgos al emitir, por nivel (de outcomes): flujo, macro, btc
rasgos = defaultdict(lambda: defaultdict(int))
for a in avisos:
    if a["display_state"] not in ("SUBIENDO",):
        continue
    t = a["tier"]
    flujo = a.get("o_flow_trades_30s")
    rasgos[t]["n"] += 1
    if flujo is None:
        rasgos[t]["sin_outcome"] += 1
        continue
    confirmado = (flujo or 0) >= 8 and (a.get("o_buy_ratio_30s") or 0) > 0
    rasgos[t]["flujo_medido"] += int((flujo or 0) >= 8)
    rasgos[t][f"btc_{a.get('o_btc_regime')}"] += 1
    rasgos[t][f"macro_{a.get('o_macro')}"] += 1
    rasgos[t][f"fase_{a.get('o_fase_impulso')}"] += 1
out["rasgos_al_emitir"] = {k: dict(v) for k, v in rasgos.items()}

# ---------------------------------------------------------------- parte 2
por_moneda = defaultdict(list)
for f in filas:
    por_moneda[f["symbol"]].append(f)
todos = defaultdict(list)          # todos los avisos (también sin ventana completa) por moneda
for a in avisos:
    todos[a["symbol"]].append((a["ts_ms"] // 60000, a["tier"], a["display_state"], float(a["entry"] or 0)))
for k in todos:
    todos[k].sort()

eventos = []
SUBIDA = 5.0
for sym, s in series.items():
    l, h = s.l, s.h
    n = s.n
    i = 60
    while i < n - 180:
        if not np.isfinite(l[i]):
            i += 1
            continue
        # mínimo local: el más bajo de +-60 min
        ventana = l[max(0, i - 60):i + 61]
        if l[i] > np.nanmin(ventana):
            i += 1
            continue
        pico_rel = np.nanargmax(h[i:i + 181])
        pico = h[i + pico_rel]
        if pico / l[i] - 1 >= SUBIDA / 100:
            t0 = s.base + i
            tp_ = s.base + i + pico_rel
            ev = {"symbol": sym, "t0": t0, "tpico": tp_, "minimo": float(l[i]), "pico": float(pico),
                  "subida": (pico / l[i] - 1) * 100, "dur": int(pico_rel)}
            primeros = {}
            for (m, tier, est, R) in todos.get(sym, []):
                if m < t0 - 30 or m > tp_:
                    continue
                for clave, cond in (("cualquiera", True),
                                    ("moderada+", tier in ("MODERADA", "FUERTE", "EXTRA-FUERTE")),
                                    ("fuerte+", tier in ("FUERTE", "EXTRA-FUERTE"))):
                    if cond and clave not in primeros and R > 0:
                        primeros[clave] = {"min_tras_minimo": m - t0, "tier": tier, "estado": est,
                                           "hecho_pct": round(100 * (R - ev["minimo"]) / (ev["pico"] - ev["minimo"]), 1),
                                           "queda_pct": round((ev["pico"] / R - 1) * 100, 2)}
            ev["primeros"] = primeros
            eventos.append(ev)
            i = i + pico_rel + 1
        else:
            i += 1

out["parte2"]["eventos"] = len(eventos)
out["parte2"]["monedas"] = len({e["symbol"] for e in eventos})
out["parte2"]["subida_mediana"] = med([e["subida"] for e in eventos])
out["parte2"]["duracion_mediana_min"] = med([e["dur"] for e in eventos])
for clave in ("cualquiera", "moderada+", "fuerte+"):
    con = [e["primeros"][clave] for e in eventos if clave in e["primeros"]]
    out["parte2"][clave] = {
        "con_aviso": len(con), "sin_aviso": len(eventos) - len(con),
        "min_tras_minimo_mediana": med([c["min_tras_minimo"] for c in con]),
        "hecho_mediana": med([c["hecho_pct"] for c in con]),
        "hecho_p25": pct([c["hecho_pct"] for c in con], 25), "hecho_p75": pct([c["hecho_pct"] for c in con], 75),
        "queda_mediana": med([c["queda_pct"] for c in con]),
        "antes_del_30pct": sum(c["hecho_pct"] < 30 for c in con),
        "despues_del_70pct": sum(c["hecho_pct"] >= 70 for c in con),
        "queda_menos_2_67": sum(c["queda_pct"] < 2.67 for c in con),
    }

# cuántas subidas grandes hay por cada aviso FUERTE: ¿los FUERTE caen dentro de subidas o en cualquier lado?
(AQUI / "retraso.json").write_bytes(json.dumps(out, indent=1, ensure_ascii=False).encode())
json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
