"""Read-only deployment verification; no Telegram requests."""
import hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
files=json.loads((HERE/'install-result.json').read_text())['files']
payload={rel:hashlib.sha256((ROOT/rel).read_bytes()).hexdigest() for rel in files}
code='expected='+repr(payload)+'\n'+r'''
import hashlib,json,pathlib,sqlite3,subprocess,urllib.request
root=pathlib.Path('/home/flox/sacbinance')
conn=sqlite3.connect('file:'+str(root/'backend/data/sacbinance.db')+'?mode=ro',uri=True)
version=conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0]
tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'notificacion_%' AND type='table'")]
conn.close()
try:
    with urllib.request.urlopen('http://127.0.0.1:8000/api/status',timeout=15) as response:
        health={'http':response.status,'payload':json.load(response)}
except Exception as exc:health={'error':str(exc)}
service=subprocess.run(['systemctl','show','sacbinance','--property=ActiveState,MainPID,ActiveEnterTimestamp'],capture_output=True,text=True).stdout
print(json.dumps({'files_match':all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in expected.items()),
    'schema_version':version,'notification_tables':tables,'service':service,'health':health}))
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','sac','python3 -'],input=code.encode(),capture_output=True)
if result.returncode:
    print(result.stderr.decode(errors='replace'));raise SystemExit(result.returncode)
data=json.loads(result.stdout)
(HERE/'verification.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(data,ensure_ascii=True))
