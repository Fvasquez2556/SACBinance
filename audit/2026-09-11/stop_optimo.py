# -*- coding: utf-8 -*-
"""
Que ancho de stop llega mejor al 3.2%, y si eso cambia segun el tipo de moneda.

No usa la escalera de la tabla (solo tiene barrotes en 1.0, 1.2, 2.0, 3.2...):
reproduce cada operacion vela a vela sobre las 24h de klines de 1m guardadas,
asi que el ancho de stop se barre en pasos de 0.1%.

Reglas de ejecucion, las mismas que el tracker en vivo:
  - Se entra al precio de la senal (`entry`).
  - Solo cuentan las velas que abren DESPUES de la emision.
  - Si una vela toca el stop y el objetivo a la vez, el orden dentro del minuto
    es desconocido: se cuenta como STOP. Supuesto pesimista, y se reporta.
  - Si al cerrar la ventana no se toco ninguno, se sale a mercado al ultimo
    cierre.

El coste (comision + deslizamiento) se descuenta SIEMPRE, gane o pierda.

La volatilidad con la que se agrupa se mide en los 60 minutos ANTERIORES a la
entrada, nunca dentro de la ventana: agrupar por lo que paso despues seria
elegir el stop sabiendo el futuro, y cualquier regla que saliera de ahi no se
podria aplicar en vivo.

Validacion: el replay reproduce exactamente la escalera guardada (242/798
llegan a +3.2%, cero discrepancias). Ver `verificar_contra_escalera()`.
"""
import sqlite3
import pathlib
import statistics as st
from bisect import bisect_left

P = pathlib.Path('audit/2026-09-10/verification/snapshot.db').resolve()
C = sqlite3.connect(f'file:{P.as_posix()}?mode=ro', uri=True)
C.row_factory = sqlite3.Row

META = 3.2          # el objetivo de Felix
COSTE = 0.5         # puntos porcentuales, ida y vuelta
VENTANA = 86_400_000
PREVIO = 60 * 60_000        # 60 min antes de la entrada, para medir volatilidad
STOPS = [round(0.8 + 0.1 * k, 1) for k in range(33)]   # 0.8% .. 4.0%


def cargar():
    lim = C.execute("select min(open_time), max(open_time) from klines where tf='1m'").fetchone()
    ops = C.execute("""
        select signal_id, symbol, ts_open, entry, sl_pct, tp_pct, score, tier,
               display_state, vol_24h, forma, ms_up_32
        from outcomes
        where cerrado=1 and sombra=0 and entry>0
          and ts_open >= ? and ts_open + ? <= ?
        order by ts_open""", (lim[0] + PREVIO, VENTANA, lim[1])).fetchall()
    out = []
    for o in ops:
        velas = C.execute("""
            select open_time, h, l, c from klines
            where symbol=? and tf='1m' and open_time>=? and open_time<?
            order by open_time""",
            (o['symbol'], o['ts_open'], o['ts_open'] + VENTANA)).fetchall()
        if len(velas) < 60:
            continue
        antes = C.execute("""
            select h, l, c from klines
            where symbol=? and tf='1m' and open_time>=? and open_time<?
            order by open_time""",
            (o['symbol'], o['ts_open'] - PREVIO, o['ts_open'])).fetchall()
        if len(antes) < 30:
            continue
        d = dict(o)
        # Volatilidad previa: recorrido medio de la vela, en % del cierre.
        d['vol_previa'] = st.mean((v['h'] - v['l']) / v['c'] * 100.0
                                  for v in antes if v['c'] > 0)
        # De donde viene: cuanto se ha movido en esa hora previa.
        d['deriva_previa'] = ((antes[-1]['c'] - antes[0]['c']) / antes[0]['c'] * 100.0
                              if antes[0]['c'] > 0 else 0.0)
        out.append((d, velas))
    return out


def perfil(entry, velas):
    """Indice del primer toque de +3.2%, y los minimos decrecientes con su indice."""
    techo = entry * (1 + META / 100.0)
    i_meta = None
    minimos, indices = [], []
    corriendo = float('inf')
    for i, v in enumerate(velas):
        if i_meta is None and v['h'] >= techo:
            i_meta = i
        if v['l'] < corriendo:
            corriendo = v['l']
            minimos.append(corriendo)
            indices.append(i)
    return i_meta, minimos, indices, velas[-1]['c']


