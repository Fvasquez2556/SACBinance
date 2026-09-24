"""Read-only: first-touch times for a ladder of fixed targets and stops, from entry."""
import sqlite3, json, gzip, sys, time, bisect
DB='file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro'
H=12*3600*1000
UP=[1,2,2.5,3,3.2,4,5,6,8,10]
DN=[1,1.5,2,2.5,3,3.5,4,5,6,8]
db=sqlite3.connect(DB,uri=True); db.row_factory=sqlite3.Row
db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
now=int(time.time()*1000)
def rows(sql): return [dict(r) for r in db.execute(sql)]
items=[('alert',r['id'],r['symbol'],r['ts_ms'],r['entry']) for r in rows(
  "SELECT id,ts_ms,symbol,entry FROM alertas_emitidas WHERE entry IS NOT NULL")]
items+=[('signal',r['id'],r['symbol'],r['ts_open'],r['entry']) for r in rows(
  "SELECT id,ts_open,symbol,entry FROM signals WHERE entry IS NOT NULL")]
by={}
for it in items: by.setdefault(it[2],[]).append(it)
out={'alert':{},'signal':{},'up':UP,'dn':DN,'now':now}
for k,sym in enumerate(sorted(by)):
    g=by[sym]; lo=min(x[3] for x in g); hi=min(now,max(x[3] for x in g)+H)
    T=[];Hh=[];L=[]
    for t,h,l in db.execute("SELECT open_time,h,l FROM klines WHERE symbol=? AND tf='1m' AND open_time>=? AND open_time<=? ORDER BY open_time",(sym,lo,hi)):
        T.append(t);Hh.append(h);L.append(l)
    for kind,key,_s,ts,E in g:
        if not E or E<=0: continue
        a=bisect.bisect_left(T,ts); b=bisect.bisect_right(T,ts+H-60000)
        if b<=a: continue
        up=[None]*len(UP); dn=[None]*len(DN); iu=0; idn=0
        for i in range(a,b):
            dt=T[i]-ts
            while iu<len(UP) and Hh[i]>=E*(1+UP[iu]/100): up[iu]=dt; iu+=1
            while idn<len(DN) and L[i]<=E*(1-DN[idn]/100): dn[idn]=dt; idn+=1
            if iu>=len(UP) and idn>=len(DN): break
        out[kind][key]={'up':up,'dn':dn,'n':b-a}
    print(f'{k+1}/{len(by)} {sym}',file=sys.stderr)
db.rollback(); db.close()
sys.stdout.buffer.write(gzip.compress(json.dumps(out).encode()))
