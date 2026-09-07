# -*- coding: utf-8 -*-
"""
La cascada: cuando una moneda toca la meta, que pasa con las demas.

Pregunta de Felix: de las senales vivas a la vez, cual sube primero, cuanto
tardan las otras, y sobre todo — en el instante en que la primera toca la meta,
a que precio estaba la segunda y cuanto le faltaba para la suya.

Primer intento fallido
----------------------
Definir "lider" como la llegada sin ninguna otra en los 60 minutos previos
dejo 2 casos de 599: con una llegada cada ~6 minutos de media, ese hueco casi
no existe. Los porcentajes que salieron de ahi no median nada.

Diseno corregido
----------------
No hace falta el concepto de lider. Cada llegada a la meta es un DISPARADOR.
Para cada disparador se mira donde estaban las demas senales abiertas y si
llegaron despues. Con 599 disparadores la muestra alcanza.

El control es lo unico que puede dar sentido al numero: una seguidora a 0.5%
de su meta llega mucho mas que una a 4%, tenga lider o no. Asi que se compara
SIEMPRE contra instantes al azar A IGUALDAD DE DISTANCIA. Si "despues de una
llegada" no bate a "en un momento cualquiera, misma distancia", no hay efecto
de arrastre: solo estabamos midiendo lo cerca que estaba del objetivo.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
SEGUIMIENTO = 360        # min que se sigue a las seguidoras
TZ = -6
MIN_N = 20


def gt(ts):
    return (dt.datetime.utcfromtimestamp(ts / 1000)
            + dt.timedelta(hours=TZ)).strftime("%d/%m %H:%M")


def cargar_klines(con):
    d = defaultdict(list)
    for sym, t, h, c in con.execute(
            "SELECT symbol, open_time, h, c FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        d[sym].append((t, h, c))
    return {s: np.array(v, dtype=np.float64) for s, v in d.items()}


def precio_en(a, ts):
    i = np.searchsorted(a[:, 0], ts, side="right") - 1
    if i < 0 or i >= len(a) or ts - a[i, 0] > 5 * 60_000:
        return None
    return float(a[i, 2])


def llega_en(a, t0, t1, nivel):
    """Minuto en que el high cruza `nivel` entre t0 y t1, o None."""
    i = np.searchsorted(a[:, 0], t0, side="left")
    j = np.searchsorted(a[:, 0], t1, side="right")
    if j <= i:
        return None
    seg = a[i:j]
    k = np.flatnonzero(seg[:, 1] >= nivel)
    return int(seg[k[0], 0]) if len(k) else None


def bandas(d, r, esp=None):
    out = []
    for lo, hi, lab in [(0, 0.5, "< 0.5%"), (0.5, 1, "0.5-1%"), (1, 2, "1-2%"),
                        (2, 3, "2-3%"), (3, 5, "3-5%"), (5, 99, "> 5%")]:
        m = (d >= lo) & (d < hi)
        n = int(m.sum())
        if n < MIN_N:
            out.append((lab, n, None, None))
            continue
        t = np.median(esp[m & np.isfinite(esp)]) if esp is not None and np.isfinite(esp[m]).any() else None
        out.append((lab, n, float(r[m].mean()), t))
    return out


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    kl = cargar_klines(con)
    filas = [dict(r) for r in con.execute(
        "SELECT signal_id, symbol, ts_open, entry, ms_up_32 FROM outcomes "
        "WHERE entry IS NOT NULL ORDER BY ts_open")]
    for f in filas:
        f["nivel"] = f["entry"] * (1 + META / 100.0)
        f["t_meta"] = (f["ts_open"] + f["ms_up_32"]) if f["ms_up_32"] else None
    disparos = sorted([f for f in filas if f["t_meta"]], key=lambda f: f["t_meta"])
    print(f"{len(filas)} senales, {len(kl)} pares con velas 1m")
    print(f"llegadas a +{META}% usables como disparador: {len(disparos)}\n")

    t_fin = max(a[-1, 0] for a in kl.values())

    # ------------------------------------------------------------------
    # 1. Tras cada llegada, donde estaban las demas
    # ------------------------------------------------------------------
    D, R, E = [], [], []
    ejemplos = []
    for L in disparos:
        T = L["t_meta"]
        if T + SEGUIMIENTO * 60_000 > t_fin:
            continue                      # sin futuro suficiente para medirlas
        vivas = []
        for g in filas:
            if g["symbol"] == L["symbol"]:
                continue
            if not (g["ts_open"] <= T <= g["ts_open"] + 24 * 3600_000):
                continue
            if g["t_meta"] is not None and g["t_meta"] <= T:
                continue                  # ya habia llegado: no es seguidora
            a = kl.get(g["symbol"])
            if a is None:
                continue
            p = precio_en(a, T)
            if p is None or p <= 0:
                continue
            falta = (g["nivel"] / p - 1) * 100.0
            if falta <= 0:
                continue
            t_ll = llega_en(a, T, T + SEGUIMIENTO * 60_000, g["nivel"])
            vivas.append((g["symbol"], falta, t_ll))
        for sym, falta, t_ll in vivas:
            D.append(falta)
            R.append(t_ll is not None)
            E.append((t_ll - T) / 60_000 if t_ll else np.nan)
        if vivas:
            vivas.sort(key=lambda v: v[1])
            ejemplos.append((L, vivas[0], len(vivas)))

    D, R, E = np.array(D), np.array(R, dtype=float), np.array(E)
    print("=" * 96)
    print("TRAS CADA LLEGADA A LA META, QUE HICIERON LAS DEMAS SENALES ABIERTAS")
    print("=" * 96)
    print(f"  parejas medidas: {len(D)}   disparadores utiles: {len(ejemplos)}")
    print(f"  distancia de la seguidora a SU meta en ese instante: "
          f"mediana {np.median(D):.2f}%   p25 {np.percentile(D,25):.2f}%")
    print(f"  llegaron en las {SEGUIMIENTO//60}h siguientes: "
          f"{int(R.sum())} / {len(R)}   {100*R.mean():.1f}%")
    fin = E[np.isfinite(E)]
    if len(fin):
        print(f"  cuanto tardaron tras la primera: mediana {np.median(fin):.0f}min   "
              f"p25 {np.percentile(fin,25):.0f}min   p75 {np.percentile(fin,75):.0f}min")

    # ------------------------------------------------------------------
    # 2. Control a igualdad de distancia
    # ------------------------------------------------------------------
    rng = np.random.default_rng(11)
    tmin = min(f["ts_open"] for f in filas)
    tmax = t_fin - SEGUIMIENTO * 60_000
    CD, CR = [], []
    intentos = 0
    while len(CD) < 12000 and intentos < 120000:
        intentos += 1
        T = int(rng.integers(tmin, tmax))
        g = filas[int(rng.integers(0, len(filas)))]
        if not (g["ts_open"] <= T <= g["ts_open"] + 24 * 3600_000):
            continue
        if g["t_meta"] is not None and g["t_meta"] <= T:
            continue
        a = kl.get(g["symbol"])
        if a is None:
            continue
        p = precio_en(a, T)
        if p is None or p <= 0:
            continue
        falta = (g["nivel"] / p - 1) * 100.0
        if falta <= 0:
            continue
        CD.append(falta)
        CR.append(llega_en(a, T, T + SEGUIMIENTO * 60_000, g["nivel"]) is not None)
    CD, CR = np.array(CD), np.array(CR, dtype=float)

    print("\n" + "=" * 96)
    print("¿HAY ARRASTRE? — misma pregunta en instantes AL AZAR, misma distancia")
    print("=" * 96)
    print(f"  control: n={len(CD)}   llegan en {SEGUIMIENTO//60}h: {100*CR.mean():.1f}%")
    print(f"\n  {'le faltaba':>12} {'tras una llegada':>26} {'al azar':>22} {'dif':>8}")
    for (lab, n1, p1, t1), (_, n2, p2, _) in zip(bandas(D, R, E), bandas(CD, CR)):
        s1 = f"{100*p1:5.1f}%  (n={n1})" if p1 is not None else f"(pocas, n={n1})"
        s2 = f"{100*p2:5.1f}%  (n={n2})" if p2 is not None else f"(pocas, n={n2})"
        dif = f"{100*(p1-p2):+.1f}" if (p1 is not None and p2 is not None) else "—"
        extra = f"  tarda {t1:.0f}min" if t1 is not None and np.isfinite(t1) else ""
        print(f"  {lab:>12} {s1:>26} {s2:>22} {dif:>8}{extra}")

    # ------------------------------------------------------------------
    # 3. ¿Importa la INTENSIDAD? (varias llegadas juntas = movimiento de mercado)
    # ------------------------------------------------------------------
    print("\n" + "=" * 96)
    print("INTENSIDAD: ¿cambia algo si llegan VARIAS a la vez?")
    print("=" * 96)
    tiempos = np.array([d["t_meta"] for d in disparos], dtype=np.float64)
    ID, IR, IN = [], [], []
    for L in disparos:
        T = L["t_meta"]
        if T + SEGUIMIENTO * 60_000 > t_fin:
            continue
        prev = int(((tiempos >= T - 30 * 60_000) & (tiempos <= T)).sum())
        for g in filas:
            if g["symbol"] == L["symbol"]:
                continue
            if not (g["ts_open"] <= T <= g["ts_open"] + 24 * 3600_000):
                continue
            if g["t_meta"] is not None and g["t_meta"] <= T:
                continue
            a = kl.get(g["symbol"])
            if a is None:
                continue
            p = precio_en(a, T)
            if p is None or p <= 0:
                continue
            falta = (g["nivel"] / p - 1) * 100.0
            if falta <= 0 or falta > 3.0:
                continue          # banda fija: comparar peras con peras
            ID.append(prev)
            IR.append(llega_en(a, T, T + SEGUIMIENTO * 60_000, g["nivel"]) is not None)
    ID, IR = np.array(ID), np.array(IR, dtype=float)
    if len(ID) >= MIN_N:
        print("  (solo seguidoras a menos de 3% de su meta, para aislar la intensidad)")
        print(f"  {'llegadas en 30min':>20} {'n':>7} {'la seguidora llega':>20}")
        for lo, hi, lab in [(0, 3, "1-2"), (3, 6, "3-5"), (6, 12, "6-11"),
                            (12, 999, "12 o mas")]:
            m = (ID >= lo) & (ID < hi)
            if m.sum() < MIN_N:
                print(f"  {lab:>20} {int(m.sum()):>7}   (pocas)")
                continue
            print(f"  {lab:>20} {int(m.sum()):>7} {100*IR[m].mean():>19.1f}%")

    print("\n" + "=" * 96)
    print("EJEMPLOS: ultimas 12 llegadas y su seguidora mas cercana")
    print("=" * 96)
    print(f"  {'hora GT':>12} {'llego':>10} {'seguidora':>10} {'le faltaba':>11} "
          f"{'llego?':>7} {'tardo':>9} {'abiertas':>9}")
    for L, (sym, falta, t_ll) in [(e[0], e[1]) for e in ejemplos[-12:]]:
        n_ab = [e[2] for e in ejemplos if e[0] is L][0]
        esp = f"{(t_ll - L['t_meta'])/60_000:.0f}min" if t_ll else "—"
        print(f"  {gt(L['t_meta']):>12} {L['symbol'].replace('USDT',''):>10} "
              f"{sym.replace('USDT',''):>10} {falta:>10.2f}% "
              f"{'si' if t_ll else 'no':>7} {esp:>9} {n_ab:>9}")


if __name__ == "__main__":
    main()
