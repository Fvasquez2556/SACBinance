"""¿Cuánto dura un episodio? Estructura de repeticiones por par y rendimiento por ordinal."""
import statistics as st
from collections import Counter,defaultdict
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert'); signals=build('signal')
EV=lambda r: r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None
ok=lambda r,t=None: (r['ms_tp'] if t is None else r['ms_meta']) is not None and (r['ms_sl'] is None or (r['ms_tp'] if t is None else r['ms_meta'])<r['ms_sl'])
H=3600000

def gaps(rows,nombre):
    by=defaultdict(list)
    for r in rows: by[r['symbol']].append(r)
    g=[]
    pares=[]
    for s,v in by.items():
        v.sort(key=lambda r:r['ts_open'])
        for a,b in zip(v,v[1:]):
            dt=(b['ts_open']-a['ts_open'])/H
            g.append(dt); pares.append((a,b,dt))
    g.sort()
    if not g: return []
    q=lambda p: g[int(p*(len(g)-1))]
    print(f'\n{nombre}: {len(rows)} avisos en {len(by)} pares | {len(g)} pares consecutivos')
    print('  huecos entre avisos del mismo par (h): p10 %.2f p25 %.2f mediana %.2f p75 %.2f p90 %.2f'%(q(.1),q(.25),q(.5),q(.75),q(.9)))
    for T in (1,2,3,4,6,8,12,24):
        d=sum(1 for x in g if x<=T)
        print(f'   ≤{T:2d} h: {d:5d} ({100*d/len(g):4.1f}% de las repeticiones)')
    return pares

print('=== ¿Cada cuánto se repite un par?')
sent=[r for r in alerts if r['telegram']=='enviado']
pares_tg=gaps(sent,'TELEGRAM (enviados)')
pares_all=gaps([r for r in alerts],'TODAS LAS ALERTAS con niveles')

print('\n=== ¿La repetición habla del mismo movimiento? (avisos de Telegram)')
for lo,hi in ((0,1),(1,3),(3,6),(6,12),(12,24),(24,999)):
    sel=[(a,b,dt) for a,b,dt in pares_tg if lo<=dt<hi]
    if len(sel)<3: continue
    dif=[abs(b['entry']/a['entry']-1)*100 for a,b,_ in sel]
    resuelto=[1 if (a['ms_tp'] is not None and a['ms_tp']<=(b['ts_open']-a['ts_open'])) or (a['ms_sl'] is not None and a['ms_sl']<=(b['ts_open']-a['ts_open'])) else 0 for a,b,_ in sel]
    dentro=[1 if (a['sl']<b['entry']<a['tp']) else 0 for a,b,_ in sel]
    print(f'  hueco {lo}-{hi} h  n={len(sel):3d} | entrada del 2º difiere {st.median(dif):5.2f}% (mediana) | el 1º ya había resuelto: {100*sum(resuelto)/len(sel):4.0f}% | 2ª entrada dentro de los niveles del 1º: {100*sum(dentro)/len(sel):4.0f}%')

print('\n=== Rendimiento por ordinal dentro del episodio, según la ventana de silencio T')
for T in (2,4,6,12,24):
    by=defaultdict(list)
    for r in alerts:
        if r['telegram']=='enviado': by[r['symbol']].append(r)
    orden=defaultdict(list)
    for s,v in by.items():
        v.sort(key=lambda r:r['ts_open'])
        n=0; last=None
        for r in v:
            if last is None or (r['ts_open']-last)/H>T: n=1
            else: n+=1
            last=r['ts_open']; r['_ord']=n
            orden[min(n,3)].append(r)
    linea=f'  T={T:2d} h |'
    for k in (1,2,3):
        v=[r for r in orden[k] if EV(r)]
        if not v: continue
        linea+=f' ordinal {k}{"+" if k==3 else ""}: n={len(v):3d} TP {100*sum(ok(r) for r in v)/len(v):4.1f}% 3,2% {100*sum(ok(r,3.2) for r in v)/len(v):4.1f}% |'
    print(linea)

print('\n=== Lo mismo sobre TODAS las señales generadas (más muestra)')
for T in (2,4,6,12,24):
    by=defaultdict(list)
    for r in signals: by[r['symbol']].append(r)
    orden=defaultdict(list)
    for s,v in by.items():
        v.sort(key=lambda r:r['ts_open'])
        n=0; last=None
        for r in v:
            if last is None or (r['ts_open']-last)/H>T: n=1
            else: n+=1
            last=r['ts_open']
            orden[min(n,5)].append(r)
    linea=f'  T={T:2d} h |'
    for k in (1,2,5):
        v=[r for r in orden[k] if EV(r)]
        if not v: continue
        et={1:'1ª',2:'2ª',5:'5ª+'}[k]
        linea+=f' {et}: n={len(v):4d} TP {100*sum(ok(r) for r in v)/len(v):4.1f}% 3,2% {100*sum(ok(r,3.2) for r in v)/len(v):4.1f}% |'
    print(linea)
