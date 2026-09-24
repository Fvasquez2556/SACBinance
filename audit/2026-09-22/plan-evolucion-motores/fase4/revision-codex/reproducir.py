"""Reproduce hallazgos con velas sinteticas y SQLite :memory:, sin produccion."""
import json
import datetime
import hashlib
import os
from pathlib import Path
import sqlite3
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[4]
os.chdir(ROOT / 'backend')
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend/tests'))

from src.state.symbol_state import Candle
from src.analysis.retroceso import detectar_retroceso
from src.analysis.base_rebote import detectar_base_rebote
from src.motores.caida import EstadoCaida, avanzar_caida, RECUPERACION
from src.motores.contrato import Observacion
from src.config.settings import get_settings
from src.motores.servicio import ServicioMotores
from src.motores.almacen import AlmacenMotores, MOTORES_SCHEMA
from src.evaluacion.almacen import AlmacenRecorridos, EVALUACION_SCHEMA
from test_motores import _EstadoFalso, ancla_rota

T = 1790058600000
results = []
v = ([Candle(T+i*60000,100,100,99.9,100,10) for i in range(52)]
     + [Candle(T+(52+i)*60000,96,96.2,96,96,10) for i in range(8)])
r = detectar_retroceso(v).to_dict()
o = Observacion(symbol='TESTUSDT',ts_ms=T,precio=96,velas_1m=60,
                fsm_state='DROPPING',display_state='CAYENDO',
                tendencias={'1h':'BAJISTA'},retroceso=r)
e,l,m = avanzar_caida(EstadoCaida(symbol='TESTUSDT'),o)
results.append({'case':'R1_real_negative_drop','retroceso':r,
                'actual_state':e.estado,'actual_verdict':l.veredicto,
                'expected_state':'CAIDA_ACTIVA'})

v2 = ([Candle(T+i*60000,101,102,101,101,10) for i in range(91)]
      + [Candle(T+(91+i)*60000,97,98.5,96,97,2) for i in range(88)]
      + [Candle(T+179*60000,98.4,99.2,98.2,99,1)])
b = detectar_base_rebote(v2).to_dict()
r2 = detectar_retroceso(v2).to_dict()
o2 = Observacion(symbol='TESTUSDT',ts_ms=T,precio=99,velas_1m=180,
                 fsm_state='RISING',display_state='SUBIENDO',
                 tendencias={'1h':'ALCISTA'},retroceso=r2,base_rebote=b,
                 plan={'valid':True,'entry':99,'take_profit':103,'stop_loss':96})
e2,l2,m2 = avanzar_caida(EstadoCaida(symbol='TESTUSDT',estado=RECUPERACION,
                                    desde_ms=T-60000,abierto_ms=T-600000,
                                    suelo=96,base_piso=96),o2)
results.append({'case':'R2_real_base_weak_volume','base':b,'retroceso':r2,
                'actual_state':e2.estado,'actual_verdict':l2.veredicto,
                'expected_verdict':'ESPERAR'})

c = sqlite3.connect(':memory:')
c.executescript(MOTORES_SCHEMA)
srv = ServicioMotores(AlmacenMotores(c))
s = get_settings()
old = s.motores_max_filas_por_pasada
s.motores_max_filas_por_pasada = 2
try:
    states = {'AAAUSDT':_EstadoFalso(symbol='AAAUSDT'),
              'BBBUSDT':_EstadoFalso(symbol='BBBUSDT')}
    for k in states:
        srv._ancla[k] = (ancla_rota(),T)
    srv.procesar('AAAUSDT',states['AAAUSDT'],T)
    srv.procesar('BBBUSDT',states['BBBUSDT'],T,origen='ALERTA',
                 alerta_id=777,plan_id=888,episode_id=999)
    srv.procesar('BBBUSDT',states['BBBUSDT'],T+60000)
    results.append({'case':'R3_alert_at_cap',
                    'rows':c.execute('select symbol,origen,alerta_id,plan_id from motor_lecturas').fetchall(),
                    'actual_linked_alert_777':c.execute('select count(*) from motor_lecturas where alerta_id=777').fetchone()[0],
                    'expected_linked_alert_777':2})
finally:
    s.motores_max_filas_por_pasada = old
    c.close()

c = sqlite3.connect(':memory:')
c.executescript(EVALUACION_SCHEMA)
c.execute('create table klines(symbol text,tf text,open_time integer,o real,h real,l real,c real)')
c.execute("insert into klines values('TESTUSDT','1m',?,100,105,99,104)",(T,))
p = {'plan_id':1,'symbol':'TESTUSDT','entry':100,'take_profit':105,
     'stop_loss':98,'ts_creado':T,'horizonte_ms':3600000,'coste_pct':0.5}
a = AlmacenRecorridos(c,coste_pct=0.5)
a.evaluar_plan(p,T+60000)
before = a.recorrido(1)['resultado_pct']
a2 = AlmacenRecorridos(c,coste_pct=0.8)
a2.evaluar_plan(p,T+120000)
after = a2.recorrido(1)['resultado_pct']
results.append({'case':'R4_frozen_cost_ignored','plan_cost':0.5,
                'before_net_pct':before,'after_net_pct':after,
                'expected_after_net_pct':4.5})
c.close()

stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
evidence = {'utc':stamp,'results':results,'source_hashes':{}}
for name in ('motores/caida.py','motores/servicio.py','evaluacion/almacen.py'):
    evidence['source_hashes'][name] = hashlib.sha256((ROOT/'backend/src'/name).read_bytes()).hexdigest()
with (BASE/f'reproducciones-{stamp}.json').open('x',encoding='utf8') as f:
    json.dump(evidence,f,ensure_ascii=False,indent=2)
print(json.dumps(results,ensure_ascii=False,indent=2))
