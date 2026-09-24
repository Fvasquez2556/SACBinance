import gzip,json,statistics as st
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert')
R2=json.load(gzip.open('rejilla2.json.gz','rt')); FIJ=R2['fijos']
EV=lambda r: r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None
S=[r for r in alerts if r['telegram']=='enviado' and EV(r)]
H=3600000
print('=== Qué ha pasado ya, hora a hora (avisos de Telegram, n=%d)'%len(S))
print('  h | +3,2% bruto antes que stop | TP del plan antes que stop | stop tocado | todavía sin resolver')
for hrs in (1,2,3,4,6,8,12):
    lim=hrs*H
    meta=sum(1 for r in S if r['ms_meta'] is not None and r['ms_meta']<=lim and (r['ms_sl'] is None or r['ms_meta']<r['ms_sl']))
    tp=sum(1 for r in S if r['ms_tp'] is not None and r['ms_tp']<=lim and (r['ms_sl'] is None or r['ms_tp']<r['ms_sl']))
    sl=sum(1 for r in S if r['ms_sl'] is not None and r['ms_sl']<=lim and (r['ms_tp'] is None or r['ms_sl']<r['ms_tp']))
    abierto=len(S)-sum(1 for r in S if (r['ms_tp'] is not None and r['ms_tp']<=lim) or (r['ms_sl'] is not None and r['ms_sl']<=lim))
    print(f' {hrs:2d} | {100*meta/len(S):24.1f}% | {100*tp/len(S):25.1f}% | {100*sl/len(S):10.1f}% | {100*abierto/len(S):19.1f}%')
print('\n  De los que acaban llegando al +3,2%%: %.0f%% lo hacen en las primeras 6 h'%(
    100*sum(1 for r in S if r['ms_meta'] is not None and r['ms_meta']<=6*H)/sum(1 for r in S if r['ms_meta'] is not None)))
print('  De los que acaban tocando el stop: %.0f%% lo hacen en las primeras 6 h'%(
    100*sum(1 for r in S if r['ms_sl'] is not None and r['ms_sl']<=6*H)/sum(1 for r in S if r['ms_sl'] is not None)))
print('  Momento del máximo (MFE) mediana: %.1f h'%st.median([r['ms_mfe']/H for r in S if r['ms_mfe'] is not None]))
print('\n=== Si cierras a las N horas pase lo que pase (objetivo +3,7%% bruto = 3,2%% neto, stop del plan)')
for hrs in (2,3,4,6,8,12):
    lim=hrs*H; v=[]
    for r in S:
        g=R2['alert'].get(str(r['id']));
        if not g: continue
        t=g['fijos'][FIJ.index(3.7)]
        if t is not None and t<=lim and (r['ms_sl'] is None or t<r['ms_sl']): v.append(3.7-0.5)
        elif r['ms_sl'] is not None and r['ms_sl']<=lim: v.append(-r['sl_pct']-0.5)
        else: v.append(None)   # sigue abierto al corte: no se sabe con estos datos
    cerr=[x for x in v if x is not None]
    print(f'  corte {hrs:2d} h: resueltos {len(cerr):3d}/{len(v)} ({100*len(cerr)/len(v):.0f}%) | esperanza de los resueltos {st.mean(cerr):+.2f}%')
