import gzip,json,statistics as st
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert'); signals=build('signal')
R=json.load(gzip.open('rejilla.json.gz','rt'))
UP,DN=R['up'],R['dn']; COSTE=0.5
sent=[r for r in alerts if r['telegram']=='enviado']
S=[r for r in sent if r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None]
G=[r for r in signals if r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None]

def rej(r,kind): return R[kind].get(str(r['id']))
def sweep(rows,kind,nombre):
    print(f'\n### {nombre} (n={len(rows)}) — esperanza media neta por señal (coste {COSTE}%), ventana 12 h')
    print('        stop:'+''.join(f'{-dn:8.1f}' for dn in DN))
    best=None
    for ui,u in enumerate(UP):
        line=f'  TP +{u:<4.1f}%  '
        for di,dnv in enumerate(DN):
            vals=[];hits=0
            for r in rows:
                g=rej(r,kind)
                if not g: continue
                tu,td=g['up'][ui],g['dn'][di]
                if tu is not None and (td is None or tu<td): vals.append(u-COSTE); hits+=1
                elif td is not None: vals.append(-dnv-COSTE)
                else: vals.append((r['close_fin_pct'] or 0)-COSTE)
            m=st.mean(vals)
            if best is None or m>best[0]: best=(m,u,dnv,100*hits/len(vals))
            line+=f'{m:+8.2f}'
        print(line)
    print(f'  mejor celda: TP +{best[1]}% / stop -{best[2]}% → {best[0]:+.2f}% por señal, aciertos {best[3]:.0f}%')

def tasa(rows,kind,nombre):
    print(f'\n### {nombre} — % que toca el objetivo ANTES que el stop')
    print('        stop:'+''.join(f'{-dn:8.1f}' for dn in DN))
    for ui,u in enumerate(UP):
        line=f'  TP +{u:<4.1f}%  '
        for di,dnv in enumerate(DN):
            n=h=0
            for r in rows:
                g=rej(r,kind)
                if not g: continue
                n+=1; tu,td=g['up'][ui],g['dn'][di]
                if tu is not None and (td is None or tu<td): h+=1
            line+=f'{100*h/n:7.1f}%'
        print(line)

sweep(S,'alert','TELEGRAM'); tasa(S,'alert','TELEGRAM'); sweep(G,'signal','TODAS LAS SEÑALES')

print('\n### Contrafactual: mismo TP del plan, stop ensanchado (cohorte Telegram)')
for w in (0,0.5,1.0,1.5,2.0,3.0):
    tp=sl=nn=0; vals=[]
    for r in S:
        lim=-(r['sl_pct']+w)
        alcanza_tp = r['ms_tp'] is not None and (r['mae_pre_tp_pct'] is None or r['mae_pre_tp_pct']>lim)
        toca_sl = (r['mae_pct'] is not None and r['mae_pct']<=lim)
        if alcanza_tp: tp+=1; vals.append(r['tp_pct']-COSTE)
        elif toca_sl: sl+=1; vals.append(-(r['sl_pct']+w)-COSTE)
        else: nn+=1; vals.append((r['close_fin_pct'] or 0)-COSTE)
    print(f'  stop +{w:.1f} pp más ancho (mediana -{st.median([r["sl_pct"] for r in S])+w:.2f}%): TP {tp} ({100*tp/len(S):.1f}%) | SL {sl} | ninguno {nn} | esperanza {st.mean(vals):+.2f}%')
print('\n### Contrafactual con objetivo fijo +3,2% y stop ensanchado (cohorte Telegram)')
for w in (0,0.5,1.0,1.5,2.0,3.0):
    tp=sl=nn=0; vals=[]
    for r in S:
        lim=-(r['sl_pct']+w)
        alcanza = r['ms_meta'] is not None and (r['mae_pre_meta_pct'] is None or r['mae_pre_meta_pct']>lim)
        toca_sl = (r['mae_pct'] is not None and r['mae_pct']<=lim)
        if alcanza: tp+=1; vals.append(3.2-COSTE)
        elif toca_sl: sl+=1; vals.append(-(r['sl_pct']+w)-COSTE)
        else: nn+=1; vals.append((r['close_fin_pct'] or 0)-COSTE)
    print(f'  stop +{w:.1f} pp: objetivo {tp} ({100*tp/len(S):.1f}%) | SL {sl} | ninguno {nn} | esperanza {st.mean(vals):+.2f}%')