def desenlace(p, entry, x):
    i_meta, minimos, indices, cierre = p
    suelo = entry * (1 - x / 100.0)
    k = bisect_left([-m for m in minimos], -suelo)
    i_stop = indices[k] if k < len(minimos) else None
    if i_stop is None and i_meta is None:
        return 'ABIERTA', (cierre - entry) / entry * 100.0
    if i_stop is None:
        return 'META', META
    if i_meta is None:
        return 'STOP', -x
    if i_stop < i_meta:
        return 'STOP', -x
    if i_meta < i_stop:
        return 'META', META
    return 'AMBIGUA', -x


def verificar_contra_escalera(muestra):
    mal = sum(1 for o, p in muestra
              if (p[0] is not None) != (o['ms_up_32'] is not None))
    llegan = sum(1 for o, p in muestra if p[0] is not None)
    print(f"Validacion: el replay y la escalera guardada coinciden en "
          f"{len(muestra)-mal}/{len(muestra)} operaciones "
          f"({llegan} llegan a +3.2% = {100*llegan/len(muestra):.1f}%)")
    return mal == 0


def barrer(muestra, titulo, detalle=True):
    """Devuelve (mejor_stop, esperanza, %meta, %parado, n) o None si es poca muestra."""
    if len(muestra) < 40:
        return None
    filas = []
    for x in STOPS:
        res = [desenlace(p, o['entry'], x) for o, p in muestra]
        netos = [r[1] - COSTE for r in res]
        meta = sum(1 for q, _ in res if q == 'META')
        stop = sum(1 for q, _ in res if q in ('STOP', 'AMBIGUA'))
        abie = sum(1 for q, _ in res if q == 'ABIERTA')
        amb = sum(1 for q, _ in res if q == 'AMBIGUA')
        filas.append((x, meta, stop, abie, amb, st.mean(netos), st.median(netos)))
    mejor = max(filas, key=lambda f: f[5])
    n = len(muestra)
    if detalle:
        print(f"\n{'='*78}\n{titulo}   (n={n})\n{'='*78}")
        print(f"{'stop':>5} {'llega 3.2%':>12} {'parado':>8} {'abierta':>8} "
              f"{'ambigua':>8} {'esperanza':>11}")
        for x, meta, stop, abie, amb, esp, med in filas:
            if round(x * 10) % 2 and x != mejor[0]:
                continue        # de 0.2 en 0.2 para que quepa, salvo el mejor
            marca = '  <-- mejor' if x == mejor[0] else ''
            print(f"{x:5.1f} {meta:7}/{n:<4} {stop:8} {abie:8} {amb:8} "
                  f"{esp:+10.3f}%{marca}")
    return (mejor[0], mejor[5], 100*mejor[1]/n, 100*mejor[2]/n, n)


