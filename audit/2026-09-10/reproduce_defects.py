"""Small deterministic reproductions against the unchanged production source."""
import json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'production'/'backend'))
from src.analysis.outcome_tracker import OutcomeTracker,_contexto
from src.analysis import hoyo
from src.data_ingestion.universe import _is_leveraged
class DB:
 def abrir_outcome(self,row):return True
 def guardar_outcome(self,*args):pass
def tracker():
 t=OutcomeTracker(DB());t.abrir(1,'TESTUSDT',100000000,{}, {'entry':100,'take_profit':105,'stop_loss':95});return t
results=[]
t=tracker();t.on_candle('TESTUSDT',99999000,106,99,101)
results.append({'defect':'outcome accepts candles before emission','actual_ms_tp':t._abiertos[1]['ms_tp'],'expected':'ignore pre-entry candle; timestamp event at close or exact event time'})
t=tracker();t.on_candle('TESTUSDT',100000000+3*86400000,110,90,100)
results.append({'defect':'outcome records hits after 24h before closing','observed':'late candle accepted; closed after updating MFE/MAE and hits'})
t=tracker();t.on_candle('TESTUSDT',100060000,101,99,100);t.on_candle('TESTUSDT',100060000,101,99,100)
results.append({'defect':'outcome processing is not idempotent','n_velas_after_same_candle_twice':t._abiertos[1]['n_velas']})
ctx=_contexto({'rsi14_1m':52,'ind_htf':{'15m':{'rsi14':55,'macd_hist':.1,'bb_position':.7}}},{})
results.append({'defect':'indicator snapshot schema mismatch','actual':{k:ctx[k] for k in ('rsi14','macd_hist','bb_position')}})
r={'hoyo_disparo':100,'stop_loss':95,'take_profit':105,'sl_pct':-5,**hoyo.campos_memoria()};hoyo.actualizar(r,{},60000,106,99,100)
results.append({'defect':'hoyo assumes TP after intrabar limit fill','candle_possible_path':'open 104 -> high 106 -> low 99 -> close 100; buy limit 100 fills after high; no subsequent TP','actual':{k:r[k] for k in ('hoyo_fill','hoyo_a','hoyo_c2','hoyo_c3')}})
results.append({'defect':'leveraged substring filter excludes ordinary ticker names','examples':{x:_is_leveraged(x) for x in ('JUP','SUPER','JUPITER','BTC')}})
assert results[0]['actual_ms_tp']==-1000
assert results[2]['n_velas_after_same_candle_twice']==2
assert all(v is None for v in results[3]['actual'].values())
assert r['hoyo_c2']=='TP'
(ROOT/'defect_reproductions.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
