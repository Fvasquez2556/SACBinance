"""Reproducible target comparison on one immutable snapshot; no production writes.

Targets are hypothetical exits for the same frozen entries and stops. A target
net percentage is converted to a gross barrier by adding 0.5 percentage points.
Only complete horizons with >=98% candle coverage and a timely final close enter.
"""
import collections
import datetime as dt
import gzip
import json
import math
from pathlib import Path
import random
import statistics as st

BASE=Path(__file__).resolve().parent
d=json.load(gzip.open(BASE/'datos/snapshot.json.gz','rt',encoding='utf8'))
NOW=d['snapshot_ms']; MINUTE=60000; COST=0.5
plans={r['alerta_id']:r for r in d['plans']}
outcomes={r['signal_id']:r for r in d['outcomes'] if not r['sombra']}
sent=[r for r in d['alerts'] if r['telegram']=='enviado']
LATEST=max(sent,key=lambda r:r['ts_ms'])['config_hash']
TARGETS=[1.2,2.2,2.7,3.2,4.2,5.2]

def quantile(values,q):
    s=sorted(values)
    if not s:return None
    p=q*(len(s)-1);lo=int(p);hi=math.ceil(p)
    return s[lo]*(hi-p)+s[hi]*(p-lo) if hi!=lo else s[lo]

