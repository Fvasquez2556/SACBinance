"""Casos adversos contra el codigo real; SQLite solo en memoria.

No modifica fuentes, configuracion ni la base de datos del sistema.
Las comprobaciones son invariantes esperadas, no snapshots del defecto.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[4]
sys.path.insert(0, str(ROOT/'backend'))
from src.episodios import EPISODIOS_SCHEMA, RegistroEpisodios
from src.experimentos.almacen import EXPERIMENTOS_SCHEMA, AlmacenExperimentos
from src.experimentos.registro import POR_CLAVE, barreras_de, huella

M = 60000
START = 1790000040000  # alineado a minuto
WINDOW = 60 * M

def setup(candles):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript(EPISODIOS_SCHEMA + EXPERIMENTOS_SCHEMA)
    db.execute('CREATE TABLE klines(symbol TEXT, tf TEXT, open_time INTEGER, open REAL, high REAL, low REAL, close REAL, o REAL, h REAL, l REAL, c REAL, volume REAL)')
    reg = RegistroEpisodios(db)
    store = AlmacenExperimentos(db)
    store.congelar(START)
    reg.registrar(symbol='TESTUSDT', ts_ms=START,
                  tl={'entry': 100., 'take_profit': 106., 'stop_loss': 97.,
                      'tf': '5m', 'sl_basis': 'soporte estructural'},
                  alerta_id=1, horizonte_ms=WINDOW, coste_pct=0.5)
    for offset, o, h, l, c in candles:
        db.execute('INSERT INTO klines VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('TESTUSDT','1m',START+offset*M,o,h,l,c,o,h,l,c,1))
    return db, store

def row(db, policy):
    return dict(db.execute('SELECT * FROM experimento_resultados WHERE politica=?', (policy,)).fetchone())

checks = []
def check(name, expected, actual, passed):
    checks.append({'case': name, 'expected': expected, 'actual': actual, 'passes_invariant': bool(passed)})

# La vela abre por encima del limite y cruza limite y stop, necesariamente
# en ese orden. La subida posterior no puede resucitar la operacion.
db, store = setup([(0,100,100.2,95,96), (1,96,107,96,106)] +
                  [(i,106,106.2,105.8,106) for i in range(2,60)])
store.evaluar_pendientes(START+WINDOW)
r = row(db, 'B2')
check('stop_en_vela_de_entrada', 'STOP, -3.5 % neto', r,
      r['desenlace']=='STOP' and abs(r['resultado_pct']+3.5)<0.0001)
db.close()

# Ninguna vela habilitada cruza la entrada; solo la vela que empieza cuando
# vence la ventana lo hace. Debe quedar NO_LLENADO.
normal = [(i,100,100.2,99.9,100) for i in range(60)]
db, store = setup(normal + [(60,100,100.2,98.4,99)])
store.evaluar_pendientes(START+WINDOW+2*M)
r = row(db, 'B2')
retry = store.evaluar_pendientes(START+WINDOW+3*M)
check('fill_fuera_de_ventana', 'NO_LLENADO; sin ms_fill fuera de ventana',
      {'row':r, 'second_pass':retry, 'after_second_pass':row(db,'B2')},
      r['desenlace']=='NO_LLENADO' and r['ms_fill'] is None)
db.close()

# Las ordenes que no entran deben aparecer en el denominador del informe,
# aunque resultado_pct permanezca NULL y no participen en la media.
db, store = setup(normal)
store.evaluar_pendientes(START+WINDOW)
summary = store.resumen()
reported = next((r for r in summary['por_politica'] if r['politica']=='B2'), None)
check('denominador_no_llenado', 'B2 presente; no_llenado=1, media_pct=NULL',
      {'stored':row(db,'B2'), 'reported':reported},
      reported is not None and reported['no_llenado']==1 and reported['media_pct'] is None)
db.close()

# Sin una sola observacion no se puede afirmar un retorno. Al llegar datos
# despues, debe ser posible completar la medicion antes de declararla final.
db, store = setup([])
store.evaluar_pendientes(START+WINDOW)
r = row(db, 'REF')
first_summary = store.resumen()
db.execute('INSERT INTO klines VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
           ('TESTUSDT','1m',START,100,107,99.9,106,100,107,99.9,106,1))
retry = store.evaluar_pendientes(START+WINDOW+M)
check('sin_datos_no_es_perdida', 'sin retorno medible; no incluido como operacion resuelta',
      {'initial':r, 'initial_summary_ref':next(x for x in first_summary['por_politica'] if x['politica']=='REF'),
       'after_data_arrive':row(db,'REF'), 'retry':retry}, r['resultado_pct'] is None)
db.close()

# Contrato escrito: mismo porcentaje de objetivo en entrada diferida.
b = barreras_de(POR_CLAVE['B2'], {'entry':100.,'take_profit':106.,'stop_loss':97.}, 0.5)
check('objetivo_documentado_entrada_diferida', '6 % bruto desde 98.5 => objetivo 104.41',
      {'entry':b.entrada,'tp':b.objetivo,'tp_pct':(b.objetivo/b.entrada-1)*100},
      abs(b.objetivo-104.41)<0.0001)

files = ['backend/src/experimentos/almacen.py','backend/src/experimentos/registro.py',
         'backend/src/evaluacion/recorrido.py','backend/tests/test_experimentos.py',
         'audit/2026-09-22/plan-evolucion-motores/fase5/REGISTRO_CONGELADO.md']
out = {'huella':huella(), 'sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}, 'checks':checks}
target = BASE/'reproducciones.json'
target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf8')
for c in checks:
    print(('PASS' if c['passes_invariant'] else 'FAIL') + ' ' + c['case'])
print(target)
