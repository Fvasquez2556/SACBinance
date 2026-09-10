# -*- coding: utf-8 -*-
"""
¿Cuantas señales tienen niveles que no significan nada?

Salio mirando las 47 que tocaron su TP despues del stop: entre ellas habia un
BTC con TP +0.6% y stop -0.3%, y un SPYB con TP +0.1% y stop -0.0%. Un stop
del 0.3% en Bitcoin no es una operacion, es ruido con nombre — y sin embargo
cuenta igual que las demas en cada estadistica que hemos hecho.

Cuatro varas, cada una con su anclaje. Ninguna es un numero inventado:

  RUIDO      el stop cabe dentro de la oscilacion normal del par. Se mide el
             recorrido maximo-minimo en ventanas de 60 minutos durante las
             12 horas ANTERIORES a la señal, y se toma la mediana. Si el stop
             es menor que eso, lo va a tocar el vaiven de cualquier hora,
             suba o baje la moneda.
  FRICCION   el TP esta por debajo de lo que cuesta operar (0.2% de comision
             mas ~0.3% de deslizamiento). Cobrar ese TP pierde dinero.
  ABSURDO    stop por debajo del 0.3% o TP por debajo del 0.3%. A ese tamaño
             el nivel esta dentro del spread de muchos pares.
  R:R ROTO   el TP no llega ni al 1%. Aunque se cobre, no mueve la aguja.

Y la pregunta que importa: ¿cuanto inflan las estadisticas? Un TP diminuto es
facil de tocar, asi que estas señales suben la tasa de acierto sin aportar
dinero. Se mide su peso en el recuento de TP.

El ruido se calcula SOLO con velas anteriores a la señal. Mirar las de despues
seria hacer trampa con el dato que justifica el filtro.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
VENTANA_RUIDO_H = 12          # horas anteriores sobre las que medir el ruido
TRAMO_MIN = 60                # tamaño de la ventana de recorrido
FRICCION = 0.5                # comision + deslizamiento, en %


def u(ms):
    return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%d/%m %H:%M")


def pct(n, d):
    return f"{100*n/d:5.1f}%" if d else "    -"


def ruido_previo(hi, lo, i, tramo=TRAMO_MIN, horas=VENTANA_RUIDO_H):
    """Mediana del recorrido max-min en ventanas de `tramo` minutos, ANTES de i."""
    ini = max(0, i - horas * 60)
    if i - ini < tramo * 3:
        return None
    h, l = hi[ini:i], lo[ini:i]
    n = (len(h) // tramo) * tramo
    if n < tramo:
        return None
    h = h[:n].reshape(-1, tramo).max(axis=1)
    l = l[:n].reshape(-1, tramo).min(axis=1)
    r = (h - l) / np.where(l > 0, l, np.nan) * 100.0
    r = r[np.isfinite(r)]
    return float(np.median(r)) if len(r) else None


def desenlace(x):
    tp, sl = x["ms_tp"], x["ms_sl"]
    if tp is not None and (sl is None or tp < sl):
        return "TP"
    if sl is not None:
        return "SL"
    return "ABIERTA" if not x["cerrado"] else "NADA"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    series = {}
    for sym, in con.execute("SELECT DISTINCT symbol FROM klines WHERE tf='1m'"):
        f = con.execute("SELECT open_time,h,l FROM klines WHERE symbol=? AND tf='1m' "
                        "ORDER BY open_time", (sym,)).fetchall()
        if len(f) < 300:
            continue
        series[sym] = (np.array([r[0] for r in f], dtype=np.int64),
                       np.array([r[1] for r in f], dtype=float),
                       np.array([r[2] for r in f], dtype=float))
    prim = int(min(s[0][0] for s in series.values()))

    datos = []
    sin_ruido = 0
    for r in con.execute(
            "SELECT * FROM outcomes WHERE sombra=0 AND ts_open>=? AND tp_pct IS NOT NULL "
            "AND sl_pct IS NOT NULL ORDER BY ts_open", (prim,)):
        x = dict(r)
        s = series.get(x["symbol"])
        if s is None:
            continue
        i = int(np.searchsorted(s[0], x["ts_open"], side="right")) - 1
        if i < 0:
            continue
        x["ruido"] = ruido_previo(s[1], s[2], i)
        if x["ruido"] is None:
            sin_ruido += 1
        x["des"] = desenlace(x)
        datos.append(x)

    n = len(datos)
    print(f"{n} señales con velas suficientes para medir su ruido previo")
    print(f"   ({sin_ruido} sin historia bastante; quedan fuera de la vara del ruido)\n")

    con_r = [x for x in datos if x["ruido"] is not None]
    ru = np.array([x["ruido"] for x in con_r])
    sl = np.abs(np.array([x["sl_pct"] for x in con_r]))
    print(f"  ruido del par (mediana del recorrido en 60 min, 12h previas):")
    for p in (10, 25, 50, 75, 90):
        print(f"     p{p:<3} {np.percentile(ru, p):5.2f}%")
    print(f"  stop que pone el sistema:")
    for p in (10, 25, 50, 75, 90):
        print(f"     p{p:<3} {np.percentile(sl, p):5.2f}%")
    print(f"\n  el stop mide {np.median(sl/ru):.2f} veces el ruido, de mediana")

    # ---- las cuatro varas -------------------------------------------
    print()
    print("=" * 96)
    print("CUANTAS NO SIGNIFICAN NADA")
    print("=" * 96)
    varas = [
        ("RUIDO    el stop cabe en la oscilacion normal",
         lambda x: x["ruido"] is not None and abs(x["sl_pct"]) < x["ruido"]),
        ("  ...y ademas es menos de la MITAD del ruido",
         lambda x: x["ruido"] is not None and abs(x["sl_pct"]) < x["ruido"] / 2),
        ("FRICCION el TP no cubre comision+deslizamiento",
         lambda x: x["tp_pct"] < FRICCION),
        ("ABSURDO  stop <0.3% o TP <0.3%",
         lambda x: abs(x["sl_pct"]) < 0.3 or x["tp_pct"] < 0.3),
        ("R:R ROTO el TP no llega al 1%",
         lambda x: x["tp_pct"] < 1.0),
    ]
    print(f"\n  {'vara':<46} {'n':>6} {'% del total':>12}")
    for etq, f in varas:
        sub = [x for x in datos if f(x)]
        print(f"  {etq:<46} {len(sub):>6} {pct(len(sub), n):>12}")

    mala = lambda x: (
        (x["ruido"] is not None and abs(x["sl_pct"]) < x["ruido"])
        or x["tp_pct"] < FRICCION
        or abs(x["sl_pct"]) < 0.3
    )
    sub = [x for x in datos if mala(x)]
    print(f"\n  {'CUALQUIERA de las tres primeras':<46} {len(sub):>6} {pct(len(sub), n):>12}")

    # ---- ¿se comportan distinto? ------------------------------------
    print()
    print("=" * 96)
    print("¿Y SE COMPORTAN DISTINTO?")
    print("=" * 96)
    print(f"\n  {'grupo':<34} {'n':>6} {'TP':>8} {'SL':>8} {'a +3.2%':>9} "
          f"{'TP medio':>9} {'stop medio':>11}")
    for etq, f in (("con niveles que SI significan", lambda x: not mala(x)),
                   ("con niveles que NO significan", mala)):
        g = [x for x in datos if f(x)]
        if len(g) < 20:
            continue
        cer = [x for x in g if x["des"] != "ABIERTA"]
        tp = sum(1 for x in g if x["des"] == "TP")
        s_ = sum(1 for x in g if x["des"] == "SL")
        m32 = sum(1 for x in g if x["ms_up_32"] is not None)
        print(f"  {etq:<34} {len(g):>6} {pct(tp, len(cer)):>8} {pct(s_, len(cer)):>8} "
              f"{pct(m32, len(g)):>9} {np.mean([x['tp_pct'] for x in g]):>8.2f}% "
              f"{np.mean([abs(x['sl_pct']) for x in g]):>10.2f}%")

    # ---- cuanto inflan el recuento ----------------------------------
    print()
    print("=" * 96)
    print("CUANTO INFLAN LA TASA DE ACIERTO")
    print("=" * 96)
    cer = [x for x in datos if x["des"] != "ABIERTA"]
    tp_tot = sum(1 for x in cer if x["des"] == "TP")
    malas_tp = sum(1 for x in cer if mala(x) and x["des"] == "TP")
    buenas = [x for x in cer if not mala(x)]
    tp_b = sum(1 for x in buenas if x["des"] == "TP")
    print(f"\n  TP contados en total                    {tp_tot:>6}   "
          f"({pct(tp_tot, len(cer))} de las cerradas)")
    print(f"  de esos, con niveles sin sentido        {malas_tp:>6}   "
          f"{pct(malas_tp, tp_tot)} de todos los TP")
    print(f"\n  tasa de TP quitandolas                  {pct(tp_b, len(buenas)):>6}")
    print(f"  tasa de TP con ellas                    {pct(tp_tot, len(cer)):>6}")
    dif = 100*tp_tot/len(cer) - 100*tp_b/len(buenas)
    print(f"  -> inflan la tasa de acierto en         {dif:>+6.1f} puntos")

    # ---- los peores casos -------------------------------------------
    print()
    print("=" * 96)
    print("LOS 15 CASOS MAS EXTREMOS")
    print("=" * 96)
    ext = sorted([x for x in datos if x["ruido"]],
                 key=lambda x: abs(x["sl_pct"]) / x["ruido"])[:15]
    print(f"\n  {'par':<13} {'señal (UTC)':<12} {'TP':>7} {'SL':>7} {'ruido':>7} "
          f"{'stop/ruido':>11} {'desenlace':>10}")
    for x in ext:
        print(f"  {x['symbol'].replace('USDT',''):<13} {u(x['ts_open']):<12} "
              f"{'+%.2f'%x['tp_pct']:>6}% {'%.2f'%x['sl_pct']:>6}% "
              f"{x['ruido']:>6.2f}% {abs(x['sl_pct'])/x['ruido']:>10.2f}x {x['des']:>10}")

    # ---- por par ----------------------------------------------------
    print()
    print("  pares que mas señales sin sentido producen:")
    porpar = defaultdict(int)
    for x in datos:
        if mala(x):
            porpar[x["symbol"]] += 1
    for sym, k in sorted(porpar.items(), key=lambda z: -z[1])[:12]:
        tot = sum(1 for x in datos if x["symbol"] == sym)
        print(f"     {sym.replace('USDT',''):<14} {k:>3} de {tot:<3} señales")


if __name__ == "__main__":
    main()
