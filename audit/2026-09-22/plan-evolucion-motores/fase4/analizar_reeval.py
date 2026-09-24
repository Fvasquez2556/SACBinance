"""Analisis local de la reevaluacion con barreras homogeneas en R."""
import gzip
import json
import math
import os
import random

AQUI = os.path.dirname(os.path.abspath(__file__))
D = json.load(gzip.open(os.path.join(AQUI, 'reeval.json.gz'), 'rt', encoding='utf-8'))

filas = {f['id']: f for f in D['filas']}
ev, ctl = D['eval'], D['control']
print(f"rupturas={len(filas)}  evaluadas={len(ev)}  control={len(ctl)}")


def usable(r, min_cob=0.9):
    if r is None or not r.get('madura') or not r.get('esperadas'):
        return False
    return r['n'] / r['esperadas'] >= min_cob


def rr(r, clave, gan):
    d = r.get(f'{clave}_desenlace')
    if d == 'OBJETIVO':
        return gan
    if d == 'STOP':
        return -1.0
    return r.get('cierre_r') or 0.0


def resumen(rs, clave, gan):
    n = len(rs)
    if not n:
        return None
    obj = sum(1 for r in rs if r.get(f'{clave}_desenlace') == 'OBJETIVO')
    stop = sum(1 for r in rs if r.get(f'{clave}_desenlace') == 'STOP')
    venc = n - obj - stop
    vals = [rr(r, clave, gan) for r in rs]
    media = sum(vals) / n
    sd = math.sqrt(sum((v - media) ** 2 for v in vals) / max(1, n - 1))
    return {'n': n, 'obj_pct': 100 * obj / n, 'stop_pct': 100 * stop / n,
            'venc_pct': 100 * venc / n, 'esperanza_r': media,
            'ic': 1.96 * sd / math.sqrt(n),
            'amb_pct': 100 * sum(r.get(f'{clave}_ambiguo', 0) for r in rs) / n}


def linea(t, s):
    if not s:
        return f"  {t:<34} sin muestra"
    return (f"  {t:<34} n={s['n']:>6}  objetivo={s['obj_pct']:>5.1f}%  "
            f"stop={s['stop_pct']:>5.1f}%  vencido={s['venc_pct']:>5.1f}%  "
            f"E={s['esperanza_r']:+.3f}R ±{s['ic']:.3f}")


# --- cobertura ---------------------------------------------------------------
maduras = [i for i, r in ev.items() if r.get('madura')]
buenas = [i for i, r in ev.items() if usable(r)]
print(f"maduras (12 h cumplidas)={len(maduras)}   con cobertura>=90%={len(buenas)}")

por_dir = {'RUPTURA_ALCISTA': [], 'RUPTURA_BAJISTA': []}
ctl_dir = {'RUPTURA_ALCISTA': [], 'RUPTURA_BAJISTA': []}
for i in buenas:
    f = filas[int(i)]
    por_dir[f['direction']].append(ev[i])
    c = ctl.get(i)
    if usable(c):
        ctl_dir[f['direction']].append(c)

print('\n=== 1. Barrera simetrica ±1R (azar ~50%) ===')
for d in por_dir:
    print(f" {d}")
    print(linea('detector', resumen(por_dir[d], 'sim', 1.0)))
    print(linea('control (entrada al azar)', resumen(ctl_dir[d], 'sim', 1.0)))

print('\n=== 2. Geometria del plan +2R / -1R (azar ~33%) ===')
for d in por_dir:
    print(f" {d}")
    print(linea('detector', resumen(por_dir[d], 'plan', 2.0)))
    print(linea('control (entrada al azar)', resumen(ctl_dir[d], 'plan', 2.0)))


# --- bootstrap de la diferencia ---------------------------------------------
def boot_dif(a, b, clave, gan, n=2000, semilla=7):
    if len(a) < 30 or len(b) < 30:
        return None
    rnd = random.Random(semilla)
    va = [rr(r, clave, gan) for r in a]
    vb = [rr(r, clave, gan) for r in b]
    ha = [1.0 if r.get(f'{clave}_desenlace') == 'OBJETIVO' else 0.0 for r in a]
    hb = [1.0 if r.get(f'{clave}_desenlace') == 'OBJETIVO' else 0.0 for r in b]
    dif_e, dif_h = [], []
    for _ in range(n):
        sa = [rnd.randrange(len(va)) for _ in range(len(va))]
        sb = [rnd.randrange(len(vb)) for _ in range(len(vb))]
        dif_e.append(sum(va[i] for i in sa) / len(sa) - sum(vb[i] for i in sb) / len(sb))
        dif_h.append(100 * (sum(ha[i] for i in sa) / len(sa) - sum(hb[i] for i in sb) / len(sb)))
    dif_e.sort(); dif_h.sort()
    q = lambda v, p: v[int(p * (len(v) - 1))]
    return {'esperanza': (q(dif_e, .025), sum(dif_e) / n, q(dif_e, .975)),
            'acierto': (q(dif_h, .025), sum(dif_h) / n, q(dif_h, .975))}


