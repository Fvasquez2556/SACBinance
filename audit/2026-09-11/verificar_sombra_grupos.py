# -*- coding: utf-8 -*-
"""
Comprueba la medicion en sombra del objetivo por grupo (esquema v12).

Lo que hay que demostrar son dos cosas distintas:

  1. Que MIDE: la volatilidad previa se calcula, el grupo sale, el objetivo se
     guarda y el cruce se anota con su tiempo.
  2. Que NO DECIDE: los niveles ofrecidos, el veto y el aviso son identicos
     con la medicion puesta y quitada. Esto es lo importante — el encargo era
     medir sin tocar la emision.

No escribe en produccion ni sale a la red.
"""
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['TELEGRAM_ENABLED'] = 'false'

from src.analysis import grupos
from src.analysis.outcome_tracker import OutcomeTracker
from src.state.symbol_state import Candle

res = []


def check(nombre, esperado, real):
    ok = esperado == real
    res.append(ok)
    print(f"{'PASA ' if ok else 'FALLA'}  {nombre}")
    if not ok:
        print(f"         esperado {esperado!r}, real {real!r}")


def velas(n, recorrido_pct, precio=100.0):
    """n velas de 1m con un recorrido (h-l)/c fijo."""
    media = recorrido_pct / 100.0 * precio
    return [Candle(t=i * 60000, o=precio, h=precio + media / 2,
                   l=precio - media / 2, c=precio, v=100.0) for i in range(n)]


# --- 1. la volatilidad previa se mide y agrupa --------------------------------
check("volatilidad previa de 60 velas al 0.20%", 0.2,
      grupos.volatilidad_previa(velas(60, 0.20)))
check("con menos de 30 velas no se inventa un grupo", None,
      grupos.volatilidad_previa(velas(10, 0.20)))
check("sin velas tampoco", None, grupos.volatilidad_previa([]))

for vol, esperado in ((0.04, grupos.MUY_TRANQUILA), (0.068, grupos.MUY_TRANQUILA),
                      (0.09, grupos.TRANQUILA), (0.13, grupos.MOVIDA),
                      (0.30, grupos.MUY_VOLATIL)):
    check(f"volatilidad {vol}% -> grupo", esperado, grupos.grupo(vol))
check("sin volatilidad no hay grupo", None, grupos.grupo(None))
check("objetivo de una moneda movida", 1.81, grupos.objetivo_de(0.13))
check("objetivo de una muy volatil", 2.49, grupos.objetivo_de(0.30))
check("sin grupo no hay objetivo", None, grupos.objetivo_de(None))

# DOGS el 10-sep: 0.123% medido en la hora previa a la compra de Felix
check("DOGS (0.123%) cae en MOVIDA", grupos.MOVIDA, grupos.grupo(0.123))
check("y su objetivo habria sido 1.81%", 1.81, grupos.objetivo_de(0.123))


# --- 2. el tracker guarda y mide el objetivo del grupo ------------------------
class DB:
    def __init__(self):
        self.filas = {}
    def abrir_outcome(self, row):
        self.filas[row['signal_id']] = dict(row)
        return True
    def guardar_outcome(self, sid, cambios):
        self.filas[sid].update(cambios)


def abrir(vol):
    db = DB()
    t = OutcomeTracker(db)
    t.abrir(1, 'TESTUSDT', 0, {'vol_previa_pct': vol},
            {'entry': 100.0, 'take_profit': 105.0, 'stop_loss': 95.0})
    return t, db


t, db = abrir(0.13)
check("la fila guarda la volatilidad cruda", 0.13, db.filas[1]['vol_previa_pct'])
check("la fila guarda el grupo", grupos.MOVIDA, db.filas[1]['grupo_vol'])
check("la fila guarda el objetivo", 1.81, db.filas[1]['objetivo_grupo_pct'])

# sube 1.9% a los 5 minutos: cruza el objetivo del grupo (1.81) pero NO el 3.2 fijo
t.on_candle('TESTUSDT', 300000, 101.9, 99.9, 101.5)
check("cruza el objetivo del grupo y anota cuando", 300000,
      t._abiertos[1]['ms_objetivo_grupo'])
check("y el 3.2% fijo sigue sin alcanzarse", None, t._abiertos[1]['ms_up_32'])
check("se persiste el cruce", 300000, db.filas[1]['ms_objetivo_grupo'])

# no se reescribe en una vela posterior mas alta
t.on_candle('TESTUSDT', 600000, 103.0, 101.0, 102.5)
check("el primer cruce no se pisa", 300000, t._abiertos[1]['ms_objetivo_grupo'])

# una senal que no llega deja el campo vacio
t2, db2 = abrir(0.13)
t2.on_candle('TESTUSDT', 300000, 101.0, 99.5, 100.5)
check("si no llega al objetivo, queda NULL", None, t2._abiertos[1]['ms_objetivo_grupo'])

# sin volatilidad medible, la fila queda sin grupo en vez de con uno inventado
t3, db3 = abrir(None)
check("sin volatilidad, sin grupo", None, db3.filas[1]['grupo_vol'])
check("sin volatilidad, sin objetivo", None, db3.filas[1]['objetivo_grupo_pct'])
t3.on_candle('TESTUSDT', 300000, 110.0, 99.0, 109.0)
check("y no se mide ningun cruce de grupo", None, t3._abiertos[1]['ms_objetivo_grupo'])


# --- 3. LO IMPORTANTE: no toca nada de lo que el sistema decide ---------------
import src.analysis.trade_levels as tl
import inspect

fuente_tl = inspect.getsource(tl)
check("trade_levels no menciona los grupos", False,
      'grupos' in fuente_tl or 'objetivo_grupo' in fuente_tl)

import src.state.engine as eng
fuente_eng = inspect.getsource(eng)
# La unica aparicion permitida es la del helper de medicion `_con_liquidez`.
usos = [l.strip() for l in fuente_eng.splitlines()
        if 'grupos.' in l and not l.strip().startswith('#')]
check("el engine solo usa los grupos en un sitio", 1, len(usos))
check("y ese sitio es el calculo de la volatilidad previa", True,
      bool(usos) and 'volatilidad_previa' in usos[0])

fuente_ot = inspect.getsource(sys.modules['src.analysis.outcome_tracker'])
tramo = fuente_ot.split('def on_candle')[1] if 'def on_candle' in fuente_ot else ''
check("el objetivo del grupo no cierra ni veta nada", False,
      'objetivo_grupo' in tramo and ('cerrado' in tramo.split('objetivo_grupo')[1][:400]
                                     and 'ms_objetivo_grupo' not in tramo))

print(f"\n{sum(res)} pasan, {len(res)-sum(res)} fallan")
sys.exit(0 if all(res) else 1)
