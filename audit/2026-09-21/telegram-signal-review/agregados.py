import gzip,json,datetime,statistics as st
from collections import Counter,defaultdict
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert'); signals=build('signal')
sent=[r for r in alerts if r['telegram']=='enviado']
S=[r for r in sent if r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None]
G=[r for r in signals if r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None]
NP={p['alerta_id']:p for p in d['planes']}
COSTE=0.5

print('=== 1) Validacion contra las etiquetas del propio sistema')
val=Counter()
for r in S:
    p=NP.get(r['id'])
    if not p: continue
    mio='TP' if (r['ms_tp'] is not None and (r['ms_sl'] is None or r['ms_tp']<r['ms_sl'])) else ('SL' if r['ms_sl'] is not None else 'ABIERTO/VENCIDO')
    val[(p['estado'],mio)]+=1
for k,v in sorted(val.items(),key=lambda x:-x[1]): print('  ',k,v)
print('   ambiguas (misma vela toca TP y SL):',sum(r['ambiguo'] for r in S),'de',len(S),
      '| en todas las señales:',sum(r['ambiguo'] for r in G))

def expectativa(rows,target=None):
    """Resultado neto por señal: TP/objetivo primero -> +obj-coste ; SL primero -> -sl-coste ; si no -> cierre a 12h-coste"""
    res=[]
    for r in rows:
        if target is None: t_obj,obj=r['ms_tp'],r['tp_pct']
        else: t_obj,obj=r['ms_meta'],target
        t_sl=r['ms_sl']
        if t_obj is not None and (t_sl is None or t_obj<t_sl): res.append(obj-COSTE)
        elif t_sl is not None: res.append(-r['sl_pct']-COSTE)
        else: res.append((r['close_fin_pct'] or 0)-COSTE)
    return res

def bloque(rows,nombre):
    print(f'\n=== {nombre}  n={len(rows)}')
    for etiq,target in (('TP del plan',None),('objetivo +3,2%',3.2)):
        res=expectativa(rows,target)
        gan=sum(x>0 for x in res)
        t_obj=[r['ms_tp'] if target is None else r['ms_meta'] for r in rows]
        sl=[r['ms_sl'] for r in rows]
        primero=sum(1 for a,b in zip(t_obj,sl) if a is not None and (b is None or a<b))
        print(f'  · {etiq:16s} toca objetivo antes que SL {primero:5d} ({100*primero/len(rows):4.1f}%) | '
              f'toca SL antes {sum(1 for a,b in zip(t_obj,sl) if b is not None and (a is None or b<a)):4d} | '
              f'ninguno {sum(1 for a,b in zip(t_obj,sl) if a is None and b is None):4d}')
        print(f'    esperanza media {st.mean(res):+.2f}% | mediana {st.median(res):+.2f}% | positivos {100*gan/len(rows):.1f}% | suma {sum(res):+.0f}%')
    # tocar el objetivo en cualquier momento (aunque despues del SL)
    print(f'    tocan TP en algun momento de las 12 h: {sum(r["ms_tp"] is not None for r in rows)} ({100*sum(r["ms_tp"] is not None for r in rows)/len(rows):.1f}%) | '
          f'+3,2%: {sum(r["ms_meta"] is not None for r in rows)} ({100*sum(r["ms_meta"] is not None for r in rows)/len(rows):.1f}%)')
bloque(S,'PLANES ENVIADOS A TELEGRAM'); bloque(G,'TODAS LAS SEÑALES GENERADAS')

print('\n=== 2) El 3,2% alcanzado y el TP no alcanzado')
for rows,nombre in ((S,'Telegram'),(G,'Todas')):
    a=[r for r in rows if r['ms_meta'] is not None and r['ms_tp'] is None]
    b=[r for r in rows if r['ms_meta'] is not None]
    print(f'  {nombre}: llegan al 3,2%: {len(b)} ({100*len(b)/len(rows):.1f}%) — de esos, NO tocan el TP: {len(a)} ({100*len(a)/max(1,len(b)):.1f}%)')
    if a:
        print(f'     de los que se quedan: MFE mediana {st.median([r["mfe_pct"] for r in a]):.2f}% | TP pedido mediana {st.median([r["tp_pct"] for r in a]):.2f}%'
              f' | luego tocan SL: {sum(r["ms_sl"] is not None for r in a)} ({100*sum(r["ms_sl"] is not None for r in a)/len(a):.0f}%)'
              f' | cierre a 12h mediana {st.median([r["close_fin_pct"] or 0 for r in a]):+.2f}%')
        sl_desp=[r for r in a if r['ms_sl'] is not None and r['ms_sl']>r['ms_meta']]
        print(f'     tocan el 3,2% y DESPUES el SL: {len(sl_desp)}')

print('\n=== 3) Familias con objetivo=3,2% (detalle de las cuatro preguntas)')
for rows,nombre in ((S,'Telegram'),(G,'Todas')):
    c=Counter(clasifica(r,3.2) for r in rows)
    print(f'  {nombre} (n={len(rows)}):',{k:c[k] for k in ORDER if c[k]})

print('\n=== 4) Reparto del exceso bajo el SL en las que despues alcanzan el objetivo')
for rows,nombre in ((S,'Telegram'),(G,'Todas')):
    for target,et in ((None,'TP'),(3.2,'3,2%')):
        sel=[r for r in rows if clasifica(r,target)=='D_SL_Y_LUEGO_OBJ']
        if not sel: continue
        b1=sum(r['sl_overshoot_pct']>=-0.5 for r in sel); b2=sum(-1<=r['sl_overshoot_pct']<-0.5 for r in sel); b3=len(sel)-b1-b2
        print(f'  {nombre} objetivo {et}: n={len(sel)} | ≤0,5% bajo SL: {b1} | 0,5–1%: {b2} | >1%: {b3} | '
              f'horas SL→objetivo mediana {st.median([( (r["ms_tp"] if target is None else r["ms_meta_post_sl"]) - r["ms_sl"])/3600000 for r in sel]):.2f}')

print('\n=== 5) El filtro de Telegram: enviados vs descartados (mismo periodo, alertas con niveles)')
desde=min(r['ts_open'] for r in S)
env=[r for r in alerts if r['telegram']=='enviado' and r['ts_open']>=desde and (r['completa'] or r['ms_tp'] or r['ms_sl'])]
des=[r for r in alerts if r['telegram']!='enviado' and r['ts_open']>=desde and (r['completa'] or r['ms_tp'] or r['ms_sl'])]
for rows,nombre in ((env,'enviadas'),(des,'descartadas')):
    res=expectativa(rows); res32=expectativa(rows,3.2)
    tp_first=sum(1 for r in rows if r['ms_tp'] is not None and (r['ms_sl'] is None or r['ms_tp']<r['ms_sl']))
    m32=sum(1 for r in rows if r['ms_meta'] is not None and (r['ms_sl'] is None or r['ms_meta']<r['ms_sl']))
    print(f'  {nombre:12s} n={len(rows):5d} | TP antes que SL {100*tp_first/len(rows):5.1f}% | +3,2% antes que SL {100*m32/len(rows):5.1f}% | '
          f'esperanza TP {st.mean(res):+.2f}% | esperanza 3,2% {st.mean(res32):+.2f}% | TP mediano {st.median([r["tp_pct"] for r in rows]):.2f}%')
