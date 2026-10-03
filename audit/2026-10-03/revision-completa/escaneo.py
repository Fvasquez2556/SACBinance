"""Escaneo de todas las monedas, cada 5 minutos, sin mirar los avisos.

Para cada momento se calculan rasgos con el PASADO (la vela que acaba de cerrar y las anteriores)
y resultados con el FUTURO (desde la vela siguiente). Entrada = cierre de la vela que acaba de cerrar.

Salida: escaneo.npz con una fila por (moneda, momento).
"""
from __future__ import annotations

import sys
import time

import numpy as np

from comun import AQUI, SL, TP, Serie, cargar

PASO = 5
PASADO = 1440
FUTURO = 720
t0 = time.time()
d = cargar()
series = {s: Serie(*a) for s, a in d["velas"].items()}
simbolos = sorted(series)
print(len(simbolos), "monedas", file=sys.stderr)

# --- mercado: BTC y amplitud (qué fracción de monedas sube en 60 min), por minuto absoluto
m_ini = min(s.base for s in series.values())
m_fin = max(s.base + s.n for s in series.values())
N = m_fin - m_ini
suben = np.zeros(N); cuentan = np.zeros(N)
suben24 = np.zeros(N); cuentan24 = np.zeros(N)
for s in series.values():
    c = s.c
    r60 = np.full(s.n, np.nan)
    r60[60:] = c[60:] / c[:-60] - 1
    ok = np.isfinite(r60)
    idx = np.arange(s.n) + s.base - m_ini
    suben[idx[ok]] += r60[ok] > 0
    cuentan[idx[ok]] += 1
    r24 = np.full(s.n, np.nan)
    r24[1440:] = c[1440:] / c[:-1440] - 1
    ok24 = np.isfinite(r24)
    suben24[idx[ok24]] += r24[ok24] > 0
    cuentan24[idx[ok24]] += 1
amplitud = np.where(cuentan > 50, suben / np.maximum(cuentan, 1), np.nan)
amplitud24 = np.where(cuentan24 > 50, suben24 / np.maximum(cuentan24, 1), np.nan)
btc = series["BTCUSDT"]
btc_c = np.full(N, np.nan)
btc_c[btc.base - m_ini: btc.base - m_ini + btc.n] = btc.c


def ret(c, i, k):
    return c[i] / c[i - k] - 1


def ventana_max(x, w):
    """max de x[j-w+1 .. j] para cada j (NaN si la ventana no está completa)."""
    from numpy.lib.stride_tricks import sliding_window_view as swv
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        out[w - 1:] = np.nanmax(swv(x, w), axis=1)
    return out


def ventana_min(x, w):
    from numpy.lib.stride_tricks import sliding_window_view as swv
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        out[w - 1:] = np.nanmin(swv(x, w), axis=1)
    return out


def ventana_sum(x, w):
    cs = np.concatenate([[0], np.cumsum(np.nan_to_num(x))])
    out = np.full(len(x), np.nan)
    out[w - 1:] = cs[w:] - cs[:-w]
    return out


NIV_ARRIBA = (0.5, 1.0, 1.5, 1.8, 2.0, 2.67, 3.0, 4.0, 5.0, 8.0)
NIV_ABAJO = (0.5, 1.0, 1.5, 1.8, 2.0, 2.67, 3.0, 4.0, 5.0, 8.0)
COLS = ["sym", "minuto", "r5", "r15", "r60", "r240", "r1440", "rng60", "rng240", "pos60", "pos1440",
        "dmax1440", "dmin60", "volr15", "volr60", "verdes15", "mecha15", "vol24h", "btc_r60", "btc_r15",
        "amplitud", "hora", "btc_r1440", "amplitud24",
        # resultados
        "tp_sl_180", "tp_sl_720", "neto_720", "max_180", "min_180", "max_720", "min_720",
        "ret_60", "ret_180", "ret_720", "cae2_antes_sube2_180", "llega267_180", "llega267_720"] +        [f"t_up_{x}" for x in NIV_ARRIBA] + [f"t_dn_{x}" for x in NIV_ABAJO]
