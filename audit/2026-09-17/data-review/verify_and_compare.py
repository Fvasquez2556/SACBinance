"""Read-only candle verification and comparison with the preserved 16 September cut."""
import collections
import gzip
import json
import pathlib
import sqlite3
import subprocess

import analyze as a

P = pathlib.Path(__file__).resolve().parent
old = json.loads(gzip.decompress((P.parents[1] / '2026-09-16/data-review/snapshot.json.gz').read_bytes()))
old_results = json.loads((P.parents[1] / '2026-09-16/data-review/results.json').read_text(encoding='utf-8'))
old_q = {r['signal_id']: r for r in old['outcomes'] if r['strategy_version'] == 'f82bcff'
         and not r['sombra'] and r['cerrado'] == 1 and r['ts_open'] <= old['as_of_ms'] - a.DAY
         and (r['cobertura_velas'] or 0) >= .98 and a.valid(r)}
current_q = {r['signal_id']: r for r in a.Q}
new_rows = [r for r in a.Q if r['signal_id'] not in old_q]

runtime = json.loads((P / 'runtime.json').read_text(encoding='utf-8'))
ruptures = runtime['rupturas']
rr = {
    'n': len(ruptures), 'first_utc': a.iso(min(r['ts_open'] for r in ruptures)),
    'last_utc': a.iso(max(r['ts_open'] for r in ruptures)),
    'oldest_minutes': (runtime['as_of_ms'] - min(r['ts_open'] for r in ruptures)) / 60000,
    'closed': sum(bool(r['closed']) for r in ruptures),
    'directions': dict(collections.Counter(r['direction'] for r in ruptures)),
    'returns_populated': {str(h): sum(r['ret_' + str(h) + 'm_pct'] is not None for r in ruptures)
                          for h in [5, 15, 30, 60, 240, 1440]},
    'service': runtime['service'],
}
configs = {}
for cfg in sorted(set(r['config_hash'] for r in a.CURRENT)):
    rows = [r for r in a.CURRENT if r['config_hash'] == cfg and a.mature(r)]
    configs[cfg] = {'mature': len(rows), 'cov98': sum((r['cobertura_velas'] or 0) >= .98 for r in rows)}

comparison = {
    'counts_delta': {k: len(a.D[k]) - len(old[k]) for k in ['outcomes', 'signals', 'alerts']},
    'newly_eligible': a.summary(new_rows),
    'removed_eligible_ids': sorted(set(old_q) - set(current_q)),
    'common_goal_labels_changed': sum(a.goal(old_q[s]) != a.goal(current_q[s]) for s in set(old_q) & set(current_q)),
    'previous_cut': old_results['clean_current'],
    'ruptures': rr, 'config_coverage': configs,
}
(P / 'comparison.json').write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding='utf-8')
print('COMPARISON', json.dumps(comparison, ensure_ascii=False), flush=True)

if not (P / 'path-check.json').exists():
    rows = [{k: r[k] for k in ['signal_id', 'ts_open', 'symbol', 'entry', 'take_profit', 'stop_loss']}
            for r in a.CURRENT if a.mature(r) and not r['sombra'] and a.valid(r)]
    code = (P / 'verify_paths.py').read_text(encoding='utf-8').replace(
        'rows=json.loads(sys.stdin.readline())', 'rows=json.loads(' + repr(json.dumps(rows)) + ')')
    run = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                          'flox@100.96.211.5', 'python3 -'],
                         input=code, text=True, capture_output=True, timeout=120, check=True)
    parsed = json.loads(run.stdout)
    (P / 'path-check.json').write_text(json.dumps(parsed, indent=2), encoding='utf-8')

replay = json.loads((P / 'path-check.json').read_text(encoding='utf-8'))
by_id = {r['signal_id']: r for r in replay['rows']}
def replay_goal(r):
    return r['goal'] is not None and (r['sl'] is None or r['goal'] < r['sl'])
changed = [r['signal_id'] for r in a.Q if a.goal(r) != replay_goal(by_id[r['signal_id']])]
confirmed_before_gap = sum(replay_goal(by_id[r['signal_id']]) and
    (by_id[r['signal_id']]['first_gap_ms'] is None or by_id[r['signal_id']]['goal'] < by_id[r['signal_id']]['first_gap_ms']) for r in a.Q)

# Independent SQL expression on the same snapshot verifies inclusion and core counts.
db = sqlite3.connect(':memory:')
fields = ['strategy_version','sombra','cerrado','ts_open','cobertura_velas','ms_up_32','ms_sl','ms_tp','ms_mfe','ms_mae','tp_pct']
db.execute('CREATE TABLE outcomes (' + ','.join(fields) + ')')
db.executemany('INSERT INTO outcomes VALUES (' + ','.join('?' for _ in fields) + ')',
               [tuple(r[k] for k in fields) for r in a.O])
sql = """SELECT COUNT(*),SUM(ms_up_32 IS NOT NULL),
SUM(ms_up_32 IS NOT NULL AND (ms_sl IS NULL OR ms_up_32<ms_sl)),
SUM(ms_up_32 IS NOT NULL AND ms_sl IS NOT NULL AND ms_up_32>ms_sl),SUM(tp_pct<3.2)
FROM outcomes WHERE strategy_version='f82bcff' AND sombra=0 AND cerrado=1
AND ts_open<=? AND cobertura_velas>=.98"""
sql += ''.join(' AND (' + k + ' IS NULL OR ' + k + ' BETWEEN 0 AND 86400000)' for k in fields[5:10])
totals = db.execute(sql, (a.NOW-a.DAY,)).fetchone()
expected = tuple(a.result['clean_current'][k] for k in ['n','touch32_n','goal_before_sl_n','goal_after_sl_n','plan_tp_below32_n'])
assert totals == expected, (totals, expected)
verification = {
    'paths_replayed': len(by_id), 'complete_raw_paths': sum(r['n'] == r['expected'] for r in by_id.values()),
    'analysis_paths': len(a.Q),
    'analysis_complete_raw_paths': sum(by_id[r['signal_id']]['n'] == by_id[r['signal_id']]['expected'] for r in a.Q),
    'analysis_goal_labels_changed': len(changed), 'changed_ids': changed,
    'analysis_confirmed_goal_before_gap': confirmed_before_gap,
    'tracker_lowcoverage_but_raw_complete': sum((r['cobertura_velas'] or 0) < .98 and
        by_id[r['signal_id']]['n'] == by_id[r['signal_id']]['expected'] for r in a.CURRENT if r['signal_id'] in by_id),
    'independent_sql_totals': totals, 'sql': sql,
}
(P / 'verification.json').write_text(json.dumps(verification, indent=2), encoding='utf-8')
print('VERIFICATION', json.dumps(verification), flush=True)
