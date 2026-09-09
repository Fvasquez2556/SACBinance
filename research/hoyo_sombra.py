# -*- coding: utf-8 -*-
"""
El informe de la sombra del hoyo. Para el sabado.

`research/entrada_en_el_hoyo.py` simulo la regla hacia atras, sobre datos que
ya habiamos visto, y de cinco variantes eligio la mejor. Eso no demuestra
nada: es el mismo error que ya cometimos con la variable "clima" y con el
filtro de calidad en sombra.

Este script lee lo que el sistema fue anotando EN VIVO desde el 9-sep, sin
saber lo que venia despues. Si los numeros de la simulacion se repiten aqui
sobre dias que no habiamos visto, la regla es real. Si se desinflan, era el
clima de esos tres dias.

Se separa siempre en dos: lo anotado ANTES del corte (los dias que ya
habiamos mirado) y lo anotado DESPUES. Solo la segunda mitad es prueba.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
from src.analysis import hoyo          # noqa: E402
from src.config.settings import get_settings  # noqa: E402

DB = "data/sacbinance.db"
TZ = -6

# El momento en que se desplego la medicion. Todo lo anterior es NULL, y todo
# lo inmediatamente posterior lo elegimos habiendo visto los datos del 6 al 9.
CORTE = "2026-09-09"


def gt(ms):
    return (dt.datetime.utcfromtimestamp(ms / 1000)
            + dt.timedelta(hours=TZ)).strftime("%d/%m %H:%M")


def pct(n, d):
    return f"{100*n/d:4.1f}%" if d else "   -"


def boot_ci(x, pares, rng, n=2000):
    """Bootstrap agrupado por par. El 84% de las señales solapa con otra del
    mismo par, asi que remuestrear operaciones sueltas estrecha el intervalo
    de forma artificial."""
    if len(x) < 10:
        return float("nan"), float("nan")
    g = defaultdict(list)
    for v, p in zip(x, pares):
        g[p].append(v)
    arrs = [np.array(v) for v in g.values()]
    m = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(arrs), len(arrs))
        m[i] = np.concatenate([arrs[j] for j in pick]).mean()
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def resultado_sistema(f):
    """Lo que habria dado entrar al precio de la señal, como hace hoy."""
    e = f["entry"]
    tp, sl = f.get("ms_tp"), f.get("ms_sl")
    if sl is not None and (tp is None or sl <= tp):
        return f["sl_pct"]
    if tp is not None:
        return f["tp_pct"]
    u = f.get("precio_ultimo")
    return (u - e) / e * 100.0 if u else None


def bloque(titulo, filas, rng):
    print()
    print("=" * 98)
    print(titulo)
    print("=" * 98)
    n = len(filas)
    if not n:
        print("  (sin señales en este tramo)")
        return
    entraron = [f for f in filas if f.get("hoyo_fill")]
    completas = [f for f in filas if f["cerrado"]]
    print(f"  {n} señales con la sombra activa   |   ventana cerrada: {len(completas)}")
    print(f"  el precio bajo hasta el hoyo en {len(entraron)} ({pct(len(entraron), n)})")
    if len(entraron) < 10:
        print("  (muy pocas entradas para medir)")
        return

    print()
    print(f"  {'regla':<34} {'ops':>5} {'TP':>7} {'SL':>7} {'abierta':>8} "
          f"{'media':>8} {'IC 95%':>18}")

    res_sis = [(r, f["symbol"]) for f in filas
               if (r := resultado_sistema(f)) is not None]
    if res_sis:
        v = [r for r, _ in res_sis]
        lo, hi = boot_ci(v, [p for _, p in res_sis], rng)
        tp = sum(1 for f in filas if f.get("ms_tp") is not None
                 and (f.get("ms_sl") is None or f["ms_tp"] < f["ms_sl"]))
        sl = sum(1 for f in filas if f.get("ms_sl") is not None
                 and (f.get("ms_tp") is None or f["ms_sl"] <= f["ms_tp"]))
        print(f"  {'SISTEMA (entrar en la señal)':<34} {len(v):>5} "
              f"{pct(tp, len(v)):>7} {pct(sl, len(v)):>7} "
              f"{pct(len(v)-tp-sl, len(v)):>8} "
              f"{np.mean(v):>7.2f}% [{lo:>6.2f}, {hi:>6.2f}]")

    nombres = {"a": "A  mismo % bajo la entrada",
               "c2": "C2 stop fijo -2.0%",
               "c3": "C3 stop fijo -3.0%"}
    for regla in hoyo.REGLAS:
        vals, pares = [], []
        for f in entraron:
            r = hoyo.resultado(f, regla)
            if r is not None:
                vals.append(r)
                pares.append(f["symbol"])
        if len(vals) < 10:
            continue
        tp = sum(1 for f in entraron if f.get(f"hoyo_{regla}") == "TP")
        sl = sum(1 for f in entraron if f.get(f"hoyo_{regla}") == "SL")
        lo, hi = boot_ci(vals, pares, rng)
        print(f"  {nombres[regla]:<34} {len(vals):>5} {pct(tp, len(vals)):>7} "
              f"{pct(sl, len(vals)):>7} {pct(len(vals)-tp-sl, len(vals)):>8} "
              f"{np.mean(vals):>7.2f}% [{lo:>6.2f}, {hi:>6.2f}]")

    # --- las celdas ---------------------------------------------------
    print()
    print("  POR CELDA (regla C3) — velocidad de la bajada x ancho del stop")
    print(f"  {'celda':<20} {'ops':>5} {'TP':>7} {'llega a +3.2%':>15} "
          f"{'media':>8} {'IC 95%':>18}")
    s = get_settings()
    for celda in ("LENTO_ANCHO", "RAPIDO_ANCHO", "LENTO_ESTRECHO", "RAPIDO_ESTRECHO"):
        sub = [f for f in entraron if f.get("hoyo_celda") == celda]
        vals = [r for f in sub if (r := hoyo.resultado(f, "c3")) is not None]
        if len(vals) < 10:
            print(f"  {celda:<20} {len(sub):>5}   (pocas)")
            continue
        tp = sum(1 for f in sub if f.get("hoyo_c3") == "TP")
        m32 = sum(1 for f in sub if (f.get("hoyo_mfe_pct") or 0) >= s.objetivo_operador_pct)
        lo, hi = boot_ci(vals, [f["symbol"] for f in sub], rng)
        print(f"  {celda:<20} {len(vals):>5} {pct(tp, len(vals)):>7} "
              f"{pct(m32, len(vals)):>15} {np.mean(vals):>7.2f}% [{lo:>6.2f}, {hi:>6.2f}]")

    # --- de donde sale el dinero --------------------------------------
    print()
    print("  DE DONDE SALE EL RESULTADO (regla C3)")
    g = defaultdict(list)
    for f in entraron:
        r = hoyo.resultado(f, "c3")
        if r is not None:
            g[f.get("hoyo_c3") or "ABIERTA"].append(r)
    tot = sum(len(v) for v in g.values())
    for k in ("TP", "SL", "ABIERTA"):
        if not g[k]:
            continue
        a = np.array(g[k])
        print(f"     {k:<9} n={len(a):>4} ({pct(len(a), tot)})  media {a.mean():>+6.2f}%"
              f"   aporta {a.sum()/tot:>+6.3f} pts")
    todos = np.concatenate([np.array(v) for v in g.values() if len(v)])
    if len(todos) > 5:
        print(f"     quitando las 5 mejores: media "
              f"{np.sort(todos)[:-5].mean():+.2f}%  (con ellas {todos.mean():+.2f}%)")


def main():
    rng = np.random.default_rng(20260913)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    filas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND hoyo_disparo IS NOT NULL "
        "ORDER BY ts_open")]
    if not filas:
        print("Todavia no hay ninguna señal con la sombra del hoyo activa.")
        return
    print(f"{len(filas)} señales con la sombra activa, "
          f"de {gt(filas[0]['ts_open'])} a {gt(filas[-1]['ts_open'])} GT")
    print(f"corte de validacion: todo lo emitido despues del {CORTE} es")
    print(f"terreno que no habiamos visto cuando se eligio la regla.")

    corte_ms = int(dt.datetime.strptime(CORTE, "%Y-%m-%d")
                   .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    antes = [f for f in filas if f["ts_open"] < corte_ms + 86400000]
    despues = [f for f in filas if f["ts_open"] >= corte_ms + 86400000]

    bloque("A. LO QUE YA HABIAMOS VISTO (9-sep) — no demuestra nada", antes, rng)
    bloque("B. TERRENO NUEVO (del 10-sep en adelante) — esto SI es prueba",
           despues, rng)
    bloque("C. TODO JUNTO", filas, rng)

    print()
    print("=" * 98)
    print("COMO LEER ESTO")
    print("=" * 98)
    print("  La simulacion hacia atras dio, sobre 1128 entradas:")
    print("     SISTEMA  -0.26%/op  [-0.40, -0.11]     A  +0.04%  [-0.11, +0.19]")
    print("     C2       +0.09%/op  [-0.10, +0.26]     C3 +0.25%  [+0.05, +0.46]")
    print("     celda LENTO_ANCHO con C3: +0.65% [+0.14, +1.16], n=180")
    print()
    print("  Si el bloque B se parece a eso, la regla vale. Si el intervalo de")
    print("  B cruza el cero, no tenemos nada — y conviene recordar que C3 se")
    print("  eligio entre cinco variantes despues de ver los datos.")


if __name__ == "__main__":
    main()
