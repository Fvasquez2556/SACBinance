"""Deterministic regression checks against the archived deployed source.
No production writes, network requests or Telegram messages. Failing checks
are recorded rather than hidden behind an all-or-nothing test runner.
"""
import asyncio,copy,json,os,pathlib,sys,types
from unittest.mock import patch,AsyncMock
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'production'/'backend'))
os.environ['TELEGRAM_ENABLED']='false'
from src.config.settings import Settings,get_settings
from src.analysis.outcome_tracker import OutcomeTracker,_contexto
from src.analysis import hoyo
from src.data_ingestion.universe import _is_leveraged
from src.data_ingestion.ws_manager import WSManager
from src.state.symbol_state import SymbolState,Candle
from src.state.engine import StateEngine
from src.utils import procedencia
from src.notify.telegram import Telegram
settings=Settings(_env_file=None,telegram_enabled=False)
results=[]
def check(name,expected,actual,passed=None):
 results.append({'check':name,'expected':expected,'actual':actual,'passed':actual==expected if passed is None else passed})
class DB:
 def __init__(self):self.saved={};self.telegram=[]
 def abrir_outcome(self,row):self.saved[row['signal_id']]=copy.deepcopy(row);return True
 def guardar_outcome(self,sid,changes):self.saved[sid].update(changes)
 def marcar_telegram(self,*args):self.telegram.append(args)
 def get_pair_meta(self,sym):return {'vol_24h':5e6}
def tracker():
 db=DB();t=OutcomeTracker(db);t.abrir(1,'TESTUSDT',100000000,{}, {'entry':100,'take_profit':105,'stop_loss':95});return t,db
t,d=tracker();t.on_candle('TESTUSDT',99999000,106,99,101)
check('F02 ignores pre-entry candle',0,t._abiertos[1]['n_velas'])
t,d=tracker();t.on_candle('TESTUSDT',100000000+3*86400000,110,90,100)
check('F02 ignores candle after 24h',None,d.saved[1].get('ms_tp'))
t,d=tracker();n=t.cerrar_vencidos(100000000+86400001)
check('F02 wall clock closes without further candles',True,n==1 and not t._abiertos and d.saved[1]['cerrado']==1)
t,d=tracker();t.on_candle('TESTUSDT',100060000,101,99,100);t.on_candle('TESTUSDT',100060000,101,99,100)
check('F11 duplicate candle is idempotent',1,t._abiertos[1]['n_velas'])
t,d=tracker();t.on_candle('TESTUSDT',100120000,101,99,100);t.on_candle('TESTUSDT',100060000,101,99,100)
check('F11 timestamp cannot move backwards',100120000,t._abiertos[1]['ts_last'])
t,d=tracker();end=100000000+86400000;bar_open=(end//60000)*60000;t.on_candle('TESTUSDT',bar_open,106,99,100)
check('F02 only candles fully closed within window contribute',None,t._abiertos[1]['ms_tp'])
ctx=_contexto({'rsi14_1m':52,'ind_htf':{'15m':{'rsi14':55,'macd_hist':.1,'bb_position':.7}}},{})
check('F07 indicator mapping with explicit timeframes',[52,55,.1,.7],[ctx.get(k) for k in ('rsi14_1m','rsi14_15m','macd_hist_15m','bb_position_15m')])
r={'hoyo_disparo':100,'stop_loss':95,'take_profit':105,'sl_pct':-5,**hoyo.campos_memoria()};hoyo.actualizar(r,{},60000,106,99,100)
check('F05 no TP awarded in ambiguous fill candle',True,r['hoyo_ambiguo']==1 and all(r[k] is None for k in ('hoyo_a','hoyo_c2','hoyo_c3')))
hoyo.actualizar(r,{},120000,106,100,105)
check('F05 subsequent candle may hit TP',True,all(r[k]=='TP' for k in ('hoyo_a','hoyo_c2','hoyo_c3')))
check('F10 ordinary coins remain eligible',[False]*4,[_is_leveraged(x) for x in ('JUP','SUPER','SYRUP','BTC')])
check('F10 leveraged examples excluded',[True]*3,[_is_leveraged(x) for x in ('BTCUP','ETHDOWN','BTC3L')])
st=SymbolState('TESTUSDT');bar=Candle(t=100020000,o=100,h=101,l=99,c=100,v=100)
st.add_closed_candle(bar);st.add_closed_candle(bar)
check('F11 indicator buffer deduplicates closed candle',1,len(st.candles))
en=StateEngine();en.preload_1m('TESTUSDT',[bar]);bar2=Candle(t=bar.t+60000,o=100,h=101,l=99,c=100,v=100)
en.preload_1m('TESTUSDT',[bar,bar2])
check('F01 repair hydrator adds missing bar to warm engine',bar2.t,en.get_symbol('TESTUSDT').candles[-1].t)
en.preload_htf('TESTUSDT','15m',[bar]);en.preload_htf('TESTUSDT','15m',[bar])
check('F01 repeated repair preserves unique HTF bars',1,len(en.get_symbol('TESTUSDT').candles_15m))
for key,value in [('rr_target',3.0),('coste_operacion_pct',1.0),('exigir_objetivo_operador',True),('flow_min_trades',99),('rise_z',99.0)]:
 s2=settings.model_copy(update={key:value})
 check('F12 config hash reflects '+key,True,procedencia._config_hash(settings)!=procedencia._config_hash(s2))
async def main():
 ws=WSManager([f'X{i}USDT' for i in range(100)],None);calls=[]
 ws._start_ws_a=lambda:calls.append('A');ws._start_ws_b=lambda:calls.append('B')
 desired=ws.symbols+['NEWUSDT']
 await ws.update_symbols(desired);await ws.update_symbols(desired)
 check('F09 repeated small universe update eventually subscribes new pair',True,'B' in calls)
 ws=WSManager([],None);ws._shortlist={f'X{i}USDT' for i in range(40)}
 wanted=list(ws._shortlist-{'X0USDT'})+['NEWUSDT']
 await ws.update_shortlist(wanted)
 en=StateEngine();en.set_shortlist(wanted)
 check('F08 engine availability matches actual accepted shortlist',True,en._shortlist==ws._shortlist)
 en=StateEngine();st=en._get('TESTUSDT');st.add_closed_candle=lambda c:True
 calls=[];en._alertas.update=lambda *a,**kw:calls.append('update')
 with patch('src.state.engine.detect_blow_off',return_value=types.SimpleNamespace(detected=True,reason='synthetic test')):
  await en.on_closed_candle('TESTUSDT',100020000,100,110,90,100,100)
 check('F13 active alert receives update during blow-off',True,bool(calls))
 en=StateEngine();d=DB();en._db=d
 tg=Telegram();tg.activo=True;tg._pedir=AsyncMock(return_value=None);tg.olvidar=lambda x:None
 en._tg=tg;st=types.SimpleNamespace(retroceso={'confirmado':True,'detectado':True},alerta={},sr_levels={})
 with patch('src.state.engine.texto_alerta',return_value='synthetic test'):
  await en._quiza_avisar('TESTUSDT',st,{'score':90,'vol_24h':5e6},200000000,alerta_id=1)
 check('F04 failed Telegram response is recorded as failure','fallo',d.telegram[-1][1])
asyncio.run(main())
out={'source_commit':json.loads((ROOT/'provenance.json').read_text())['commit'],'checks':results,'passed':sum(x['passed'] for x in results),'failed':sum(not x['passed'] for x in results)}
(ROOT/'behaviour_checks.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
