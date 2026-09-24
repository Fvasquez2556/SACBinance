import gzip,json,datetime,statistics as st
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert'); signals=build('signal')
S=[r for r in alerts if r['telegram']=='enviado' and (r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None)]
f=lambda r: datetime.datetime.utcfromtimestamp(r['ts_open']/1000).strftime('%d-%b %H:%M')
h=lambda ms: '—' if ms is None else '%.1f h'%(ms/3600000)
pct=lambda x: '—' if x is None else '%+.2f%%'%x
out=[]
def tabla_obj(cat):
    sel=sorted([r for r in S if clasifica(r)==cat],key=lambda r:r['ts_open'])
    out.append('')
    out.append('| Par | Aviso (UTC) | TP | SL | Retroceso antes del TP | Mínimo en 12 h | Máx. a favor | t→TP | t→+3,2% | Escenario |')
    out.append('|---|---|---|---|---|---|---|---|---|---|')
    for r in sel:
        out.append('| %s | %s | +%.2f%% | −%.2f%% | %s | %s | %s | %s | %s | %s |'%(
            r['symbol'],f(r),r['tp_pct'],r['sl_pct'],pct(r['mae_pre_tp_pct']),pct(r['mae_pct']),
            pct(r['mfe_pct']),h(r['ms_tp']),h(r['ms_meta']),r['estado']))
    return sel
for cat,tit in (('A_LIMPIA','A · Camino tranquilo hasta el TP'),
                ('B_ROZO_SL','B · Rozaron el stop y aun así tocaron el TP'),
                ('D_SL_Y_LUEGO_OBJ','D · Perforaron el stop y después tocaron el TP')):
    out.append('\n#### '+tit); tabla_obj(cat)
out.append('\n#### E · Tocaron el stop y no volvieron ni al +0,4%')
sel=sorted([r for r in S if clasifica(r)=='E_SL_SIN_RETORNO'],key=lambda r:r['ts_open'])
out.append('')
out.append('| Par | Aviso (UTC) | SL | t→SL | Caída máxima | Máximo tras el stop | ¿Llegó a tocar +3,2%? |')
out.append('|---|---|---|---|---|---|---|')
for r in sel:
    out.append('| %s | %s | −%.2f%% | %s | %s | %s | %s |'%(r['symbol'],f(r),r['sl_pct'],h(r['ms_sl']),
        pct(r['mae_pct']),pct(r['post_sl_max_pct']),('sí, a las '+h(r['ms_meta'])) if r['ms_meta'] is not None else 'no'))
out.append('\n#### Tocaron +3,2% y nunca el TP')
sel=sorted([r for r in S if r['ms_meta'] is not None and r['ms_tp'] is None],key=lambda r:r['ts_open'])
out.append('')
out.append('| Par | Aviso (UTC) | TP pedido | Máximo alcanzado | t→+3,2% | ¿Stop después? | Cierre a 12 h |')
out.append('|---|---|---|---|---|---|---|')
for r in sel:
    if r['ms_sl'] is None: s='no'
    elif r['ms_sl']>r['ms_meta']: s='sí, después'
    else: s='sí, antes'
    out.append('| %s | %s | +%.2f%% | %s | %s | %s | %s |'%(r['symbol'],f(r),r['tp_pct'],pct(r['mfe_pct']),h(r['ms_meta']),s,pct(r['close_fin_pct'] or 0)))
open('tablas.md','w',encoding='utf-8').write('\n'.join(out))
print('\n'.join(out[:8])); print('...',len(out),'lineas')
