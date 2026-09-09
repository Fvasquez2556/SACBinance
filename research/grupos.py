# -*- coding: utf-8 -*-
"""
Separar las senales en grupos por lo que HIZO el precio, y perfilar cada uno.

Los grupos que pidio Felix se solapaban entre si, asi que aqui se convierten en
una particion: cada senal cae en uno y solo uno.

    pedido                              se convierte en
    ---------------------------------   ----------------------------------
    subio y cumplio la meta             CUMPLIO   3.2% <= MFE < 4.7%
    subio y paso 1.5% de la meta        SUPERO    MFE >= 4.7%
      (era un subconjunto del anterior; se separan por el corte 4.7%)

    no paso de 2.2%                     se parte en tres por lo que hizo
    bajo al stop y no subio             hacia ABAJO, que es lo unico que
    ni subio ni bajo                    los distinguia:
                                          AL_STOP  toco el SL del sistema
                                          BAJO     cayo <= -1.2% sin tocar SL
                                          PLANA    ni una cosa ni la otra

    y queda un hueco que el pedido no cubria:
                                          CERCA    2.2% <= MFE < 3.2%
                                          (subio de verdad pero no llego)

MFE es la subida maxima desde el entry congelado y MAE la bajada maxima. Un
mismo caso puede haber hecho las dos cosas: el grupo lo decide la subida, y el
comportamiento hacia abajo se reporta aparte, porque "toco el stop y ADEMAS
llego a la meta" es un caso real y frecuente que conviene no esconder.
"""
from __future__ import annotations

import csv
import datetime as dt
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

DB = "data/sacbinance.db"
SALIDA = Path("../informes/grupos")
META = 3.2
SUPERA = META + 1.5      # 4.7
CORTO = 2.2
BAJADA = 1.2             # el SL medio observado
ZONA, LOOKBACK = 8, 40   # para reconstruir el patron en el instante de la senal
TZ = -6


def gt(ts):
    return dt.datetime.utcfromtimestamp(ts / 1000) + dt.timedelta(hours=TZ)


def clasificar(r: dict) -> str:
    mfe = r.get("mfe_pct") or 0.0
    mae = r.get("mae_pct") or 0.0
    if mfe >= SUPERA:
        return "SUPERO"
    if mfe >= META:
        return "CUMPLIO"
    if mfe >= CORTO:
        return "CERCA"
    if r.get("ms_sl") is not None:
        return "AL_STOP"
    if mae <= -BAJADA:
        return "BAJO"
    return "PLANA"