filas = []
for k, sym in enumerate(simbolos):
    s = series[sym]
    if s.n < PASADO + FUTURO + 10:
        continue
    o, h, l, v = s.o, s.h, s.l, s.v
    # cierre rellenado hacia adelante para los rasgos (un minuto sin operaciones no cambia el precio)
    c = s.c.copy()
    ok = np.isfinite(c)
    c = c[np.maximum.accumulate(np.where(ok, np.arange(s.n), 0))]
    c[~np.isfinite(c)] = np.nan
    max60, min60 = ventana_max(h, 60), ventana_min(l, 60)
    max240, min240 = ventana_max(h, 240), ventana_min(l, 240)
    max1440, min1440 = ventana_max(h, 1440), ventana_min(l, 1440)
    max15, min15 = ventana_max(h, 15), ventana_min(l, 15)
    v15, v60, v1440 = ventana_sum(v, 15), ventana_sum(v, 60), ventana_sum(v, 1440)
    verde = ventana_sum((s.c > o).astype(float), 15)
    huecos = ventana_sum(np.isnan(s.c).astype(float), 1440)
    huecos_f = ventana_sum(np.isnan(s.c).astype(float), FUTURO)
    # momentos alineados al reloj (minuto múltiplo de 5) para que todas las monedas compartan instantes
    inicio = PASADO + ((-(s.base + PASADO)) % PASO)
    idx = np.arange(inicio, s.n - FUTURO, PASO)
    idx = idx[(huecos[idx] <= 72) & np.isfinite(s.c[idx]) & (huecos_f[np.minimum(idx + FUTURO, s.n - 1)] <= 36)]
    if len(idx) == 0:
        continue
    R = c[idx]
    F = {}
    F["r5"] = ret(c, idx, 5); F["r15"] = ret(c, idx, 15); F["r60"] = ret(c, idx, 60)
    F["r240"] = ret(c, idx, 240); F["r1440"] = ret(c, idx, 1440)
    F["rng60"] = max60[idx] / min60[idx] - 1; F["rng240"] = max240[idx] / min240[idx] - 1
    F["pos60"] = (R - min60[idx]) / np.maximum(max60[idx] - min60[idx], 1e-12)
    F["pos1440"] = (R - min1440[idx]) / np.maximum(max1440[idx] - min1440[idx], 1e-12)
    F["dmax1440"] = R / max1440[idx] - 1
    F["dmin60"] = R / min60[idx] - 1
    F["volr15"] = v15[idx] / np.maximum(v1440[idx] / 96, 1e-9)
    F["volr60"] = v60[idx] / np.maximum(v1440[idx] / 24, 1e-9)
    F["verdes15"] = verde[idx] / 15
    F["mecha15"] = (max15[idx] - R) / np.maximum(max15[idx] - min15[idx], 1e-12)
    F["vol24h"] = v1440[idx]
    g = s.base + idx - m_ini
    F["btc_r60"] = btc_c[g] / btc_c[g - 60] - 1
    F["btc_r15"] = btc_c[g] / btc_c[g - 15] - 1
    F["amplitud"] = amplitud[g]
    F["btc_r1440"] = btc_c[g] / btc_c[g - 1440] - 1
    F["amplitud24"] = amplitud24[g]
    F["hora"] = ((s.base + idx) // 60) % 24

    # --- resultados: primer toque de TP/SL, recorriendo el futuro minuto a minuto
    up, dn = R * (1 + TP / 100), R * (1 - SL / 100)
    up2, dn2 = R * 1.02, R * 0.98
    primero_tp = np.full(len(idx), 10 ** 6); primero_sl = np.full(len(idx), 10 ** 6)
    primero_up2 = np.full(len(idx), 10 ** 6); primero_dn2 = np.full(len(idx), 10 ** 6)
    hmax = np.full(len(idx), -np.inf); lmin = np.full(len(idx), np.inf)
    out = {}
    t_arriba = {nv: np.full(len(idx), 32767, np.int16) for nv in NIV_ARRIBA}
    t_abajo = {nv: np.full(len(idx), 32767, np.int16) for nv in NIV_ABAJO}
    for j in range(1, FUTURO + 1):
        hj = h[idx + j]; lj = l[idx + j]
        hj = np.where(np.isfinite(hj), hj, -np.inf); lj = np.where(np.isfinite(lj), lj, np.inf)
        hmax = np.maximum(hmax, hj); lmin = np.minimum(lmin, lj)
        for nv in NIV_ARRIBA:
            t = t_arriba[nv]; t[(t == 32767) & (hj >= R * (1 + nv / 100))] = j
        for nv in NIV_ABAJO:
            t = t_abajo[nv]; t[(t == 32767) & (lj <= R * (1 - nv / 100))] = j
        primero_tp = np.where((primero_tp > j) & (hj >= up), j, primero_tp)
        primero_sl = np.where((primero_sl > j) & (lj <= dn), j, primero_sl)
        primero_up2 = np.where((primero_up2 > j) & (hj >= up2), j, primero_up2)
        primero_dn2 = np.where((primero_dn2 > j) & (lj <= dn2), j, primero_dn2)
        if j == 180:
            out["max_180"] = hmax / R - 1; out["min_180"] = lmin / R - 1
            out["tp_sl_180"] = np.where((primero_tp <= 180) & (primero_tp < primero_sl), 1,
                                        np.where(primero_sl <= 180, -1, 0))
            out["cae2_antes_sube2_180"] = np.where((primero_dn2 <= 180) & (primero_dn2 <= primero_up2), 1,
                                                   np.where(primero_up2 <= 180, -1, 0))
            out["llega267_180"] = (primero_tp <= 180).astype(float)
    out["max_720"] = hmax / R - 1; out["min_720"] = lmin / R - 1
    gana = (primero_tp <= FUTURO) & (primero_tp < primero_sl)
    pierde = (primero_sl <= FUTURO) & ~gana
    out["tp_sl_720"] = np.where(gana, 1, np.where(pierde, -1, 0))
    cierre = c[idx + FUTURO] / R - 1
    out["neto_720"] = np.where(gana, TP, np.where(pierde, -SL, cierre * 100))      # bruto; el coste se resta al analizar
    out["llega267_720"] = (primero_tp <= FUTURO).astype(float)
    out["ret_60"] = c[idx + 60] / R - 1; out["ret_180"] = c[idx + 180] / R - 1; out["ret_720"] = cierre

    for nv in NIV_ARRIBA:
        out[f"t_up_{nv}"] = t_arriba[nv]
    for nv in NIV_ABAJO:
        out[f"t_dn_{nv}"] = t_abajo[nv]
    bloque = np.empty((len(idx), len(COLS)), dtype=np.float64)
    bloque[:, 0] = k; bloque[:, 1] = s.base + idx
    for ci, col in enumerate(COLS[2:], start=2):
        bloque[:, ci] = F[col] if col in F else out[col]
    filas.append(bloque.astype(np.float32) if False else bloque)
    if k % 50 == 0:
        print(k, sym, len(idx), round(time.time() - t0), file=sys.stderr)

X = np.concatenate(filas)
np.savez_compressed(AQUI / "escaneo.npz", X=X, cols=np.array(COLS), simbolos=np.array(simbolos))
print("filas", X.shape, "segundos", round(time.time() - t0), file=sys.stderr)
