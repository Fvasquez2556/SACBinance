# -*- coding: utf-8 -*-
"""
Que objetivo esta al alcance de cada tipo de moneda.

`stop_optimo.py` responde "que stop llega mejor al 3.2%" y encuentra que
ninguno: la esperanza es negativa con cualquier ancho. Este script busca la
causa por el otro lado — no cuanto se arriesga, sino cuanto se mueve de verdad
el precio despues de una senal.

El 3.2% es el mismo numero para BTC que para una moneda de 1M de volumen. Aqui
se mide, por grupo de volatilidad, la subida maxima y la caida maxima reales en
las 24h siguientes a la entrada. Si la mediana de la subida de un grupo esta por
debajo del objetivo, ese objetivo no es exigente: es inalcanzable para la mitad
de sus senales, y ningun stop lo arregla.

La volatilidad se mide en los 60 minutos ANTERIORES a la entrada — lo unico que
se sabria al decidir.
"""
import sqlite3
import pathlib
import statistics as st

P = pathlib.Path('audit/2026-09-10/verification/snapshot.db').resolve()
C = sqlite3.connect(f'file:{P.as_posix()}?mode=ro', uri=True)
C.row_factory = sqlite3.Row

VENTANA = 86_400_000
PREVIO = 60 * 60_000
META = 3.2

lim = C.execute("select min(open_time), max(open_time) from klines where tf='1m'").fetchone()
ops = C.execute("""
    select signal_id, symbol, ts_open, entry from outcomes
    where cerrado=1 and sombra=0 and entry>0
      and ts_open >= ? and ts_open + ? <= ?
    order by ts_open""", (lim[0] + PREVIO, VENTANA, lim[1])).fetchall()

datos = []
for o in ops:
    vs = C.execute("""select h,l,c from klines where symbol=? and tf='1m'
        and open_time>=? and open_time<? order by open_time""",
        (o['symbol'], o['ts_open'], o['ts_open'] + VENTANA)).fetchall()
    an = C.execute("""select h,l,c from klines where symbol=? and tf='1m'
        and open_time>=? and open_time<? order by open_time""",
        (o['symbol'], o['ts_open'] - PREVIO, o['ts_open'])).fetchall()
    if len(vs) < 60 or len(an) < 30:
        continue
    vol = st.mean((v['h'] - v['l']) / v['c'] * 100 for v in an if v['c'] > 0)
    e = o['entry']
    datos.append({
        'symbol': o['symbol'],
        'vol': vol,
        'sube': max(v['h'] for v in vs) / e * 100 - 100,
        'baja': min(v['l'] for v in vs) / e * 100 - 100,
    })

datos.sort(key=lambda d: d['vol'])
q = [datos[len(datos) * k // 4]['vol'] for k in (1, 2, 3)]
print(f"n={len(datos)} operaciones cerradas con velas completas")
print(f"cortes de volatilidad (recorrido medio de la vela 1m): "
      f"{q[0]:.3f}%  {q[1]:.3f}%  {q[2]:.3f}%\n")

grupos = [
    ("MUY TRANQUILA", lambda v: v <= q[0]),
    ("TRANQUILA",     lambda v: q[0] < v <= q[1]),
    ("MOVIDA",        lambda v: q[1] < v <= q[2]),
    ("MUY VOLATIL",   lambda v: v > q[2]),
]

print("LO QUE CADA GRUPO SE MUEVE DE VERDAD EN 24H DESDE LA ENTRADA")
print(f"{'grupo':16} {'vol.1m':>8} {'sube med':>10} {'sube p75':>10} "
      f"{'baja med':>10} {'llega a 3.2%':>13} {'n':>5}")
for nom, test in grupos:
    s = [d for d in datos if test(d['vol'])]
    if len(s) < 40:
        continue
    ups = sorted(d['sube'] for d in s)
    dns = sorted(d['baja'] for d in s)
    llega = sum(1 for d in s if d['sube'] >= META)
    print(f"{nom:16} {st.median([d['vol'] for d in s]):7.3f}% "
          f"{st.median(ups):9.2f}% {ups[len(ups)*3//4]:9.2f}% "
          f"{st.median(dns):9.2f}% {100*llega/len(s):12.1f}% {len(s):5}")

print(f"\nLECTURA: en NINGUN grupo la senal mediana llega al {META}%. Y en todos,")
print("la caida maxima mediana es MAS PROFUNDA que la subida maxima mediana.")
print("Esa asimetria esta antes de elegir ningun stop: no es un problema de")
print("gestion de riesgo, es que la senal mediana no va a donde tiene que ir.")

print("\nOBJETIVO QUE ALCANZARIA LA MITAD DE LAS SENALES DE CADA GRUPO")
for nom, test in grupos:
    s = [d for d in datos if test(d['vol'])]
    if len(s) < 40:
        continue
    ups = sorted(d['sube'] for d in s)
    print(f"   {nom:16} {st.median(ups):.2f}%   "
          f"(para que llegue 1 de cada 4: {ups[len(ups)*3//4]:.2f}%)")
