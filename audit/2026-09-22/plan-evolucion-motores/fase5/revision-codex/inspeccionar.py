"""Inventario remoto de solo lectura; no importa ni arranca la aplicacion."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[4]
REMOTE = r'''
import pathlib, hashlib, json, sqlite3, datetime, subprocess, urllib.request
root = pathlib.Path('/home/flox/sacbinance')
out = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'files': {}}
names = ['backend/main.py', 'backend/src/state/engine.py', 'backend/src/persistence/db.py', 'backend/src/config/settings.py', 'backend/tests/test_experimentos.py', 'backend/src/evaluacion/recorrido.py']
names += ['backend/src/experimentos/' + n for n in ('__init__.py', 'registro.py', 'almacen.py')]
for name in names:
    p = root / name
    if p.exists():
        b = p.read_bytes()
        out['files'][name] = {'sha256': hashlib.sha256(b).hexdigest(), 'normalized': hashlib.sha256(b.replace(b'\r\n', b'\n')).hexdigest(), 'mtime_utc': datetime.datetime.fromtimestamp(p.stat().st_mtime, datetime.timezone.utc).isoformat()}
    else:
        out['files'][name] = {'missing': True}
out['service'] = subprocess.check_output(['systemctl', 'show', 'sacbinance', '--property=ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp'], text=True)
try:
    with urllib.request.urlopen('http://127.0.0.1:8000/api/status', timeout=10) as r:
        body = json.load(r)
        out['http'] = {'status': r.status, 'pairs_count': body.get('pairs_count'), 'state': body.get('state')}
except Exception as exc:
    out['http'] = {'error': str(exc)}
db = sqlite3.connect('file:' + str(root/'backend/data/sacbinance.db') + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
db.execute('PRAGMA query_only=ON')
db.execute('BEGIN')
def q(sql, params=()):
    return [dict(r) for r in db.execute(sql, params)]
out['schema'] = q('SELECT * FROM schema_meta')
out['experiment_tables'] = q("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'experimento_%'")
if len(out['experiment_tables']) == 2:
    out['registry'] = q('SELECT * FROM experimento_registro')
    out['results'] = q('SELECT politica, huella, COUNT(*) n, MIN(ts_evaluado) first_eval, MAX(ts_evaluado) last_eval FROM experimento_resultados GROUP BY politica,huella')
    out['new_plans'] = q('SELECT e.huella, COUNT(p.plan_id) n, MIN(p.ts_creado) first_created, MIN(p.ts_creado+p.horizonte_ms) first_due FROM experimento_registro e LEFT JOIN planes p ON p.ts_creado>=e.ts_congelado GROUP BY e.huella')
db.rollback()
out['flags_explicit_in_env'] = {}
for line in (root/'backend/.env').read_text().splitlines():
    k, sep, v = line.partition('=')
    if sep and k.strip().lower().startswith('experimentos_'):
        out['flags_explicit_in_env'][k.strip()] = v.strip()
log = root/'logs/sacbinance.log'
if log.exists():
    with log.open('rb') as f:
        f.seek(max(0, log.stat().st_size - 3000000))
        tail = f.read().decode('utf8', errors='replace')
    out['experiment_log'] = [l for l in tail.splitlines() if 'Experimentos de la fase 5:' in l or 'experimentos error:' in l][-10:]
print(json.dumps(out))
'''

proc = subprocess.run(['ssh', '-o', 'BatchMode=yes', 'sac',
                       '/home/flox/sacbinance/backend/venv/bin/python', '-B', '-'],
                      input=REMOTE, text=True, encoding='utf8', capture_output=True, timeout=60)
if proc.returncode:
    raise RuntimeError(proc.stderr)
out = json.loads(proc.stdout)
out['comparison'] = {'matching': [], 'different': [], 'missing_remote': []}
for name, remote in out['files'].items():
    b = (ROOT/name).read_bytes()
    remote['local_sha256'] = hashlib.sha256(b).hexdigest()
    if remote.get('missing'):
        out['comparison']['missing_remote'].append(name)
    elif hashlib.sha256(b.replace(b'\r\n', b'\n')).hexdigest() == remote['normalized']:
        out['comparison']['matching'].append(name)
    else:
        out['comparison']['different'].append(name)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
target = BASE / ('estado-' + stamp + '.json')
target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf8')
print(json.dumps({k: v for k, v in out.items() if k != 'files'}, ensure_ascii=False, indent=2))
print(target)
