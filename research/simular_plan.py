# -*- coding: utf-8 -*-
"""
El plan de Felix, simulado con los retornos REALES del sistema.

Plan: 20 USD, apalancamiento x5, operar las senales del sistema, cerrar y
reabrir cada vez que se acumulan +10 USD, hasta llegar a 100.

Esto NO es una recomendacion ni un pronostico. Es aritmetica sobre la
distribucion de retornos que el sistema produjo realmente estos dias: se
remuestrean operaciones de esa lista y se compone el capital. Si la
distribucion futura cambia —y en otro regimen de mercado va a cambiar— el
resultado cambia con ella.

Tres limitaciones que hacen que esto sea OPTIMISTA, no pesimista:

  1. Se remuestrea de forma independiente. Las operaciones reales estan
     correlacionadas: cuando el mercado cae, muchas pierden a la vez. Eso
     concentra las rachas malas y sube la probabilidad de ruina por encima de
     lo que sale aqui.
  2. Los retornos vienen de una ventana alcista/plana. No hay ni un dia rojo.
  3. No se modela deslizamiento ni el interes del prestamo de margen.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
FEE = 0.2
VENTANA_H = 24
CAPITAL_INI = 20.0
OBJETIVO_USD = 100.0
APALANCAMIENTO = 5
MAX_OPS = 400
RUINA = 4.0        # por debajo de esto no se puede abrir posicion util
N_SIM = 6000


def cargar(con):
    d = defaultdict(list)
    for s, t, h, l, c in con.execute(
            "SELECT symbol, open_time, h, l, c FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        d[s].append((t, h, l, c))
    return {s: np.array(v, dtype=np.float64) for s, v in d.items()}


def opera(a, i0, E, dip_pct, stop_pct):
    fin = min(i0 + VENTANA_H * 60, len(a))
    if fin - i0 < 10:
        return None
    obj = E * (1 + META / 100.0)
    if dip_pct is None:
        entrada, j = E, i0
    else:
        nivel = E * (1 - dip_pct / 100.0)
        j = None
        for k in range(i0, fin):
            if a[k, 2] <= nivel:
                j = k
                break
            if a[k, 1] >= obj:
                return None
        if j is None:
            return None
        entrada = nivel
    stp = entrada * (1 - stop_pct / 100.0)
    for _, hi, lo, cl in a[j:fin]:
        if lo <= stp:
            return -stop_pct
        if hi >= obj:
            return (obj / entrada - 1) * 100.0
    return (float(a[fin - 1, 3]) / entrada - 1) * 100.0


def simular(rets: np.ndarray, rng, bloque: int = 1) -> tuple:
    """
    Una vida: opera hasta llegar al objetivo, arruinarse o agotar MAX_OPS.

    `bloque` es la clave de que esto no mienta. Con bloque=1 se sortea cada
    operacion por separado, y entonces arruinarse exige una racha larguisima
    de mala suerte independiente — que casi nunca ocurre. Pero las operaciones
    reales NO son independientes: cuando el mercado cae, las perdidas llegan
    juntas. Con bloque>1 se sortean TRAMOS CONSECUTIVOS de la secuencia real,
    que conservan esas rachas tal y como pasaron.
    """
    cap = CAPITAL_INI
    pico = cap
    peor = 0.0
    pos, resto = 0, 0
    for n in range(1, MAX_OPS + 1):
        if resto == 0:
            pos = int(rng.integers(0, len(rets)))
            resto = bloque
        r = rets[pos % len(rets)]
        pos += 1
        resto -= 1
        # x5 sobre el capital, comisiones ya descontadas en `rets`
        cap *= (1 + APALANCAMIENTO * r / 100.0)
        pico = max(pico, cap)
        peor = min(peor, (cap / pico - 1) * 100.0)
        if cap <= RUINA:
            return False, cap, n, peor
        if cap >= OBJETIVO_USD:
            return True, cap, n, peor
    return False, cap, MAX_OPS, peor


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    kl = cargar(con)
    t_fin = max(a[-1, 0] for a in kl.values())
    rng = np.random.default_rng(2026)

    filas = []
    for r in con.execute("SELECT symbol, ts_open, entry FROM outcomes "
                         "WHERE sombra=0 AND entry IS NOT NULL"):
        a = kl.get(r["symbol"])
        if a is None:
            continue
        i = int(np.searchsorted(a[:, 0], r["ts_open"], side="right")) - 1
        if i < 48 or a[i, 0] + VENTANA_H * 3600_000 > t_fin:
            continue
        filas.append((a, i, float(r["entry"])))

    print(f"{len(filas)} senales con futuro completo")
    print(f"Plan: {CAPITAL_INI:.0f} USD -> {OBJETIVO_USD:.0f} USD, "
          f"apalancamiento x{APALANCAMIENTO}, {N_SIM:,} vidas simuladas\n")

    estrategias = [
        ("entrar en E, stop -2%", None, 2.0),
        ("esperar -1.8%, stop -2%", 1.8, 2.0),
        ("esperar -1.8%, stop -3.2%", 1.8, 3.2),
        ("entrar en E, stop -1.2%", None, 1.2),
    ]

    # Las operaciones, EN ORDEN CRONOLOGICO: es lo que permite que los tramos
    # consecutivos conserven las rachas reales.
    filas_ord = sorted(filas, key=lambda x: x[0][x[1], 0])

    for bloque in (1, 10, 30):
        etq = ("independiente (OPTIMISTA: ignora que las perdidas se agrupan)"
               if bloque == 1 else f"tramos de {bloque} operaciones seguidas")
        print("=" * 100)
        print(f"  MUESTREO {etq}")
        print("=" * 100)
        print(f"  {'estrategia':<26} {'media/op':>9} {'llega a 100':>12} "
              f"{'se arruina':>11} {'ops al 100':>11} {'peor caida':>11}")
        for nombre, dip, stop in estrategias:
            rets = np.array([x for x in (opera(a, i, E, dip, stop)
                                         for a, i, E in filas_ord)
                             if x is not None]) - FEE
            if len(rets) < 30:
                print(f"  {nombre:<26} (pocas: {len(rets)})")
                continue
            ok = np.zeros(N_SIM, dtype=bool)
            ops = np.zeros(N_SIM)
            peor = np.zeros(N_SIM)
            ruina = 0
            for k in range(N_SIM):
                llego, cap, n, pe = simular(rets, rng, bloque)
                ok[k] = llego
                ops[k] = n
                peor[k] = pe
                if cap <= RUINA:
                    ruina += 1
            med_ops = np.median(ops[ok]) if ok.any() else float("nan")
            print(f"  {nombre:<26} {rets.mean():>+8.2f}% {100*ok.mean():>11.1f}% "
                  f"{100*ruina/N_SIM:>10.1f}% {med_ops:>11.0f} "
                  f"{np.median(peor):>10.1f}%")
        print()

    # --- La aritmetica cruda, sin simulacion ---
    print("\n" + "=" * 100)
    print("LA ARITMETICA, SIN SIMULAR")
    print("=" * 100)
    print(f"  Con {CAPITAL_INI:.0f} USD y x{APALANCAMIENTO}, la posicion es "
          f"{CAPITAL_INI*APALANCAMIENTO:.0f} USD.")
    print(f"  Para ganar 10 USD hace falta que el capital suba un "
          f"{100*10/CAPITAL_INI:.0f}%, o sea que el PRECIO suba "
          f"{100*10/CAPITAL_INI/APALANCAMIENTO:.1f}%.")
    print()
    rets_ref = np.array([x for x in (opera(a, i, E, None, 2.0)
                                     for a, i, E in filas) if x is not None]) - FEE
    for objetivo in (2.0, 5.0, 10.0):
        p = (rets_ref >= objetivo).mean()
        print(f"    de las operaciones reales, el {100*p:>5.1f}% dio "
              f"+{objetivo:.0f}% o mas de precio")
    print()
    print(f"  Cada perdida con stop del 2% cuesta un "
          f"{2.0*APALANCAMIENTO:.0f}% del capital.")
    n_seguidas = int(np.ceil(np.log(RUINA / CAPITAL_INI) /
                             np.log(1 - 2.0 * APALANCAMIENTO / 100.0)))
    print(f"  {n_seguidas} perdidas seguidas dejan el capital por debajo de "
          f"{RUINA:.0f} USD.")
    p_perd = (rets_ref < 0).mean()
    print(f"  Con {100*p_perd:.0f}% de operaciones perdedoras, la probabilidad "
          f"de {n_seguidas} seguidas es {100*p_perd**n_seguidas:.2f}%")
    print(f"  ...pero eso asume independencia. En una caida de mercado las")
    print(f"  perdidas llegan juntas, y esa probabilidad sube mucho.")


if __name__ == "__main__":
    main()