print('\n=== 3. Detector menos control, con intervalo del 95% ===')
for clave, gan, tit in (('sim', 1.0, '±1R'), ('plan', 2.0, '+2R/-1R')):
    for d in por_dir:
        b = boot_dif(por_dir[d], ctl_dir[d], clave, gan)
        if not b:
            continue
        e, h = b['esperanza'], b['acierto']
        print(f"  {tit:<8} {d:<17} acierto {h[1]:+5.2f} pp [{h[0]:+.2f}, {h[2]:+.2f}]"
              f"   esperanza {e[1]:+.3f} R [{e[0]:+.3f}, {e[2]:+.3f}]")


# --- celdas ------------------------------------------------------------------
def celdas(rs_ids, campo, fn=None, clave='sim', gan=1.0, min_n=100):
    grupos = {}
    for i in rs_ids:
        f = filas[int(i)]
        v = fn(f) if fn else f.get(campo)
        grupos.setdefault(v, []).append(ev[i])
    out = []
    for v, rs in grupos.items():
        s = resumen(rs, clave, gan)
        if s and s['n'] >= min_n:
            out.append((v, s))
    return sorted(out, key=lambda x: -x[1]['obj_pct'])


def tramo_vol(f):
    v = f.get('vol_ratio')
    if v is None:
        return 'sin dato'
    for t in (0.5, 1.0, 1.5, 2.5):
        if v < t:
            return f'<{t}'
    return '>=2.5'


def tramo_toques(f):
    t = f.get('toques_nivel')
    if t is None:
        return 'sin dato'
    return '2' if t <= 2 else ('3-4' if t <= 4 else ('5-7' if t <= 7 else '>=8'))


print('\n=== 4. Celdas, barrera simetrica ±1R (alcistas) ===')
alc = [i for i in buenas if filas[int(i)]['direction'] == 'RUPTURA_ALCISTA']
baj = [i for i in buenas if filas[int(i)]['direction'] == 'RUPTURA_BAJISTA']
for titulo, campo, fn in (
        ('marco', 'tf', None),
        ('confirmada', 'confirmada', None),
        ('tendencia del marco', 'tendencia', None),
        ('marcos confirmados', 'conf_confirmadas', None),
        ('marcos en conflicto', 'conf_en_conflicto', None),
        ('dominante', 'conf_dominante', None),
        ('toques del nivel', None, tramo_toques),
        ('volumen relativo', None, tramo_vol)):
    print(f" -- {titulo}")
    for v, s in celdas(alc, campo, fn):
        print(linea(str(v), s))

print('\n=== 5. Celdas, barrera simetrica ±1R (bajistas: ¿sigue cayendo?) ===')
for titulo, campo, fn in (('marco', 'tf', None), ('confirmada', 'confirmada', None),
                          ('tendencia del marco', 'tendencia', None),
                          ('marcos en conflicto', 'conf_en_conflicto', None)):
    print(f" -- {titulo}")
    for v, s in celdas(baj, campo, fn):
        print(linea(str(v), s))


# --- AUC ---------------------------------------------------------------------
def auc(ids, campo, clave='sim'):
    pos, neg = [], []
    for i in ids:
        d = ev[i].get(f'{clave}_desenlace')
        if d not in ('OBJETIVO', 'STOP'):
            continue
        v = filas[int(i)].get(campo)
        if v is None:
            continue
        (pos if d == 'OBJETIVO' else neg).append(float(v))
    if len(pos) < 50 or len(neg) < 50:
        return None
    todos = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank, i, n = {}, 0, len(todos)
    ranks = [0.0] * n
    while i < n:
        j = i
        while j + 1 < n and todos[j + 1][0] == todos[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[k] = r
        i = j + 1
    sp = sum(ranks[k] for k in range(n) if todos[k][1] == 1)
    np_, nn = len(pos), len(neg)
    return (sp - np_ * (np_ + 1) / 2) / (np_ * nn), np_, nn


print('\n=== 6. ¿Alguna columna ordena el resultado? (AUC, ±1R) ===')
print('    0,50 = no distingue nada. Se necesita >=0,60 para mirarlo dos veces.')
for nombre in ('atr_pct', 'rsi14', 'vol_ratio', 'toques_nivel', 'velas_desde_ruptura',
               'conf_confirmadas', 'conf_en_conflicto', 'conf_alcistas', 'conf_bajistas',
               'risk_pct', 'confirmada'):
    for etiq, ids in (('alcista', alc), ('bajista', baj)):
        a = auc(ids, nombre)
        if a:
            print(f"  {nombre:<22} {etiq:<8} AUC={a[0]:.3f}  (obj={a[1]}, stop={a[2]})")

# --- cuanto tarda ------------------------------------------------------------
print('\n=== 7. ¿Cabe en la jornada? minutos hasta el desenlace (±1R, alcistas) ===')
for d in ('OBJETIVO', 'STOP'):
    ms = sorted(ev[i]['sim_min'] for i in alc
                if ev[i].get('sim_desenlace') == d and ev[i].get('sim_min') is not None)
    if ms:
        q = lambda p: ms[int(p * (len(ms) - 1))]
        print(f"  {d:<9} n={len(ms):>6}  mediana={q(.5):>4} min  p75={q(.75):>4}  "
              f"p90={q(.9):>4}  dentro de 6h={100*sum(1 for m in ms if m<=360)/len(ms):.1f}%")
