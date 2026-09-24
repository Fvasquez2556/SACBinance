"""Solo lectura: primer toque de objetivos fijos extra y de multiplos del riesgo (R = entrada - stop)."""
import sqlite3, json, gzip, sys, time, bisect
DB='file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro'
H=12*3600*1000
FIJOS=[3.7,4.2,4.7,5.2]
RMULT=[0.5,0.75,1.0,1.5,2.0]
db=sqlite3.connect(DB,uri=True); db.row_factory=sqlite3.Row
db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
now=int(time.time()*1000)
def rows(sql): return [dict(r) for r in db.execute(sql)]
items=[('alert',r['id'],r['symbol'],r['ts_ms'],r['entry'],r['stop_loss']) for r in rows(
  "SELECT id,ts_ms,symbol,entry,stop_loss FROM alertas_emitidas WHERE entry IS NOT NULL AND stop_loss IS NOT NULL")]
items+=[('signal',r['id'],r['symbol'],r['ts_open'],r['entry'],r['stop_loss']) for r in rows(
  "SELECT id,ts_open,symbol,entry,stop_loss FROM signals WHERE entry IS NOT NULL AND stop_loss IS NOT NULL")]
by={}
for it in items: by.setdefault(it[2],[]).append(it)
out={'alert':{},'signal':{},'fijos':FIJOS,'rmult':RMULT,'now':now}
for k,sym in enumerate(sorted(by)):
    g=by[sym]; lo=min(x[3] for x in g); hi=min(now,max(x[3] for x in g)+H)
    T=[];Hh=[]
    for t,h in db.execute("SELECT open_time,h FROM klines WHERE symbol=? AND tf='1m' AND open_time>=? AND open_time<=? ORDER BY open_time",(sym,lo,hi)):
        T.append(t);Hh.append(h)
    for kind,key,_s,ts,E,SL in g:
        if not E or E<=0 or not SL or SL>=E: continue
        a=bisect.bisect_left(T,ts); b=bisect.bisect_right(T,ts+H-60000)
        if b<=a: continue
        Rd=E-SL
        niveles=[E*(1+p/100) for p in FIJOS]+[E+m*Rd for m in RMULT]
        res=[None]*len(niveles)
        pend=set(range(len(niveles)))
        for i in range(a,b):
            if not pend: break
            for j in list(pend):
                if Hh[i]>=niveles[j]: res[j]=T[i]-ts; pend.discard(j)
        out[kind][key]={'fijos':res[:len(FIJOS)],'r':res[len(FIJOS):]}
    print(f'{k+1}/{len(by)} {sym}',file=sys.stderr)
db.rollback(); db.close()
sys.stdout.buffer.write(gzip.compress(json.dumps(out).encode()))
