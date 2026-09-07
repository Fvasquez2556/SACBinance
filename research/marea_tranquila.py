# -*- coding: utf-8 -*-
"""
Cuantas velas de quietud hacen falta para que la zona prediga una subida.

La pregunta la puso Felix asi: la "marea tranquila" es la zona donde el precio
se mueve pero SIN SESGO — sube tanto como baja y termina donde empezo. Lo que
hay que averiguar es cuantas velas, y de que timeframe, tienen que pasar en ese
estado para que sirva de aviso.

Definicion operativa
--------------------
Sobre las ultimas N velas del timeframe TF:

    rango      = (max high - min low) / min low * 100
    deriva     = (close final - open inicial) / open inicial * 100
    equilibrio = |deriva| / rango          <- el "1:1"

`equilibrio` cerca de 0 significa que se movio y volvio: marea. Cerca de 1
significa que todo el movimiento fue en una direccion, que es una tendencia
lenta y no una marea. Separar esos dos casos es justo el punto.

Disciplina
----------
- Grupo de control: la misma medida sobre TODOS los instantes, no solo sobre
  los detectados. Sin eso cualquier numero parece bueno.
- Deduplicacion: una zona tranquila que dura una hora dispara en cada vela.
  Contarlas todas infla la muestra con lo que en realidad es un solo evento.
  Solo cuenta la primera de cada racha.
- Nada de porcentajes por debajo de MIN_N casos.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
OBJETIVO = 3.2          # meta de referencia fijada por Felix
STOP_REF = 1.2          # para la version cobrable: llega arriba antes que abajo
HORIZONTES = (60, 180, 360)   # minutos hacia delante
MIN_N = 30              # menos que esto no se reporta como porcentaje
DEDUP_MIN = 60          # dos detecciones a menos de esto son el mismo evento

REJILLA_N = (5, 8, 10, 13, 15, 20, 30)
REJILLA_RANGO = (1.0, 1.5, 2.0, 3.0)      # rango maximo de la zona, %
REJILLA_EQUIL = (0.15, 0.30, 0.50)        # |deriva| / rango
REJILLA_CAIDA = (0.0, 2.0)                # caida previa exigida, %
TFS = (1, 3, 5)
CAIDA_LOOKBACK = 40     # velas TF hacia atras para buscar el pico previo


def cargar(con) -> dict:
    """symbol -> array de velas 1m ordenadas (open_time, o, h, l, c)."""
    datos = defaultdict(list)
    q = ("SELECT symbol, open_time, o, h, l, c FROM klines "
         "WHERE tf='1m' ORDER BY symbol, open_time")
    for sym, t, o, h, l, c in con.execute(q):
        datos[sym].append((t, o, h, l, c))
    out = {}
    for sym, filas in datos.items():
        if len(filas) < 800:
            continue
        a = np.array(filas, dtype=np.float64)
        # Pares con huecos grandes falsean las ventanas hacia delante
        d = np.diff(a[:, 0])
        if len(d) and (d > 5 * 60_000).sum() > len(d) * 0.02:
            continue
        out[sym] = a
    return out


def agregar(a: np.ndarray, tf: int):
    """Agrupa velas 1m en bloques de `tf` alineados al reloj.
    Devuelve (o, h, l, c, idx_1m_de_cierre) o None si no hay bastante."""
    if tf == 1:
        return a[:, 1], a[:, 2], a[:, 3], a[:, 4], np.arange(len(a))
    minuto = (a[:, 0] // 60_000).astype(np.int64)
    bloque = minuto // tf
    corte = np.flatnonzero(np.diff(bloque)) + 1
    inicios = np.concatenate(([0], corte))
    finales = np.concatenate((corte, [len(a)]))
    completos = (finales - inicios) == tf
    inicios, finales = inicios[completos], finales[completos]
    if len(inicios) < 50:
        return None
    o = a[inicios, 1]
    c = a[finales - 1, 4]
    h = np.array([a[i:f, 2].max() for i, f in zip(inicios, finales)])
    l = np.array([a[i:f, 3].min() for i, f in zip(inicios, finales)])
    return o, h, l, c, finales - 1


def rolling(x: np.ndarray, n: int, func) -> np.ndarray:
    """func sobre ventanas de n que TERMINAN en cada posicion. NaN al principio."""
    if len(x) < n:
        return np.full(len(x), np.nan)
    v = np.lib.stride_tricks.sliding_window_view(x, n)
    return np.concatenate((np.full(n - 1, np.nan), func(v, axis=1)))


def futuro(a: np.ndarray, h_min: int):
    """Para cada vela 1m: llega a +OBJETIVO% en las proximas h_min minutos, y
    llega antes de caer -STOP_REF%. Dos arrays booleanos."""
    n = len(a)
    high, low, close = a[:, 2], a[:, 3], a[:, 4]
    sube = np.zeros(n, dtype=bool)
    cobra = np.zeros(n, dtype=bool)
    if n <= h_min + 1:
        return sube, cobra
    vh = np.lib.stride_tricks.sliding_window_view(high[1:], h_min)
    vl = np.lib.stride_tricks.sliding_window_view(low[1:], h_min)
    m = len(vh)
    c0 = close[:m]
    hit_up = vh >= (c0 * (1 + OBJETIVO / 100.0))[:, None]
    hit_dn = vl <= (c0 * (1 - STOP_REF / 100.0))[:, None]
    any_up = hit_up.any(axis=1)
    any_dn = hit_dn.any(axis=1)
    i_up = np.where(any_up, hit_up.argmax(axis=1), h_min + 1)
    i_dn = np.where(any_dn, hit_dn.argmax(axis=1), h_min + 1)
    sube[:m] = any_up
    cobra[:m] = any_up & (i_up < i_dn)
    return sube, cobra


def main() -> None:
    con = sqlite3.connect(DB)
    print("cargando velas 1m...", flush=True)
    pares = cargar(con)
    print(f"{len(pares)} pares con datos utilizables\n", flush=True)

    fut, base = {}, {}
    for h in HORIZONTES:
        tot = subio = cobro = 0
        for sym, a in pares.items():
            s, c = futuro(a, h)
            fut[(sym, h)] = (s, c)
            valido = len(a) - h - 1
            if valido <= 0:
                continue
            tot += valido
            subio += int(s[:valido].sum())
            cobro += int(c[:valido].sum())
        base[h] = (subio / tot, cobro / tot, tot)
        print(f"CONTROL  horizonte {h:3}min: desde un instante cualquiera llega "
              f"a +{OBJETIVO}% el {100*subio/tot:5.2f}%   y antes de -{STOP_REF}% "
              f"el {100*cobro/tot:5.2f}%   (n={tot:,})")
    print(flush=True)

    print("midiendo zonas...", flush=True)
    zonas = {}
    for sym, a in pares.items():
        for tf in TFS:
            ag = agregar(a, tf)
            if ag is None:
                continue
            o, hi, lo, c, idx = ag
            pico = rolling(hi, CAIDA_LOOKBACK, np.max)
            for N in REJILLA_N:
                if len(c) < N + CAIDA_LOOKBACK + 5:
                    continue
                mx = rolling(hi, N, np.max)
                mn = rolling(lo, N, np.min)
                with np.errstate(invalid="ignore", divide="ignore"):
                    rango = (mx - mn) / mn * 100.0
                    o_ini = np.concatenate((np.full(N - 1, np.nan),
                                            o[: len(o) - N + 1]))
                    deriv = (c - o_ini) / o_ini * 100.0
                    equil = np.abs(deriv) / np.where(rango > 0, rango, np.nan)
                    pico_prev = np.concatenate((np.full(N, np.nan),
                                                pico[: len(pico) - N]))
                    caida = (mn - pico_prev) / pico_prev * 100.0
                zonas[(sym, tf, N)] = (rango, equil, caida, idx)
    print(f"listo: {len(zonas)} series\n", flush=True)

    filas = []
    for tf in TFS:
        for N in REJILLA_N:
            for rmax in REJILLA_RANGO:
                for emax in REJILLA_EQUIL:
                    for cmin in REJILLA_CAIDA:
                        det = defaultdict(int)
                        up = defaultdict(int)
                        cb = defaultdict(int)
                        for sym, a in pares.items():
                            z = zonas.get((sym, tf, N))
                            if z is None:
                                continue
                            rango, equil, caida, idx = z
                            ok = ((rango <= rmax) & (equil <= emax)
                                  & np.isfinite(equil))
                            if cmin > 0:
                                ok &= (caida <= -cmin)
                            pos = idx[ok].astype(int)
                            if len(pos) == 0:
                                continue
                            keep = [pos[0]]
                            for p in pos[1:]:
                                if p - keep[-1] >= DEDUP_MIN:
                                    keep.append(p)
                            keep = np.array(keep)
                            for h in HORIZONTES:
                                k = keep[keep < len(a) - h - 1]
                                if len(k) == 0:
                                    continue
                                s, c = fut[(sym, h)]
                                det[h] += len(k)
                                up[h] += int(s[k].sum())
                                cb[h] += int(c[k].sum())
                        for h in HORIZONTES:
                            if det[h] >= MIN_N:
                                filas.append({
                                    "tf": tf, "N": N, "rango": rmax,
                                    "equil": emax, "caida": cmin, "h": h,
                                    "n": det[h],
                                    "p_sube": up[h] / det[h],
                                    "p_cobra": cb[h] / det[h],
                                    "lift": up[h] / det[h] - base[h][0],
                                    "lift_c": cb[h] / det[h] - base[h][1],
                                })

    if not filas:
        print("ninguna combinacion alcanzo el minimo de muestras")
        return

    def imprime(titulo, orden, top=18):
        print("=" * 102)
        print(titulo)
        print("=" * 102)
        print(f"  {'TF':>3} {'N':>3} {'dura':>6} {'rango':>6} {'equil':>6} "
              f"{'caida':>6} {'horiz':>6} {'n':>6} {'llega':>7} {'base':>7} "
              f"{'lift':>7} {'cobra':>7} {'lift':>7}")
        for f in sorted(filas, key=orden, reverse=True)[:top]:
            cai = f"-{f['caida']:.0f}%" if f["caida"] else "no"
            print(f"  {f['tf']:>2}m {f['N']:>3} {f['tf']*f['N']:>5}m "
                  f"{f['rango']:>5.1f}% {f['equil']:>6.2f} {cai:>6} "
                  f"{f['h']:>5}m {f['n']:>6} {100*f['p_sube']:>6.1f}% "
                  f"{100*base[f['h']][0]:>6.1f}% {100*f['lift']:>+6.1f} "
                  f"{100*f['p_cobra']:>6.1f}% {100*f['lift_c']:>+6.1f}")
        print()

    imprime("MEJORES POR LIFT EN 'LLEGA A +3.2%'", lambda f: f["lift"])
    imprime("MEJORES POR LIFT EN 'LLEGA ANTES DE CAER -1.2%' (la version cobrable)",
            lambda f: f["lift_c"])
    imprime("MEJORES CON MUESTRA GRANDE (n>=300, por lift cobrable)",
            lambda f: (f["lift_c"] if f["n"] >= 300 else -9))

    print("=" * 102)
    print("CUANTAS VELAS: mejor lift cobrable para cada (TF, N)")
    print("=" * 102)
    print(f"  {'TF':>4} {'N velas':>8} {'duracion':>9} {'n':>7} {'cobra':>8} "
          f"{'lift':>8} {'rango':>7} {'equil':>6} {'caida':>6} {'horiz':>6}")
    for tf in TFS:
        for N in REJILLA_N:
            cand = [f for f in filas if f["tf"] == tf and f["N"] == N]
            if not cand:
                continue
            b = max(cand, key=lambda f: f["lift_c"])
            cai = f"-{b['caida']:.0f}%" if b["caida"] else "no"
            print(f"  {tf:>3}m {N:>8} {tf*N:>8}m {b['n']:>7} "
                  f"{100*b['p_cobra']:>7.1f}% {100*b['lift_c']:>+7.1f} "
                  f"{b['rango']:>6.1f}% {b['equil']:>6.2f} {cai:>6} {b['h']:>5}m")


if __name__ == "__main__":
    main()
