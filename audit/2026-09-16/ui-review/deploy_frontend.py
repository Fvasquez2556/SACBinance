"""Publish this verified frontend to the existing private server, preserving backend state."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
REVIEW = Path(__file__).resolve().parent
before = json.loads((REVIEW / "remote-before.json").read_text(encoding="utf-8"))
files = {}
for name, previous in before["files"].items():
    local = ROOT / name
    if not local.exists():
        continue
    old_text = base64.b64decode(previous["content"]).decode("utf-8-sig").replace("\r\n", "\n")
    if local.read_text(encoding="utf-8-sig") != old_text:
        files[name] = {"content": base64.b64encode(local.read_bytes()).decode(), "expected": previous["sha256"]}
for path in (ROOT / "frontend/tests").rglob("*.ts"):
    name = path.relative_to(ROOT).as_posix()
    files[name] = {"content": base64.b64encode(path.read_bytes()).decode(), "expected": None}
for path in (ROOT / "frontend/dist").rglob("*"):
    if path.is_file():
        name = path.relative_to(ROOT).as_posix()
        files[name] = {"content": base64.b64encode(path.read_bytes()).decode(), "asset": True}
payload = json.dumps(files)
remote = '''
import base64, datetime, hashlib, json, os, pathlib, subprocess, tempfile
files = json.loads(PAYLOAD)
root = pathlib.Path('/home/flox/sacbinance').resolve()
frontend = (root / 'frontend').resolve()
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
backup = pathlib.Path('/home/flox/.cache/sacbinance-ui-backups') / stamp
for name, item in files.items():
    target = (root / name).resolve()
    assert target.is_relative_to(frontend), name
    if not item.get('asset'):
        actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        assert actual == item['expected'], 'File changed since review: ' + name
# Back up every existing destination before any replacement. Old hashed assets remain available.
backup.mkdir(parents=True, exist_ok=False)
manifest = {}
for name, item in files.items():
    target = (root / name).resolve()
    previous = target.read_bytes() if target.exists() else None
    if previous is not None:
        saved = backup / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(previous)
    manifest[name] = {'before': hashlib.sha256(previous).hexdigest() if previous is not None else None,
                      'after': hashlib.sha256(base64.b64decode(item['content'])).hexdigest()}
(backup / 'manifest.json').write_text(json.dumps(manifest, indent=2))
# HTML is switched last, after all referenced assets are ready.
names = sorted(files, key=lambda name: name == 'frontend/dist/index.html')
for name in names:
    target = (root / name).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = base64.b64decode(files[name]['content'])
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.ui-', delete=False) as temp:
        temp.write(data)
        temp.flush()
        os.fsync(temp.fileno())
        temp_name = temp.name
    os.chmod(temp_name, 0o644)
    os.replace(temp_name, target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == manifest[name]['after']
print(json.dumps({'backup': str(backup), 'files': manifest,
  'service': subprocess.check_output(['systemctl','show','sacbinance','--property=MainPID,ActiveEnterTimestamp,ActiveState'],text=True)}))
'''.replace("PAYLOAD", repr(payload))
result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "flox@100.96.211.5", "python3 -"],
                        input=remote, encoding="utf-8", capture_output=True, check=True)
deployed = json.loads(result.stdout)
(REVIEW / "deployment.json").write_text(json.dumps(deployed, indent=2), encoding="utf-8")
print(json.dumps({"backup": deployed["backup"], "files": list(deployed["files"]), "service": deployed["service"]}, indent=2))
