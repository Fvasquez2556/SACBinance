"""Read-only audit of the captured SQLite database; no application imports/writes."""
from pathlib import Path
import bisect
import collections
import datetime as dt
import json
import sqlite3

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'snapshot.db'
conn = sqlite3.connect(DB.as_uri() + '?mode=ro&immutable=1', uri=True)
conn.row_factory = sqlite3.Row
queries = {}

def query(name, sql, args=()):
    queries[name] = {'sql': sql, 'parameters': args}
    return [dict(row) for row in conn.execute(sql, args)]

report = {'snapshot': json.loads((ROOT / 'provenance.json').read_text('utf-8'))}
report['schema_version'] = query('schema_version', 'SELECT * FROM schema_meta')
report['outcome_cohorts'] = query('outcome_cohorts', '''SELECT strategy_version,
    count(*) n, sum(cerrado=1) closed, sum(sombra=1) shadow,
    min(ts_open) first_entry_ms, max(ts_open) last_entry_ms,
    sum(cobertura_velas IS NOT NULL) with_coverage,
    sum(cobertura_velas>=0.95 AND cerrado=1) closed_coverage_ge_95pct,
    sum(ms_up_32 IS NOT NULL) ever_32,
    sum(ms_up_32 IS NOT NULL AND (ms_sl IS NULL OR ms_up_32<ms_sl)) raw_32_before_sl,
    sum(ms_up_32 IS NOT NULL AND ms_up_32=ms_sl) same_bar_32_sl,
    sum(stop_loss IS NOT NULL) with_sl
    FROM outcomes GROUP BY strategy_version ORDER BY first_entry_ms''')
report['states'] = query('states', '''SELECT taxonomia, display_state, sombra,
    count(*) n FROM outcomes GROUP BY 1,2,3 ORDER BY n DESC''')
report['alert_profiles'] = query('alert_profiles', '''SELECT display_state,
    count(*) n, sum(signal_id IS NULL) without_signal FROM alertas_emitidas
    GROUP BY 1''')
report['profile_logs'] = query('profile_logs', '''SELECT level, count(*) n
    FROM analysis_log WHERE level IN ('TENDENCIA','IGNICION','BASE') GROUP BY level''')
report['kline_ranges'] = query('kline_ranges', '''SELECT tf, count(*) n,
    count(DISTINCT symbol) symbols, min(open_time) first_ms, max(open_time) last_ms
    FROM klines GROUP BY tf''')
report['outcome_quality'] = query('outcome_quality', '''SELECT cerrado, count(*) n,
    min(n_velas) min_bars, max(n_velas) max_bars,
    sum(n_velas=0) zero_bars, sum(n_velas>1440) over_1440_bars,
    min(cobertura_velas) min_coverage, max(cobertura_velas) max_coverage,
    sum(ms_tp=ms_sl) same_bar_plan_tp_sl,
    sum(ms_mfe>86400000 OR ms_mae>86400000) extrema_after_24h
    FROM outcomes GROUP BY cerrado''')
cols = [r[1] for r in conn.execute('PRAGMA table_info(outcomes)')]
features = ['drawdown_pct','sigma_pct','atr_pct','atr_percentile','vol_ratio',
    'rsi5','rsi14_1m','rsi14_15m','macd_hist_15m','dist_soporte_pct',
    'dist_resistencia_pct','retro_caida_pct','retro_rebote_pct','retro_confirmado',
    'btc_regime','strategy_version','config_hash','cobertura_velas']
report['feature_coverage'] = {col: query('nonnull_'+col,
    f'SELECT count(*) n, count({col}) non_null FROM outcomes')[0]
    for col in features}
report['absent_outcome_columns'] = [c for c in ['grupo_vol','vol_previa_pct',
    'horizonte','horizon_min','swing_high','swing_low','swing_high_ts',
    'swing_low_ts','grind_r2','grind_slope','compression_state'] if c not in cols]
times = collections.defaultdict(list)
for sym, timestamp in conn.execute("SELECT symbol, open_time FROM klines WHERE tf='1m' ORDER BY symbol, open_time"):
    times[sym].append(timestamp)
snapshot_time = int(dt.datetime.fromisoformat(report['snapshot']['finished_utc']).timestamp()*1000)
outcome_rows = query('outcome_entries', 'SELECT signal_id,symbol,ts_open FROM outcomes')
report['reconstructability'] = []
for minutes in [15,30,60,120,240,360,480,1440]:
    mature = complete = absent = 0
    coverage = []
    for row in outcome_rows:
        start = row['ts_open']
        end = start + minutes*60000
        if end > snapshot_time:
            continue
        mature += 1
        # Conservative: only entire 1m candles after the recorded entry and
        # fully closed before horizon. Excludes uncertain boundary fragments.
        first = ((start+59999)//60000)*60000
        last = ((end-60000)//60000)*60000
        expected = max(0, (last-first)//60000+1)
        seq = times[row['symbol']]
        observed = bisect.bisect_right(seq,last)-bisect.bisect_left(seq,first)
        complete += int(observed==expected and expected>0)
        absent += int(observed==0)
        coverage.append(observed/expected if expected else 0)
    report['reconstructability'].append({'horizon_min':minutes,'mature_rows':mature,
        'all_full_1m_bars_present':complete,'no_bars':absent,
        'mean_bar_coverage':sum(coverage)/len(coverage) if coverage else None})
report['local_database_schemas'] = []
for path in [Path('D:/SACBinance/data/sacbinance.db'),
             Path('D:/SACBinance/data/sacbinance_2026-09-10.db'),
             Path('D:/SACBinance/backend/data/sacbinance.db')]:
    if not path.exists():
        continue
    other = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    tables = [r[0] for r in other.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    report['local_database_schemas'].append({'path':str(path),'tables':tables,
        'has_labels': 'labels' in tables})
    other.close()
conn.close()
# Entries were used only to calculate coverage; retain a compact artifact.
report.pop('outcome_entries',None)
(ROOT/'inspection.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),'utf-8')
(ROOT/'queries.json').write_text(json.dumps(queries,indent=2,ensure_ascii=False),'utf-8')
summary = {k:v for k,v in report.items() if k not in ('snapshot','states','feature_coverage')}
print(json.dumps(summary,indent=2,ensure_ascii=False))
