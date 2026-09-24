"""Independent checks against raw saved bars, without importing analizar.py."""
import gzip
import json
import math
from pathlib import Path
import statistics

BASE=Path(__file__).resolve().parent
d=json.load(gzip.open(BASE/'datos/snapshot.json.gz','rt',encoding='utf8'))
results=json.loads((BASE/'datos/resultados.json').read_text(encoding='utf8'))
latest=results['source_joins']['latest_config_hash']
plans={p['alerta_id']:p for p in d['plans']}
selected=[]
for a in d['alerts']:
    if a['telegram']!='enviado' or a['config_hash']!=latest:continue
    if not 0<a['stop_loss']<a['entry']<a['take_profit']:continue
    anchor=max(a['ts_ms'],plans[a['id']]['ts_activado']) if a['id'] in plans else a['ts_ms']
    end=anchor+43200000
    if end>d['snapshot_ms']:continue
    bs=[b for b in d['sent_paths_1m'][str(a['id'])] if b[0]>=anchor and b[0]+60000<=end]
    expected=list(range(math.ceil(anchor/60000)*60000,math.floor(end/60000)*60000,60000))
    if not bs or len(bs)/len(expected)<.98 or bs[-1][0]!=expected[-1]:continue
    selected.append((a,anchor,bs))
assert len(selected)==176
checks=[]
for goal in [None,1.2,2.2,2.7,3.2,4.2,5.2]:
    pnl=[];wins=0
    for a,anchor,bars in selected:
        tp=a['take_profit'] if goal is None else a['entry']*(1+(goal+.5)/100)
        hit=next((i for i,b in enumerate(bars) if b[1]>=tp),None)
        stop=next((i for i,b in enumerate(bars) if b[2]<=a['stop_loss']),None)
        if hit is not None and (stop is None or hit<stop):
            exit_price=tp;wins+=1
        elif stop is not None:exit_price=a['stop_loss']
        else:exit_price=bars[-1][3]
        pnl.append((exit_price-a['entry'])/a['entry']*100-.5)
    claimed=next(x for x in results['target_comparisons']['telegram_latest_config_12h'] if x['target_net_pct']==goal)
    assert wins==claimed['hits_before_sl']
    assert abs(statistics.mean(pnl)-claimed['mean_net_pct'])<1e-10
    checks.append({'target_net_pct':goal,'n':len(selected),'hits':wins,'mean_net_pct':statistics.mean(pnl),'verified':True})
validation={'independent_raw_bar_recalculation':checks,'source_sha256_valid':True}
import hashlib
manifest=json.loads((BASE/'datos/manifest.json').read_text(encoding='utf8'))
assert hashlib.sha256((BASE/'datos/snapshot.json.gz').read_bytes()).hexdigest()==manifest['snapshot_sha256']
(BASE/'datos/verification.json').write_text(json.dumps(validation,indent=2),encoding='utf8')
print(json.dumps(validation))
