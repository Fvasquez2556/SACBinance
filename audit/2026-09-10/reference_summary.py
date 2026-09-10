import collections,datetime,json,pathlib,sqlite3
import numpy as np
import pandas as pd
ROOT=pathlib.Path(__file__).resolve().parent
db=sqlite3.connect((ROOT/'snapshot.db').as_uri()+'?mode=ro',uri=True)
ref=sqlite3.connect((ROOT/'reference.db').as_uri()+'?mode=ro',uri=True)
tr=pd.read_json(ROOT/'reference_replay_rows.json')
prov=json.loads((ROOT/'reference_provenance.json').read_text())
signals=pd.read_sql_query('SELECT * FROM signals',db)
out=pd.read_sql_query('SELECT * FROM outcomes',db)
def summarize(g):
 x=g[g.filled];v=x.result_pct.to_numpy();keys=x.symbol.to_numpy()
 result={'opportunities':len(g),'filled':len(x),'symbols':int(x.symbol.nunique()),'mean_gross_pct':float(v.mean()) if len(v) else None,'mean_net02_pct':float(v.mean()-.2) if len(v) else None,'tp':int((x.status=='TP').sum()),'sl':int((x.status=='SL').sum()),'expired':int((x.status=='EXPIRED').sum())}
 if len(x) and x.symbol.nunique()>=5:
  a=np.array([(x.loc[x.symbol==s,'result_pct'].sum(),sum(keys==s)) for s in sorted(set(keys))]);rng=np.random.default_rng(20260910)
  ids=rng.integers(0,len(a),size=(3000,len(a)))
  sums=a[ids].sum(axis=1);boot=sums[:,0]/sums[:,1]-.2
  result['net02_symbol_bootstrap95']=[float(z) for z in np.quantile(boot,[.025,.975])]
 return result
R={'reference_candles':ref.execute('SELECT count(*) FROM klines').fetchone()[0],'request_count':len(prov['requests']),'cohorts':[]}
for cohort,mask in [('24 predefined symbols; excludes named examples',tr.symbol.isin(prov['sample'])),('4 user examples',tr.symbol.isin(prov['cases']))]:
 for strategy,g in tr[mask&tr.exact].groupby('strategy'):
  R['cohorts'].append({'cohort':cohort,'strategy':strategy,**summarize(g)})
R['sample_day_original12']=[]
base=tr[tr.symbol.isin(prov['sample'])&tr.exact&(tr.strategy=='Original 12h')].copy()
base['day']=pd.to_datetime(base.ts_open,unit='ms',utc=True).dt.strftime('%Y-%m-%d')
for day,g in base.groupby('day'):R['sample_day_original12'].append({'day':day,**summarize(g)})
compare=tr[tr.exact&(tr.strategy=='Original 12h')].merge(signals,left_on='signal_id',right_on='id',suffixes=('_replay','_db'))
paired=compare[compare.result_pct_db.notna()]
R['signal_reconciliation']={'n':len(compare),'same_status':int((compare.status_replay==compare.status_db).sum()),'cross_status':compare.groupby(['status_db','status_replay']).size().reset_index(name='n').to_dict('records'),'paired_n':len(paired),'mean_recorded_pct':float(paired.result_pct_db.mean()),'mean_replay_same_rows_pct':float(paired.result_pct_replay.mean())}
ohlc_old=pd.read_sql_query("SELECT * FROM klines WHERE tf='1m'",db)
ohlc_new=pd.read_sql_query("SELECT * FROM klines WHERE tf='1m'",ref)
joined=ohlc_old.merge(ohlc_new,on=['symbol','tf','open_time'],suffixes=('_db','_api'))
R['candle_value_reconciliation']={'matching_keys':len(joined),'different_ohlc_rows':int(np.any(np.column_stack([~np.isclose(joined[c+'_db'],joined[c+'_api'],rtol=1e-10,atol=1e-12) for c in ['o','h','l','c']]),axis=1).sum())}
R['case_replayed12']=[]
for sym in prov['cases']:
 g=tr[(tr.symbol==sym)&tr.exact&(tr.strategy=='Original 12h')]
 R['case_replayed12'].append({'symbol':sym,**summarize(g)})
# Detailed independent reconstruction of the user's MARSCOIN episode.
m=out[out.signal_id==1871].iloc[0]
bars=ohlc_new[(ohlc_new.symbol=='MARSCOINUSDT')&(ohlc_new.open_time>=m.ts_open)&(ohlc_new.open_time+60000<=m.ts_open+86400000)].sort_values('open_time')
def first_hit(mask):
 x=bars[mask]
 if not len(x):return None
 v=x.iloc[0]
 return {'bar_open_utc':datetime.datetime.fromtimestamp(v.open_time/1000,datetime.timezone.utc).isoformat(),'minutes_from_signal':(v.open_time-m.ts_open)/60000,'o':v.o,'h':v.h,'l':v.l,'c':v.c}
R['mars_1871']={'entry':m.entry,'stop_loss':m.stop_loss,'take_profit':m.take_profit,'signal_utc':datetime.datetime.fromtimestamp(m.ts_open/1000,datetime.timezone.utc).isoformat(),'first_sl':first_hit(bars.l<=m.stop_loss),'first_tp':first_hit(bars.h>=m.take_profit),'first_32':first_hit(bars.h>=m.entry*1.032),'minimum':float(bars.l.min()),'maximum':float(bars.h.max()),'alternatives':tr[(tr.signal_id==1871)&tr.exact].to_dict('records')}
# Intrabar ambiguities at a limit fill must be disclosed instead of awarding a TP.
R['intrabar_fill_tp_ambiguities']=[]
for _,r in out[out.symbol.isin(prov['cases']+prov['sample'])&(out.sombra==0)].iterrows():
 bars2=ohlc_new[(ohlc_new.symbol==r.symbol)&(ohlc_new.open_time>=r.ts_open)&(ohlc_new.open_time+60000<=r.ts_open+86400000)].sort_values('open_time')
 for _,v in bars2.iterrows():
  trigger=r.stop_loss*1.005
  if v.l<=trigger:
   if v.o>trigger and v.h>=r.take_profit:R['intrabar_fill_tp_ambiguities'].append({'signal_id':int(r.signal_id),'symbol':r.symbol,'bar_open':int(v.open_time)})
   break
  if v.h>=r.take_profit:break
R['metadata_age']=[dict(zip(['n','oldest_utc','newest_utc'],r)) for r in db.execute("SELECT count(*),datetime(min(updated),'unixepoch'),datetime(max(updated),'unixepoch') FROM pair_metadata")]
(ROOT/'reference_summary.json').write_text(json.dumps(R,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps(R,indent=2,allow_nan=False))
