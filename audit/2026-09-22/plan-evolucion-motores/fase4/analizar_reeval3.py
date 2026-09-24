"""
Lo unico que batio al control en toda la medicion son las rupturas alcistas de
1h y 4h. Antes de dejar que eso oriente la fase 4 hay que preguntarle lo de
siempre: ¿se sostiene fuera de la mitad donde se vio, o es un dia?
"""
import gzip
import json
import math
import os
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
D = json.load(gzip.open(os.path.join(AQUI, 'reeval.json.gz'), 'rt', encoding='utf-8'))
filas = {f['id']: f for f in D['filas']}
ev, ctl = D['eval'], D['control']


def usable(r):
    return bool(r) and r.get('madura') and r.get('esperadas') and r['n'] / r['esperadas'] >= 0.9


def acierto(r, clave='sim'):
    return 1.0 if r.get(f'{clave}_desenlace') == 'OBJETIVO' else 0.0


def rr(r, clave, gan):
    d = r.get(f'{clave}_desenlace')
    return gan if d == 'OBJETIVO' else (-1.0 if d == 'STOP' else (r.get('cierre_r') or 0.0))


pares = [(filas[int(i)], r, ctl[i]) for i, r in ev.items()
         if usable(r) and usable(ctl.get(i))]


def pareado(sub, clave='sim', gan=1.0):
    n = len(sub)
    if n < 30:
        return None
    da = [acierto(r, clave) - acierto(c, clave) for _, r, c in sub]
    de = [rr(r, clave, gan) - rr(c, clave, gan) for _, r, c in sub]

    def mid(v):
        m = sum(v) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / max(1, n - 1))
        return m, 1.96 * sd / math.sqrt(n)
    ma, ia = mid(da)
    me, ie = mid(de)
    return {'n': n, 'tasa': 100 * sum(acierto(r, clave) for _, r, _ in sub) / n,
            'ctrl': 100 * sum(acierto(c, clave) for _, _, c in sub) / n,
            'dif': 100 * ma, 'ic': 100 * ia, 'difr': me, 'icr': ie}


def pinta(t, s):
    if not s:
        print(f'  {t:<26} sin muestra')
        return
    m = '  ' if abs(s['dif']) <= s['ic'] else ('++' if s['dif'] > 0 else '--')
    print(f"  {t:<26} n={s['n']:>5}  det={s['tasa']:>5.1f}%  ctl={s['ctrl']:>5.1f}%  "
          f"dif={s['dif']:+6.2f} pp ±{s['ic']:.2f}   {s['difr']:+.3f}R ±{s['icr']:.3f} {m}")


alc_lentos = [p for p in pares
              if p[0]['direction'] == 'RUPTURA_ALCISTA' and p[0]['tf'] in ('1h', '4h')]
ts = sorted(p[0]['ts_open'] for p in alc_lentos)
corte = ts[len(ts) // 2]
print(f"corte temporal: {datetime.fromtimestamp(corte/1000, timezone.utc):%d-%b %H:%M} UTC\n")

print('=== Rupturas alcistas de marco lento, partidas por la mitad del periodo ===')
for etiq, sub in (('primera mitad', [p for p in alc_lentos if p[0]['ts_open'] < corte]),
                  ('segunda mitad', [p for p in alc_lentos if p[0]['ts_open'] >= corte])):
    pinta(etiq, pareado(sub))
    for tf in ('1h', '4h'):
        pinta(f'  {tf}', pareado([p for p in sub if p[0]['tf'] == tf]))

print('\n=== Dia a dia (UTC), 1h y 4h alcistas juntos ===')
por_dia = {}
for p in alc_lentos:
    d = f"{datetime.fromtimestamp(p[0]['ts_open']/1000, timezone.utc):%d-%b}"
    por_dia.setdefault(d, []).append(p)
for d in sorted(por_dia, key=lambda x: min(p[0]['ts_open'] for p in por_dia[x])):
    pinta(d, pareado(por_dia[d]))

print('\n=== ¿Y cuantas de esas se resuelven dentro de la jornada? ===')
for tf in ('1h', '4h'):
    sub = [p for p in alc_lentos if p[0]['tf'] == tf]
    n = len(sub)
    if not n:
        continue
    venc = sum(1 for _, r, _ in sub if r.get('sim_desenlace') == 'VENCIDO')
    ms = sorted(r['sim_min'] for _, r, _ in sub if r.get('sim_min') is not None)
    q = lambda p: ms[int(p * (len(ms) - 1))] if ms else None
    print(f'  {tf}: n={n}  sin resolver en 12 h={100*venc/n:.1f}%  '
          f'mediana={q(.5)} min  p75={q(.75)}  p90={q(.9)}')

print('\n=== Cuantas hay al dia: ¿da para operar? ===')
for tf in ('5m', '15m', '1h', '4h'):
    n = sum(1 for f in filas.values()
            if f['tf'] == tf and f['direction'] == 'RUPTURA_ALCISTA')
    span = (max(f['ts_open'] for f in filas.values())
            - min(f['ts_open'] for f in filas.values())) / 86400_000
    print(f'  {tf}: {n} alcistas en {span:.1f} dias = {n/span:.0f}/dia sobre 319 pares')

print('\n=== El hallazgo bajista: ruptura a la baja CON volumen ===')
baj = [p for p in pares if p[0]['direction'] == 'RUPTURA_BAJISTA']
for etiq, fn in (('vol >=2', lambda f: (f.get('vol_ratio') or 0) >= 2),
                 ('vol 1-2', lambda f: 1 <= (f.get('vol_ratio') or 0) < 2),
                 ('vol <1', lambda f: f.get('vol_ratio') is not None and f['vol_ratio'] < 1)):
    sub = [p for p in baj if fn(p[0])]
    pinta(etiq, pareado(sub))
    mitad = sorted(p[0]['ts_open'] for p in sub)
    if len(mitad) >= 60:
        c = mitad[len(mitad) // 2]
        pinta('   1a mitad', pareado([p for p in sub if p[0]['ts_open'] < c]))
        pinta('   2a mitad', pareado([p for p in sub if p[0]['ts_open'] >= c]))
