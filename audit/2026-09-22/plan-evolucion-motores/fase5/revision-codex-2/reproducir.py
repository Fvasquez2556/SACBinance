"""Segunda revision: regresiones anteriores y casos nuevos, solo SQLite en memoria."""
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
from src.experimentos.cartera import Cartera, Escenario
from src.experimentos.informe import Informe
from src.experimentos import registro as R

M = 60000
START = 1790000040000
WINDOW = 60*M
checks = []

def setup(maximo=40):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.executescript(EPISODIOS_SCHEMA + EXPERIMENTOS_SCHEMA)
    db.executescript('''CREATE TABLE klines(symbol TEXT, tf TEXT, open_time INTEGER,
                       o REAL, h REAL, l REAL, c REAL, v REAL,
                       PRIMARY KEY(symbol,tf,open_time));
                       CREATE TABLE alertas_emitidas(id INTEGER PRIMARY KEY,telegram TEXT);''')
    store = AlmacenExperimentos(db, max_por_pasada=maximo)
    store.congelar(START)
    return db, store

def alta(db, symbol='TESTUSDT', ts=START):
    alert = db.execute("INSERT INTO alertas_emitidas(telegram) VALUES ('enviado')").lastrowid
    return RegistroEpisodios(db).registrar(
        symbol=symbol, ts_ms=ts, tl={'entry':100., 'take_profit':106.,
                                    'stop_loss':97., 'tf':'5m'},
        alerta_id=alert, horizonte_ms=WINDOW, coste_pct=0.5)['plan_id']

def seed(db, candles, symbol='TESTUSDT', ts=START):
    db.executemany('INSERT OR REPLACE INTO klines VALUES (?,?,?,?,?,?,?,?)',
                   [(symbol,'1m',ts+i*M,*c,1) for i,c in enumerate(candles)])

def row(db, policy='REF', plan_id=1):
    r = db.execute('SELECT * FROM experimento_resultados WHERE politica=? AND plan_id=?',
                   (policy,plan_id)).fetchone()
    return dict(r) if r else None

def check(name, expected, actual, passed, group='nueva_revision'):
    checks.append(dict(case=name, expected=expected, actual=actual,
                       passes_invariant=bool(passed), group=group))

flat = [(100,100.2,99.9,100)]*60
win = [(100,107,99.9,106)] + [(106,106,106,106)]*59

# R1: conservar el stop al llenar, aun cuando despues se alcanza el objetivo.
db, store = setup(); alta(db)
seed(db, [(100,100.2,95,96),(96,107,96,106)]+[(106,106.2,105.8,106)]*58)
store.evaluar_pendientes(START+WINDOW)
r = row(db,'B2')
check('R1_stop_del_fill', 'STOP -3.5%', r,
      r['desenlace']=='STOP' and r['resultado_pct']==-3.5, 'regresion')
db.close()

# R2 y R4: fill fuera de ventana y denominador de no llenadas.
db, store = setup(); alta(db)
seed(db, flat+[(100,100.2,98.4,99)])
store.evaluar_pendientes(START+WINDOW+2*M)
r = row(db,'B2')
check('R2_fill_fuera_de_ventana', 'NO_LLENADO, sin fill', r,
      r['desenlace']=='NO_LLENADO' and r['ms_fill'] is None, 'regresion')
s = next(x for x in store.resumen()['por_politica'] if x['politica']=='B2')
check('R4_denominador', '1 elegible, 1 no llenada, media desconocida', s,
      s['elegibles']==1 and s['no_llenado']==1 and s['media_pct'] is None, 'regresion')
db.close()

# R3: se recupera la medicion despues de llegar los datos.
db, store = setup(); alta(db)
store.evaluar_pendientes(START+WINDOW)
before = row(db)
seed(db, win)
retry = store.evaluar_pendientes(START+WINDOW+M)
after = row(db)
check('R3_recuperacion_de_datos', 'SIN_DATOS NULL -> OBJETIVO +5.5%',
      dict(before=before,after=after,retry=retry),
      before['desenlace']=='SIN_DATOS' and before['resultado_pct'] is None
      and after['desenlace']=='OBJETIVO' and after['resultado_pct']==5.5, 'regresion')
db.close()

# R5/R6: la variante de precio absoluto esta declarada y el hash es comprobable.
doc = ROOT/'audit/2026-09-22/plan-evolucion-motores/fase5/REGISTRO_CONGELADO.md'
b = R.barreras_de(R.POR_CLAVE['B2'],dict(entry=100.,take_profit=106.,stop_loss=97.),0.5)
check('R5_precio_absoluto_declarado', 'TP 106 y documento explica mismo precio objetivo',
      dict(entry=b.entrada,tp=b.objetivo),
      b.objetivo==106. and 'Mismo precio objetivo' in doc.read_text(encoding='utf8'), 'regresion')
