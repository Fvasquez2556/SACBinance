"""Preserve only the remote source files that differ from this workspace."""
import hashlib
import json
from pathlib import Path
import subprocess

BASE=Path(__file__).resolve().parent
m=json.loads((BASE/'datos/manifest.json').read_text(encoding='utf8'))
files=m['different_local_remote']
remote="from pathlib import Path\nimport json\nroot=Path('/home/flox/sacbinance')\nfiles="+repr(files)+"\nprint(json.dumps({f:(root/f).read_text() for f in files}))\n"
p=subprocess.run(['ssh','-o','BatchMode=yes','sac','python3','-'],input=remote.encode(),capture_output=True,timeout=30,check=True)
data=json.loads(p.stdout)
for f,content in data.items():
    encoded=content.encode()
    assert hashlib.sha256(encoded).hexdigest()==m['remote_file_sha256'][f],f+' changed during review'
    target=BASE/'datos/remoto'/f
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(encoded)
print(json.dumps({'saved':list(data)}))
