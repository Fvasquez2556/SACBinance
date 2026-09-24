import gzip,json,statistics as st,re,datetime
from collections import Counter,defaultdict
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert'); signals=build('signal')
raw={str(a['id']):a for a in d['alerts']}
S=[r for r in alerts if r['telegram']=='enviado' and (r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None)]
ok=lambda r,t=None: (r['ms_tp'] if t is None else r['ms_meta']) is not None and (r['ms_sl'] is None or (r['ms_tp'] if t is None else r['ms_meta'])<r['ms_sl'])

def corte(rows,key,nombre,minimo=5):
    g=defaultdict(list)
    for r in rows: g[key(r)].append(r)
    print(f'\n--- {nombre}')
    for k,v in sorted(g.items(),key=lambda x:-len(x[1])):
        if len(v)<minimo: continue
        print(f'  {str(k):24s} n={len(v):4d} | TP antes SL {100*sum(ok(r) for r in v)/len(v):5.1f}% | +3,2%% antes SL {100*sum(ok(r,3.2) for r in v)/len(v):5.1f}%'
              f' | MFE med {st.median([r["mfe_pct"] for r in v]):5.2f}% | MAE med {st.median([r["mae_pct"] for r in v]):6.2f}%')
corte(S,lambda r:r['estado'],'TELEGRAM por escenario (display_state)',3)
corte(S,lambda r:'score %d-%d'%(r['score']//10*10,r['score']//10*10+9) if r['score'] else 'sin score','TELEGRAM por score',3)
corte(S,lambda r:'TP<4%%' if r['tp_pct']<4 else ('TP 4-7%' if r['tp_pct']<7 else 'TP>=7%'),'TELEGRAM por distancia del TP',3)
corte(S,lambda r:datetime.datetime.utcfromtimestamp(r['ts_open']/1000).strftime('%d-%b'),'TELEGRAM por dia (UTC)',4)
print('\n--- concentracion por par (cohorte Telegram)')
c=Counter(r['symbol'] for r in S)
for sym,n in c.most_common(10):
    v=[r for r in S if r['symbol']==sym]
    print(f'  {sym:14s} {n:2d} avisos | TP antes SL {sum(ok(r) for r in v)} | +3,2%% {sum(ok(r,3.2) for r in v)} | MAE med {st.median([r["mae_pct"] for r in v]):6.2f}%')
print(f'  pares distintos: {len(c)} para {len(S)} avisos')

print('\n--- motivos de descarte: ¿qué se estaba dejando fuera? (alertas con niveles y ventana evaluable)')
des=[r for r in alerts if r['telegram']!='enviado' and (r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None)]
def motivo(r):
    t=(raw[str(r['id'])].get('telegram_detalle') or '').strip()
    t=re.sub(r'\d+','N',t)
    return t[:52] or '(sin detalle)'
g=defaultdict(list)
for r in des: g[motivo(r)].append(r)
for k,v in sorted(g.items(),key=lambda x:-len(x[1]))[:14]:
    print(f'  {k:54s} n={len(v):5d} | +3,2%% antes SL {100*sum(ok(r,3.2) for r in v)/len(v):5.1f}% | TP med {st.median([r["tp_pct"] for r in v]):5.2f}%')
print(f'  (referencia enviadas: +3,2%% antes SL {100*sum(ok(r,3.2) for r in S)/len(S):.1f}%)')
