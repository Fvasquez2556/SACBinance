import gzip,json,random,statistics as st
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert')
S=[r for r in alerts if r['telegram']=='enviado' and (r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None)]
C=json.load(gzip.open('control.json.gz','rt'))['controls']
COSTE=0.5
def stats(rows,get):
    tp=[get(r) for r in rows]; return tp
def tasa_tp(rows): return 100*sum(1 for r in rows if r['ms_tp'] is not None and (r['ms_sl'] is None or r['ms_tp']<r['ms_sl']))/len(rows)
def tasa_meta(rows): return 100*sum(1 for r in rows if r['ms_meta'] is not None and (r['ms_sl'] is None or r['ms_meta']<r['ms_sl']))/len(rows)
def esper(rows,target=None):
    v=[]
    for r in rows:
        tp_pct=r['tp_pct']; sl_pct=r['sl_pct']
        t_obj=r['ms_tp'] if target is None else r['ms_meta']; obj=tp_pct if target is None else target
        t_sl=r['ms_sl']
        cierre=r.get('close_fin_pct', r.get('cierre')) or 0
        if t_obj is not None and (t_sl is None or t_obj<t_sl): v.append(obj-COSTE)
        elif t_sl is not None: v.append(-sl_pct-COSTE)
        else: v.append(cierre-COSTE)
    return v
def ic(vals,n=4000):
    m=st.mean(vals); bs=[]
    for _ in range(n):
        s=[vals[random.randrange(len(vals))] for _ in range(len(vals))]
        bs.append(sum(s)/len(s))
    bs.sort(); return m,bs[int(.025*n)],bs[int(.975*n)]
random.seed(7)
print('señales enviadas n=%d | controles aleatorios n=%d (%d por señal, mismo par, mismas distancias TP/SL)'%(len(S),len(C),10))
for nombre,rows in (('SEÑAL',S),('AZAR',C)):
    print(f'\n{nombre}:')
    print('  toca TP antes que SL: %.1f%%'%tasa_tp(rows))
    print('  toca +3,2%% antes que SL: %.1f%%'%tasa_meta(rows))
    for et,t in (('TP del plan',None),('objetivo 3,2%',3.2)):
        m,lo,hi=ic(esper(rows,t))
        print(f'  esperanza {et:14s}: {m:+.2f}%  IC95 [{lo:+.2f}, {hi:+.2f}]')
# diferencia señal - azar con bootstrap
def diff(metric):
    a=[metric([r]) for r in S]; b=[metric([r]) for r in C]
    bs=[]
    for _ in range(4000):
        sa=sum(a[random.randrange(len(a))] for _ in range(len(a)))/len(a)
        sb=sum(b[random.randrange(len(b))] for _ in range(len(b)))/len(b)
        bs.append(sa-sb)
    bs.sort(); return st.mean(a)-st.mean(b), bs[100], bs[3899]
d,lo,hi=diff(tasa_tp); print(f'\nDiferencia señal-azar en tasa TP antes que SL: {d:+.1f} pp  IC95 [{lo:+.1f}, {hi:+.1f}]')
d,lo,hi=diff(tasa_meta); print(f'Diferencia señal-azar en tasa +3,2%% antes que SL: {d:+.1f} pp  IC95 [{lo:+.1f}, {hi:+.1f}]')
d,lo,hi=diff(lambda rs: esper(rs)[0]); print(f'Diferencia en esperanza (TP del plan): {d:+.2f} pp  IC95 [{lo:+.2f}, {hi:+.2f}]')
d,lo,hi=diff(lambda rs: esper(rs,3.2)[0]); print(f'Diferencia en esperanza (objetivo 3,2%%): {d:+.2f} pp  IC95 [{lo:+.2f}, {hi:+.2f}]')
# MFE/MAE comparados
print('\nMFE mediana señal %.2f%% vs azar %.2f%% | MAE mediana señal %.2f%% vs azar %.2f%%'%(
    st.median([r['mfe_pct'] for r in S]),st.median([r['mfe'] for r in C]),
    st.median([r['mae_pct'] for r in S]),st.median([r['mae'] for r in C])))
print('cierre a 12h mediana señal %+.2f%% vs azar %+.2f%%'%(
    st.median([r['close_fin_pct'] or 0 for r in S]),st.median([r['cierre'] for r in C])))
