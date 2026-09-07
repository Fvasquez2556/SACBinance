# -*- coding: utf-8 -*-
"""
1. ¿Cuantas operaciones efectivas al dia, y entre que horas?
2. ¿Se puede saber DE ANTEMANO si subira directo o bajara antes de subir?

La segunda es la pregunta que Felix lleva siguiendo. Es distinta de todo lo
medido hasta ahora: no es "¿llegara a +3.2%?" sino, entre las que SI llegan,
"¿ira directo o me hara pasar por un retroceso primero?".

Importa porque cambia el stop que hace falta. Una DIRECTO aguanta con un stop
corto; una DIP_Y_SUBE lo salta y te saca de una operacion que iba a funcionar
—que es exactamente el 33% de casos que se midio esta manana.

Se prueba si alguna variable disponible EN EL MOMENTO DE LA SENAL separa las
dos. Si ninguna lo hace, la respuesta honesta es que no se puede saber, y
entonces el stop hay que dimensionarlo para el peor caso, no para el tipico.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import Counter, defaultdict

import numpy as np

DB = "data/sacbinance.db"
META = 3.2
TZ = -6
MIN_N = 30


def gt(ts):
    return dt.datetime.utcfromtimestamp(ts / 1000) + dt.timedelta(hours=TZ)


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    filas = [dict(r) for r in con.execute(
        "SELECT * FROM outcomes WHERE sombra=0 AND entry IS NOT NULL "
        "ORDER BY ts_open")]

    # ------------------------------------------------------------------
    print("=" * 94)
    print("1. RITMO: operaciones efectivas por dia")
    print("=" * 94)
    por_dia = defaultdict(list)
    for f in filas:
        por_dia[gt(f["ts_open"]).date()].append(f)

    print(f"  {'dia':>12} {'emitidas':>9} {'llegaron a +3.2%':>17} "
          f"{'1a en cumplir':>14} {'ultima':>8} {'mediana':>9}")
    for dia in sorted(por_dia):
        g = por_dia[dia]
        # "efectiva" = alcanzo la meta, y lo hizo dentro del mismo dia natural
        hechas = []
        for f in g:
            if f["ms_up_32"] is None:
                continue
            t_meta = gt(f["ts_open"] + f["ms_up_32"])
            if t_meta.date() == dia:
                hechas.append((t_meta, f["ms_up_32"]))
        if not hechas:
            print(f"  {str(dia):>12} {len(g):>9} {0:>17}")
            continue
        hechas.sort()
        med = np.median([h[1] for h in hechas]) / 60000.0
        print(f"  {str(dia):>12} {len(g):>9} "
              f"{len(hechas):>7} ({100*len(hechas)/len(g):>4.1f}%) "
              f"{hechas[0][0].strftime('%H:%M'):>14} "
              f"{hechas[-1][0].strftime('%H:%M'):>8} "
              f"{med:>7.0f}min")

    completos = [d for d in sorted(por_dia) if len(por_dia[d]) > 100]
    if completos:
        tot = sum(len(por_dia[d]) for d in completos)
        efe = 0
        for d in completos:
            for f in por_dia[d]:
                if f["ms_up_32"] is not None and \
                        gt(f["ts_open"] + f["ms_up_32"]).date() == d:
                    efe += 1
        print(f"\n  Solo dias completos ({len(completos)}): "
              f"{tot/len(completos):.0f} senales/dia, "
              f"{efe/len(completos):.0f} efectivas/dia "
              f"({100*efe/tot:.1f}%)")

    # ------------------------------------------------------------------
    print("\n" + "=" * 94)
    print("2. ¿SUBE DIRECTO O BAJA PRIMERO? — reparto")
    print("=" * 94)
    cer = [f for f in filas if f["cerrado"]]
    formas = Counter(f["forma"] or "—" for f in cer)
    for k, n in formas.most_common():
        print(f"  {k:<14} {n:>5}  {100*n/len(cer):>5.1f}%")

    gan = [f for f in cer if f["forma"] in ("DIRECTO", "DIP_Y_SUBE")]
    dire = [f for f in gan if f["forma"] == "DIRECTO"]
    dip = [f for f in gan if f["forma"] == "DIP_Y_SUBE"]
    print(f"\n  De las {len(gan)} que llegaron a la meta:")
    print(f"    DIRECTO     {len(dire):>4}  {100*len(dire)/len(gan):.1f}%")
    print(f"    DIP_Y_SUBE  {len(dip):>4}  {100*len(dip)/len(gan):.1f}%")
    if dip:
        dips = [f["dip_antes_obj"] for f in dip if f.get("dip_antes_obj")]
        if dips:
            print(f"    el retroceso previo: mediana {np.median(dips):+.2f}%   "
                  f"p90 {np.percentile(dips, 10):+.2f}%   peor {min(dips):+.2f}%")

    # ------------------------------------------------------------------
    print("\n" + "=" * 94)
    print("3. ¿ALGO EN EL MOMENTO DE LA SENAL LO ANTICIPA?")
    print("=" * 94)
    print("  Si una variable separa DIRECTO de DIP_Y_SUBE, el % de DIRECTO")
    print("  cambiara entre sus bandas. Si no cambia, no anticipa nada.\n")
    base = 100 * len(dire) / len(gan)
    print(f"  base: {base:.1f}% de las ganadoras van DIRECTO\n")

    def separa(nombre, clave, bandas):
        print(f"  por {nombre}:")
        for lo, hi, lab in bandas:
            sel = [f for f in gan
                   if f.get(clave) is not None and lo <= f[clave] < hi]
            if len(sel) < MIN_N:
                print(f"    {lab:<18} (pocas: {len(sel)})")
                continue
            d = sum(1 for f in sel if f["forma"] == "DIRECTO")
            print(f"    {lab:<18} n={len(sel):>4}  DIRECTO {100*d/len(sel):>5.1f}%  "
                  f"({100*d/len(sel) - base:+5.1f})")
        print()

    separa("score", "score", [(0, 70, "< 70"), (70, 80, "70-80"),
                              (80, 90, "80-90"), (90, 200, ">= 90")])
    separa("volumen 24h", "vol_24h", [(0, 2e6, "< 2M"), (2e6, 5e6, "2-5M"),
                                      (5e6, 2e7, "5-20M"), (2e7, 1e12, "> 20M")])
    separa("volumen 1m", "vol_1m_medio",
           [(0, 1000, "< 1.000"), (1000, 5000, "1.000-5.000"),
            (5000, 20000, "5.000-20.000"), (20000, 1e12, "> 20.000")])
    separa("TP ofrecido", "tp_pct", [(0, 2, "< 2%"), (2, 3.2, "2-3.2%"),
                                     (3.2, 6, "3.2-6%"), (6, 100, "> 6%")])

    for campo in ("tier", "display_state", "macro", "taxonomia"):
        print(f"  por {campo}:")
        vals = sorted({f[campo] for f in gan if f[campo]})
        for v in vals:
            sel = [f for f in gan if f[campo] == v]
            if len(sel) < MIN_N:
                print(f"    {str(v):<18} (pocas: {len(sel)})")
                continue
            d = sum(1 for f in sel if f["forma"] == "DIRECTO")
            print(f"    {str(v):<18} n={len(sel):>4}  DIRECTO {100*d/len(sel):>5.1f}%  "
                  f"({100*d/len(sel) - base:+5.1f})")
        print()

    # ------------------------------------------------------------------
    print("=" * 94)
    print("4. LAS QUE CUMPLEN, BAJAN Y VUELVEN A CUMPLIR")
    print("=" * 94)
    # Una senal que toca la meta, cae por debajo del entry y vuelve a tocarla
    multi = [f for f in cer if f["ms_up_32"] is not None
             and f["ms_dn_12"] is not None and f["ms_dn_12"] > f["ms_up_32"]]
    llegaron = [f for f in cer if f["ms_up_32"] is not None]
    print(f"  De {len(llegaron)} que llegaron a +{META}%:")
    print(f"    {len(multi)} ({100*len(multi)/len(llegaron):.1f}%) despues "
          f"cayeron a -1.2% desde el entry")
    vuelven = [f for f in multi if (f["mfe_pct"] or 0) >= META + 1.0]
    print(f"    de esas, {len(vuelven)} llegaron a superar +{META+1.0}% en algun momento")
    print("\n  Ojo: el sistema guarda el MAXIMO y el MINIMO, no cada pasada.")
    print("  Contar cuantas veces cruza la meta necesitaria recorrer las velas")
    print("  una a una — se puede hacer, pero no esta en la tabla actual.")


if __name__ == "__main__":
    main()
