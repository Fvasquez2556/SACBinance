"""Read the consistent, read-only SQLite export. No network or trading actions."""
import collections, datetime as dt, gzip, json, math, pathlib, random, statistics as st

ROOT = pathlib.Path(__file__).resolve().parent
D = json.loads(gzip.decompress((ROOT / 'snapshot.json.gz').read_bytes()))
NOW = D['as_of_ms']; DAY = 86_400_000
S = {r['id']:r for r in D['signals']}
O = D['outcomes']; A = D['alerts']
def iso(ms): return dt.datetime.fromtimestamp(ms/1000, dt.timezone.utc).isoformat(timespec='seconds')
def stamp(s): return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp()*1000)
def avg(values):
    values=[v for v in values if v is not None]
    return st.mean(values) if values else None
def median(values):
    values=[v for v in values if v is not None]
    return st.median(values) if values else None
def rate(k,n): return 100*k/n if n else None
def timevalid(x): return x is None or (isinstance(x,(int,float)) and math.isfinite(x) and 0<=x<=DAY)
def valid(r): return all(timevalid(r[k]) for k in ('ms_up_32','ms_sl','ms_tp','ms_mfe','ms_mae'))
def mature(r): return r['cerrado']==1 and r['ts_open']<=NOW-DAY
def quality(r): return mature(r) and valid(r) and (r.get('cobertura_velas') or 0)>=.98
def goal(r,h=DAY):
    a,b=r['ms_up_32'],r['ms_sl']
    return a is not None and a<=h and (b is None or a<b)
def touched(r,h=DAY): return r['ms_up_32'] is not None and r['ms_up_32']<=h
def order(r):
    a,b=r['ms_tp'],r['ms_sl']
    if a is not None and b is not None and a==b:return 'AMBIGUOUS'
    if a is not None and (b is None or a<b):return 'TP_FIRST'
    if b is not None:return 'SL_FIRST'
    return 'NEITHER'
def plan24(r):
    # Scenario shared with previous report; flat expiry is NOT an observed fill.
    if order(r)=='TP_FIRST':return r['tp_pct']
    if order(r) in ('SL_FIRST','AMBIGUOUS'):return r['sl_pct']
    return 0
def summary(rows):
    n=len(rows);res=[S[r['signal_id']] for r in rows if r['signal_id'] in S]
    closed=[s for s in res if s['status'] in ('TP','SL','EXPIRED') and s['result_pct'] is not None]
    wins=sum(goal(r) for r in rows)
    return {'n':n,'symbols':len(set(r['symbol'] for r in rows)),
        'first':iso(min(r['ts_open'] for r in rows)) if rows else None,'last':iso(max(r['ts_open'] for r in rows)) if rows else None,
        'touch32_n':sum(touched(r) for r in rows),'touch32_pct':rate(sum(touched(r) for r in rows),n),
        'goal_before_sl_n':wins,'goal_before_sl_pct':rate(wins,n),
        'goal_tie_n':sum(r['ms_up_32'] is not None and r['ms_up_32']==r['ms_sl'] for r in rows),
        'goal_after_sl_n':sum(touched(r) and r['ms_sl'] is not None and r['ms_up_32']>r['ms_sl'] for r in rows),
        'goal_after_short_tp_n':sum(goal(r) and order(r)=='TP_FIRST' and r['ms_tp']<r['ms_up_32'] for r in rows),
        'goal_before_sl_by_horizon_pct':{str(h):rate(sum(goal(r,h*60000) for r in rows),n) for h in [15,30,60,120,240,360,480,1440]},
        'plan_order':dict(collections.Counter(order(r) for r in rows)),
        'plan_tp_below32_n':sum(r['tp_pct'] is not None and r['tp_pct']<3.2 for r in rows),
        'tp_median':median(r['tp_pct'] for r in rows),'sl_median':median(r['sl_pct'] for r in rows),
        'net_target_median':median(r['reward_neto_pct'] for r in rows),
        'cov_median':median(r['cobertura_velas'] for r in rows),
        'median_hours_success':median(r['ms_up_32']/3600000 for r in rows if goal(r)),
        'signal_result_n':len(closed),'signal_status':dict(collections.Counter(s['status'] for s in res)),
        'signal_gross_mean':avg(s['result_pct'] for s in closed),
        'signal_net_scenario_mean':avg(s['result_pct']-.5 for s in closed),
        'signal_close32_n':sum(s['result_pct']>=3.2 for s in closed),
        'signal_close32_pct':rate(sum(s['result_pct']>=3.2 for s in closed),len(closed)),
        'plan24_net_flat_expiry':avg(plan24(r)-.5 for r in rows),
        'vol_mix':dict(collections.Counter(r['grupo_vol'] for r in rows)),
        'btc_mix':dict(collections.Counter(r['btc_regime'] for r in rows))}

CURRENT=[r for r in O if r['strategy_version']=='f82bcff']
Q=[r for r in CURRENT if quality(r) and not r['sombra']]
CUTOFF=stamp('2026-09-14T00:00:00')
EARLY=[r for r in Q if r['ts_open']<CUTOFF]
RECENT=[r for r in Q if r['ts_open']>=CUTOFF]
def group_summary(rows,key):
    groups=collections.defaultdict(list)
    for r in rows:groups[str(key(r))].append(r)
    return {k:summary(v) for k,v in sorted(groups.items())}

