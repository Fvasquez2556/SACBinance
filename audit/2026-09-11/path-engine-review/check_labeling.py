"""Small synthetic reproductions of limits in the existing offline labeler.

No strategy changes, network requests, or production database writes.
"""
from pathlib import Path
import json
import sqlite3
import sys
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2]))
from research.labeling import Serie, SCHEMA_LABELS, calcular_features, triple_barrera, cargar

def series(highs, lows, times=None):
    n = len(highs)
    return Serie(t=np.arange(n)*60000 if times is None else np.array(times),
        o=np.full(n,100.), h=np.array(highs,dtype=float), l=np.array(lows,dtype=float),
        c=np.full(n,100.), v=np.full(n,100.), n=n)

def evaluate(s, horizon):
    return triple_barrera(s,np.array([0]),np.array([3.2]),np.array([2.]),horizon)

results = {}
db = sqlite3.connect(':memory:')
db.executescript(SCHEMA_LABELS)
sql = 'INSERT OR REPLACE INTO labels(symbol,interval,t0,precio_e,horizonte,tp_pct,sl_pct) VALUES(?,?,?,?,?,?,?)'
db.execute(sql,('TESTUSDT','1m',0,100,240,3.2,2))
db.execute(sql,('TESTUSDT','1m',0,100,480,3.2,2))
rows = db.execute('SELECT horizonte FROM labels').fetchall()
assert rows == [(480,)]
results['horizon_overwrite'] = {'horizons_written_bars':[240,480],'horizons_retained_bars':[r[0] for r in rows]}
db.close()

n = 5000
a = series(np.full(n,101.),np.full(n,99.))
b = series(np.full(n,101.),np.full(n,99.))
atr_a = np.ones(n); atr_b = atr_a.copy()
# First 101 observations are identical; modify only strictly later data.
atr_b[200:500] = 5
b.v[150:200] = 500
fa = calcular_features(a,atr_a,60,None)
fb = calcular_features(b,atr_b,60,None)
assert fa['f_atr_rel'][100] != fb['f_atr_rel'][100]
assert fa['f_vol_rel'][100] != fb['f_vol_rel'][100]
results['future_leak_at_index_100'] = {
    'identical_history_through_index':100,
    'atr_relative_original':float(fa['f_atr_rel'][100]),
    'atr_relative_after_future_change':float(fb['f_atr_rel'][100]),
    'volume_relative_original':float(fa['f_vol_rel'][100]),
    'volume_relative_after_future_change':float(fb['f_vol_rel'][100])}

s = series([100,101,105],[100,97,99])
r = evaluate(s,2)
assert int(r['etiqueta'][0]) == -1 and np.isclose(r['mfe'][0],1)
results['mfe_definition_after_sl'] = {'label':int(r['etiqueta'][0]),
    'mfe_until_exit_pct':float(r['mfe'][0]),
    'mfe_full_horizon_pct':float((s.h[1:].max()/s.c[0]-1)*100),
    'bars_until_tp_despite_sl_first':int(r['velas_tp'][0])}

r = evaluate(series([100,104],[100,97]),1)
assert int(r['etiqueta'][0]) == -1 and int(r['ambiguo'][0]) == 1
results['same_candle_tie'] = {'label':int(r['etiqueta'][0]),'ambiguous':int(r['ambiguo'][0])}

s = series([100,101,104],[100,99,99],times=[0,60000,3600000])
r = evaluate(s,2)
assert int(r['etiqueta'][0]) == 1
results['bar_count_is_not_elapsed_time'] = {'requested_bars':2,
    'declared_interval_min':1,'tp_bar_open_minutes_after_entry_bar_open':
        int(s.t[int(r['t1_idx'][0])]-s.t[0])//60000,'label':int(r['etiqueta'][0])}

db = sqlite3.connect((ROOT/'snapshot.db').as_uri()+'?mode=ro&immutable=1',uri=True)
try:
    cargar(db,'BTCUSDT','1m')
except sqlite3.OperationalError as exc:
    results['production_schema_adapter_required'] = str(exc)
else:
    raise AssertionError('Expected incompatible column names to require an adapter')
finally:
    db.close()

(ROOT/'labeling_checks.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),'utf-8')
print(json.dumps(results,indent=2,ensure_ascii=False))
