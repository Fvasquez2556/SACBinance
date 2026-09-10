# -*- coding: utf-8 -*-
"""
La entrada REAL: a que precio se compra de verdad, y que pasa cuando cae.

Todo lo medido hasta ahora daba por supuesto que se compra al precio que el
sistema propone. Eso pierde -0.33% por operacion con el intervalo entero en
negativo, asi que la pregunta util es otra: **de todos los precios por los que
pasa esa moneda despues de la señal, ¿cual es el bueno?**

Tres preguntas, en este orden:

1. LA CAIDA. ¿Cuanto bajan antes de hacer nada? ¿Ha cambiado ese numero segun
   pasan los dias, o es una constante del mercado?

2. AL CAER, ¿SUBEN O SIGUEN CAYENDO? Esta es la que no habia medido bien.
   Se condiciona: **dado que ya bajo un X%**, desde ESE minuto en adelante,
   ¿cuanto sube, cuanto mas cae, y con que probabilidad vuelve al precio de la
   señal? Sin condicionar, cualquier respuesta mezcla las que nunca bajaron.

3. LA ESCALERA DE ENTRADAS. En vez de un unico disparo pegado al stop —que
   depende del ancho del stop y por tanto significa cosas distintas en cada
   par— se barre una escalera fija de descuentos sobre el precio de la señal:
   0%, -0.5%, -1%, -1.5%, -2%, -3%, -5%. Para cada uno: cuantas veces se llena
   la orden, y que pasa despues.

Reglas de la casa, todas por algo que ya salio mal
--------------------------------------------------
- Solo señales con la ventana COMPLETA de velas por delante. Una media
  dominada por posiciones sin resolver no es un resultado, es una foto: el
  +0.25% del 9-sep se dio la vuelta en tres horas por esto.
- Bootstrap agrupado POR PAR. El 84% de las señales solapa con otra del mismo
  par.
- Cada tasa de acierto va con su linea base geometrica B/(A+B). Un acierto sin
  su base no dice nada: se fabrica ensanchando el stop.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
VENTANA_H = 12                 # horizonte fijo, con velas completas exigidas
NIVELES = (0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
DESCUENTOS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
STOPS = (1.5, 3.0, 5.0)


def u(ms):
    return dt.datetime.utcfromtimestamp(ms / 1000).strftime("%d/%m %H:%M")


def pct(n, d):
    return f"{100*n/d:4.1f}%" if d else "   -"


def boot_ci(x, pares, rng, n=1500):
    x = np.asarray(x, dtype=float)
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


def cargar(con):
    """Señales con velas completas por delante, ya recortadas a la ventana."""
    series = {}
    for sym, in con.execute("SELECT DISTINCT symbol FROM klines WHERE tf='1m'"):
        f = con.execute("SELECT open_time,h,l,c FROM klines WHERE symbol=? AND tf='1m' "
                        "ORDER BY open_time", (sym,)).fetchall()
        if len(f) < 200:
            continue
        series[sym] = {
            "t": np.array([r[0] for r in f], dtype=np.int64),
            "h": np.array([r[1] for r in f], dtype=float),
            "l": np.array([r[2] for r in f], dtype=float),
            "c": np.array([r[3] for r in f], dtype=float),
        }
    prim = int(min(s["t"][0] for s in series.values()))
    minutos = VENTANA_H * 60
    out = []
    for r in con.execute(
            "SELECT * FROM outcomes WHERE sombra=0 AND ts_open>=? AND entry>0 "
            "AND stop_loss>0 AND sl_pct<0 AND tp_pct IS NOT NULL ORDER BY ts_open",
            (prim,)):
        s = series.get(r["symbol"])
        if s is None:
            continue
        i0 = int(np.searchsorted(s["t"], r["ts_open"], side="right")) - 1
        if i0 < 0 or i0 + minutos > len(s["t"]):
            continue
        out.append({
            "symbol": r["symbol"], "ts": r["ts_open"], "entry": float(r["entry"]),
            "tp": r["take_profit"], "sl": r["stop_loss"],
            "tp_pct": r["tp_pct"], "sl_pct": r["sl_pct"],
            "senal_n": r["senal_n"], "retro": r["retro_confirmado"],
            "hi": s["h"][i0:i0 + minutos], "lo": s["l"][i0:i0 + minutos],
            "cl": s["c"][i0:i0 + minutos],
        })
    return out


def primer_cruce(arr, umbral, arriba):
    x = arr >= umbral if arriba else arr <= umbral
    return int(np.argmax(x)) if x.any() else None


def main():
    rng = np.random.default_rng(20260910)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    datos = cargar(con)
    print(f"{len(datos)} señales con {VENTANA_H}h completas de velas, "
          f"{len({d['symbol'] for d in datos})} pares")
    print(f"de {u(datos[0]['ts'])} a {u(datos[-1]['ts'])} UTC\n")

    # =================================================================
    print("=" * 104)
    print("1. LA CAIDA: ¿cuanto bajan, y ha cambiado con los dias?")
    print("=" * 104)
    for d in datos:
        e = d["entry"]
        d["mae"] = float((d["lo"].min() - e) / e * 100)
        d["mfe"] = float((d["hi"].max() - e) / e * 100)
        d["ms_mae"] = int(np.argmin(d["lo"]))
    mae = np.array([d["mae"] for d in datos])
    print(f"\n  Peor caida desde el precio de la señal, en {VENTANA_H}h:")
    for p in (10, 25, 50, 75, 90):
        print(f"     p{p:<3} {np.percentile(mae, p):>7.2f}%")
    print(f"\n  ¿Y cuando toca ese fondo? mediana "
          f"{np.median([d['ms_mae'] for d in datos]):.0f} min desde la señal")

    print(f"\n  {'tramo':<26} {'n':>5} {'caida media':>12} {'mediana':>9} "
          f"{'p90':>8} {'bajan >2%':>10} {'subida media':>13}")
    bordes = np.linspace(datos[0]["ts"], datos[-1]["ts"] + 1, 5)
    for k in range(4):
        sub = [d for d in datos if bordes[k] <= d["ts"] < bordes[k + 1]]
        if len(sub) < 20:
            continue
        m = np.array([d["mae"] for d in sub])
        f = np.array([d["mfe"] for d in sub])
        etq = f"{u(int(bordes[k]))}-{u(int(bordes[k+1]))[6:]}"
        print(f"  {etq:<26} {len(sub):>5} {m.mean():>11.2f}% {np.median(m):>8.2f}% "
              f"{np.percentile(m,90):>7.2f}% {pct((m<=-2).sum(), len(m)):>10} "
              f"{f.mean():>12.2f}%")

    # =================================================================
    print()
    print("=" * 104)
    print("2. AL CAER, ¿SUBEN O SIGUEN CAYENDO?")
    print("=" * 104)
    print("  Condicionado: DADO que ya bajo un X%, desde ese minuto en adelante.")
    print("  'vuelve' = recupera el precio de la señal. 'sigue' = cae otro tanto.")
    print()
    print(f"  {'ya bajo':<10} {'n':>5} {'% de las':>9} {'vuelve a':>10} "
          f"{'llega a':>9} {'cae otro':>9} {'subida':>9} {'caida':>9} {'saldo':>9}")
    print(f"  {'':<10} {'':>5} {'señales':>9} {'la señal':>10} "
          f"{'+3.2%':>9} {'tanto':>9} {'media':>9} {'media':>9} {'12h':>9}")
    for niv in NIVELES:
        casos = []
        for d in datos:
            e = d["entry"]
            objetivo = e * (1 - niv / 100.0)
            i = primer_cruce(d["lo"], objetivo, arriba=False)
            if i is None or len(d["hi"]) - i < 60:
                continue
            p = objetivo                      # se compra AHI, no al cierre
            hi, lo, cl = d["hi"][i + 1:], d["lo"][i + 1:], d["cl"][i + 1:]
            if len(hi) < 30:
                continue
            casos.append({
                "symbol": d["symbol"],
                "vuelve": bool((hi >= e).any()),
                "meta": bool((hi >= p * (1 + META / 100)).any()),
                "sigue": bool((lo <= e * (1 - 2 * niv / 100)).any()),
                "sube": float((hi.max() - p) / p * 100),
                "cae": float((lo.min() - p) / p * 100),
                "saldo": float((cl[-1] - p) / p * 100),
            })
        if len(casos) < 25:
            continue
        n = len(casos)
        par = [c["symbol"] for c in casos]
        saldo = [c["saldo"] for c in casos]
        lo_, hi_ = boot_ci(saldo, par, rng)
        print(f"  -{niv:<9.1f} {n:>5} {pct(n, len(datos)):>9} "
              f"{pct(sum(c['vuelve'] for c in casos), n):>10} "
              f"{pct(sum(c['meta'] for c in casos), n):>9} "
              f"{pct(sum(c['sigue'] for c in casos), n):>9} "
              f"{np.mean([c['sube'] for c in casos]):>8.2f}% "
              f"{np.mean([c['cae'] for c in casos]):>8.2f}% "
              f"{np.mean(saldo):>8.2f}%")
    print()
    print("  Leido: si 'vuelve' y 'llega a +3.2%' son altos y 'cae otro tanto' bajo,")
    print("  la caida es un hoyo. Si es al reves, es el principio de un desplome.")

    # =================================================================
    print()
    print("=" * 104)
    print("3. LA ESCALERA DE ENTRADAS REALES")
    print("=" * 104)
    print(f"  Comprar con un descuento fijo sobre el precio de la señal, aguantando")
    print(f"  {VENTANA_H}h. El objetivo es siempre +{META}% DESDE LA COMPRA.")
    print()
    print(f"  {'compra en':<12} {'se llena':>10} {'ops':>5} {'acierto':>9} {'azar':>7} "
          f"{'ventaja':>8} {'media':>8} {'IC 95%':>17} {'mediana':>8}")
    for stop in STOPS:
        print(f"\n  --- con stop de -{stop}% bajo la compra ---")
        for desc in DESCUENTOS:
            res, par, tp_n, sl_n = [], [], 0, 0
            llenas = 0
            for d in datos:
                e = d["entry"]
                p = e * (1 - desc / 100.0)
                i = 0 if desc == 0 else primer_cruce(d["lo"], p, arriba=False)
                if i is None:
                    continue
                llenas += 1
                hi, lo, cl = d["hi"][i:], d["lo"][i:], d["cl"][i:]
                if len(hi) < 30:
                    continue
                techo, suelo = p * (1 + META / 100), p * (1 - stop / 100)
                t_up = primer_cruce(hi, techo, arriba=True)
                t_dn = primer_cruce(lo, suelo, arriba=False)
                if t_dn is not None and (t_up is None or t_dn <= t_up):
                    res.append(-stop); sl_n += 1
                elif t_up is not None:
                    res.append(META); tp_n += 1
                else:
                    res.append(float((cl[-1] - p) / p * 100))
                par.append(d["symbol"])
            if len(res) < 25:
                continue
            resueltas = tp_n + sl_n
            acierto = 100 * tp_n / resueltas if resueltas else float("nan")
            geo = 100 * stop / (META + stop)
            lo_, hi_ = boot_ci(res, par, rng)
            etq = "la señal" if desc == 0 else f"-{desc}%"
            print(f"  {etq:<12} {pct(llenas, len(datos)):>10} {len(res):>5} "
                  f"{acierto:>8.1f}% {geo:>6.1f}% {acierto-geo:>+7.1f} "
                  f"{np.mean(res):>7.2f}% [{lo_:>6.2f},{hi_:>6.2f}] "
                  f"{np.median(res):>7.2f}%")

    # =================================================================
    print()
    print("=" * 104)
    print("4. LO MISMO, SOLO EN LA PRIMERA SEÑAL DE CADA PAR")
    print("=" * 104)
    vistos = set()
    primeras = []
    for d in sorted(datos, key=lambda x: x["ts"]):
        if d["symbol"] in vistos:
            continue
        vistos.add(d["symbol"])
        primeras.append(d)
    print(f"  {len(primeras)} primeras señales\n")
    print(f"  {'compra en':<12} {'se llena':>10} {'ops':>5} {'acierto':>9} {'azar':>7} "
          f"{'ventaja':>8} {'media':>8} {'IC 95%':>17} {'mediana':>8}")
    for stop in (3.0, 5.0):
        print(f"\n  --- con stop de -{stop}% ---")
        for desc in DESCUENTOS:
            res, par, tp_n, sl_n, llenas = [], [], 0, 0, 0
            for d in primeras:
                e = d["entry"]
                p = e * (1 - desc / 100.0)
                i = 0 if desc == 0 else primer_cruce(d["lo"], p, arriba=False)
                if i is None:
                    continue
                llenas += 1
                hi, lo, cl = d["hi"][i:], d["lo"][i:], d["cl"][i:]
                if len(hi) < 30:
                    continue
                t_up = primer_cruce(hi, p * (1 + META / 100), arriba=True)
                t_dn = primer_cruce(lo, p * (1 - stop / 100), arriba=False)
                if t_dn is not None and (t_up is None or t_dn <= t_up):
                    res.append(-stop); sl_n += 1
                elif t_up is not None:
                    res.append(META); tp_n += 1
                else:
                    res.append(float((cl[-1] - p) / p * 100))
                par.append(d["symbol"])
            if len(res) < 20:
                continue
            resueltas = tp_n + sl_n
            acierto = 100 * tp_n / resueltas if resueltas else float("nan")
            geo = 100 * stop / (META + stop)
            lo_, hi_ = boot_ci(res, par, rng)
            etq = "la señal" if desc == 0 else f"-{desc}%"
            print(f"  {etq:<12} {pct(llenas, len(primeras)):>10} {len(res):>5} "
                  f"{acierto:>8.1f}% {geo:>6.1f}% {acierto-geo:>+7.1f} "
                  f"{np.mean(res):>7.2f}% [{lo_:>6.2f},{hi_:>6.2f}] "
                  f"{np.median(res):>7.2f}%")


if __name__ == "__main__":
    main()
