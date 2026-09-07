# -*- coding: utf-8 -*-
"""
¿Hay filo, o solo hubo mercado?

Este es el informe que manda. Todos los demas comparan las senales contra "un
instante cualquiera", lo que solo dice que el sistema elige mejor que el azar
al tocar un umbral. No dice si se gana MAS QUE SIN HACER NADA.

En un mercado que sube, comprar casi cualquier cosa funciona. Un 57.9% de
aciertos puede ser habilidad o puede ser la marea. Se distingue con dos
referencias que hay que batir:

  AZAR         moneda al azar, momento al azar, mismas reglas de salida.
               Si la estrategia no lo bate, la SELECCION no aporta nada.

  AGUANTAR     las mismas monedas y los mismos momentos, pero sin TP ni SL.
               Si no lo bate, la maquinaria de entrada y salida no aporta nada.

Ambas referencias se sacan de la MISMA ventana de tiempo que las senales, para
que el regimen de mercado sea el mismo y la comparacion sea limpia.

El intervalo se calcula por bootstrap y no con la formula normal: los retornos
por operacion tienen cola larga —una senal puede hacer +50%— y la aproximacion
normal daria un intervalo demasiado estrecho, que es la forma educada de
mentir.

Uso
---
    python analyze_edge.py                 # todo lo que haya
    python analyze_edge.py --dias 1        # ultimas 24h
    python analyze_edge.py --periodo previa
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

DB = str(Path(__file__).resolve().parent / "data" / "sacbinance.db")
META = 3.2
FEE = 0.2               # ida y vuelta, spot
VENTANA_H = 24          # cuanto se aguanta una operacion
TZ_OFFSET_H = -6        # Guatemala
N_AZAR = 4000
BOOT = 2000
MIN_N = 30


def _local(ts_ms: int) -> dt.datetime:
    return dt.datetime.utcfromtimestamp(ts_ms / 1000) + dt.timedelta(hours=TZ_OFFSET_H)


def _ms_desde_local(local: dt.datetime) -> int:
    return int((local - dt.timedelta(hours=TZ_OFFSET_H)
                - dt.datetime(1970, 1, 1)).total_seconds() * 1000)


def rango_periodo(nombre: str) -> tuple:
    hoy = _local(int(time.time() * 1000)).date()
    if nombre == "hoy":
        ini = dt.datetime.combine(hoy, dt.time.min)
        return _ms_desde_local(ini), _ms_desde_local(ini + dt.timedelta(days=1))
    if nombre == "semana":
        lun = hoy - dt.timedelta(days=hoy.weekday())
        ini = dt.datetime.combine(lun, dt.time.min)
        return _ms_desde_local(ini), _ms_desde_local(ini + dt.timedelta(days=7))
    if nombre == "previa":
        lun = hoy - dt.timedelta(days=hoy.weekday() + 7)
        ini = dt.datetime.combine(lun, dt.time.min)
        return _ms_desde_local(ini), _ms_desde_local(ini + dt.timedelta(days=7))
    if nombre == "finde":
        sab = hoy - dt.timedelta(days=(hoy.weekday() - 5) % 7)
        ini = dt.datetime.combine(sab, dt.time.min)
        return _ms_desde_local(ini), _ms_desde_local(ini + dt.timedelta(days=2))
    return 0, 1 << 62


def cargar_klines(con) -> dict:
    d = defaultdict(list)
    for s, t, h, l, c in con.execute(
            "SELECT symbol, open_time, h, l, c FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        d[s].append((t, h, l, c))
    return {s: np.array(v, dtype=np.float64) for s, v in d.items()}


def simular(a: np.ndarray, i0: int, entry: float, stop_pct):
    """
    Retorno bruto de una operacion: sale al tocar META, al tocar el stop, o al
    agotarse la ventana. Cuando una vela toca los dos, se asume el stop — el
    peor caso, porque con velas de 1m no se sabe cual ocurrio antes y suponer
    lo contrario inflaria el resultado.
    """
    fin = min(i0 + VENTANA_H * 60, len(a))
    if fin - i0 < 10:
        return None
    seg = a[i0:fin]
    obj = entry * (1 + META / 100.0)
    stp = entry * (1 - stop_pct / 100.0) if stop_pct else None
    for _, hi, lo, cl in seg:
        if stp is not None and lo <= stp:
            return -stop_pct
        if hi >= obj:
            return META
    return (float(seg[-1][3]) / entry - 1) * 100.0


def boot_ci(x: np.ndarray, rng, reps: int = BOOT) -> tuple:
    """Intervalo del 90% de la media, por remuestreo."""
    if len(x) < 5:
        return float("nan"), float("nan")
    idx = rng.integers(0, len(x), size=(reps, len(x)))
    medias = x[idx].mean(axis=1)
    return float(np.percentile(medias, 5)), float(np.percentile(medias, 95))


def acierto_sin_filo(stop_pct) -> float:
    """
    Tasa de acierto que sale SOLO de la geometria, sin ninguna habilidad.

    En un paseo aleatorio la probabilidad de tocar +A antes que -B es
    B/(A+B). Sin esta referencia, un "62% de aciertos" parece bueno cuando es
    exactamente lo que da un stop de -3.2% contra un objetivo de +3.2%
    tirando una moneda. El % de acierto se fabrica moviendo el stop: solo
    significa algo comparado con su propia geometria.
    """
    if not stop_pct:
        return float("nan")
    return 100.0 * stop_pct / (META + stop_pct)


def linea(nombre, rets, rng, base_media=None, stop_pct=None):
    if len(rets) < MIN_N:
        print(f"  {nombre:<38} (pocas: {len(rets)})")
        return None
    r = np.array(rets) - FEE
    m = r.mean()
    lo, hi = boot_ci(r, rng)
    extra = ""
    if base_media is not None:
        extra = f"  vs referencia {m - base_media:+6.2f}"
    ac = 100 * (r > 0).mean()
    geo = acierto_sin_filo(stop_pct)
    ref = f" (sin filo {geo:.0f}%)" if geo == geo else ""
    print(f"  {nombre:<38} {len(r):>5} ops  {m:>+6.2f}%  "
          f"[{lo:>+5.2f}, {hi:>+5.2f}]  acierto {ac:>4.1f}%{ref}{extra}")
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dias", type=float, default=None)
    ap.add_argument("--periodo", choices=["hoy", "finde", "semana", "previa"])
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rng = np.random.default_rng(20260907)

    if args.periodo:
        t0, t1 = rango_periodo(args.periodo)
        etiqueta = f"periodo {args.periodo}"
    elif args.dias:
        t1 = int(time.time() * 1000)
        t0 = t1 - int(args.dias * 86400_000)
        etiqueta = f"ultimos {args.dias:g} dias"
    else:
        t0, t1 = 0, 1 << 62
        etiqueta = "todo el historico"

    kl = cargar_klines(con)
    if not kl:
        print("Sin velas 1m: no se puede evaluar.")
        return
    t_fin = max(a[-1, 0] for a in kl.values())

    filas = [dict(r) for r in con.execute(
        "SELECT symbol, ts_open, entry, score, tier, vol_24h FROM outcomes "
        "WHERE sombra=0 AND entry IS NOT NULL AND ts_open >= ? AND ts_open < ? "
        "ORDER BY ts_open", (t0, t1))]

    usables = []
    for f in filas:
        a = kl.get(f["symbol"])
        if a is None:
            continue
        i = int(np.searchsorted(a[:, 0], f["ts_open"], side="right")) - 1
        if i < 48 or a[i, 0] + VENTANA_H * 3600_000 > t_fin:
            continue
        f["i"] = i
        seg, prev = a[i - 7:i + 1], a[i - 47:i - 7]
        pico, suelo = prev[:, 1].max(), seg[:, 2].min()
        if pico > 0 and suelo > 0:
            caida = (suelo - pico) / pico * 100.0
            rebote = (a[i, 3] - suelo) / suelo * 100.0
            f["conf"] = caida <= -2.0 and rebote >= 1.0
        else:
            f["conf"] = False
        usables.append(f)

    print("=" * 92)
    print(f"  ¿HAY FILO, O SOLO HUBO MERCADO?   —   {etiqueta}")
    print("=" * 92)
    print(f"  {len(filas)} senales en el periodo, {len(usables)} con "
          f"{VENTANA_H}h de futuro completas")
    if len(usables) < MIN_N:
        print("\n  Muestra insuficiente para un veredicto. Hacen falta al menos "
              f"{MIN_N} operaciones cerradas.")
        return
    print(f"  Salida: +{META}% / stop / {VENTANA_H}h. "
          f"Comisiones {FEE}% descontadas, sin deslizamiento.")
    print("  El intervalo es del 90%, por bootstrap.\n")

    # Ventana temporal real para que el azar se muestree del mismo regimen
    ts_min = min(f["ts_open"] for f in usables)
    ts_max = max(f["ts_open"] for f in usables)

    # --- Referencias ---
    print("  REFERENCIAS")
    print("  " + "-" * 88)
    aguantar = []
    for f in usables:
        a = kl[f["symbol"]]
        fin = min(f["i"] + VENTANA_H * 60, len(a))
        if fin - f["i"] >= 10:
            aguantar.append((float(a[fin - 1, 3]) / f["entry"] - 1) * 100.0)
    ref_aguantar = linea("AGUANTAR (mismas monedas, sin TP/SL)", aguantar, rng)

    syms = [s for s, a in kl.items() if len(a) > VENTANA_H * 60 + 100]
    azar_por_stop = {}
    for stop in (1.2, 2.0, 3.2, None):
        rets = []
        for _ in range(N_AZAR):
            s = syms[int(rng.integers(0, len(syms)))]
            a = kl[s]
            lo_i = int(np.searchsorted(a[:, 0], ts_min, side="left"))
            hi_i = int(np.searchsorted(a[:, 0], ts_max, side="right"))
            hi_i = min(hi_i, len(a) - VENTANA_H * 60 - 1)
            if hi_i <= lo_i + 48:
                continue
            i = int(rng.integers(lo_i + 48, hi_i))
            r = simular(a, i, float(a[i, 3]), stop)
            if r is not None:
                rets.append(r)
        etq = f"stop -{stop}%" if stop else "sin stop"
        azar_por_stop[stop] = linea(f"AZAR ({etq})", rets, rng, stop_pct=stop)

    # --- Estrategia ---
    print("\n  EL SISTEMA")
    print("  " + "-" * 88)
    mejor = None
    for stop in (1.2, 2.0, 3.2, None):
        rets = [r for r in (simular(kl[f["symbol"]], f["i"], f["entry"], stop)
                            for f in usables) if r is not None]
        etq = f"stop -{stop}%" if stop else "sin stop"
        m = linea(f"todas las senales ({etq})", rets, rng,
                  azar_por_stop.get(stop), stop_pct=stop)
        if m is not None and (mejor is None or m > mejor[1]):
            mejor = (etq, m, stop)

    conf = [f for f in usables if f["conf"]]
    if len(conf) >= MIN_N:
        print()
        for stop in (2.0, 3.2, None):
            rets = [r for r in (simular(kl[f["symbol"]], f["i"], f["entry"], stop)
                                for f in conf) if r is not None]
            etq = f"stop -{stop}%" if stop else "sin stop"
            linea(f"patron confirmado ({etq})", rets, rng,
                  azar_por_stop.get(stop), stop_pct=stop)
    else:
        print(f"\n  patron confirmado: solo {len(conf)} casos, no se reporta")

    # --- Contexto ---
    print("\n  QUE HIZO EL MERCADO EN ESTA VENTANA")
    print("  " + "-" * 88)
    subs = []
    for s, a in kl.items():
        i0 = int(np.searchsorted(a[:, 0], ts_min, side="left"))
        i1 = int(np.searchsorted(a[:, 0], ts_max, side="right")) - 1
        if i1 - i0 > 60 and a[i0, 3] > 0:
            subs.append((float(a[i1, 3]) / float(a[i0, 3]) - 1) * 100.0)
    if subs:
        subs = np.array(subs)
        print(f"  {len(subs)} pares: mediana {np.median(subs):+.2f}%   "
              f"suben {100*(subs > 0).mean():.0f}%   "
              f"p25 {np.percentile(subs, 25):+.2f}%  "
              f"p75 {np.percentile(subs, 75):+.2f}%")
        regimen = ("ALCISTA" if np.median(subs) > 0.5
                   else "BAJISTA" if np.median(subs) < -0.5 else "PLANO")
        print(f"  regimen: {regimen}")

    # --- Veredicto ---
    print("\n" + "=" * 92)
    print("  VEREDICTO")
    print("=" * 92)
    if mejor is None:
        print("  Sin muestra suficiente.")
        return
    etq, m, stop = mejor
    ref_azar = azar_por_stop.get(stop)
    partes = []
    if ref_azar is not None:
        d = m - ref_azar
        partes.append(f"{'BATE' if d > 0 else 'NO bate'} al azar por {d:+.2f}%/op")
    if ref_aguantar is not None:
        d2 = m - ref_aguantar
        partes.append(f"{'BATE' if d2 > 0 else 'NO bate'} a aguantar por {d2:+.2f}%/op")
    print(f"  Mejor variante: {etq}, {m:+.2f}% por operacion")
    for p in partes:
        print(f"    {p}")
    print("\n  Un filo por debajo de ~0.3%/op se lo come el deslizamiento en")
    print("  pares de poca liquidez, que aqui NO esta modelado.")
    print("\n  El % de acierto NO mide habilidad: se fabrica moviendo el stop.")
    print("  Con objetivo +3.2%, un stop de -9.6% da 75% de aciertos tirando")
    print("  una moneda, perdiendo el triple de lo que gana. Lo que no se")
    print("  puede fabricar es el valor esperado por operacion.")
    if subs is not None and len(subs) and abs(np.median(subs)) > 0.5:
        print(f"\n  AVISO: el mercado fue {regimen} en esta ventana. Cualquier")
        print("  resultado aqui dice poco sobre el regimen contrario.")


if __name__ == "__main__":
    main()
