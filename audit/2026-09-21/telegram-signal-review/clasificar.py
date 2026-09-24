import gzip,json,datetime,statistics
from collections import Counter,defaultdict

d=json.load(gzip.open('paths.json.gz','rt',encoding='utf-8'))
NOW=d['now']; NEAR=d['near_frac']; META=d['meta_pct']/100
def ts(ms): return datetime.datetime.utcfromtimestamp(ms/1000).strftime('%d-%b %H:%M')

def build(kind):
    src=d['alerts'] if kind=='alert' else d['signals']
    paths=d['paths_alert'] if kind=='alert' else d['paths_signal']
    out=[]
    for r in src:
        key=str(r['id'])
        p=paths.get(key)
        if not p or p.get('n_velas',0)==0: continue
        E,TP,SL=r['entry'],r['take_profit'],r['stop_loss']
        if not (0<SL<E<TP): continue
        rec=dict(p)
        rec.update(id=r['id'],symbol=r['symbol'],ts_open=r.get('ts_ms') or r.get('ts_open'),
                   entry=E,tp=TP,sl=SL,score=r.get('score'),tier=r.get('tier'),
                   estado=r.get('display_state'),telegram=r.get('telegram'),
                   signal_id=r.get('signal_id') if kind=='alert' else r['id'],
                   status=r.get('status'),senal_n=r.get('senal_n'))
        rec['tp_pct']=(TP/E-1)*100; rec['sl_pct']=(1-SL/E)*100
        rec['near_pct']=-(1-(E-(E-SL)*NEAR)/E)*100   # % bajo la entrada del umbral "cerca del SL"
        out.append(rec)
    return out

def clasifica(r,target_pct=None):
    """target_pct=None -> objetivo = TP del plan; si no, objetivo = entrada*(1+target/100)."""
    if target_pct is None:
        t_obj=r['ms_tp']; mae_pre=r['mae_pre_tp_pct']; obj_post_sl=r['ms_tp_post_sl']; obj_pct=r['tp_pct']
    else:
        t_obj=r['ms_meta']; mae_pre=r['mae_pre_meta_pct']; obj_post_sl=r['ms_meta_post_sl']; obj_pct=target_pct
    t_sl=r['ms_sl']; near=r['near_pct']
    toco_cerca_antes = (r['ms_cerca_sl_low'] is not None and (t_obj is None or r['ms_cerca_sl_low']<=t_obj))
    sl_antes = (t_sl is not None and (t_obj is None or t_sl<=t_obj))
    if t_obj is not None and not sl_antes:
        if mae_pre is not None and mae_pre>=-1.0 and not toco_cerca_antes: return 'A_LIMPIA'
        if toco_cerca_antes: return 'B_ROZO_SL'
        return 'C_RETROCESO_MEDIO'
    if t_sl is not None and obj_post_sl is not None: return 'D_SL_Y_LUEGO_OBJ'
    if t_sl is not None:
        if r['post_sl_max_pct'] is not None and r['post_sl_max_pct']<=0.4: return 'E_SL_SIN_RETORNO'
        return 'F_SL_REBOTE_PARCIAL'
    return 'G_NI_OBJ_NI_SL'

ETQ={'A_LIMPIA':'Llega al objetivo sin sobresaltos (retroceso ≤1% y nunca cerca del SL)',
     'B_ROZO_SL':'Roza el SL (≤20% de margen) y aun así llega al objetivo',
     'C_RETROCESO_MEDIO':'Llega al objetivo con retroceso intermedio (>1%, sin rozar el SL)',
     'D_SL_Y_LUEGO_OBJ':'Toca el SL y después alcanza el objetivo',
     'E_SL_SIN_RETORNO':'Toca el SL y no vuelve ni al +0,4% sobre la entrada',
     'F_SL_REBOTE_PARCIAL':'Toca el SL, rebota por encima del +0,4% pero no llega al objetivo',
     'G_NI_OBJ_NI_SL':'Ni objetivo ni SL en 12 h'}
ORDER=['A_LIMPIA','B_ROZO_SL','C_RETROCESO_MEDIO','D_SL_Y_LUEGO_OBJ','E_SL_SIN_RETORNO','F_SL_REBOTE_PARCIAL','G_NI_OBJ_NI_SL']

def resumen(rows,target=None,titulo=''):
    c=Counter(clasifica(r,target) for r in rows)
    n=len(rows)
    print(f'\n### {titulo}  (n={n})')
    for k in ORDER:
        if c[k]: print(f'  {k:22s} {c[k]:5d}  {100*c[k]/n:5.1f}%  {ETQ[k]}')
    return c

alerts=build('alert'); signals=build('signal')
sent=[r for r in alerts if r['telegram']=='enviado']
print('cohorte enviados',len(sent),'completos',sum(r['completa'] for r in sent))
sent_c=[r for r in sent if r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None]
print('evaluables',len(sent_c))
json.dump({'alerts':alerts,'signals':signals},gzip.open('clasificado.json.gz','wt',encoding='utf-8'))

resumen(sent_c,None,'TELEGRAM · objetivo = TP del plan')
resumen(sent_c,3.2,'TELEGRAM · objetivo = +3,2%')
sig_c=[r for r in signals if r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None]
print('\nseñales evaluables',len(sig_c),'de',len(signals))
resumen(sig_c,None,'TODAS LAS SEÑALES · objetivo = TP')
resumen(sig_c,3.2,'TODAS LAS SEÑALES · objetivo = +3,2%')
