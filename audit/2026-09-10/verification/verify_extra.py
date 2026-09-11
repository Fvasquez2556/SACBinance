import json,pathlib,sqlite3,subprocess,urllib.request
ROOT=pathlib.Path(__file__).resolve().parent
c=sqlite3.connect((ROOT/'snapshot.db').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
out={}
out['htf_null_cases']=[dict(r) for r in c.execute("SELECT signal_id,symbol,ts_open,sombra,rsi14_1m FROM outcomes WHERE strategy_version='b8a3d64' AND rsi14_15m IS NULL")]
out['alert_thresholds']=dict(c.execute("SELECT count(*) n,sum(tp_pct<3.2) below_gross,sum(reward_neto_pct<3.2) below_net FROM alertas_emitidas").fetchone())
out['historical_closed_missing_coverage']=c.execute('SELECT count(*) FROM outcomes WHERE cerrado=1 AND cobertura_velas IS NULL').fetchone()[0]
# Verify a precise missing minute independently, on the official public endpoint.
start=1789103760000
url=f'https://api.binance.com/api/v3/klines?symbol=ADAUSDT&interval=1m&startTime={start}&endTime={start+59999}&limit=1'
try:
 with urllib.request.urlopen(url,timeout=15) as r:bars=json.load(r)
 out['gap_reference']={'url':url,'bars':bars,'present_in_snapshot':c.execute("SELECT count(*) FROM klines WHERE symbol='ADAUSDT' AND tf='1m' AND open_time=?",(start,)).fetchone()[0]}
except Exception as e:out['gap_reference']={'error':str(e)}
code=r'''
import json,pathlib,subprocess
p=pathlib.Path('/home/flox/sacbinance/frontend/dist')
assets=list(p.glob('assets/*.js'))
text='\n'.join(x.read_text(errors='replace') for x in assets)
print(json.dumps({'git_head':subprocess.check_output(['git','-C','/home/flox/sacbinance','rev-parse','HEAD'],text=True).strip(),'dist_exists':p.exists(),'js_assets':len(assets),'new_historical_tooltip':'FRECUENCIA HISTORICA' in text,'new_net_label':'reward_neto_pct' in text,'js_mtimes':[x.stat().st_mtime for x in assets]}))
'''
r=subprocess.run(['ssh','-o','BatchMode=yes','flox@100.96.211.5','python3 -'],input=code,text=True,capture_output=True,check=True,timeout=30)
out['frontend_deployment']=json.loads(r.stdout)
(ROOT/'extra_checks.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
