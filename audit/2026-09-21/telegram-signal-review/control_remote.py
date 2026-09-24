"""Read-only control: same pairs and same TP/SL distances, entry times drawn at random."""
import sqlite3, json, gzip, sys, time, bisect, random
DB='file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro'
H=12*3600*1000; K=10
random.seed(20260921)
db=sqlite3.connect(DB,uri=True); db.row_factory=sqlite3.Row
db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
now=int(time.time()*1000)
plans=[dict(r) for r in db.execute("""SELECT id,ts_ms,symbol,entry,take_profit,stop_loss FROM alertas_emitidas
        WHERE telegram='enviado' AND entry IS NOT NULL AND take_profit IS NOT NULL AND stop_loss IS NOT NULL""")]
lo_all=min(p['ts_ms'] for p in plans); hi_all=now-H
by={}
for p in plans:
    if 0<p['stop_loss']<p['entry']<p['take_profit']: by.setdefault(p['symbol'],[]).append(p)
out={'controls':[], 'k':K, 'now':now}
for k,sym in enumerate(sorted(by)):
    T=[];Hh=[];L=[];C=[]
    for t,h,l,c in db.execute("SELECT open_time,h,l,c FROM klines WHERE symbol=? AND tf='1m' ORDER BY open_time",(sym,)):
        T.append(t);Hh.append(h);L.append(l);C.append(c)
    if len(T)<60: continue
    lo=max(lo_all,T[0]); hi=min(hi_all,T[-1]-H)
    if hi<=lo: continue
    for p in by[sym]:
        tp_pct=(p['take_profit']/p['entry']-1); sl_pct=(1-p['stop_loss']/p['entry'])
        for _ in range(K):
            ts=random.randint(lo,hi)
            a=bisect.bisect_left(T,ts); b=bisect.bisect_right(T,ts+H-60000)
            if b-a<60: continue
            E=C[a-1] if a>0 else C[a]
            tp=E*(1+tp_pct); sl=E*(1-sl_pct); meta=E*1.032
            t_tp=t_sl=t_meta=None; mx=-9e9; mn=9e9
            for i in range(a,b):
                dt=T[i]-ts
                if Hh[i]>mx: mx=Hh[i]
                if L[i]<mn: mn=L[i]
                if t_tp is None and Hh[i]>=tp: t_tp=dt
                if t_sl is None and L[i]<=sl: t_sl=dt
                if t_meta is None and Hh[i]>=meta: t_meta=dt
                if t_tp is not None and t_sl is not None and t_meta is not None: break
            out['controls'].append({'sym':sym,'alerta':p['id'],'tp_pct':tp_pct*100,'sl_pct':sl_pct*100,
                'ms_tp':t_tp,'ms_sl':t_sl,'ms_meta':t_meta,'mfe':(mx/E-1)*100,'mae':(mn/E-1)*100,
                'cierre':(C[b-1]/E-1)*100,'n':b-a})
    print(f'{k+1}/{len(by)} {sym}',file=sys.stderr)
db.rollback(); db.close()
sys.stdout.buffer.write(gzip.compress(json.dumps(out).encode()))
