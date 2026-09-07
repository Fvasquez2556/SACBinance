# -*- coding: utf-8 -*-
"""
¿Hay filo, o solo hubo mercado alcista?

La pregunta que ningun informe anterior contesta. Todo lo medido hasta ahora
compara las senales del sistema contra "un instante cualquiera", y eso solo
dice que el sistema elige mejor que el azar. No dice lo unico que importa:

    ¿se gana MAS que sin hacer nada?

En 2.7 dias de mercado subiendo, comprar casi cualquier cosa funciona. Un
57.9% de aciertos puede ser habilidad o puede ser la marea. Se distingue con
dos referencias que hay que batir:

  BENCHMARK 1 — las mismas monedas, sin TP ni SL
      Entrar donde entro el sistema y aguantar 24h. Si esto rinde igual o
      mas, toda la maquinaria de TP/SL no aporta nada.

  BENCHMARK 2 — moneda al azar, momento al azar
      Mismas reglas de salida, eleccion aleatoria. Si esto rinde igual, la
      SELECCION no aporta nada y el sistema es un generador de ruido caro.

Se descuentan comisiones (0.2% ida y vuelta, spot). No se modela deslizamiento:
en pares de poca liquidez seria peor de lo que sale aqui, nunca mejor.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
FEE = 0.2            # ida y vuelta, spot
VENTANA_H = 24


def cargar(con):
    d = defaultdict(list)
    for s, t, h, l, c in con.execute(
            "SELECT symbol, open_time, h, l, c FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        d[s].append((t, h, l, c))
    return {s: np.array(v, dtype=np.float64) for s, v in d.items()}


def simular(a, i0, entry, stop_pct):
    """
    Devuelve (retorno_bruto_pct, motivo) aplicando: sale al tocar META,
    al tocar el stop, o al agotarse la ventana. Si el stop es None, aguanta.
    """
    fin = min(i0 + VENTANA_H * 60, len(a))
    if fin - i0 < 10:
        return None, None
    seg = a[i0:fin]
    obj = entry * (1 + META / 100.0)
    stp = entry * (1 - stop_pct / 100.0) if stop_pct else None
    for fila in seg:
        _, hi, lo, cl = fila
        # Peor caso dentro de la vela: si toca los dos, se asume que salta el stop
        if stp is not None and lo <= stp:
            return -stop_pct, "STOP"
        if hi >= obj:
            return META, "META"
    return (float(seg[-1][3]) / entry - 1) * 100.0, "VENTANA"


def resumen(nombre, rets):
    if len(rets) < 30:
        print(f"  {nombre:<44} (pocas: {len(rets)})")
        return None
    r = np.array(rets)
    neto = r - FEE
    med = neto.mean()
    tot = neto.sum()
    gan = (neto > 0).sum()
    print(f"  {nombre:<44} {len(r):>5} ops  "
          f"media {med:>+6.2f}%  acierto {100*gan/len(r):>5.1f}%  "
          f"suma {tot:>+8.1f}%")
    return med


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    kl = cargar(con)
    filas = [dict(r) for r in con.execute(
        "SELECT symbol, ts_open, entry, score, tier, vol_24h, sombra "
        "FROM outcomes WHERE entry IS NOT NULL AND sombra=0 ORDER BY ts_open")]

    t_fin = max(a[-1, 0] for a in kl.values())
    print(f"{len(filas)} senales, {len(kl)} pares\n")

    # --- Marcar el patron en el instante de cada senal ---
    for f in filas:
        a = kl.get(f["symbol"])
        f["i"] = None
        f["conf"] = False
        if a is None:
            continue
        i = int(np.searchsorted(a[:, 0], f["ts_open"], side="right")) - 1
        if i < 48 or a[i, 0] + VENTANA_H * 3600_000 > t_fin:
            continue
        f["i"] = i
        seg, prev = a[i - 7:i + 1], a[i - 47:i - 7]
        pico, suelo = prev[:, 1].max(), seg[:, 2].min()
        if pico <= 0 or suelo <= 0:
            continue
        caida = (suelo - pico) / pico * 100.0
        rebote = (a[i, 3] - suelo) / suelo * 100.0
        f["conf"] = caida <= -2.0 and rebote >= 1.0

    usables = [f for f in filas if f["i"] is not None]
    print(f"{len(usables)} con 24h de futuro completas\n")

    print("=" * 92)
    print(f"ESTRATEGIA: entrar en la senal, salir a +{META}% / stop / {VENTANA_H}h")
    print(f"(comisiones {FEE}% descontadas; sin deslizamiento)")
    print("=" * 92)

    for stop in (1.2, 2.0, 3.2, None):
        etq = f"stop -{stop}%" if stop else "sin stop"
        rets = []
        for f in usables:
            r, _ = simular(kl[f["symbol"]], f["i"], f["entry"], stop)
            if r is not None:
                rets.append(r)
        resumen(f"todas las senales, {etq}", rets)

    print()
    for stop in (1.2, 2.0, 3.2, None):
        etq = f"stop -{stop}%" if stop else "sin stop"
        rets = []
        for f in usables:
            if not f["conf"]:
                continue
            r, _ = simular(kl[f["symbol"]], f["i"], f["entry"], stop)
            if r is not None:
                rets.append(r)
        resumen(f"solo patron confirmado, {etq}", rets)

    # --- BENCHMARK 1: mismas monedas, sin TP ni SL ---
    print("\n" + "=" * 92)
    print("BENCHMARK 1 — las MISMAS monedas, entrando igual, pero SIN TP ni SL")
    print("=" * 92)
    rets = []
    for f in usables:
        a = kl[f["symbol"]]
        fin = min(f["i"] + VENTANA_H * 60, len(a))
        if fin - f["i"] < 10:
            continue
        rets.append((float(a[fin - 1, 3]) / f["entry"] - 1) * 100.0)
    b1 = resumen("comprar y aguantar 24h", rets)
    rets_c = []
    for f in usables:
        if not f["conf"]:
            continue
        a = kl[f["symbol"]]
        fin = min(f["i"] + VENTANA_H * 60, len(a))
        if fin - f["i"] < 10:
            continue
        rets_c.append((float(a[fin - 1, 3]) / f["entry"] - 1) * 100.0)
    resumen("idem, solo patron confirmado", rets_c)

    # --- BENCHMARK 2: moneda al azar, momento al azar ---
    print("\n" + "=" * 92)
    print("BENCHMARK 2 — moneda AL AZAR en momento AL AZAR, mismas salidas")
    print("=" * 92)
    rng = np.random.default_rng(3)
    syms = [s for s, a in kl.items() if len(a) > VENTANA_H * 60 + 100]
    for stop in (1.2, 2.0, None):
        rets = []
        for _ in range(3000):
            s = syms[int(rng.integers(0, len(syms)))]
            a = kl[s]
            i = int(rng.integers(48, len(a) - VENTANA_H * 60 - 1))
            r, _ = simular(a, i, float(a[i, 3]), stop)
            if r is not None:
                rets.append(r)
        etq = f"stop -{stop}%" if stop else "sin stop"
        resumen(f"azar, {etq}", rets)
    rets = []
    for _ in range(3000):
        s = syms[int(rng.integers(0, len(syms)))]
        a = kl[s]
        i = int(rng.integers(48, len(a) - VENTANA_H * 60 - 1))
        rets.append((float(a[i + VENTANA_H * 60, 3]) / float(a[i, 3]) - 1) * 100.0)
    resumen("azar, comprar y aguantar 24h", rets)

    # --- El contexto que lo explica todo ---
    print("\n" + "=" * 92)
    print("CONTEXTO: ¿que hizo el mercado en la ventana medida?")
    print("=" * 92)
    subs = []
    for s, a in kl.items():
        if len(a) < 100:
            continue
        subs.append((float(a[-1, 3]) / float(a[0, 3]) - 1) * 100.0)
    subs = np.array(subs)
    print(f"  {len(subs)} pares, de principio a fin de los datos:")
    print(f"    mediana {np.median(subs):+.2f}%   "
          f"suben {100*(subs > 0).mean():.0f}% de los pares")
    print(f"    p25 {np.percentile(subs, 25):+.2f}%   "
          f"p75 {np.percentile(subs, 75):+.2f}%")
    print("\n  Si la mediana es claramente positiva, todo lo de arriba se midio")
    print("  en un mercado alcista y NO dice nada sobre uno bajista.")


if __name__ == "__main__":
    main()