ORDEN = ["SUPERO", "CUMPLIO", "CERCA", "AL_STOP", "BAJO", "PLANA"]
DESC = {
    "SUPERO":  f"MFE >= {SUPERA}%  (paso la meta por mas de 1.5%)",
    "CUMPLIO": f"{META}% <= MFE < {SUPERA}%  (llego justo)",
    "CERCA":   f"{CORTO}% <= MFE < {META}%  (subio pero no llego)",
    "AL_STOP": f"MFE < {CORTO}% y toco el SL del sistema",
    "BAJO":    f"MFE < {CORTO}%, cayo <= -{BAJADA}% pero sin tocar el SL",
    "PLANA":   f"MFE < {CORTO}% y MAE > -{BAJADA}%  (no hizo nada)",
}


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # Velas para reconstruir el patron en el momento de cada senal
    kl = defaultdict(list)
    for s, t, h, l, c in con.execute(
            "SELECT symbol, open_time, h, l, c FROM klines WHERE tf='1m' "
            "ORDER BY symbol, open_time"):
        kl[s].append((t, h, l, c))
    kl = {s: np.array(v, dtype=np.float64) for s, v in kl.items()}

    filas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND cerrado=1 ORDER BY ts_open")]
    if not filas:
        print("Sin senales cerradas.")
        return

    for f in filas:
        f["grupo"] = clasificar(f)
        f["hora"] = gt(f["ts_open"]).hour
        f["caida_prev"] = None
        f["rebote"] = None
        a = kl.get(f["symbol"])
        if a is None:
            continue
        i = int(np.searchsorted(a[:, 0], f["ts_open"], side="right")) - 1
        if i < ZONA + LOOKBACK:
            continue
        seg = a[i - ZONA + 1:i + 1]
        prev = a[i - ZONA - LOOKBACK + 1:i - ZONA + 1]
        pico, suelo = prev[:, 1].max(), seg[:, 2].min()
        if pico > 0 and suelo > 0:
            f["caida_prev"] = (suelo - pico) / pico * 100.0
            f["rebote"] = (a[i, 3] - suelo) / suelo * 100.0

    n = len(filas)
    ini, fin = gt(filas[0]["ts_open"]), gt(filas[-1]["ts_open"])
    print("=" * 96)
    print(f"  {n} senales reales con la ventana de 24h cumplida")
    print(f"  de {ini:%d/%m %H:%M} a {fin:%d/%m %H:%M} (hora Guatemala)")
    print("=" * 96)

    grupos = defaultdict(list)
    for f in filas:
        grupos[f["grupo"]].append(f)

    print(f"\n  {'grupo':<10} {'n':>5} {'%':>7}   definicion")
    print("  " + "-" * 92)
    for g in ORDEN:
        sub = grupos.get(g, [])
        print(f"  {g:<10} {len(sub):>5} {100*len(sub)/n:>6.1f}%   {DESC[g]}")

    # --- Lo que el reparto por grupo no enseña: quien toco el stop igualmente
    print("\n  " + "-" * 92)
    print("  CRUCE CON EL STOP — un grupo lo decide la SUBIDA, pero muchas")
    print("  ganadoras tocaron el stop antes de llegar:")
    print(f"  {'grupo':<10} {'n':>5} {'toco SL':>9} {'y aun asi llego':>17} "
          f"{'SL antes de la meta':>21}")
    for g in ORDEN:
        sub = grupos.get(g, [])
        if not sub:
            continue
        sl = [x for x in sub if x.get("ms_sl") is not None]
        antes = [x for x in sl if x.get("ms_up_32") is not None
                 and x["ms_sl"] < x["ms_up_32"]]
        llego = [x for x in sl if x.get("ms_up_32") is not None]
        print(f"  {g:<10} {len(sub):>5} {100*len(sl)/len(sub):>8.1f}% "
              f"{len(llego):>17} {len(antes):>21}")

    # --- Perfil de cada grupo ---
    def med(sub, campo):
        v = [x[campo] for x in sub if x.get(campo) is not None]
        return np.median(v) if v else float("nan")

    print("\n" + "=" * 96)
    print("  PERFIL DE CADA GRUPO (medianas)")
    print("=" * 96)
    print(f"  {'grupo':<10} {'n':>5} {'MFE':>8} {'MAE':>8} {'score':>6} "
          f"{'vol24h':>9} {'vol1m':>8} {'TP':>7} {'SL':>7} {'caida':>7} {'rebote':>7}")
    for g in ORDEN:
        sub = grupos.get(g, [])
        if not sub:
            continue
        print(f"  {g:<10} {len(sub):>5} {med(sub,'mfe_pct'):>+7.2f}% "
              f"{med(sub,'mae_pct'):>+7.2f}% {med(sub,'score'):>6.0f} "
              f"{med(sub,'vol_24h')/1e6:>8.1f}M {med(sub,'vol_1m_medio'):>8.0f} "
              f"{med(sub,'tp_pct'):>+6.2f}% {med(sub,'sl_pct'):>+6.2f}% "
              f"{med(sub,'caida_prev'):>+6.2f}% {med(sub,'rebote'):>+6.2f}%")

    # --- Reparto de las categoricas ---
    for campo in ("tier", "display_state", "macro", "taxonomia"):
        vals = [v for v in sorted({str(f[campo]) for f in filas if f[campo]})]
        print(f"\n  reparto por {campo} (% dentro de cada grupo)")
        print(f"  {'grupo':<10} " + " ".join(f"{v[:11]:>12}" for v in vals))
        for g in ORDEN:
            sub = grupos.get(g, [])
            if not sub:
                continue
            cnt = Counter(str(x[campo]) for x in sub)
            fila = " ".join(f"{100*cnt.get(v,0)/len(sub):>11.1f}%" for v in vals)
            print(f"  {g:<10} {fila}")

    # --- Tiempos ---
    print("\n" + "=" * 96)
    print("  CUANTO TARDARON (solo las que llegaron a la meta)")
    print("=" * 96)
    for g in ("SUPERO", "CUMPLIO"):
        sub = [x for x in grupos.get(g, []) if x.get("ms_up_32")]
        if len(sub) < 10:
            continue
        t = np.array([x["ms_up_32"] for x in sub]) / 60000.0
        print(f"  {g:<10} n={len(sub):>4}  mediana {np.median(t):>5.0f}min  "
              f"p25 {np.percentile(t,25):>5.0f}  p75 {np.percentile(t,75):>5.0f}  "
              f"max {t.max():>5.0f}")

    # --- Exportar ---
    SALIDA.mkdir(parents=True, exist_ok=True)
    campos = ["symbol", "ts_open", "hora", "grupo", "entry", "tp_pct", "sl_pct",
              "score", "tier", "display_state", "macro", "taxonomia",
              "vol_24h", "vol_1m_medio", "mfe_pct", "mae_pct", "forma",
              "caida_prev", "rebote", "ms_up_32", "ms_sl", "ms_tp"]
    for g in ORDEN:
        sub = grupos.get(g, [])
        if not sub:
            continue
        ruta = SALIDA / f"{g.lower()}.csv"
        with ruta.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(campos + ["hora_gt"])
            for x in sub:
                w.writerow([x.get(c) for c in campos]
                           + [gt(x["ts_open"]).strftime("%Y-%m-%d %H:%M")])
    print(f"\n  CSV por grupo en {SALIDA.resolve()}")


if __name__ == "__main__":
    main()
