"""Inspeccion de solo lectura. No importa la aplicacion ni migra la DB remota."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[4]
REMOTE = r'''
import pathlib,hashlib,json,sqlite3,datetime,subprocess,urllib.request
root=pathlib.Path('/home/flox/sacbinance')
paths=[]
for d in ('episodios','evaluacion','operaciones','motores'):
 paths.extend((root/'backend/src'/d).glob('*.py'))
paths.extend(root/n for n in ('backend/main.py','backend/src/persistence/db.py','backend/src/state/engine.py','backend/src/config/settings.py','backend/src/api/routes.py','backend/src/state/active_alert.py','frontend/dist/index.html'))
paths.extend((root/'backend/tests').glob('test_*.py'))
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{}}
for p in paths:
 if p.exists():
  b=p.read_bytes();out['files'][str(p.relative_to(root))]={'sha256':hashlib.sha256(b).hexdigest(),'normalized':hashlib.sha256(b.replace(b'\r\n',b'\n')).hexdigest(),'mtime_utc':datetime.datetime.fromtimestamp(p.stat().st_mtime,datetime.timezone.utc).isoformat()}
out['service']=subprocess.check_output(['systemctl','show','sacbinance','--property=ActiveState,SubState,MainPID,ExecMainStartTimestamp,NRestarts,StandardOutput,StandardError'],text=True)
for endpoint in ('status','operaciones'):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8000/api/'+endpoint,timeout=10) as res:
   d=json.load(res);out[endpoint]={'http':res.status,'data':d if endpoint=='status' else {'n':len(d['operaciones']),'resumen':d['resumen']}}
 except Exception as e:out[endpoint]={'error':str(e)}
c=sqlite3.connect('file:/home/flox/sacbinance/backend/data/sacbinance.db?mode=ro',uri=True)
c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
def q(sql):return [dict(r) for r in c.execute(sql)]
out['schema']=q('select * from schema_meta')
out['tables']={t:c.execute('select count(*) from '+t).fetchone()[0] for t in ('episodios','planes','plan_recorrido','plan_horizontes','operaciones','operacion_eventos')}
out['alerts_new']=q('select count(*) n,sum(plan_id is null) missing_plan,sum(episode_id is null) missing_episode,sum(signal_id is null) missing_signal from alertas_emitidas where ts_ms>=(select min(ts_creado) from planes)')
out['orphans']=q('select count(*) n from planes p left join episodios e on e.episode_id=p.episode_id where e.episode_id is null')
out['replay_comparison']=q("select n.estado legado,r.desenlace nuevo,count(*) n from planes p join plan_recorrido r on r.plan_id=p.plan_id join notificacion_planes n on n.alerta_id=p.legacy_alerta_id where n.estado in ('TP','SL','VENCIDO') group by 1,2")
out['episodes']=q('select fase,motivo_cierre,count(*) n from episodios group by 1,2')
out['replay']=q('select count(*) n,sum(completa) complete,sum(desenlace is not null) resolved,min(ts_evaluado) min_eval,max(ts_evaluado) max_eval from plan_recorrido')
for t in ('motor_lecturas','motor_transiciones','motor_estado'):
 if c.execute('select 1 from sqlite_master where name=?',(t,)).fetchone():
  out['tables'][t]=c.execute('select count(*) from '+t).fetchone()[0]
  out[t]=q('select min(ts_ms) first,max(ts_ms) last,count(distinct symbol) symbols from '+t)
  if t=='motor_lecturas':out['motor_groups']=q('select motor,veredicto,origen,count(*) n from motor_lecturas group by 1,2,3')
out['plan_times']=q('select min(ts_creado) first,max(ts_creado) last from planes')
c.rollback()
flags={}
for line in (root/'backend/.env').read_text().splitlines():
 k,sep,v=line.partition('=')
 if sep and k.strip().lower().startswith(('motores_','motor_caida_','episodio_','evaluador_')):flags[k.strip()]=v.strip()
out['flags_explicit_in_env']=flags
print(json.dumps(out))
'''

p = subprocess.run(['ssh','-o','BatchMode=yes','sac',
                    '/home/flox/sacbinance/backend/venv/bin/python','-B','-'],
                   input=REMOTE, text=True, encoding='utf8', capture_output=True, timeout=60)
if p.returncode:
    raise RuntimeError(p.stderr)
data = json.loads(p.stdout)
comparison = {'exact':[], 'line_endings_only':[], 'different':[], 'missing_local':[]}
for name, remote in data['files'].items():
    local = ROOT / name
    if not local.exists():
        comparison['missing_local'].append(name)
        continue
    b = local.read_bytes()
    remote['local_sha256'] = hashlib.sha256(b).hexdigest()
    if remote['local_sha256'] == remote['sha256']:
        comparison['exact'].append(name)
    elif hashlib.sha256(b.replace(b'\r\n',b'\n')).hexdigest() == remote['normalized']:
        comparison['line_endings_only'].append(name)
    else:
        comparison['different'].append(name)
data['comparison'] = comparison
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
output = BASE / f'estado-{stamp}.json'
with output.open('x', encoding='utf8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(json.dumps({k:v for k,v in data.items() if k!='files'}, ensure_ascii=False, indent=2))
print(output)
