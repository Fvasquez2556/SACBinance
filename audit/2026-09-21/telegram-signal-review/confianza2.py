import gzip,json,datetime,statistics as st
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert'); signals=build('signal')
F={r['signal_id']:r for r in json.load(gzip.open('feats.json.gz','rt'))}
R2=json.load(gzip.open('rejilla2.json.gz','rt')); FIJ=R2['fijos']; RM=R2['rmult']
EV=lambda r: r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None
S=[r for r in alerts if r['telegram']=='enviado' and EV(r)]
G=[r for r in signals if EV(r) and r['id'] in F]
COSTE=0.5
def antes(r,kind,t):
    g=R2[kind].get(str(r['id']))
    if not g: return None
    return t is not None and (r['ms_sl'] is None or t<r['ms_sl'])
def fijo(r,kind,p):
    g=R2[kind].get(str(r['id']));  return None if not g else antes(r,kind,g['fijos'][FIJ.index(p)])
def rmul(r,kind,m):
    g=R2[kind].get(str(r['id']));  return None if not g else antes(r,kind,g['r'][RM.index(m)])

print('=== Objetivos netos, con el stop del plan (avisos de Telegram n=%d)'%len(S))
for p in FIJ:
    v=[fijo(r,'alert',p) for r in S]; v=[x for x in v if x is not None]
    esp=[]
    for r in S:
        g=R2['alert'].get(str(r['id']));
        if not g: continue
        t=g['fijos'][FIJ.index(p)]
        if t is not None and (r['ms_sl'] is None or t<r['ms_sl']): esp.append(p-COSTE)
        elif r['ms_sl'] is not None: esp.append(-r['sl_pct']-COSTE)
        else: esp.append((r['close_fin_pct'] or 0)-COSTE)
    print(f'  objetivo +{p}% bruto (= +{p-COSTE:.1f}% neto): llega antes que el stop {100*sum(v)/len(v):5.1f}% | esperanza {st.mean(esp):+.2f}%')

print('\n=== Objetivo expresado en múltiplos del riesgo R (R = entrada − stop)')
for m in RM:
    v=[rmul(r,'alert',m) for r in S]; v=[x for x in v if x is not None]
    w=[rmul(r,'signal',m) for r in G]; w=[x for x in w if x is not None]
    print(f'  {m:4.2f} R: Telegram {100*sum(v)/len(v):5.1f}%  |  todas las señales {100*sum(w)/len(w):5.1f}%')

def auc(pairs):
    pairs=[(x,y) for x,y in pairs if x is not None and y is not None]
    pos=[x for x,y in pairs if y]; neg=[x for x,y in pairs if not y]
    if len(pos)<20 or len(neg)<20: return None
    xs=sorted(pos+neg); ranks={}; i=0
    while i<len(xs):
        j=i
        while j+1<len(xs) and xs[j+1]==xs[i]: j+=1
        ranks[xs[i]]=(i+j)/2+1; i=j+1
    s=sum(ranks[x] for x in pos)
    return (s-len(pos)*(len(pos)+1)/2)/(len(pos)*len(neg))

print('\n=== ¿Discrimina algo cuando el objetivo es 1R (neutral a volatilidad)?  [todas las señales]')
corte=datetime.datetime(2026,9,15,tzinfo=datetime.timezone.utc).timestamp()*1000
campos=['score','rango_1h_pct','atr_pct','ruido_1m_pct','vol_ratio','z_rise','consumido_pct','pos_en_rango',
        'dist_resistencia_pct','rsi14','rsi14_15m','macd_hist','buy_ratio_30s','fuerza_impulso','macro_gate_mult','senal_n','sigma_pct']
for et,sel in (('hasta 14-sep',[r for r in G if r['ts_open']<corte]),('15–21 sep',[r for r in G if r['ts_open']>=corte])):
    base=[rmul(r,'signal',1.0) for r in sel]; base=[x for x in base if x is not None]
    print(f'\n  {et}: n={len(sel)} | tasa base 1R antes del stop {100*sum(base)/len(base):.1f}%')
    out=[]
    for c in campos:
        a=auc([(F[r['id']].get(c),rmul(r,'signal',1.0)) for r in sel])
        if a: out.append((abs(a-0.5),a,c))
    for _,a,c in sorted(out,reverse=True)[:6]:
        print(f'    {c:22s} AUC {a:.3f}')
    a=auc([(F[r['id']].get('score'),rmul(r,'signal',1.0)) for r in sel])
    print(f'    {"score (referencia)":22s} AUC {a:.3f}')

print('\n=== Reparto de 1R por escenario y tramo horario (todas las señales, 15–21 sep)')
sel=[r for r in G if r['ts_open']>=corte]
from collections import defaultdict
g=defaultdict(list)
for r in sel:
    v=rmul(r,'signal',1.0)
    if v is not None: g[r['estado']].append(v)
for k,v in sorted(g.items(),key=lambda x:-len(x[1])):
    if len(v)<30: continue
    print(f'  {k:22s} n={len(v):4d} 1R antes del stop {100*sum(v)/len(v):5.1f}%')
