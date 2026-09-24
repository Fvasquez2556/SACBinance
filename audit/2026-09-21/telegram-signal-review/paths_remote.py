"""Read-only path reconstruction on the production DB. Emits gzipped JSON to stdout."""
import sqlite3, json, gzip, sys, time, bisect

DB='file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro'
HORIZON_MS=12*3600*1000
NEAR_FRAC=0.8
META=0.032

db=sqlite3.connect(DB,uri=True); db.row_factory=sqlite3.Row
db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
now=int(time.time()*1000)

def rows(sql,args=()): return [dict(r) for r in db.execute(sql,args)]

alerts=rows("""SELECT id,ts_ms,symbol,signal_id,entry,take_profit,stop_loss,tp_pct,sl_pct,
                      reward_neto_pct,objetivo_alcanzable,tier,score,display_state,senal_n,
                      telegram,telegram_detalle,strategy_version,config_hash
               FROM alertas_emitidas WHERE entry IS NOT NULL AND take_profit IS NOT NULL AND stop_loss IS NOT NULL""")
signals=rows("""SELECT id,symbol,ts_open,display_state,tier,score,entry,take_profit,stop_loss,
                       risk_reward,macro,status,ts_close,result_pct
                FROM signals WHERE entry IS NOT NULL AND take_profit IS NOT NULL AND stop_loss IS NOT NULL""")
planes=rows("SELECT * FROM notificacion_planes")
eventos=rows("SELECT event_key,alerta_id,symbol,tipo,ts_ms,estado FROM notificacion_eventos")

# work items: (kind, key, symbol, ts_open, entry, tp, sl)
items=[]
for a in alerts: items.append(('alert',a['id'],a['symbol'],a['ts_ms'],a['entry'],a['take_profit'],a['stop_loss']))
for s in signals: items.append(('signal',s['id'],s['symbol'],s['ts_open'],s['entry'],s['take_profit'],s['stop_loss']))

by_symbol={}
for it in items: by_symbol.setdefault(it[2],[]).append(it)

def evaluate(ts,entry,tp,sl,T,H,L,C):
    start=bisect.bisect_left(T,ts)              # only whole minutes inside the window
    end=bisect.bisect_right(T,ts+HORIZON_MS-60000)
    n=end-start
    horizon_end=min(ts+HORIZON_MS,now)
    expected=max(0,(horizon_end-ts)//60000)
    r={'n_velas':n,'esperadas':expected,'completa':int(ts+HORIZON_MS<=now)}
    if n==0: return r
    meta=entry*(1+META)
    near=entry-(entry-sl)*NEAR_FRAC
    t_tp=t_sl=t_meta=t_near_low=t_near_close=None
    amb=0
    mfe=-9e9; mae=9e9; ms_mfe=ms_mae=None
    min_low_pre_tp=9e9; min_low_pre_meta=9e9
    post_sl_max=None; post_sl_min=None; t_post_sl_tp=None; t_post_sl_meta=None
    sl_min_after=None
    for i in range(start,end):
        t,h,l,c=T[i],H[i],L[i],C[i]
        dt=t-ts
        if h>mfe: mfe=h; ms_mfe=dt
        if l<mae: mae=l; ms_mae=dt
        if t_tp is None and h>=tp:
            t_tp=dt
            if l<=sl and t_sl is None: amb=1
        if t_sl is None and l<=sl:
            t_sl=dt
            if h>=tp and t_tp is not None and t_tp==dt: amb=1
        if t_meta is None and h>=meta: t_meta=dt
        if t_near_low is None and l<=near: t_near_low=dt
        if t_near_close is None and c<=near: t_near_close=dt
        if t_tp is None and l<min_low_pre_tp: min_low_pre_tp=l
        if t_meta is None and l<min_low_pre_meta: min_low_pre_meta=l
        if t_sl is not None:
            sl_min_after=l if sl_min_after is None else min(sl_min_after,l)
            post_sl_max=h if post_sl_max is None else max(post_sl_max,h)
            post_sl_min=l if post_sl_min is None else min(post_sl_min,l)
            if t_post_sl_tp is None and h>=tp and dt>=t_sl: t_post_sl_tp=dt
            if t_post_sl_meta is None and h>=meta and dt>=t_sl: t_post_sl_meta=dt
    pct=lambda x: None if x is None else (x/entry-1)*100
    r.update({
        'ms_tp':t_tp,'ms_sl':t_sl,'ms_meta':t_meta,'ambiguo':amb,
        'ms_cerca_sl_low':t_near_low,'ms_cerca_sl_close':t_near_close,
        'mfe_pct':pct(mfe),'mae_pct':pct(mae),'ms_mfe':ms_mfe,'ms_mae':ms_mae,
        'mae_pre_tp_pct':None if min_low_pre_tp>8e9 else pct(min_low_pre_tp),
        'mae_pre_meta_pct':None if min_low_pre_meta>8e9 else pct(min_low_pre_meta),
        'post_sl_max_pct':pct(post_sl_max),'post_sl_min_pct':pct(post_sl_min),
        'ms_tp_post_sl':t_post_sl_tp,'ms_meta_post_sl':t_post_sl_meta,
        'sl_overshoot_pct':None if sl_min_after is None else (sl_min_after/sl-1)*100,
        'close_fin_pct':pct(C[end-1]),'ms_ultima_vela':T[end-1]-ts,
    })
    return r

results={'alert':{}, 'signal':{}}
syms=sorted(by_symbol)
for k,sym in enumerate(syms):
    group=by_symbol[sym]
    lo=min(g[3] for g in group); hi=min(now,max(g[3] for g in group)+HORIZON_MS)
    T=[];H=[];L=[];C=[]
    for t,h,l,c in db.execute("SELECT open_time,h,l,c FROM klines WHERE symbol=? AND tf='1m' AND open_time>=? AND open_time<=? ORDER BY open_time",(sym,lo,hi)):
        T.append(t);H.append(h);L.append(l);C.append(c)
    for kind,key,_s,ts,entry,tp,sl in group:
        if not (entry and tp and sl) or entry<=0: continue
        results[kind][key]=evaluate(ts,entry,tp,sl,T,H,L,C)
    print(f'{k+1}/{len(syms)} {sym} velas={len(T)}',file=sys.stderr)

out={'now':now,'horizon_ms':HORIZON_MS,'near_frac':NEAR_FRAC,'meta_pct':META*100,
     'alerts':alerts,'signals':signals,'planes':planes,'eventos':eventos,
     'paths_alert':results['alert'],'paths_signal':results['signal']}
db.rollback(); db.close()
sys.stdout.buffer.write(gzip.compress(json.dumps(out,ensure_ascii=False).encode('utf-8')))
