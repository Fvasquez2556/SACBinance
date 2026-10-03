"""Escaneo de 7 meses (velas oficiales de Binance), cada 10 minutos por moneda. Ver REGLAS.md.

Igual que revision-completa/escaneo.py, más:
- flujo comprador (taker_buy_quote / quote_volume) a 1, 2, 15 y 60 min, y operaciones relativas;
- el disparo "como SAC": z de subida a 3 min con la sigma EWMA de adaptive.py y pendiente de 5 min;
- BTC respecto de su media de 7 días.
Salida: data/binance_vision/escaneo7.npz (fuera de git por tamaño).
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

AQUI = Path(__file__).resolve().parent
NPZ = AQUI.parents[2] / "data" / "binance_vision" / "npz"
SALIDA = AQUI.parents[2] / "data" / "binance_vision" / "escaneo7.npz"
PASO, PASADO, FUTURO = 10, 1440, 720
TP, SL = 2.67, 1.8
NIVELES = (0.5, 1.0, 1.5, 1.8, 2.0, 2.67, 3.0, 4.0, 5.0, 8.0)
ALFA, SIGMA_MIN = 0.05, 0.0008          # adaptive.py / settings.py de SAC
t0 = time.time()

monedas = json.loads((AQUI / "monedas.json").read_text(encoding="utf-8"))["monedas"]
monedas = [m for m in monedas if (NPZ / f"{m}.npz").exists()]
if "--prueba" in sys.argv:                      # corrida corta para encontrar errores
    monedas = monedas[:12]
    SALIDA = SALIDA.with_name("escaneo7_prueba.npz")


class Serie:
    def __init__(self, z):
        t = z["t"].astype(np.int64)
        self.base = int(t[0]); self.n = int(t[-1]) - self.base + 1
        idx = t - self.base
        for k, nombre in (("o", "o"), ("h", "h"), ("l", "l"), ("c", "c"), ("qv", "qv"), ("tbq", "tbq"), ("n", "nt")):
            a = np.full(self.n, np.nan)            # "n" de Binance = operaciones; aquí se llama nt
            a[idx] = z[k]
            setattr(self, nombre, a)


series = {m: Serie(np.load(NPZ / f"{m}.npz")) for m in monedas}
print(len(series), "monedas cargadas", round(time.time() - t0), "s", file=sys.stderr, flush=True)

# ---------------------------------------------------------------- mercado por minuto absoluto
m_ini = min(s.base for s in series.values()); m_fin = max(s.base + s.n for s in series.values())
N = m_fin - m_ini
suben = np.zeros(N); cuentan = np.zeros(N); suben24 = np.zeros(N); cuentan24 = np.zeros(N)
for s in series.values():
    c = s.c
    pos = np.arange(s.n) + s.base - m_ini
    for k, (sb, ct) in ((60, (suben, cuentan)), (1440, (suben24, cuentan24))):
        r = np.full(s.n, np.nan); r[k:] = c[k:] / c[:-k] - 1
        ok = np.isfinite(r)
        sb[pos[ok]] += r[ok] > 0; ct[pos[ok]] += 1
amplitud = np.where(cuentan > 30, suben / np.maximum(cuentan, 1), np.nan)
amplitud24 = np.where(cuentan24 > 30, suben24 / np.maximum(cuentan24, 1), np.nan)
btc = series["BTCUSDT"]
btc_c = np.full(N, np.nan); btc_c[btc.base - m_ini: btc.base - m_ini + btc.n] = btc.c
cs = np.concatenate([[0], np.cumsum(np.nan_to_num(btc_c))]); cnt = np.concatenate([[0], np.cumsum(np.isfinite(btc_c))])
btc_sma7 = np.full(N, np.nan)
W7 = 10080
btc_sma7[W7 - 1:] = (cs[W7:] - cs[:-W7]) / np.maximum(cnt[W7:] - cnt[:-W7], 1)


def vmax(x, w):
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        out[w - 1:] = np.nanmax(swv(x, w), axis=1)
    return out


def vmin(x, w):
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        out[w - 1:] = np.nanmin(swv(x, w), axis=1)
    return out


def vsum(x, w):
    acc = np.concatenate([[0], np.cumsum(np.nan_to_num(x))])
    out = np.full(len(x), np.nan)
    out[w - 1:] = acc[w:] - acc[:-w]
    return out


def sigma_ewma(c):
    """Sigma de retornos de 1 m como AdaptiveStats de SAC (alfa 0,05, mínimo 0,08 %)."""
    sig = np.full(len(c), np.nan)
    mean = var = 0.0
    n = 0
    prev = math.nan
    for i, x in enumerate(c):
        if x != x:          # NaN: minuto sin vela, SAC no actualiza
            continue
        if prev == prev:
            r = x / prev - 1.0
            n += 1
            if n == 1:
                mean, var = r, 0.0
            else:
                d = r - mean
                mean += ALFA * d
                var = (1 - ALFA) * (var + ALFA * d * d)
            sig[i] = max(math.sqrt(max(var, 0.0)), SIGMA_MIN)
        prev = x
    return sig


RASGOS = ["r5", "r15", "r60", "r240", "r1440", "rng60", "rng240", "pos60", "pos1440", "dmax1440", "dmin60",
          "volr15", "volr60", "verdes15", "mecha15", "vol24h", "btc_r60", "btc_r15", "amplitud", "hora",
          "btc_r1440", "amplitud24", "tbr15", "tbr60", "ntr15", "zrise", "vel", "tbr1", "tbr2", "btc_sma7"]
RESULTADOS = ["ret_60", "ret_180", "ret_720", "max_720", "min_720"] + \
             [f"t_up_{x}" for x in NIVELES] + [f"t_dn_{x}" for x in NIVELES]
COLS = RASGOS + RESULTADOS
bloques, minutos, syms = [], [], []
for k, sym in enumerate(monedas):
    s = series[sym]
    if s.n < PASADO + FUTURO + 10:
        continue
    o, h, l, qv, tbq, nn = s.o, s.h, s.l, s.qv, s.tbq, s.nt
    ok_c = np.isfinite(s.c)
    c = s.c[np.maximum.accumulate(np.where(ok_c, np.arange(s.n), 0))]     # cierre rellenado
    max60, min60 = vmax(h, 60), vmin(l, 60); max240, min240 = vmax(h, 240), vmin(l, 240)
    max1440, min1440 = vmax(h, 1440), vmin(l, 1440); max15, min15 = vmax(h, 15), vmin(l, 15)
    q1, q2, q15, q60, q1440 = qv, vsum(qv, 2), vsum(qv, 15), vsum(qv, 60), vsum(qv, 1440)
    b1, b2, b15, b60 = tbq, vsum(tbq, 2), vsum(tbq, 15), vsum(tbq, 60)
    n15, n1440 = vsum(nn, 15), vsum(nn, 1440)
    verde = vsum((s.c > o).astype(float), 15)
    huecos = vsum((~ok_c).astype(float), PASADO); huecos_f = vsum((~ok_c).astype(float), FUTURO)
    sig = sigma_ewma(s.c)
    lc = np.log(c)
    pend = np.full(s.n, np.nan)
    pend[4:] = (-2 * lc[:-4] - lc[1:-3] + lc[3:-1] + 2 * lc[4:]) / 10.0       # pendiente de 5 puntos
    inicio = PASADO + ((-(s.base + PASADO)) % PASO)
    idx = np.arange(inicio, s.n - FUTURO, PASO)
    idx = idx[(huecos[idx] <= 72) & ok_c[idx] & (huecos_f[np.minimum(idx + FUTURO, s.n - 1)] <= 36)]
    if len(idx) == 0:
        continue
    R = c[idx]
    g = s.base + idx - m_ini
    F = {
        "r5": R / c[idx - 5] - 1, "r15": R / c[idx - 15] - 1, "r60": R / c[idx - 60] - 1,
        "r240": R / c[idx - 240] - 1, "r1440": R / c[idx - 1440] - 1,
        "rng60": max60[idx] / min60[idx] - 1, "rng240": max240[idx] / min240[idx] - 1,
        "pos60": (R - min60[idx]) / np.maximum(max60[idx] - min60[idx], 1e-12),
        "pos1440": (R - min1440[idx]) / np.maximum(max1440[idx] - min1440[idx], 1e-12),
        "dmax1440": R / max1440[idx] - 1, "dmin60": R / min60[idx] - 1,
        "volr15": q15[idx] / np.maximum(q1440[idx] / 96, 1e-9), "volr60": q60[idx] / np.maximum(q1440[idx] / 24, 1e-9),
        "verdes15": verde[idx] / 15, "mecha15": (max15[idx] - R) / np.maximum(max15[idx] - min15[idx], 1e-12),
        "vol24h": q1440[idx],
        "btc_r60": btc_c[g] / btc_c[g - 60] - 1, "btc_r15": btc_c[g] / btc_c[g - 15] - 1,
        "amplitud": amplitud[g], "hora": ((s.base + idx) // 60) % 24,
        "btc_r1440": btc_c[g] / btc_c[g - 1440] - 1, "amplitud24": amplitud24[g],
        "tbr15": b15[idx] / np.maximum(q15[idx], 1e-9), "tbr60": b60[idx] / np.maximum(q60[idx], 1e-9),
        "ntr15": n15[idx] / np.maximum(n1440[idx] / 96, 1e-9),
        "zrise": (R / c[idx - 3] - 1) / (sig[idx] * math.sqrt(3)),
        "vel": pend[idx] / sig[idx],
        "tbr1": np.where(np.nan_to_num(q1[idx]) > 0, np.nan_to_num(b1[idx]) / np.maximum(np.nan_to_num(q1[idx]), 1e-9), 0.5),
        "tbr2": b2[idx] / np.maximum(q2[idx], 1e-9),
        "btc_sma7": btc_c[g] / btc_sma7[g] - 1,
    }
    # --- resultados
    t_up = {x: np.full(len(idx), 32767, np.int16) for x in NIVELES}
    t_dn = {x: np.full(len(idx), 32767, np.int16) for x in NIVELES}
    hmax = np.full(len(idx), -np.inf); lmin = np.full(len(idx), np.inf)
    for j in range(1, FUTURO + 1):
        hj = h[idx + j]; lj = l[idx + j]
        hj = np.where(np.isfinite(hj), hj, -np.inf); lj = np.where(np.isfinite(lj), lj, np.inf)
        hmax = np.maximum(hmax, hj); lmin = np.minimum(lmin, lj)
        for x in NIVELES:
            a = t_up[x]; a[(a == 32767) & (hj >= R * (1 + x / 100))] = j
            b = t_dn[x]; b[(b == 32767) & (lj <= R * (1 - x / 100))] = j
    out = {"ret_60": c[idx + 60] / R - 1, "ret_180": c[idx + 180] / R - 1, "ret_720": c[idx + FUTURO] / R - 1,
           "max_720": hmax / R - 1, "min_720": lmin / R - 1}
    for x in NIVELES:
        out[f"t_up_{x}"] = t_up[x]; out[f"t_dn_{x}"] = t_dn[x]
    bloque = np.empty((len(idx), len(COLS)), np.float32)
    for ci, col in enumerate(COLS):
        bloque[:, ci] = F[col] if col in F else out[col]
    bloques.append(bloque); minutos.append((s.base + idx).astype(np.int32)); syms.append(np.full(len(idx), k, np.int16))
    if k % 25 == 0:
        print(k, sym, len(idx), round(time.time() - t0), "s", file=sys.stderr, flush=True)

X = np.concatenate(bloques)
np.savez(SALIDA, X=X, minuto=np.concatenate(minutos), sym=np.concatenate(syms), cols=np.array(COLS),
         simbolos=np.array(monedas))
print("filas", X.shape, "segundos", round(time.time() - t0), file=sys.stderr)
