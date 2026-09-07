# -*- coding: utf-8 -*-
"""
¿Sirve esperar un retroceso antes de entrar?

La idea de Felix: el sistema senala una entrada E. En vez de comprar ahi, poner
una alerta en Binance a E-1.8%, entrar cuando salte, y medir el objetivo de
+3.2% SOBRE E —no sobre el precio al que se entro—, con un stop corto.

Tiene una logica clara: si entras 1.8% mas abajo, el mismo objetivo queda mas
cerca y el riesgo por operacion baja.

Y tiene un riesgo igual de claro que hay que cuantificar: el 57.9% de las
senales ganadoras suben DIRECTO sin retroceder. A esas no entrarias nunca.
Mientras que TODAS las perdedoras que se desploman si tocan el -1.8%. O sea
que el filtro puede estar seleccionando justo al reves de lo que conviene.

Cual de los dos efectos pesa mas no se decide razonando: se mide.

Se reportan dos cosas distintas y las dos importan:
    por OPERACION   calidad de las que llegan a ejecutarse
    por SENAL       lo que rinde la estrategia completa, contando como cero
                    las senales en las que nunca se entro
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
FEE = 0.2
VENTANA_H = 24
MIN_N = 30


def cargar(con):
    d = defaultdict(list)
    for s, t, h, l, c in con.execute(
            "SELECT symbol, open_time, h, l, c FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        d[s].append((t, h, l, c))
    return {s: np.array(v, dtype=np.float64) for s, v in d.items()}


def directo(a, i0, E, stop_pct):
    """Entrar en E. Objetivo E*(1+META), stop a stop_pct por debajo de E."""
    fin = min(i0 + VENTANA_H * 60, len(a))
    if fin - i0 < 10:
        return None
    obj = E * (1 + META / 100.0)
    stp = E * (1 - stop_pct / 100.0) if stop_pct else None
    for _, hi, lo, cl in a[i0:fin]:
        if stp is not None and lo <= stp:
            return -stop_pct
        if hi >= obj:
            return META
    return (float(a[fin - 1, 3]) / E - 1) * 100.0


def esperando(a, i0, E, dip_pct, stop_pct):
    """
    Esperar a que el precio toque E*(1-dip_pct) y entrar ahi. Objetivo sigue
    siendo E*(1+META). Stop a stop_pct por debajo de la entrada REAL.

    Devuelve (retorno_pct, entro). Si nunca toca el nivel, entro=False y no se
    inmoviliza capital.
    """
    fin = min(i0 + VENTANA_H * 60, len(a))
    if fin - i0 < 10:
        return None, False
    nivel = E * (1 - dip_pct / 100.0)
    obj = E * (1 + META / 100.0)
    j = None
    for k in range(i0, fin):
        if a[k, 2] <= nivel:
            j = k
            break
        # Si alcanza el objetivo antes de retroceder, esta operacion no existe
        if a[k, 1] >= obj:
            return None, False
    if j is None:
        return None, False
    entrada = nivel
    stp = entrada * (1 - stop_pct / 100.0) if stop_pct else None
    # Desde la MISMA vela del toque: si ahi mismo cae hasta el stop, cuenta.
    for _, hi, lo, cl in a[j:fin]:
        if stp is not None and lo <= stp:
            return -stop_pct, True
        if hi >= obj:
            return (obj / entrada - 1) * 100.0, True
    return (float(a[fin - 1, 3]) / entrada - 1) * 100.0, True


def resumen(nombre, rets, n_senales, rng):
    if len(rets) < MIN_N:
        print(f"  {nombre:<40} (pocas: {len(rets)})")
        return
    r = np.array(rets) - FEE
    idx = rng.integers(0, len(r), size=(1500, len(r)))
    ci = np.percentile(r[idx].mean(axis=1), [5, 95])
    # Por senal: las que no se ejecutaron cuentan como 0 (no se opero)
    por_senal = r.sum() / n_senales
    print(f"  {nombre:<40} {len(r):>4} ops de {n_senales:<4} "
          f"({100*len(r)/n_senales:>4.0f}%)  "
          f"op {r.mean():>+6.2f}% [{ci[0]:>+5.2f},{ci[1]:>+5.2f}]  "
          f"senal {por_senal:>+6.2f}%  acierto {100*(r > 0).mean():>4.1f}%")


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    kl = cargar(con)
    t_fin = max(a[-1, 0] for a in kl.values())
    rng = np.random.default_rng(11)

    filas = []
    for r in con.execute("SELECT symbol, ts_open, entry FROM outcomes "
                         "WHERE sombra=0 AND entry IS NOT NULL ORDER BY ts_open"):
        a = kl.get(r["symbol"])
        if a is None:
            continue
        i = int(np.searchsorted(a[:, 0], r["ts_open"], side="right")) - 1
        if i < 48 or a[i, 0] + VENTANA_H * 3600_000 > t_fin:
            continue
        filas.append((a, i, float(r["entry"])))
    n = len(filas)
    print(f"{n} senales con {VENTANA_H}h de futuro completas")
    print(f"objetivo +{META}% sobre la entrada del SISTEMA; comisiones {FEE}%\n")

    print("=" * 108)
    print("REFERENCIA: entrar donde dice el sistema")
    print("=" * 108)
    for stop in (1.2, 2.0, 3.2, None):
        rets = [x for x in (directo(a, i, E, stop) for a, i, E in filas)
                if x is not None]
        etq = f"stop -{stop}%" if stop else "sin stop"
        resumen(f"entrar en E ({etq})", rets, n, rng)

    print("\n" + "=" * 108)
    print("TU IDEA: esperar el retroceso y entrar mas abajo")
    print("=" * 108)
    for dip in (1.0, 1.8, 2.5):
        print(f"\n  --- esperando a que caiga {dip}% desde E ---")
        for stop in (1.2, 2.0, 3.2):
            rets = []
            for a, i, E in filas:
                r, entro = esperando(a, i, E, dip, stop)
                if entro and r is not None:
                    rets.append(r)
            resumen(f"entrar a -{dip}% (stop -{stop}% de ahi)", rets, n, rng)

    print("\n" + "=" * 108)
    print("EL COSTE OCULTO: ¿a cuantas GANADORAS no habrias entrado?")
    print("=" * 108)
    for dip in (1.0, 1.8, 2.5):
        gan_dir = perdidas = 0
        for a, i, E in filas:
            fin = min(i + VENTANA_H * 60, len(a))
            obj = E * (1 + META / 100.0)
            nivel = E * (1 - dip / 100.0)
            toco_obj = False
            for k in range(i, fin):
                if a[k, 1] >= obj:
                    toco_obj = True
                    break
                if a[k, 2] <= nivel:
                    break
            if toco_obj:
                gan_dir += 1
        # las que llegan al objetivo SIN retroceder antes = no las cogerias
        print(f"  cayendo {dip}%: {gan_dir} senales llegaron a +{META}% "
              f"SIN retroceder antes ({100*gan_dir/n:.1f}% del total). "
              f"A esas no entrarias.")

    print("\n" + "=" * 108)
    print("ARITMETICA DEL APALANCAMIENTO x5 (no es consejo, son cuentas)")
    print("=" * 108)
    print("  Sobre el capital, un movimiento del precio se multiplica por 5:")
    for p in (1.2, 1.8, 2.0, 3.2, 3.73):
        print(f"    precio {-p:>5.2f}%  ->  capital {-p*5:>6.1f}%")
    print("\n  El retroceso mediano de las ganadoras DIP_Y_SUBE es -1.90% y su")
    print("  p90 es -3.73%. Con x5 eso es -9.5% y -18.7% del capital.")


if __name__ == "__main__":
    main()
