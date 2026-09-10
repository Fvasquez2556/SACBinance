"""Public Binance OHLCV reference: four requested cases + deterministic sample.
Selection uses symbol identity only, never performance. Source DB is untouched.
"""
import datetime,hashlib,json,pathlib,sqlite3,time,urllib.parse,urllib.request,urllib.error
ROOT=pathlib.Path(__file__).resolve().parent
s=sqlite3.connect((ROOT/'snapshot.db').as_uri()+'?mode=ro',uri=True)
symbols=[x[0] for x in s.execute('SELECT DISTINCT symbol FROM signals ORDER BY symbol')]
cases=['MARSCOINUSDT','ETHFIUSDT','RAYUSDT','IOUSDT']
sample=sorted([x for x in symbols if x not in cases],key=lambda x:hashlib.sha256(('sac-audit-20260910:'+x).encode()).hexdigest())[:24]
cutoff=s.execute("SELECT max(open_time)+60000 FROM klines WHERE tf='1m'").fetchone()[0]
start=s.execute('SELECT min(ts_open) FROM signals').fetchone()[0]//60000*60000
dest=sqlite3.connect(ROOT/'reference.db')
dest.execute('CREATE TABLE IF NOT EXISTS klines(symbol TEXT,tf TEXT,open_time INTEGER,o REAL,h REAL,l REAL,c REAL,v REAL,PRIMARY KEY(symbol,tf,open_time))')
receipt={'provider':'Binance public REST API','endpoint':'https://api.binance.com/api/v3/klines','selection':'Four user-named cases plus first 24 other signal symbols sorted by SHA256(sac-audit-20260910:SYMBOL). No outcome-based selection.','cases':cases,'sample':sample,'start_ms':start,'end_exclusive_ms':cutoff,'requests':[]}
for symbol in cases+sample:
 cursor=start
 count=0
 while cursor<cutoff:
  args={'symbol':symbol,'interval':'1m','startTime':cursor,'endTime':cutoff-1,'limit':1000}
  url=receipt['endpoint']+'?'+urllib.parse.urlencode(args)
  try:
   with urllib.request.urlopen(url,timeout=20) as r: raw=r.read(); rows=json.loads(raw)
  except urllib.error.HTTPError as e:
   receipt['requests'].append({'args':args,'error_http':e.code})
   if e.code in (429,418):raise
   print(symbol,'HTTP',e.code,flush=True);break
  if not rows:break
  dest.executemany('INSERT OR REPLACE INTO klines VALUES(?,?,?,?,?,?,?,?)',[(symbol,'1m',r[0],float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[7])) for r in rows if r[6]<cutoff])
  count+=len(rows)
  receipt['requests'].append({'args':args,'rows':len(rows),'sha256':hashlib.sha256(raw).hexdigest(),'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
  cursor=rows[-1][0]+60000
  time.sleep(.1)
 dest.commit()
 print(symbol,count,flush=True)
 (ROOT/'reference_provenance.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
dest.close()
