"""Narrow, hash-guarded deployment; never copies credentials or unrelated WIP."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
FILES = [
    'backend/main.py', 'backend/src/config/settings.py',
    'backend/src/persistence/db.py', 'backend/src/notify/telegram.py',
    'backend/src/state/engine.py', 'backend/src/notify/policy.py',
    'backend/src/notify/service.py', 'backend/tests/test_notification_policy.py',
]
BASELINE = json.loads((HERE/'remote-before.json').read_text(encoding='utf-8'))

REMOTE = r'''
import base64, hashlib, json, os, pathlib, shutil, sqlite3, subprocess, sys, time
root = pathlib.Path('/home/flox/sacbinance')
work = pathlib.Path('/home/flox/.cache/sacbinance-notification-deploy') / request['name']
def checked(base, rel):
    p = (base/rel).resolve()
    if not p.is_relative_to(base.resolve()):
        raise RuntimeError('Path outside intended directory')
    return p
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def check_old():
    for rel, item in request['files'].items():
        if digest(checked(root,rel)) != item['before']:
            raise RuntimeError('Server changed since baseline: '+rel)
if request['mode']=='stage':
    check_old()
    work.mkdir(parents=True,exist_ok=False)
    stage = work/'stage'
    for rel in ('backend/src','backend/tests'):
        if (root/rel).exists():
            shutil.copytree(root/rel,stage/rel,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copy2(root/'backend/main.py',stage/'backend/main.py')
    for rel,item in request['files'].items():
        p=checked(stage,rel)
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(base64.b64decode(item['content']))
    python=str(root/'backend/venv/bin/python')
    runner="import logging,unittest; logging.disable(logging.CRITICAL); r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests')); raise SystemExit(not r.wasSuccessful())"
    result=subprocess.run([python,'-c',runner],cwd=stage/'backend',capture_output=True,text=True,timeout=180)
    log=result.stdout+result.stderr
    (work/'tests.txt').write_text(log)
    compile_result=subprocess.run([python,'-m','py_compile',*[str(stage/rel) for rel in request['files']]],capture_output=True,text=True)
    (work/'manifest.json').write_text(json.dumps(request,indent=2))
    ok=result.returncode==0 and compile_result.returncode==0
    if ok: (work/'TESTS_OK').write_text(str(time.time()))
    print(json.dumps({'ok':ok,'work':str(work),'tests':log,'compile':compile_result.stderr}))
elif request['mode']=='install':
    manifest=json.loads((work/'manifest.json').read_text())
    if manifest['files']!=request['files'] or not (work/'TESTS_OK').exists():
        raise RuntimeError('Install payload does not match tested stage')
    check_old()
    backup=work/'backup'
    backup.mkdir(exist_ok=False)
    for rel,item in request['files'].items():
        p=checked(root,rel)
        if p.exists():
            dest=checked(backup,rel)
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,dest)
        if digest(checked(work/'stage',rel))!=item['after']:
            raise RuntimeError('Staged file changed: '+rel)
    source=sqlite3.connect('file:'+str(root/'backend/data/sacbinance.db')+'?mode=ro',uri=True,timeout=30)
    dest=sqlite3.connect(str(backup/'sacbinance.db'))
    source.backup(dest,pages=512,sleep=0.1)
    integrity=dest.execute('PRAGMA quick_check').fetchone()[0]
    source.close();dest.close()
    if integrity!='ok':raise RuntimeError('Backup integrity: '+integrity)
    # Exercise the real additive migration and adoption on an isolated copy.
    validation=work/'migration-validation.db'
    shutil.copy2(backup/'sacbinance.db',validation)
    migration_code="""
import json,logging,sqlite3,sys,time
from unittest.mock import patch
from src.config.settings import get_settings
from src.persistence.db import Database
logging.disable(logging.CRITICAL)
tables=('signals','outcomes','alertas_emitidas','klines','rupturas','rupturas_tf')
conn=sqlite3.connect(sys.argv[1])
existing={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
before={t:conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables if t in existing}
conn.close()
settings=get_settings().model_copy(update={'db_path':sys.argv[1]})
with patch('src.persistence.db.get_settings',return_value=settings):db=Database()
policy=db.notification_policy()
policy.adopt_legacy(int(time.time()*1000),settings.signal_expiry_hours)
after={t:db._conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in before}
integrity=db._conn.execute('PRAGMA quick_check').fetchone()[0]
summary={'unchanged_counts':before==after,'source_counts':before,'integrity':integrity,
    'notification_states':policy.rows('SELECT estado,COUNT(*) AS n FROM notificacion_planes GROUP BY estado')}
db._conn.close()
print(json.dumps(summary))
raise SystemExit(0 if before==after and integrity=='ok' else 1)
"""
    result=subprocess.run([str(root/'backend/venv/bin/python'),'-c',migration_code,str(validation)],
        cwd=work/'stage/backend',capture_output=True,text=True,timeout=180)
    (work/'migration-test.txt').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('Migration validation failed: '+result.stdout+result.stderr)
    migration=json.loads(result.stdout.strip().splitlines()[-1])
    check_old()
    for rel,item in request['files'].items():
        target=checked(root,rel)
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_name(target.name+'.notification-new')
        temporary.write_bytes(base64.b64decode(item['content']))
        temporary.chmod(target.stat().st_mode & 0o777 if target.exists() else 0o644)
        os.replace(temporary,target)
    verified=all(digest(checked(root,rel))==item['after'] for rel,item in request['files'].items())
    (work/'INSTALLED').write_text(str(time.time()))
    print(json.dumps({'installed':verified,'backup':str(backup),'db_integrity':integrity,'migration':migration,'files':list(request['files'])}))
else:raise RuntimeError('Unknown mode')
'''

mode=sys.argv[1]
if mode=='stage':
    import datetime
    name=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
else:
    name=json.loads((HERE/'stage-result.json').read_text())['work'].split('/')[-1]
payload={'mode':mode,'name':name,'files':{}}
for rel in FILES:
    content=(ROOT/rel).read_bytes()
    payload['files'][rel]={'before':BASELINE['files'].get(rel,{}).get('sha256'),
        'after':hashlib.sha256(content).hexdigest(),'content':base64.b64encode(content).decode()}
script='request = '+repr(payload)+'\n'+REMOTE
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','sac','python3 -'],
    input=script.encode(),capture_output=True)
if result.returncode:
    print(result.stderr.decode(errors='replace'))
    raise SystemExit(result.returncode)
response=json.loads(result.stdout)
(HERE/(mode+'-result.json')).write_text(json.dumps(response,indent=2),encoding='utf-8')
brief={k:v for k,v in response.items() if k!='tests'}
if 'tests' in response:brief['tests_summary']=response['tests'].strip().splitlines()[-3:]
print(json.dumps(brief,ensure_ascii=True))
