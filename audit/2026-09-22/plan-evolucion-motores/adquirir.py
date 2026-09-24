"""Save one bounded, read-only production snapshot and local code manifest."""
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BASE=Path(__file__).resolve().parent
REPO=BASE.parents[2]
DATA=BASE/'datos'
DATA.mkdir(exist_ok=True)
target=DATA/'snapshot.json.gz'
if target.exists():
    raise SystemExit('Snapshot already exists. Use another dated package; do not overwrite evidence.')
script=BASE/'remote_export.py'
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','sac','python3','-'],input=script.read_bytes(),capture_output=True,timeout=180)
if result.returncode:
    sys.stderr.buffer.write(result.stderr)
    raise SystemExit(result.returncode)
d=json.loads(gzip.decompress(result.stdout))
target.write_bytes(result.stdout)
local_hashes={f:hashlib.sha256((REPO/f).read_bytes()).hexdigest() for f in d['remote_file_sha256'] if (REPO/f).exists()}
manifest={'captured_local_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'snapshot_utc':d['snapshot_utc'],'snapshot_sha256':hashlib.sha256(result.stdout).hexdigest(),'exporter_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),'totals':d['totals'],'schema_version':d['schema_version'],'remote_head':d['remote_head'],'local_head':subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,capture_output=True,text=True).stdout.strip(),'service':d['service'],'remote_file_sha256':d['remote_file_sha256'],'local_file_sha256':local_hashes,'different_local_remote':[f for f in local_hashes if local_hashes[f]!=d['remote_file_sha256'][f]],'local_status':subprocess.run(['git','status','--short'],cwd=REPO,capture_output=True,text=True).stdout.splitlines()}
(DATA/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'snapshot_utc':d['snapshot_utc'],'bytes':len(result.stdout),'totals':d['totals'],'sent_paths':len(d['sent_paths_1m']),'schema':d['schema_version'],'different_local_remote':manifest['different_local_remote']},ensure_ascii=False))