result={'as_of_utc':iso(NOW),'maturity_cutoff_utc':iso(NOW-DAY),
  'counts':{k:len(D[k]) for k in ('outcomes','signals','alerts')},
  'quality_by_version':{},'quality_by_day':{},'alerts_by_day':{},
  'all_current_emitted':summary([r for r in CURRENT if mature(r) and valid(r) and not r['sombra']]),
  'clean_current':summary(Q),'early':summary(EARLY),'recent':summary(RECENT),
  'daily':group_summary(Q,lambda r:iso(r['ts_open'])[:10]),
  'by_config':group_summary(Q,lambda r:r['config_hash']),
  'by_volatility':group_summary(Q,lambda r:r['grupo_vol']),
  'by_profile':group_summary(Q,lambda r:r['taxonomia']),
  'by_veto':group_summary([r for r in CURRENT if quality(r)],lambda r:(r.get('sombra_motivo') or 'EMITIDA').split(' en ')[0]),
  'klines':D['klines']}
for keyname,key in [('quality_by_version',lambda r:r['strategy_version']),('quality_by_day',lambda r:iso(r['ts_open'])[:10])]:
    for k in sorted(set(str(key(r)) for r in O)):
        rows=[r for r in O if str(key(r))==k];m=[r for r in rows if mature(r)]
        result[keyname][k]={'n':len(rows),'mature':len(m),'cov98':sum((r.get('cobertura_velas') or 0)>=.98 for r in m),
        'coverage_median':median(r['cobertura_velas'] for r in m),'invalid_times':sum(not valid(r) for r in m),
        'open_over24h':sum(not r['cerrado'] and NOW-r['ts_open']>DAY+60000 for r in rows)}
for date in sorted(set(iso(a['ts_ms'])[:10] for a in A)):
    rows=[a for a in A if iso(a['ts_ms'])[:10]==date]
    result['alerts_by_day'][date]={'n':len(rows),'no_id':sum(a['signal_id'] is None for a in rows),
      'no_id_pct':rate(sum(a['signal_id'] is None for a in rows),len(rows)),
      'orphan_id':sum(a['signal_id'] is not None and a['signal_id'] not in S for a in rows),
      'telegram':dict(collections.Counter(a['telegram'] for a in rows))}
result['integrity']={
    'emitted_outcomes_without_signal':sum(not r['sombra'] and r['signal_id'] not in S for r in O),
    'signals_without_outcome':sum(sid not in set(r['signal_id'] for r in O) for sid in S),
    'open_signals_over12h':sum(s['status']=='OPEN' and NOW-s['ts_open']>12*3600000+60000 for s in S.values()),
    'oldest_open_signal_hours':max((NOW-s['ts_open'])/3600000 for s in S.values() if s['status']=='OPEN'),
    'last_outcome_utc':iso(max(r['ts_open'] for r in O)),
    'current_missing_features':{k:sum(r.get(k) is None for r in CURRENT) for k in ['strategy_version','config_hash','grupo_vol','drawdown_pct','atr_pct','vol_ratio','rsi14_15m','macd_hist_15m','retro_confirmado']},
    'alert_no_id_total':sum(a['signal_id'] is None for a in A),
    'alert_plan_mismatch':sum(a['signal_id'] in S and any(abs((a[k] or 0)-(S[a['signal_id']][k] or 0))>1e-8 for k in ('entry','take_profit','stop_loss')) for a in A)}

# A fixed threshold, learned from the EARLY period only, avoids ranking against future test observations.
ranges=sorted(r['rango_1h_pct'] for r in EARLY if r['rango_1h_pct'] is not None)
threshold=ranges[math.ceil(.8*len(ranges))-1]
ranked_recent=[r for r in RECENT if r['rango_1h_pct'] is not None and r['rango_1h_pct']>=threshold]
result['range_holdout']={'training_cutoff_utc':iso(CUTOFF),'threshold_pct':threshold,'n_train':len(EARLY),'n_test':len(RECENT),
    'selected':summary(ranked_recent),'rest':summary([r for r in RECENT if r not in ranked_recent])}

# Cluster bootstrap by symbol (all of one pair's correlated signals travel together).
# Same sampled symbols in each period; this is uncertainty in a descriptive comparison, not causality.
rng=random.Random(20260916)
symbols=sorted(set(r['symbol'] for r in EARLY+RECENT))
bucket=[]
for sym in symbols:
    e=[r for r in EARLY if r['symbol']==sym];r=[r for r in RECENT if r['symbol']==sym]
    bucket.append((len(e),sum(goal(x) for x in e),len(r),sum(goal(x) for x in r)))
diffs=[]
for _ in range(3000):
    sampled=rng.choices(bucket,k=len(bucket));en=sum(x[0] for x in sampled);rn=sum(x[2] for x in sampled)
    if en and rn:diffs.append(100*(sum(x[3] for x in sampled)/rn-sum(x[1] for x in sampled)/en))
diffs.sort();result['change_cluster_bootstrap']={'unit':'symbol','iterations':3000,'delta_pp':result['recent']['goal_before_sl_pct']-result['early']['goal_before_sl_pct'],
    'p025_pp':diffs[int(.025*len(diffs))],'p975_pp':diffs[int(.975*len(diffs))]}
result['coverage_sensitivity']={str(c):summary([r for r in CURRENT if mature(r) and valid(r) and not r['sombra'] and (r.get('cobertura_velas') or 0)>=c]) for c in [.95,.98,.99,.995,1]}
result['retention_1m_days']=next((r['last_ms']-r['first_ms'])/DAY for r in D['klines'] if r['tf']=='1m')
(ROOT/'results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
if __name__=='__main__':
    for k in ('clean_current','early','recent','change_cluster_bootstrap','integrity','range_holdout'):
        print(k,json.dumps(result[k],ensure_ascii=False))