def prepare(a,hours,anchor='activation'):
    p=plans.get(a['id'])
    entry,sl,tp=a['entry'],a['stop_loss'],a['take_profit']
    if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in (entry,sl,tp)) or not 0<sl<entry<tp:
        return None,'invalid_levels'
    start=max(a['ts_ms'],p['ts_activado']) if p and anchor=='activation' else a['ts_ms']
    horizon=start+hours*3600000
    if horizon>NOW:return None,'open_window'
    first=((start+MINUTE-1)//MINUTE)*MINUTE
    last=((horizon-MINUTE)//MINUTE)*MINUTE
    expected=max(0,(last-first)//MINUTE+1)
    bars=[b for b in d['sent_paths_1m'].get(str(a['id']),[]) if start<=b[0] and b[0]+MINUTE<=horizon]
    if not bars:return None,'no_bars'
    assert len(set(b[0] for b in bars))==len(bars)
    assert all(b[1]>=b[2] and b[2]<=b[3]<=b[1] for b in bars)
    coverage=len(bars)/expected
    if coverage<.98:return None,'low_coverage'
    if bars[-1][0]!=last:return None,'missing_final_candle'
    o=outcomes.get(a['signal_id'],{})
    return {**a,'anchor_ms':start,'end_ms':horizon,'bars':bars,'coverage':coverage,'entry':entry,'sl_pct':(1-sl/entry)*100,'tp_pct':(tp/entry-1)*100,'day':dt.datetime.fromtimestamp(start/1000,dt.UTC).strftime('%Y-%m-%d'),'btc_regime':o.get('btc_regime'),'grupo_vol':o.get('grupo_vol'),'rango_1h_pct':o.get('rango_1h_pct'),'outcome_present':bool(o),'clock':'activation' if p and anchor=='activation' else 'alert_proxy'},None

def evaluate(r,net_target=None,cost=COST):
    target=r['take_profit'] if net_target is None else r['entry']*(1+(net_target+COST)/100)
    gross_target=(target/r['entry']-1)*100
    result=None
    for t,high,low,close in r['bars']:
        stop=low<=r['stop_loss'];goal=high>=target
        if stop or goal:
            kind='AMBIGUO' if stop and goal else 'SL' if stop else 'TP'
            gross=-r['sl_pct'] if stop else gross_target
            result={'kind':kind,'net':gross-cost,'exit_ms':t+MINUTE,'hours':(t+MINUTE-r['anchor_ms'])/3600000}
            break
    if result is None:
        result={'kind':'VENCIDO','net':(r['bars'][-1][3]/r['entry']-1)*100-cost,'exit_ms':r['end_ms'],'hours':(r['end_ms']-r['anchor_ms'])/3600000}
    result['ever']=any(b[1]>=target for b in r['bars'])
    result['risk_multiple']=result['net']/(r['sl_pct']+cost)
    return result

def aggregate(rows,target=None):
    vals=[evaluate(r,target) for r in rows]
    if not vals:return {'n':0}
    counter=collections.Counter(v['kind'] for v in vals)
    won=[v for v in vals if v['kind']=='TP']
    return {'n':len(rows),'target_net_pct':target,'target_gross_pct':None if target is None else round(target+COST,2),'hits_before_sl':counter['TP'],'hit_pct':100*counter['TP']/len(vals),'ever_pct':100*sum(v['ever'] for v in vals)/len(vals),'sl':counter['SL'],'ambiguous':counter['AMBIGUO'],'expired':counter['VENCIDO'],'mean_net_pct':st.mean(v['net'] for v in vals),'median_net_pct':st.median(v['net'] for v in vals),'positive_pct':100*sum(v['net']>0 for v in vals)/len(vals),'median_hours_to_target':st.median(v['hours'] for v in won) if won else None,'mean_risk_multiple':st.mean(v['risk_multiple'] for v in vals),'mean_cost08_pct':st.mean(evaluate(r,target,.8)['net'] for r in rows)}

def day_bootstrap_difference(rows,high=4.2,low=3.2):
    days=collections.defaultdict(list)
    for r in rows:days[r['day']].append(evaluate(r,high)['net']-evaluate(r,low)['net'])
    groups=list(days.values());rng=random.Random(20260922)
    bs=[]
    for _ in range(4000):
        chosen=[groups[rng.randrange(len(groups))] for _ in groups]
        bs.append(sum(sum(g) for g in chosen)/sum(len(g) for g in chosen))
    return {'comparison':f'{high} net minus '+('original plan' if low is None else f'{low} net'),'days':len(groups),'mean_difference_pp':st.mean(v for group in groups for v in group),'exploratory_day_bootstrap_95':[quantile(bs,.025),quantile(bs,.975)],'warning':'Exploratory resampling by UTC day. Few days, repeated symbols and cross-day dependence remain; not out-of-sample evidence.'}

prepared={};excluded={}
for hours in [1,4,12,24]:
    prepared[hours]=[];excluded[hours]=collections.Counter()
    for a in sent:
        r,why=prepare(a,hours)
        if r:prepared[hours].append(r)
        else:excluded[hours][why]+=1

all12=prepared[12];current=[r for r in all12 if r['config_hash']==LATEST]
groups={'telegram_all_configs_12h':all12,'telegram_latest_config_12h':current,'telegram_latest_config_12h_complete_coverage':[r for r in current if r['coverage']==1]}
summaries={name:[aggregate(rows,t) for t in [None]+TARGETS] for name,rows in groups.items()}
for name,rows in groups.items():
    counts=[aggregate(rows,t)['hits_before_sl'] for t in TARGETS]
    assert counts==sorted(counts,reverse=True),(name,'target hit monotonicity')
    assert all(x['n']==x['hits_before_sl']+x['sl']+x['ambiguous']+x['expired'] for x in summaries[name])

path_stats={}
for name,rows in groups.items():
    mfe=[(max(b[1] for b in r['bars'])/r['entry']-1)*100 for r in rows]
    mae=[(min(b[2] for b in r['bars'])/r['entry']-1)*100 for r in rows]
    path_stats[name]={'n':len(rows),'mfe_gross_mean':st.mean(mfe),'mfe_gross_median':st.median(mfe),'mfe_p25':quantile(mfe,.25),'mfe_p75':quantile(mfe,.75),'mae_median':st.median(mae),'coverage_mean':st.mean(r['coverage'] for r in rows),'days':len(set(r['day'] for r in rows)),'symbols':len(set(r['symbol'] for r in rows))}

nonoverlap={}
for target in [None,3.2,4.2]:
    last_exit={};taken=[];skipped=[]
    for r in sorted(all12,key=lambda r:(r['anchor_ms'],r['id'])):
        if r['anchor_ms']<last_exit.get(r['symbol'],0):skipped.append(r['id']);continue
        taken.append(r);last_exit[r['symbol']]=evaluate(r,target)['exit_ms']
    nonoverlap[str(target)]={'stats':aggregate(taken,target),'skipped':len(skipped),'skipped_alert_ids':skipped,'definition':'First available sent signal per symbol while flat under that exit policy. Hypothetical; does not identify market episodes or actual user trades.'}

same_plan_mismatches=[]
for a in sent:
    p=plans.get(a['id'])
    if p and any(a[k]!=p[k] for k in ('entry','take_profit','stop_loss')):same_plan_mismatches.append(a['id'])

source_joins={'sent':len(sent),'sent_missing_signal_id':sum(a['signal_id'] is None for a in sent),'sent_without_notification_plan':sum(a['id'] not in plans for a in sent),'sent_without_outcome':sum(a['signal_id'] not in outcomes for a in sent),'notification_plan_level_mismatches':same_plan_mismatches,'senal_n_counts_sent':dict(collections.Counter(a['senal_n'] for a in sent)),'latest_config_hash':LATEST,'all_alerts_in_export':len(d['alerts']),'all_alerts_missing_signal_id':sum(a['signal_id'] is None for a in d['alerts'])}
filter42=[r for r in current if r['tp_pct']-COST>=4.2]
filter_sensitivity={'definition':'Retrospective exclusion among already sent latest-config alerts if original offered TP net were required >=4.2. Does not replay selection batches or replacement candidates.','original_n':len(current),'retained_n':len(filter42),'excluded_n':len(current)-len(filter42),'retained_original_plan':aggregate(filter42),'excluded_original_plan':aggregate([r for r in current if r not in filter42])}
config_summary=[]
for config in sorted(set(r['config_hash'] for r in all12)):
    selected=[r for r in all12 if r['config_hash']==config]
    config_summary.append({'config_hash':config,'n':len(selected),'first_utc':min(r['day'] for r in selected),'last_utc':max(r['day'] for r in selected),'plan':aggregate(selected),'net32':aggregate(selected,3.2),'net42':aggregate(selected,4.2)})
by_regime={str(k):{'n':len(rs),'net32':aggregate(rs,3.2),'net42':aggregate(rs,4.2)} for k,rs in [(k,[r for r in current if r['btc_regime']==k]) for k in set(r['btc_regime'] for r in current)]}
anchor_rows=[prepare(a,12,'alert')[0] for a in sent];anchor_rows=[r for r in anchor_rows if r]
result={'snapshot_utc':d['snapshot_utc'],'cost_assumed_pct':COST,'scope':'Sent Telegram alerts only. Complete fixed windows; no actual user fills.','source_joins':source_joins,'excluded_by_horizon':{k:dict(v) for k,v in excluded.items()},'target_comparisons':summaries,'path_stats':path_stats,'config_comparisons':config_summary,'latest_regime':by_regime,'horizon_latest_config':{h:[aggregate([r for r in rs if r['config_hash']==LATEST],t) for t in [3.2,4.2]] for h,rs in prepared.items()},'paired_comparisons':{name:day_bootstrap_difference(rows) for name,rows in groups.items()},'nonoverlap_policy':nonoverlap,'anchor_sensitivity_alert_clock':[aggregate(anchor_rows,t) for t in [None,3.2,4.2]],'directional_inventory':d['directional'],'validation':{'exclusive_outcome_counts':'pass','target_hit_monotonicity':'pass','bar_uniqueness_and_ohlc':'pass','mature_cohorts':'pass'},'limitations':['Targets were inspected retrospectively, not selected before these outcomes.','No matched contemporaneous random control was rebuilt in this target comparison.','Candle high/low touches assume fills at barriers; execution costs and gaps may differ.','Activation precedes Telegram receipt and user entry; true user entry timestamps are not recorded.','Do not interpret MFE as captured profit, notification success as trade execution, or bearish directional returns as spot short returns.']}
result['paired_42_vs_original']={name:day_bootstrap_difference(rows,4.2,None) for name,rows in groups.items()}
result['filter42_sensitivity']=filter_sensitivity
(BASE/'datos/resultados.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
compact={name:[{k:round(v,3) if isinstance(v,float) else v for k,v in row.items() if k in ['n','target_net_pct','hits_before_sl','hit_pct','mean_net_pct','median_net_pct','median_hours_to_target','mean_risk_multiple','ambiguous']} for row in values] for name,values in summaries.items()}
print(json.dumps({'source':source_joins,'excluded':dict(excluded[12]),'comparisons':compact,'path_stats':path_stats,'paired':result['paired_comparisons'],'nonoverlap':{k:dict(n=v['stats']['n'],skipped=v['skipped']) for k,v in nonoverlap.items()}},ensure_ascii=False,indent=2))