original = R.METODO_VERSION
before = R.huella()
try:
    R.METODO_VERSION = 'prueba-local-sin-escribir'
    changed = R.huella()!=before
finally:
    R.METODO_VERSION = original
sha = hashlib.sha256(doc.read_bytes()).hexdigest()
check('R6_huella_metodo_documento', 'hash de documento valido; cambio de metodo cambia huella',
      dict(document_sha256=sha, expected_sha256=R.DOCUMENTO_SHA256, method_changes_hash=changed),
      sha==R.DOCUMENTO_SHA256 and changed, 'regresion')

# N1: tres casos irrecuperables no pueden ocupar todas las pasadas para siempre.
db, store = setup(3)
ids = [alta(db,f'S{i}USDT',START+i*M) for i in range(4)]
seed(db,win,'S3USDT',START+3*M)
passes = [store.evaluar_pendientes(START+100*M+i*M) for i in range(5)]
measured = [x[0] for x in db.execute('SELECT DISTINCT plan_id FROM experimento_resultados')]
check('N1_cola_tras_sin_datos', 'el cuarto plan con cobertura debe recibir turno',
      dict(ids=ids, passes=passes, measured_ids=measured, fourth=row(db,plan_id=ids[-1])),
      row(db,plan_id=ids[-1]) is not None)
db.close()

# N2: el tiempo hasta el desenlace diferido es relativo al fill, no al aviso.
db, store = setup()
a = alta(db,'AUSDT')
candles = [(100,100.2,99.9,100)]*10 + [(100,100.2,98.4,99),(99,100,98.6,99),
                                                  (99,107,98.6,106)] + [(106,106,106,106)]*47
seed(db,candles,'AUSDT')
c = alta(db,'BUSDT',START+11*M)
seed(db,[(100,100.2,98.4,99),(99,107,98.6,106)]+[(106,106,106,106)]*58,
     'BUSDT',START+11*M)
store.evaluar_pendientes(START+100*M)
portfolio = Cartera(db).simular('B2')
ops = [vars(o) for o in portfolio.operaciones]
check('N2_cierre_antes_de_entrada', '1 posicion; cierre A posterior a su entrada; B solapa A',
      dict(result=portfolio.como_dict(), operations=ops, measured_a=row(db,'B2',a)),
      len(ops)==1 and all(o['cierra_ms']>=o['abre_ms'] for o in ops))
db.close()

# N2b: cero minutos de desenlace es un valor valido, no ventana completa.
db, store = setup(); alta(db); seed(db,win)
store.evaluar_pendientes(START+WINDOW)
p = Cartera(db).simular('REF')
o = vars(p.operaciones[0])
check('N2b_desencadenante_minuto_cero', 'no ocupar la hora completa al salir en la primera vela',
      dict(operation=o, stored=row(db)), o['cierra_ms']<=START+M)

# N3: riesgo normalizado != retorno del capital realmente disponible en spot.
p = Cartera(db).simular('C1')
check('N3_tamano_imposible_spot', 'con 10 invertidos, +5.5% neto -> 10.55, no posicion ficticia de 15',
      dict(result=p.como_dict(), operations=[vars(o) for o in p.operaciones], stored=row(db,'C1')),
      abs(p.capital_final-10.55)<1e-8)
p = Cartera(db).simular('REF',Escenario(fraccion_por_posicion=0.5))
check('N3b_fraccion_invertida', '5 invertidos y 5 en efectivo, +5.5% -> 10.275',
      dict(result=p.como_dict(), operations=[vars(o) for o in p.operaciones]),
      abs(p.capital_final-10.275)<1e-8)
db.close()

# N4: aprobar ganancias absolutas no demuestra mejora sobre la referencia.
db, store = setup(100)
for i in range(50):
    symbol = f'P{i:02}USDT'
    alta(db,symbol)
    seed(db,win,symbol)
store.evaluar_pendientes(START+WINDOW)
v = Informe(db).evaluar_politica('A1')
check('N4_aprobacion_inferior_a_referencia', 'no aprobar como mejora si REF supera al rival en todos los pares',
      v, v['veredicto']!='APROBADA')
db.close()

files = [*sorted((ROOT/'backend/src/experimentos').glob('*.py')),
         ROOT/'backend/src/evaluacion/recorrido.py', ROOT/'backend/tests/test_experimentos.py', doc]
out = dict(huella=R.huella(), sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}, checks=checks)
(BASE/'reproducciones.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
for c in checks:
    print(('PASS ' if c['passes_invariant'] else 'FAIL ') + c['case'])
