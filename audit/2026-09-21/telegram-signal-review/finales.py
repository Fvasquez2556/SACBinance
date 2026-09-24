import gzip,json,statistics as st
from collections import Counter
exec(open('clasificar.py').read().split("alerts=build('alert')")[0])
alerts=build('alert'); signals=build('signal')
S=[r for r in alerts if r['telegram']=='enviado' and (r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None)]
G=[r for r in signals if r['completa'] or r['ms_tp'] is not None or r['ms_sl'] is not None]
for rows,n in ((S,'Telegram'),(G,'Todas')):
    sl=[r for r in rows if r['ms_sl'] is not None]
    slf=[r for r in rows if r['ms_sl'] is not None and (r['ms_tp'] is None or r['ms_sl']<r['ms_tp'])]
    print(f'{n}: tocan SL {len(sl)} ({100*len(sl)/len(rows):.1f}%) | SL antes que TP {len(slf)}')
    print(f'   exceso bajo el SL mediana {st.median([r["sl_overshoot_pct"] for r in sl]):.2f}% | p90 {sorted(r["sl_overshoot_pct"] for r in sl)[len(sl)//10]:.2f}%')
    print(f'   de los que tocan SL primero: luego TP {sum(1 for r in slf if r["ms_tp_post_sl"] is not None)} | luego +3,2% {sum(1 for r in slf if r["ms_meta_post_sl"] is not None)} | no pasan de +0,4% {sum(1 for r in slf if (r["post_sl_max_pct"] or -9)<=0.4)}')
    print(f'   horas hasta el SL mediana {st.median([r["ms_sl"]/3600000 for r in sl]):.2f} | hasta el TP mediana {st.median([r["ms_tp"]/3600000 for r in rows if r["ms_tp"] is not None]):.2f} | hasta +3,2% mediana {st.median([r["ms_meta"]/3600000 for r in rows if r["ms_meta"] is not None]):.2f}')
    g=[r for r in rows if r['ms_tp'] is None and r['ms_sl'] is None]
    print(f'   ni TP ni SL: {len(g)} | cierre>0 {sum(1 for r in g if (r["close_fin_pct"] or 0)>0)} | cierre mediana {st.median([r["close_fin_pct"] or 0 for r in g]):+.2f}%')
    print(f'   excluidas por ventana incompleta: {len([1 for r in (alerts if n=="Telegram" else signals) if (r["telegram"]=="enviado" if n=="Telegram" else True) and not (r["completa"] or r["ms_tp"] is not None or r["ms_sl"] is not None)])}')
# cuantas de las A_LIMPIA tenian SL mas cerca de 1%
print('\nPlanes con SL a menos de 1%: Telegram', sum(r['sl_pct']<1 for r in S),'| Todas',sum(r['sl_pct']<1 for r in G))
print('Umbral cerca-SL (80%% del recorrido) mediana: Telegram -%.2f%%'%abs(st.median([r['near_pct'] for r in S])))
# reparto del resultado neto por familia (telegram, objetivo TP)
print('\nAporte de cada familia al resultado (Telegram, objetivo TP, coste 0,5%):')
tot=0; det={}
for r in S:
    c=clasifica(r)
    if r['ms_tp'] is not None and (r['ms_sl'] is None or r['ms_tp']<r['ms_sl']): v=r['tp_pct']-0.5
    elif r['ms_sl'] is not None: v=-r['sl_pct']-0.5
    else: v=(r['close_fin_pct'] or 0)-0.5
    det.setdefault(c,[]).append(v); tot+=v
for k in ORDER:
    if k in det: print(f'  {k:22s} n={len(det[k]):4d}  suma {sum(det[k]):+7.1f} pp  media {st.mean(det[k]):+6.2f} pp')
print(f'  TOTAL                       n={len(S)}  suma {tot:+.1f} pp  media {tot/len(S):+.2f} pp')
