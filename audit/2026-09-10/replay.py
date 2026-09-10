"""Audit replay: time-based windows, coverage disclosure, no strategy optimization."""
import collections,datetime,json,pathlib,sqlite3,sys
import numpy as np
import pandas as pd
ROOT=pathlib.Path(__file__).resolve().parent
db=sqlite3.connect((ROOT/'snapshot.db').as_uri()+'?mode=ro',uri=True)
out=pd.read_sql_query('SELECT * FROM outcomes ORDER BY ts_open,signal_id',db)
sig=pd.read_sql_query('SELECT * FROM signals ORDER BY ts_open,id',db)
reference='--reference' in sys.argv
prefix='reference_' if reference else ''
kdb=sqlite3.connect((ROOT/'reference.db').as_uri()+'?mode=ro',uri=True) if reference else db
k=pd.read_sql_query("SELECT symbol,open_time,o,h,l,c FROM klines WHERE tf='1m' ORDER BY symbol,open_time",kdb)
arrays={s:g[['open_time','o','h','l','c']].to_numpy() for s,g in k.groupby('symbol',sort=False)}
end=int(k.open_time.max()+60000)
def serial(v):
 if isinstance(v,np.generic):return v.item()
 if isinstance(v,np.ndarray):return v.tolist()
 raise TypeError(type(v).__name__)
def summary(g):
 if not len(g): return {'n':0}
 return {'n':len(g),'symbols':int(g.symbol.nunique()),'mean_gross_pct':float(g.result_pct.mean()),'mean_net_scenario_02_pct':float(g.result_pct.mean()-.2),'median_pct':float(g.result_pct.median()),'tp':int((g.status=='TP').sum()),'sl':int((g.status=='SL').sum()),'expired':int((g.status=='EXPIRED').sum())}
R={'official':summary(sig[sig.status.isin(['TP','SL','EXPIRED'])]),'snapshot_last_closed_candle_utc':datetime.datetime.fromtimestamp(end/1000,datetime.timezone.utc).isoformat()}
gaps=[]
for sym,a in arrays.items():
 dif=np.diff(a[:,0]); missing=np.maximum(dif/60000-1,0)
 gaps.append({'symbol':sym,'n':len(a),'internal_missing_minutes':int(missing.sum()),'gaps':int((dif>60000).sum()),'max_gap_minutes':int(dif.max()/60000) if len(dif) else 0,'stale_minutes':int((end-60000-a[-1,0])/60000)})
R['gaps_summary']={'symbols':len(gaps),'symbols_with_internal_gaps':sum(x['gaps']>0 for x in gaps),'missing_internal_symbol_minutes':sum(x['internal_missing_minutes'] for x in gaps),'symbols_stale_over10min':sum(x['stale_minutes']>10 for x in gaps),'top_gaps':sorted(gaps,key=lambda x:-x['internal_missing_minutes'])[:12]}
rows=[]; sims=[]; cases=[]
def simulate(seg,entry,sl,tp,delay=False):
 fill_idx=None
 if not delay:fill_idx=0
 else:
  for i,v in enumerate(seg):
   if v[3]<=entry:
    fill_idx=i;break
   if v[2]>=tp:return None # opportunity already completed before fill
 if fill_idx is None:return None
 fill=entry
 for i in range(fill_idx,len(seg)):
  t,o,h,l,c=seg[i]
  if l<=sl:return {'status':'SL','result_pct':(min(o,sl)/fill-1)*100,'exit':t,'fill_idx':fill_idx,'ambiguous_fill_tp':False}
  if h>=tp:
   if delay and i==fill_idx and o>entry:
    # Unknown if high preceded the fill; never award this TP.
    continue
   return {'status':'TP','result_pct':(tp/fill-1)*100,'exit':t,'fill_idx':fill_idx,'ambiguous_fill_tp':False}
 return {'status':'EXPIRED','result_pct':(seg[-1,4]/fill-1)*100,'exit':seg[-1,0]+60000,'fill_idx':fill_idx,'ambiguous_fill_tp':False}
