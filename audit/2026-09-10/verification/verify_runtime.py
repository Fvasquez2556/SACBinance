"""Read-only runtime provenance, whitelisted settings and aggregate logs."""
import json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parent
code=r'''
import os,json,pathlib,subprocess,urllib.request,collections
from src.config.settings import get_settings
keys=['exigir_objetivo_operador','coste_operacion_pct','objetivo_operador_pct','universe_refresh_seconds','universe_min_churn','reparacion_velas_seconds','reparacion_velas_umbral_min','outcome_window_hours','shortlist_min_churn','rr_target','telegram_enabled']
props=subprocess.check_output(['systemctl','show','sacbinance','-p','MainPID','-p','ActiveState','-p','ExecMainStartTimestamp','-p','StandardOutput','-p','StandardError'],text=True)
meta=dict(x.split('=',1) for x in props.splitlines() if '=' in x)
pid=meta['MainPID']; env=pathlib.Path('/proc/'+pid+'/environ').read_bytes().split(b'\x00')
for x in env:
 k,sep,v=x.partition(b'=')
 if k.decode(errors='replace').lower() in keys:os.environ[k.decode()]=v.decode()
s=get_settings()
out={'service':meta,'settings':{k:getattr(s,k) for k in keys},'process_cwd':os.readlink('/proc/'+pid+'/cwd')}
for p in ['status','signals/stats']:
 try:
  with urllib.request.urlopen('http://127.0.0.1:8000/api/'+p,timeout=10) as r:out[p]=json.load(r)
 except Exception as e:out[p]=type(e).__name__
patterns=['Reparando velas:','Universo actualizado:','Shortlist aggTrade actualizada','Traceback','handler error','flush error','outcome_tracker error','Telegram sendMessage fallo','Telegram sendMessage rechazado','Version de estrategia:']
out['log_counts']={}
for field in ['StandardOutput','StandardError']:
 descriptor='1' if field=='StandardOutput' else '2'
 p=pathlib.Path(os.readlink('/proc/'+pid+'/fd/'+descriptor))
 if not p.is_file():continue
 with p.open('rb') as f:
  f.seek(max(0,p.stat().st_size-12000000));raw=f.read().decode(errors='replace')
 # Aggregate only lines bearing a timestamp after deployment. No credentials or message text exported.
 lines=[line for line in raw.splitlines() if line[1:20]>='2026-09-10 22:54:02' and line[1:5]=='2026']
 out['log_counts'][field]={'lines':len(lines),**{v:sum(v in x for x in lines) for v in patterns}}
print(json.dumps(out))
'''
r=subprocess.run(['ssh','-o','BatchMode=yes','flox@100.96.211.5','cd /home/flox/sacbinance/backend && venv/bin/python -'],input=code,text=True,capture_output=True,timeout=60,check=True)
out=json.loads(r.stdout)
(ROOT/'runtime_checks.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
