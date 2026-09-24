"""Read-only event trace for COTIUSDT; run on the Ubuntu host over SSH."""
import datetime as dt
import json
import re
import sqlite3
import time

db = sqlite3.connect('file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro', uri=True)
db.row_factory = sqlite3.Row
db.execute('PRAGMA query_only=ON')
db.execute('BEGIN')
start = int(dt.datetime(2026, 9, 16, tzinfo=dt.timezone.utc).timestamp()*1000)
symbol = 'COTIUSDT'
def rows(sql, args=()):
    return [dict(r) for r in db.execute(sql,args)]

queries = {
    'alerts': ('SELECT * FROM alertas_emitidas WHERE symbol=? ORDER BY ts_ms', (symbol,)),
    'signals': ('SELECT * FROM signals WHERE symbol=? AND ts_open>=? ORDER BY ts_open', (symbol,start)),
    'outcomes': ('SELECT * FROM outcomes WHERE symbol=? AND ts_open>=? ORDER BY ts_open', (symbol,start)),
    'rupturas': ('SELECT * FROM rupturas WHERE symbol=? ORDER BY ts_open', (symbol,)),
    'rupturas_tf': ('SELECT * FROM rupturas_tf WHERE symbol=? ORDER BY ts_open', (symbol,)),
    'log': ('SELECT * FROM analysis_log WHERE symbol=? AND ts_ms>=? ORDER BY ts_ms', (symbol,start)),
    'states': ('SELECT * FROM symbol_states WHERE symbol=? AND ts_ms>=? ORDER BY ts_ms', (symbol,start)),
    'candles_15m': ("SELECT * FROM klines WHERE symbol=? AND tf='15m' AND open_time>=? ORDER BY open_time", (symbol,start)),
    'log_span': ('SELECT min(ts_ms) first_ms,max(ts_ms) last_ms,count(*) n FROM analysis_log',()),
    'all_ruptures_delivery': ('SELECT direction,telegram,count(*) n,min(ts_open) first_ms,max(ts_open) last_ms FROM rupturas GROUP BY direction,telegram',()),
}
out = {'as_of_ms':int(time.time()*1000),'since_ms':start,'symbol':symbol,
       'queries':{k:x[0] for k,x in queries.items()}}
for k,(sql,args) in queries.items():
    out[k] = rows(sql,args)
db.rollback()
db.close()
payload = json.dumps(out,ensure_ascii=False)
payload = re.sub(r'https://api\.telegram\.org/bot[^/\s"\\]+','https://api.telegram.org/bot[REDACTED]',payload)
payload = re.sub(r'\d{6,}:[A-Za-z0-9_-]{20,}','[REDACTED]',payload)
print(payload)
