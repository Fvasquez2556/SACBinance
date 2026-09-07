# -*- coding: utf-8 -*-
"""
El retroceso que se espera, ¿fijo o proporcional al par?

Felix: el -1.8% no deberia ser fijo sino salir de los datos, y ademas hay dos
casos distintos —los pares cuyo stop es ancho (volatiles, retroceden mucho) y
los que suben sin bajar apenas—, asi que quiza no toque tratarlos igual.

Las dos observaciones tienen respaldo medido:
  - research/ritmo_y_forma.py: con TP ofrecido <2% el 65.2% sube DIRECTO; con
    TP >6% solo el 46.1%. La volatilidad del par predice si retrocede.
  - El TP sale de riesgo x2 y el riesgo del ATR, asi que `sl_pct` ya ES un
    medidor de volatilidad calculado por el sistema. No hace falta inventar
    otro: se usa el que ya hay.

Se prueban tres familias:
  FIJO        esperar siempre el mismo % (lo medido antes)
  PROPORCIONAL esperar k veces el propio SL del par
  HIBRIDO     entrar directo en los tranquilos, esperar en los volatiles

Y una advertencia previa: en reglas_especificas.py, normalizar por el caracter
del par EMPEORO el umbral de la caida de entrada. Que aqui funcione no esta
garantizado solo porque suene razonable.
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


def opera(a, i0, E, dip_pct, stop_pct):
    """
    dip_pct None -> entrar en E. Si no, esperar a E*(1-dip) y entrar ahi.
    Objetivo siempre E*(1+META). Stop a stop_pct por debajo de la entrada real.
    Devuelve (retorno, entro).
    """
    fin = min(i0 + VENTANA_H * 60, len(a))
    if fin - i0 < 10:
        return None, False
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
            if a[k, 1] >= obj:      # llego al objetivo sin retroceder
                return None, False
        if j is None:
            return None, False
        entrada = nivel

    stp = entrada * (1 - stop_pct / 100.0) if stop_pct else None
    for _, hi, lo, cl in a[j:fin]:
        if stp is not None and lo <= stp:
            return -stop_pct, True
        if hi >= obj:
            return (obj / entrada - 1) * 100.0, True
    return (float(a[fin - 1, 3]) / entrada - 1) * 100.0, True


def resumen(nombre, rets, n, rng):
    if len(rets) < MIN_N:
        print(f"  {nombre:<46} (pocas: {len(rets)})")
        return
    r = np.array(rets) - FEE
    idx = rng.integers(0, len(r), size=(1500, len(r)))
    ci = np.percentile(r[idx].mean(axis=1), [5, 95])
    print(f"  {nombre:<46} {len(r):>4}/{n:<4} ({100*len(r)/n:>3.0f}%)  "
          f"op {r.mean():>+6.2f}% [{ci[0]:>+5.2f},{ci[1]:>+5.2f}]  "
          f"senal {r.sum()/n:>+6.2f}%  ac {100*(r > 0).mean():>4.1f}%")


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    kl = cargar(con)
    t_fin = max(a[-1, 0] for a in kl.values())
    rng = np.random.default_rng(5)

    filas = []
    for r in con.execute("SELECT symbol, ts_open, entry, sl_pct, tp_pct FROM outcomes "
                         "WHERE sombra=0 AND entry IS NOT NULL AND sl_pct IS NOT NULL "
                         "ORDER BY ts_open"):
        a = kl.get(r["symbol"])
        if a is None:
            continue
        i = int(np.searchsorted(a[:, 0], r["ts_open"], side="right")) - 1
        if i < 48 or a[i, 0] + VENTANA_H * 3600_000 > t_fin:
            continue
        filas.append({"a": a, "i": i, "E": float(r["entry"]),
                      "sl": abs(float(r["sl_pct"])), "tp": float(r["tp_pct"] or 0)})
    n = len(filas)
    sls = np.array([f["sl"] for f in filas])
    print(f"{n} senales con futuro completo")
    print(f"SL que ofrece el sistema: mediana {np.median(sls):.2f}%  "
          f"p25 {np.percentile(sls,25):.2f}%  p75 {np.percentile(sls,75):.2f}%\n")

    def corre(nombre, dip_de, stop_de):
        rets = []
        for f in filas:
            d = dip_de(f)
            s = stop_de(f)
            r, entro = opera(f["a"], f["i"], f["E"], d, s)
            if entro and r is not None:
                rets.append(r)
        resumen(nombre, rets, n, rng)

    print("=" * 112)
    print("REFERENCIAS")
    print("=" * 112)
    corre("entrar en E, stop -2.0% fijo", lambda f: None, lambda f: 2.0)
    corre("entrar en E, stop = el del sistema", lambda f: None, lambda f: f["sl"])
    corre("esperar -1.8% fijo, stop -2.0%", lambda f: 1.8, lambda f: 2.0)

    print("\n" + "=" * 112)
    print("PROPORCIONAL: esperar k veces el SL que el sistema calculo para ese par")
    print("=" * 112)
    for k in (0.5, 0.75, 1.0, 1.5):
        corre(f"esperar {k}x SL, stop = el del sistema",
              lambda f, k=k: k * f["sl"], lambda f: f["sl"])
    print()
    for k in (0.75, 1.0):
        corre(f"esperar {k}x SL, stop -2.0% fijo",
              lambda f, k=k: k * f["sl"], lambda f: 2.0)

    print("\n" + "=" * 112)
    print("HIBRIDO: directo en los tranquilos, esperar en los volatiles")
    print("=" * 112)
    for corte in (1.5, 2.0, 2.5):
        for k in (0.75, 1.0):
            corre(f"SL<{corte}% -> directo | SL>={corte}% -> esperar {k}x SL",
                  lambda f, c=corte, k=k: None if f["sl"] < c else k * f["sl"],
                  lambda f: f["sl"])
        print()

    print("=" * 112)
    print("¿DONDE ESTA LA DIFERENCIA? — el mismo experimento partido por volatilidad")
    print("=" * 112)
    med = float(np.median(sls))
    for etq, filtro in (("pares TRANQUILOS (SL < mediana)", lambda f: f["sl"] < med),
                        ("pares VOLATILES (SL >= mediana)", lambda f: f["sl"] >= med)):
        sub = [f for f in filas if filtro(f)]
        print(f"\n  --- {etq}: {len(sub)} senales ---")
        for nombre, dip_de in (("entrar en E", lambda f: None),
                               ("esperar 0.75x SL", lambda f: 0.75 * f["sl"]),
                               ("esperar 1.0x SL", lambda f: 1.0 * f["sl"])):
            rets = []
            for f in sub:
                r, entro = opera(f["a"], f["i"], f["E"], dip_de(f), f["sl"])
                if entro and r is not None:
                    rets.append(r)
            resumen(f"  {nombre}", rets, len(sub), rng)


if __name__ == "__main__":
    main()
