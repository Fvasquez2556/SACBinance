import gzip,json,datetime,statistics as st
from collections import Counter,defaultdict
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert'); signals=build('signal')
sent=[r for r in alerts if r['telegram']=='enviado']
S=[r for r in sent if r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None]
G=[r for r in signals if r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None]
fecha=lambda r: datetime.datetime.utcfromtimestamp(r['ts_open']/1000).strftime('%d-%b %H:%M')
med=lambda xs: round(st.median(xs),2) if xs else None
h=lambda ms: round(ms/3600000,2) if ms is not None else None

def perfil(rows,nombre):
    print(f'\n== {nombre} (n={len(rows)})')
    print('  tp_pct  mediana %.2f  p10 %.2f p90 %.2f'%(st.median([r['tp_pct'] for r in rows]),
        sorted(r['tp_pct'] for r in rows)[len(rows)//10],sorted(r['tp_pct'] for r in rows)[9*len(rows)//10]))
    print('  sl_pct  mediana %.2f  p10 %.2f p90 %.2f'%(st.median([r['sl_pct'] for r in rows]),
        sorted(r['sl_pct'] for r in rows)[len(rows)//10],sorted(r['sl_pct'] for r in rows)[9*len(rows)//10]))
    print('  TP≥3.2%%: %d (%.0f%%)'%(sum(r['tp_pct']>=3.2 for r in rows),100*sum(r['tp_pct']>=3.2 for r in rows)/len(rows)))
    print('  umbral cerca-SL mediana %.2f%% bajo entrada'%st.median([r['near_pct'] for r in rows]))
perfil(S,'Plan enviado a Telegram'); perfil(G,'Todas las señales')

def lista(rows,cat,target=None,limite=99):
    sel=[r for r in rows if clasifica(r,target)==cat]
    return sel

print('\n########## TELEGRAM · objetivo TP ##########')
for cat in ORDER:
    sel=lista(S,cat)
    if not sel: continue
    print(f'\n--- {cat}: {len(sel)} ({100*len(sel)/len(S):.1f}%) — {ETQ[cat]}')
    if cat in ('A_LIMPIA','B_ROZO_SL','C_RETROCESO_MEDIO'):
        print('   horas hasta TP: mediana',med([r['ms_tp']/3600000 for r in sel]),'| retroceso previo mediana %.2f%%'%st.median([r['mae_pre_tp_pct'] for r in sel]))
    if cat=='D_SL_Y_LUEGO_OBJ':
        print('   exceso bajo SL mediana %.2f%% | horas SL→TP mediana %.2f'%(
            st.median([r['sl_overshoot_pct'] for r in sel]), st.median([(r['ms_tp_post_sl']-r['ms_sl'])/3600000 for r in sel])))
        print('   exceso ≤0.5%%: %d | 0.5–1%%: %d | >1%%: %d'%(
            sum(r['sl_overshoot_pct']>=-0.5 for r in sel),
            sum(-1<=r['sl_overshoot_pct']<-0.5 for r in sel),
            sum(r['sl_overshoot_pct']<-1 for r in sel)))
    if cat in ('E_SL_SIN_RETORNO','F_SL_REBOTE_PARCIAL'):
        print('   horas hasta SL mediana %.2f | rebote posterior mediana %.2f%% | caida total mediana %.2f%%'%(
            st.median([r['ms_sl']/3600000 for r in sel]), st.median([r['post_sl_max_pct'] for r in sel]),
            st.median([r['mae_pct'] for r in sel])))
    if cat=='G_NI_OBJ_NI_SL':
        print('   MFE mediana %.2f%% | MAE mediana %.2f%% | llegaron al 3.2%%: %d | cierre mediana %.2f%%'%(
            st.median([r['mfe_pct'] for r in sel]),st.median([r['mae_pct'] for r in sel]),
            sum(r['ms_meta'] is not None for r in sel),st.median([r['close_fin_pct'] for r in sel])))
    for r in sorted(sel,key=lambda r:r['ts_open'])[:99]:
        print(f"    {r['symbol']:14s} {fecha(r)}  TP {r['tp_pct']:5.2f}%  SL -{r['sl_pct']:4.2f}%  "
              f"mfe {r['mfe_pct']:6.2f}  mae {r['mae_pct']:6.2f}  tTP {str(h(r['ms_tp'])):>6s}  tSL {str(h(r['ms_sl'])):>6s}  "
              f"t3.2 {str(h(r['ms_meta'])):>6s} score {r['score']} {r['estado']}")