for r in out.to_dict('records'):
 a=arrays.get(r['symbol']);t=r['ts_open'];deadline=t+86400000
 if a is None:continue
 # Use only full candles whose open is at/after emission and close <= deadline.
 i=np.searchsorted(a[:,0],t,side='left');j=np.searchsorted(a[:,0],deadline-60000,side='right')
 seg=a[i:j]
 first=((t+59999)//60000)*60000;last=((deadline-60000)//60000)*60000
 expected=max(0,int((last-first)//60000+1))
 mature=deadline<=end
 if not len(seg):continue
 row={'signal_id':r['signal_id'],'symbol':r['symbol'],'ts_open':t,'sombra':r['sombra'],'mature':bool(mature),'expected_candles':expected,'n_candles':len(seg),'coverage':len(seg)/expected if expected else 0,'exact':len(seg)==expected,'mfe_replay':(seg[:,2].max()/r['entry']-1)*100,'mae_replay':(seg[:,3].min()/r['entry']-1)*100,'db_mfe':r['mfe_pct'],'db_mae':r['mae_pct'],'db_closed':r['cerrado']}
 rows.append(row)
 if not mature or r['sombra']:continue
 for name,entry,sl,tp,delay,hours in (
  ('Original 12h',r['entry'],r['stop_loss'],r['take_profit'],False,12),
  ('Original 24h',r['entry'],r['stop_loss'],r['take_profit'],False,24),
  ('Esperar SL+0.5%, SL original',r['stop_loss']*1.005,r['stop_loss'],r['take_profit'],True,24),
  ('Esperar SL+0.5%, SL -2%',r['stop_loss']*1.005,r['stop_loss']*1.005*.98,r['take_profit'],True,24),
  ('Esperar SL+0.5%, SL -3%',r['stop_loss']*1.005,r['stop_loss']*1.005*.97,r['take_profit'],True,24),
  ('Meta fija +3.2%, SL original',r['entry'],r['stop_loss'],r['entry']*1.032,False,24),
 ):
  sub=seg[seg[:,0]+60000<=t+hours*3600000]
  if not len(sub):continue
  ans=simulate(sub,entry,sl,tp,delay)
  sims.append({'strategy':name,**{key:row[key] for key in ('signal_id','symbol','ts_open','coverage','exact')},'filled':ans is not None,**(ans or {'status':'NO_FILL','result_pct':None})})
df=pd.DataFrame(rows);ss=pd.DataFrame(sims)
R['replay_coverage']={'real_mature_with_any_candles':len(df[(df.sombra==0)&df.mature]),'real_mature_exact':len(df[(df.sombra==0)&df.mature&df.exact]),'real_mature_over98pct':len(df[(df.sombra==0)&df.mature&(df.coverage>=.98)]),'real_mature_over95pct':len(df[(df.sombra==0)&df.mature&(df.coverage>=.95)]),'mature_outcomes_left_open':int(((out.ts_open+86400000<=end)&(out.cerrado==0)).sum()),'open_signals_over12h':int(((sig.status=='OPEN')&(sig.ts_open+43200000<end)).sum())}
R['strategy_results']=[]
for label,mask in [('exact',ss.exact),('coverage_ge98',ss.coverage>=.98),('coverage_ge95',ss.coverage>=.95)]:
 for strategy,g in ss[mask].groupby('strategy'):
  x=g[g.filled]
  R['strategy_results'].append({'coverage_group':label,'strategy':strategy,'opportunities':len(g),'filled':len(x),**summary(x),'hit_net32':int((x.result_pct-.2>=3.2).sum())})
R['case_summary']=[]
for sym in ['MARSCOINUSDT','ETHFIUSDT','RAYUSDT','IOUSDT']:
 o=out[(out.symbol==sym)&(out.sombra==0)]
 s=sig[sig.symbol==sym]
 R['case_summary'].append({'symbol':sym,'signals':len(s),'closed_outcomes':int((o.cerrado==1).sum()),'hit32_all':int(o.ms_up_32.notna().sum()),'hit32_before_sl_all':int((o.ms_up_32.notna()&(o.ms_sl.isna()|(o.ms_up_32<o.ms_sl))).sum()),'max_mfe':float(o.mfe_pct.max()) if len(o) else None,**summary(s[s.status.isin(['TP','SL','EXPIRED'])])})
R['feature_nulls_recent']={c:int(out.loc[out.retro_caida_pct.notna(),c].isna().sum()) for c in ['rsi14','macd_hist','bb_position','rsi5','atr_percentile','buy_ratio_30s','flow_trades_30s','retro_caida_pct','rango_1h_pct','dist_resistencia_pct']}
recent=out[(out.retro_caida_pct.notna())&(out.sombra==0)&(out.cerrado==1)]
R['recent_features_mature_n']=len(recent)
R['retro_signal_segments']=[]
for name,g in [('with_drop_confirmed',recent[(recent.retro_caida_pct<=-2)&(recent.retro_confirmado==1)]),('other',recent[~((recent.retro_caida_pct<=-2)&(recent.retro_confirmado==1))])]:
 R['retro_signal_segments'].append({'group':name,'n':len(g),'hit32':int(g.ms_up_32.notna().sum()),'first32':int((g.ms_up_32.notna()&(g.ms_sl.isna()|(g.ms_up_32<g.ms_sl))).sum())})
df.to_json(ROOT/(prefix+'coverage_rows.json'),orient='records',indent=2)
ss.to_json(ROOT/(prefix+'replay_rows.json'),orient='records',indent=2)
(ROOT/(prefix+'replay_results.json')).write_text(json.dumps(R,indent=2,default=serial),encoding='utf-8')
print(json.dumps(R,indent=2,default=serial))