def cuartiles(muestra, campo):
    vals = sorted(o[campo] for o, _ in muestra)
    return [vals[len(vals)*k//4] for k in (1, 2, 3)]


print("Cargando operaciones con velas completas...")
OPS = cargar()
PERF = [(o, perfil(o['entry'], v)) for o, v in OPS]
print(f"  {len(OPS)} operaciones reales cerradas, con sus 24h de velas de 1m")
verificar_contra_escalera(PERF)

barrer(PERF, "1 · TODAS LAS OPERACIONES")

# ---------------------------------------------------------------- por volatilidad
q1, q2, q3 = cuartiles(PERF, 'vol_previa')
print(f"\n\n{'#'*78}\n2 · POR VOLATILIDAD PREVIA (recorrido medio de la vela 1m, hora anterior)")
print(f"    cortes de cuartil: {q1:.3f}%  {q2:.3f}%  {q3:.3f}%\n{'#'*78}")
grupos = [
    ("MUY TRANQUILA", lambda v: v <= q1),
    ("TRANQUILA",     lambda v: q1 < v <= q2),
    ("MOVIDA",        lambda v: q2 < v <= q3),
    ("MUY VOLATIL",   lambda v: v > q3),
]
resumen = []
for nom, test in grupos:
    sub = [(o, p) for o, p in PERF if test(o['vol_previa'])]
    r = barrer(sub, f"2.{len(resumen)+1} · {nom}")
    if r:
        vm = st.median([o['vol_previa'] for o, _ in sub])
        resumen.append((nom, vm, *r))

print(f"\n\n{'='*78}\nRESUMEN POR VOLATILIDAD\n{'='*78}")
print(f"{'grupo':16} {'vol.1m':>8} {'stop optimo':>12} {'esperanza':>11} "
      f"{'llega':>7} {'parado':>8} {'n':>5}")
for nom, vm, stop, esp, pmeta, pstop, n in resumen:
    print(f"{nom:16} {vm:7.3f}% {stop:11.1f}% {esp:+10.3f}% "
          f"{pmeta:6.1f}% {pstop:7.1f}% {n:5}")

# ---------------------------------------------------------------- por deriva previa
print(f"\n\n{'#'*78}\n3 · POR DE DONDE VIENE (movimiento en la hora previa)\n{'#'*78}")
res2 = []
for nom, test in [("VIENE CAYENDO (<-1%)", lambda d: d < -1.0),
                  ("PLANA (-1% a +1%)",    lambda d: -1.0 <= d <= 1.0),
                  ("VIENE SUBIENDO (>+1%)", lambda d: d > 1.0)]:
    sub = [(o, p) for o, p in PERF if test(o['deriva_previa'])]
    r = barrer(sub, f"3 · {nom}", detalle=False)
    if r:
        res2.append((nom, *r))
print(f"{'grupo':24} {'stop optimo':>12} {'esperanza':>11} {'llega':>7} {'parado':>8} {'n':>5}")
for nom, stop, esp, pmeta, pstop, n in res2:
    print(f"{nom:24} {stop:11.1f}% {esp:+10.3f}% {pmeta:6.1f}% {pstop:7.1f}% {n:5}")

# ---------------------------------------------------------------- por estado y score
print(f"\n\n{'#'*78}\n4 · POR ESTADO Y POR SCORE\n{'#'*78}")
estados = sorted({o['display_state'] for o, _ in PERF})
print(f"{'grupo':24} {'stop optimo':>12} {'esperanza':>11} {'llega':>7} {'parado':>8} {'n':>5}")
for e in estados:
    sub = [(o, p) for o, p in PERF if o['display_state'] == e]
    r = barrer(sub, '', detalle=False)
    if r:
        print(f"{e:24} {r[0]:11.1f}% {r[1]:+10.3f}% {r[2]:6.1f}% {r[3]:7.1f}% {r[4]:5}")
for lo, hi in ((0, 69), (70, 79), (80, 100)):
    sub = [(o, p) for o, p in PERF if lo <= (o['score'] or 0) <= hi]
    r = barrer(sub, '', detalle=False)
    if r:
        print(f"{'score '+str(lo)+'-'+str(hi):24} {r[0]:11.1f}% {r[1]:+10.3f}% "
              f"{r[2]:6.1f}% {r[3]:7.1f}% {r[4]:5}")

# ---------------------------------------------------------------- arquetipos de moneda
print(f"\n\n{'#'*78}\n5 · ARQUETIPOS DE MONEDA (por su comportamiento medio)\n{'#'*78}")
porsim = {}
for o, p in PERF:
    porsim.setdefault(o['symbol'], []).append((o, p))
perfiles = []
for sym, lst in porsim.items():
    if len(lst) < 5:
        continue
    vol = st.median([o['vol_previa'] for o, _ in lst])
    llega = sum(1 for _, p in lst if p[0] is not None) / len(lst) * 100
    v24 = st.median([o['vol_24h'] or 0 for o, _ in lst])
    perfiles.append((sym, vol, llega, v24, len(lst)))
perfiles.sort(key=lambda x: -x[2])
print(f"monedas con >=5 operaciones cerradas: {len(perfiles)}\n")
print("LAS 12 QUE MAS LLEGAN A +3.2%")
print(f"{'moneda':14} {'vol.1m':>8} {'llega':>8} {'vol.24h':>14} {'ops':>5}")
for s, v, l, v24, n in perfiles[:12]:
    print(f"{s:14} {v:7.3f}% {l:7.1f}% {v24:13,.0f} {n:5}")
print("\nLAS 12 QUE MENOS")
for s, v, l, v24, n in perfiles[-12:]:
    print(f"{s:14} {v:7.3f}% {l:7.1f}% {v24:13,.0f} {n:5}")
vols = [p[1] for p in perfiles]
lleg = [p[2] for p in perfiles]
if len(vols) > 10:
    m_v, m_l = st.mean(vols), st.mean(lleg)
    cov = sum((a-m_v)*(b-m_l) for a, b in zip(vols, lleg)) / len(vols)
    r = cov / (st.pstdev(vols) * st.pstdev(lleg))
    print(f"\nCorrelacion entre volatilidad de la moneda y su tasa de llegar a 3.2%: "
          f"r = {r:+.2f}  (n={len(perfiles)} monedas)")
