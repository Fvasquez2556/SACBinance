"""¿Discrimina algo la puntuación? Prueba prospectiva del hallazgo de 14-sep (rango_1h_pct)."""
import gzip,json,datetime,statistics as st,random
from collections import Counter,defaultdict
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert'); signals=build('signal')
F={r['signal_id']:r for r in json.load(gzip.open('feats.json.gz','rt'))}
R=json.load(gzip.open('rejilla.json.gz','rt')); UP=R['up']
EV=lambda r: r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None
COSTE=0.5
def gana(r,t=None):  # objetivo antes que el stop DEL PLAN
    tt=r['ms_tp'] if t is None else r['ms_meta']
    return tt is not None and (r['ms_sl'] is None or tt<r['ms_sl'])
def gana_nivel(r,kind,pct):
    g=R[kind].get(str(r['id']));
    if not g: return None
    tu=g['up'][UP.index(pct)]
    return tu is not None and (r['ms_sl'] is None or tu<r['ms_sl'])

S=[r for r in alerts if r['telegram']=='enviado' and EV(r)]
print('=== Tasa de llegar a cada objetivo ANTES del stop del plan (avisos de Telegram, n=%d)'%len(S))
for p in (2,2.5,3,3.2,4,5,6):
    v=[gana_nivel(r,'alert',p) for r in S]; v=[x for x in v if x is not None]
    print(f'  +{p}% bruto → {100*sum(v)/len(v):5.1f}%   (neto {p-COSTE:.1f}%)')
print(f'  TP del plan (mediana +6,72%) → {100*sum(gana(r) for r in S)/len(S):5.1f}%')

G=[r for r in signals if EV(r) and r['id'] in F]
print('\n=== ¿Qué columna ordena? AUC de "llega al +3,2% antes que el stop"')
def auc(pairs):
    pairs=[(x,y) for x,y in pairs if x is not None]
    pos=[x for x,y in pairs if y]; neg=[x for x,y in pairs if not y]
    if len(pos)<20 or len(neg)<20: return None,len(pos),len(neg)
    allv=sorted(set(pos+neg)); rank={v:i for i,v in enumerate(sorted(pos+neg))}
    # Mann-Whitney con empates promediados
    xs=sorted(pos+neg); ranks={}
    i=0
    while i<len(xs):
        j=i
        while j+1<len(xs) and xs[j+1]==xs[i]: j+=1
        r=(i+j)/2+1
        ranks[xs[i]]=r; i=j+1
    s=sum(ranks[x] for x in pos)
    a=(s-len(pos)*(len(pos)+1)/2)/(len(pos)*len(neg))
    return a,len(pos),len(neg)
campos=['score','rango_1h_pct','atr_pct','sigma_pct','ruido_1m_pct','vol_ratio','vol_24h','z_rise','z_drop','velocity',
        'consumido_pct','fuerza_impulso','pos_en_rango','dist_resistencia_pct','dist_soporte_pct','rsi5','rsi14',
        'rsi14_15m','macd_hist','bb_position','buy_ratio_30s','flow_trades_30s','macro_gate_mult','score_trend',
        'atr_percentile','ret_1m_pct','drawdown_pct','reward_neto_pct','senal_n']
res=[]
for c in campos:
    a,np_,nn=auc([(F[r['id']].get(c),gana(r,3.2)) for r in G])
    if a: res.append((abs(a-0.5),a,c,np_+nn))
for _,a,c,n in sorted(res,reverse=True)[:12]:
    print(f'  {c:22s} AUC {a:.3f}  n={n}')

print('\n=== Prueba prospectiva: ¿se sostiene rango_1h_pct después del 14-sep?')
corte=datetime.datetime(2026,9,15,tzinfo=datetime.timezone.utc).timestamp()*1000
for et,sel in (('hasta 14-sep',[r for r in G if r['ts_open']<corte]),('15–21 sep (fuera de muestra)',[r for r in G if r['ts_open']>=corte])):
    if len(sel)<50: continue
    print(f'\n  {et}: n={len(sel)} | tasa base +3,2% antes del stop {100*sum(gana(r,3.2) for r in sel)/len(sel):.1f}%')
    for c in ('rango_1h_pct','score','atr_pct'):
        vals=[(F[r['id']].get(c),r) for r in sel if F[r['id']].get(c) is not None]
        vals.sort(key=lambda x:-x[0])
        top=vals[:max(1,len(vals)//5)]
        a,_,_=auc([(F[r['id']].get(c),gana(r,3.2)) for r in sel])
        tasa=100*sum(gana(r,3.2) for _,r in top)/len(top)
        esp=st.mean([ (3.2-COSTE) if gana(r,3.2) else (-(r['sl_pct'])-COSTE if r['ms_sl'] is not None else (r['close_fin_pct'] or 0)-COSTE) for _,r in top])
        espall=st.mean([ (3.2-COSTE) if gana(r,3.2) else (-(r['sl_pct'])-COSTE if r['ms_sl'] is not None else (r['close_fin_pct'] or 0)-COSTE) for r in sel])
        print(f'    {c:16s} AUC {a if a else float("nan"):.3f} | top 20%: acierta {tasa:.1f}% (n={len(top)}) esperanza {esp:+.2f}% | todas: esperanza {espall:+.2f}%')

print('\n=== La puntuación actual como "confianza" (avisos de Telegram)')
for lo,hi in ((70,79),(80,84),(85,89),(90,101)):
    v=[r for r in S if lo<=(r['score'] or 0)<=hi]
    if len(v)<5: continue
    print(f'  score {lo}–{hi}: n={len(v):3d} | TP antes del stop {100*sum(gana(r) for r in v)/len(v):5.1f}% | +3,2% antes del stop {100*sum(gana(r,3.2) for r in v)/len(v):5.1f}%')
