"""Read-only production snapshot over SSH; no source/server file modifications."""
import datetime, hashlib, json, pathlib, shlex, sqlite3, subprocess, tarfile

ROOT = pathlib.Path(__file__).resolve().parent
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'flox@100.96.211.5']

def remote(command):
    return subprocess.check_output(SSH + [command], timeout=180)

started = datetime.datetime.now(datetime.timezone.utc).isoformat()
revision = remote('git -C ~/sacbinance rev-parse HEAD').decode().strip()
status = remote('git -C ~/sacbinance status --porcelain').decode()
code = "import sqlite3,sys; s=sqlite3.connect('file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro',uri=True); d=sqlite3.connect(':memory:'); s.backup(d,pages=256,sleep=0.01); sys.stdout.buffer.write(d.serialize()); d.close(); s.close()"
db = ROOT / 'snapshot.db'
with db.open('wb') as out:
    subprocess.run(SSH + ['python3 -c ' + shlex.quote(code)], stdout=out, check=True, timeout=180)
with (ROOT / 'production.tar').open('wb') as out:
    subprocess.run(SSH + ['git -C ~/sacbinance archive HEAD'], stdout=out, check=True, timeout=90)
with tarfile.open(ROOT / 'production.tar') as archive:
    archive.extractall(ROOT / 'production', filter='data')
conn = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
integrity = conn.execute('pragma integrity_check').fetchall()
schema = conn.execute("select name,sql from sqlite_master where type='table' order by name").fetchall()
profile = []
for name, sql in schema:
    safe = name.replace('"', '""')
    profile.append({'table': name, 'rows': conn.execute(f'SELECT COUNT(*) FROM "{safe}"').fetchone()[0], 'sql': sql})
metadata = {'source':'flox@100.96.211.5:/home/flox/sacbinance/backend/data/sacbinance.db', 'started_utc': started, 'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'commit': revision, 'working_tree_status': status, 'size_bytes': db.stat().st_size, 'sha256': hashlib.sha256(db.read_bytes()).hexdigest(), 'integrity_check': integrity, 'tables':profile}
(ROOT / 'provenance.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
print(json.dumps(metadata,indent=2))
