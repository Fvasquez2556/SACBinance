"""Read-only evidence export. Run through adquirir.py; stdout is gzip JSON.

No imports from the live application, no SQLite writes, no Telegram requests.
"""
import bisect
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path('/home/flox/sacbinance')
DB = 'file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro'
db = sqlite3.connect(DB, uri=True, timeout=15)
db.row_factory = sqlite3.Row
db.execute('PRAGMA query_only=ON')
db.execute('BEGIN')

def rows(sql, params=()):
    return [dict(r) for r in db.execute(sql, params)]

now = int(time.time() * 1000)
sent = rows("SELECT * FROM alertas_emitidas WHERE telegram='enviado' ORDER BY ts_ms,id")
since = min(r['ts_ms'] for r in sent)
alerts = rows('SELECT * FROM alertas_emitidas WHERE ts_ms>=? ORDER BY ts_ms,id', (since,))
plans = rows('SELECT alerta_id,symbol,signal_id,ts_open,ts_activado,entry,take_profit,stop_loss,contexto,estado,meta,cerca_sl,last_candle,last_price,mfe,mae FROM notificacion_planes')
outcome_fields = 'signal_id,symbol,ts_open,cerrado,sombra,senal_n,config_hash,strategy_version,cobertura_velas,btc_regime,taxonomia,grupo_vol,vol_previa_pct,atr_pct,rango_1h_pct,ruido_1m_pct,score,display_state,retro_confirmado,consumido_pct,vol_ratio,vol_24h,flow_disponible,ms_up_32,ms_up_42,ms_up_5,ms_sl,ms_tp,mfe_pct,mae_pct'
outcomes = rows('SELECT '+outcome_fields+' FROM outcomes WHERE ts_open>=?', (since,))
plan_by_id = {p['alerta_id']: p for p in plans}
by_symbol = {}
for a in sent:
    by_symbol.setdefault(a['symbol'], []).append(a)
paths = {}
for sym, records in sorted(by_symbol.items()):
    lo = min(a['ts_ms'] for a in records)
    hi = min(now - 60000, max(max(a['ts_ms'], plan_by_id.get(a['id'], {}).get('ts_activado', a['ts_ms'])) for a in records) + 86400000 - 60000)
    bars = [list(r) for r in db.execute("SELECT open_time,h,l,c FROM klines WHERE symbol=? AND tf='1m' AND open_time>=? AND open_time<=? ORDER BY open_time", (sym, lo, hi))]
    times = [r[0] for r in bars]
    for a in records:
        end = min(now, max(a['ts_ms'], plan_by_id.get(a['id'], {}).get('ts_activado', a['ts_ms'])) + 86400000)
        first = bisect.bisect_left(times, a['ts_ms'])
        last = bisect.bisect_right(times, end - 60000)
        paths[str(a['id'])] = bars[first:last]

totals = {}
for table in ('signals','outcomes','alertas_emitidas','rupturas','rupturas_tf','notificacion_planes','notificacion_eventos'):
    totals[table] = db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
directional = {}
for table in ('rupturas','rupturas_tf'):
    group = 'tf,direction' if table == 'rupturas_tf' else 'direction'
    extra = ',SUM(plan_valid) AS plan_valid,SUM(ms_fill IS NOT NULL) AS fills,SUM(ms_tp IS NOT NULL AND (ms_sl IS NULL OR ms_tp<ms_sl)) AS tp_first_all_rows,SUM(ms_tp=ms_sl AND ms_tp IS NOT NULL) AS ambiguous_barriers' if table == 'rupturas_tf' else ''
    directional[table] = rows('SELECT '+group+',COUNT(*) AS n,SUM(closed) AS closed,MIN(ts_open) AS first_ms,MAX(ts_open) AS last_ms,AVG(n_velas) AS mean_bars'+extra+' FROM '+table+' GROUP BY '+group)
    directional[table+'_schema'] = rows('PRAGMA table_info('+table+')')
schemas = rows("SELECT name FROM sqlite_master WHERE type='table'")
schema_version = rows("SELECT value FROM schema_meta WHERE key='version'")
file_names = ['backend/main.py','backend/src/state/engine.py','backend/src/state/active_alert.py','backend/src/config/settings.py','backend/src/persistence/db.py','backend/src/analysis/ruptures.py','backend/src/analysis/rupture_tracker.py','backend/src/analysis/tf_rupture.py','backend/src/analysis/tf_rupture_tracker.py','backend/src/analysis/pair_report.py','backend/src/analysis/trade_levels.py','backend/src/analysis/signal_tracker.py','backend/src/analysis/outcome_tracker.py','backend/src/notify/policy.py','backend/src/notify/service.py','backend/src/api/routes.py','frontend/src/components/SignalStats.tsx','frontend/src/domain/analysis.ts']
hashes = {f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in file_names if (ROOT/f).exists()}
service = subprocess.run(['systemctl','show','sacbinance','--property=ActiveState','--property=MainPID','--property=ActiveEnterTimestamp'],capture_output=True,text=True).stdout.strip()
head = subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
export = {'snapshot_ms': now, 'snapshot_utc': datetime.datetime.fromtimestamp(now/1000,datetime.timezone.utc).isoformat(), 'source': DB, 'mode': 'read-only transaction', 'schema_version': schema_version, 'totals': totals,'tables':[r['name'] for r in schemas], 'remote_head':head,'service':service,'remote_file_sha256':hashes,'alerts':alerts,'plans':plans,'outcomes':outcomes,'sent_paths_1m':paths,'directional':directional,'candles_columns':['open_time','high','low','close'],'clock_anchor':'alert.ts_ms; notified plan ts_activado exported separately'}
db.rollback()
db.close()
sys.stdout.buffer.write(gzip.compress(json.dumps(export,ensure_ascii=False,separators=(',',':')).encode('utf8')))
