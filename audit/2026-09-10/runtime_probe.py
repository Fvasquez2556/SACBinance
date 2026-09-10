"""Read-only server diagnostics; persist only non-secret settings and aggregates."""
import json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parent
code=r'''
import collections,json,os,pathlib,re,subprocess,urllib.request,time
p=pathlib.Path('/home/flox/sacbinance/backend')
keys={'MIN_VOLUME_24H','MAX_PAIRS_TO_SCAN','UNIVERSE_REFRESH_SECONDS','CANDLE_BUFFER_1M','SHORTLIST_REFRESH_SECONDS','SHORTLIST_MAX','SHORTLIST_MIN_CHURN','DB_FLUSH_INTERVAL','SIGNAL_EXPIRY_HOURS','OUTCOME_WINDOW_HOURS','MIN_RISK_ATR','MAX_RISK_PCT','RR_TARGET','OBJETIVO_OPERADOR_PCT','SCORE_MIN_DASHBOARD','AVISO_SCORE_MIN','AVISO_VOL24H_MIN','AVISO_SOLO_CONFIRMADO','ALERTA_CONGELADA_ENABLED','TELEGRAM_ENABLED','LOG_LEVEL','KLINE_RETENTION_DAYS'}
overrides={}
if (p/'.env').exists():
 for line in (p/'.env').read_text().splitlines():
  k,sep,v=line.partition('=')
  if sep and k.strip().upper() in keys: overrides[k.strip()]=v.strip()
pid=subprocess.check_output(['systemctl','show','sacbinance','-p','MainPID','--value'],text=True).strip()
out={'env_file_nonsecret_overrides':overrides,'process_cwd':os.readlink('/proc/'+pid+'/cwd'),'process_executable':os.readlink('/proc/'+pid+'/exe')}
for path in ('status','signals/stats'):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8000/api/'+path,timeout=10) as r: out[path]=json.load(r)
 except Exception as e: out[path]=str(type(e).__name__)
raw=subprocess.run(['journalctl','-u','sacbinance','--since','2026-09-10 05:48:00','--no-pager','-o','cat'],capture_output=True,text=True).stdout
patterns={'ws_a_reconnect':'Shortlist aggTrade actualizada','ws_disconnect':'desconectado:','handler_error':'handler error','telegram_success':'AVISO inicial','telegram_fail':'aviso fallo','db_flush_error':'flush error','outcome_open_error':'abrir_outcome error','outcome_id_collision':'NO se guardo','traceback':'Traceback'}
out['journal_pattern_counts']={k:raw.count(v) for k,v in patterns.items()}
out['journal_line_count']=len(raw.splitlines())
out['code_mtimes']={str(f.relative_to(p.parent)):f.stat().st_mtime for f in p.glob('src/**/*.py')}
print(json.dumps(out))
'''
r=subprocess.run(['ssh','-o','BatchMode=yes','flox@100.96.211.5','python3 -'],input=code,text=True,capture_output=True,check=True,timeout=90)
data=json.loads(r.stdout)
(ROOT/'runtime.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in data.items() if k!='code_mtimes'},indent=2))
