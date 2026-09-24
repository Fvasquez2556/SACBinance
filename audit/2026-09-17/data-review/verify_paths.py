"""Independent read-only reconciliation against retained 1m candles on server."""
import sqlite3, pathlib, json, time, sys
rows=json.loads(sys.stdin.readline())
db=sqlite3.connect('file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro',uri=True)
db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
out=[];minute=60000;day=86400000
for r in rows:
    start=((r['ts_open']+minute-1)//minute)*minute
    end=((r['ts_open']+day-minute)//minute)*minute
    candles=db.execute("SELECT open_time,h,l,c FROM klines WHERE symbol=? AND tf='1m' AND open_time>=? AND open_time<=? ORDER BY open_time",(r['symbol'],start,end)).fetchall()
    expected=(end-start)//minute+1
    first_gap=None;next_time=start;hits={k:None for k in ('goal','tp','sl')}
    horizon={}
    for t,high,low,close in candles:
        if t!=next_time and first_gap is None:first_gap=next_time-r['ts_open']
        next_time=t+minute
        for k,hit in [('goal',high>=r['entry']*1.032),('tp',r['take_profit'] is not None and high>=r['take_profit']),('sl',r['stop_loss'] is not None and low<=r['stop_loss'])]:
            if hits[k] is None and hit:hits[k]=t-r['ts_open']
    if next_time<=end and first_gap is None:first_gap=next_time-r['ts_open']
    out.append({'signal_id':r['signal_id'],'n':len(candles),'expected':expected,'first_gap_ms':first_gap,**hits})
db.rollback();db.close()
print(json.dumps({'as_of_ms':int(time.time()*1000),'rows':out}))
