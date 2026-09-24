"""
Comparacion PAREADA detector-control. Cada ruptura tiene su propio control en
el mismo par, mismo periodo y misma R, asi que la diferencia se mide dentro del
par y no entre poblaciones: mucho mas potente, y el ancho de la barrera deja de
contaminar la comparacion entre marcos.
"""
import gzip
import json
import math
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
D = json.load(gzip.open(os.path.join(AQUI, 'reeval.json.gz'), 'rt', encoding='utf-8'))
filas = {f['id']: f for f in D['filas']}
ev, ctl = D['eval'], D['control']


def usable(r):
    return bool(r) and r.get('madura') and r.get('esperadas') and r['n'] / r['esperadas'] >= 0.9


def rr(r, clave, gan):
    d = r.get(f'{clave}_desenlace')
    return gan if d == 'OBJETIVO' else (-1.0 if d == 'STOP' else (r.get('cierre_r') or 0.0))


def acierto(r, clave):
    return 1.0 if r.get(f'{clave}_desenlace') == 'OBJETIVO' else 0.0


pares = []
for i, r in ev.items():
    c = ctl.get(i)
    if usable(r) and usable(c):
        pares.append((filas[int(i)], r, c))
print(f'parejas detector/control utilizables: {len(pares)}')


def pareado(sub, clave, gan):
    n = len(sub)
    if n < 50:
        return None
    da = [acierto(r, clave) - acierto(c, clave) for _, r, c in sub]
    de = [rr(r, clave, gan) - rr(c, clave, gan) for _, r, c in sub]

    def mid(v):
        m = sum(v) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / max(1, n - 1))
        return m, 1.96 * sd / math.sqrt(n)
    ma, ia = mid(da)
    me, ie = mid(de)
    tasa = sum(acierto(r, clave) for _, r, c in sub) / n
    ctrl = sum(acierto(c, clave) for _, r, c in sub) / n
    return {'n': n, 'tasa': 100 * tasa, 'ctrl': 100 * ctrl,
            'dif_pp': 100 * ma, 'ic_pp': 100 * ia, 'dif_r': me, 'ic_r': ie}


def pinta(t, s):
    if not s:
        print(f'  {t:<30} sin muestra suficiente')
        return
    marca = '  ' if abs(s['dif_pp']) <= s['ic_pp'] else ('++' if s['dif_pp'] > 0 else '--')
    print(f"  {t:<30} n={s['n']:>6}  detector={s['tasa']:>5.1f}%  control={s['ctrl']:>5.1f}%  "
          f"dif={s['dif_pp']:+6.2f} pp ±{s['ic_pp']:.2f}  {s['dif_r']:+.3f}R ±{s['ic_r']:.3f} {marca}")


print('\n=== Pareado por marco y direccion, barrera simetrica ±1R ===')
print('   ++ / -- = el intervalo del 95 % no toca el cero\n')
for d in ('RUPTURA_ALCISTA', 'RUPTURA_BAJISTA'):
    print(f' {d}')
    sub = [p for p in pares if p[0]['direction'] == d]
    pinta('todos', pareado(sub, 'sim', 1.0))
    for tf in ('5m', '15m', '1h', '4h'):
        pinta(f'  marco {tf}', pareado([p for p in sub if p[0]['tf'] == tf], 'sim', 1.0))

print('\n=== Pareado con la geometria del plan +2R / -1R ===')
for d in ('RUPTURA_ALCISTA', 'RUPTURA_BAJISTA'):
    print(f' {d}')
    sub = [p for p in pares if p[0]['direction'] == d]
    pinta('todos', pareado(sub, 'plan', 2.0))
    for tf in ('5m', '15m', '1h', '4h'):
        pinta(f'  marco {tf}', pareado([p for p in sub if p[0]['tf'] == tf], 'plan', 2.0))

print('\n=== ¿Hay ALGUNA celda donde el detector bata a su control? (±1R) ===')


def tramo_vol(f):
    v = f.get('vol_ratio')
    if v is None:
        return None
    return '<1' if v < 1 else ('1-2' if v < 2 else '>=2')


cortes = [
    ('confirmada', lambda f: f'confirmada={f.get("confirmada")}'),
    ('tendencia', lambda f: f'tendencia={f.get("tendencia")}'),
    ('confluencia', lambda f: f'confirmadas={f.get("conf_confirmadas")}'),
    ('conflicto', lambda f: f'conflicto={f.get("conf_en_conflicto")}'),
    ('dominante', lambda f: f'dominante={f.get("conf_dominante")}'),
    ('volumen', lambda f: (f'vol {tramo_vol(f)}' if tramo_vol(f) else None)),
    ('toques', lambda f: f'toques={"2" if (f.get("toques_nivel") or 0)<=2 else ("3-4" if f["toques_nivel"]<=4 else ">=5")}'),
]
for d in ('RUPTURA_ALCISTA', 'RUPTURA_BAJISTA'):
    sub = [p for p in pares if p[0]['direction'] == d]
    print(f' {d}')
    for nombre, fn in cortes:
        grupos = {}
        for p in sub:
            k = fn(p[0])
            if k is not None:
                grupos.setdefault(k, []).append(p)
        for k in sorted(grupos):
            s = pareado(grupos[k], 'sim', 1.0)
            if s and s['n'] >= 300:
                pinta(f'  {k}', s)

print('\n=== Reparto de desenlaces: ¿el precio se queda quieto? ===')
for d in ('RUPTURA_ALCISTA', 'RUPTURA_BAJISTA'):
    sub = [p for p in pares if p[0]['direction'] == d]
    n = len(sub)
    venc = sum(1 for _, r, _ in sub if r.get('sim_desenlace') == 'VENCIDO')
    amb = sum(r.get('sim_ambiguo', 0) for _, r, _ in sub)
    salto = sum(r.get('sim_salto', 0) for _, r, _ in sub)
    mfe = sorted(r.get('mfe_r') or 0 for _, r, _ in sub)
    mae = sorted(r.get('mae_r') or 0 for _, r, _ in sub)
    q = lambda v, p: v[int(p * (len(v) - 1))]
    print(f' {d}: n={n} vencidos={100*venc/n:.2f}%  ambiguos={100*amb/n:.2f}%  '
          f'saltos={100*salto/n:.2f}%')
    print(f'    MFE mediana={q(mfe,.5):+.2f}R p90={q(mfe,.9):+.2f}R | '
          f'MAE mediana={q(mae,.5):+.2f}R p10={q(mae,.1):+.2f}R')
