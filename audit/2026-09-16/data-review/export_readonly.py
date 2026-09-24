import sqlite3, pathlib, json, time, gzip, sys

path = pathlib.Path('/home/flox/sacbinance/backend/data/sacbinance.db')
db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
db.execute('PRAGMA query_only=ON')
db.execute('BEGIN')
now = int(time.time() * 1000)
def rows(sql):
    return [dict(r) for r in db.execute(sql)]

result = {
    'source': str(path), 'as_of_ms': now, 'schema': rows('SELECT * FROM schema_meta'),
    'outcomes': rows('SELECT * FROM outcomes ORDER BY ts_open,signal_id'),
    'signals': rows('SELECT * FROM signals ORDER BY ts_open,id'),
    'alerts': rows('SELECT id,ts_ms,symbol,signal_id,entry,take_profit,stop_loss,tp_pct,sl_pct,reward_neto_pct,objetivo_alcanzable,tier,score,display_state,senal_n,telegram,strategy_version,config_hash FROM alertas_emitidas ORDER BY ts_ms,id'),
    'klines': rows('SELECT tf,COUNT(*) n,COUNT(DISTINCT symbol) symbols,MIN(open_time) first_ms,MAX(open_time) last_ms FROM klines GROUP BY tf'),
    'state_span': rows('SELECT COUNT(*) n,MIN(ts_ms) first_ms,MAX(ts_ms) last_ms FROM symbol_states'),
    'log_levels': rows('SELECT level,COUNT(*) n,MIN(ts_ms) first_ms,MAX(ts_ms) last_ms FROM analysis_log GROUP BY level'),
}
db.rollback()
db.close()
sys.stdout.buffer.write(gzip.compress(json.dumps(result,ensure_ascii=False).encode('utf-8')))
