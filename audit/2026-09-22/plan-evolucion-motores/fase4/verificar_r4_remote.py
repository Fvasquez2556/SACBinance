"""
R4 en la base real, sin tocar produccion.

El defecto solo se manifiesta cuando cambia `coste_operacion_pct`, y ese valor
nunca ha cambiado (0,5 por defecto, sin override en `.env`). Asi que esperar a
verlo en vivo seria esperar a que el dano ocurra.

Esto lo comprueba sobre una COPIA de la base real: se reevaluan los planes con
la ventana abierta usando un coste global distinto (0,8 %) y se mira si su
resultado neto cambia. Con el codigo corregido no debe moverse ni uno.

Produccion se abre solo en modo lectura para copiarla.
"""
import os
import shutil
import sqlite3
import sys
import time

ORIGEN = '/home/flox/sacbinance/backend/data/sacbinance.db'
COPIA = '/home/flox/.cache/sacbinance-r4/copia.db'

os.makedirs(os.path.dirname(COPIA), exist_ok=True)
for sufijo in ('', '-wal', '-shm'):
    if os.path.exists(COPIA + sufijo):
        os.remove(COPIA + sufijo)

t0 = time.time()
src = sqlite3.connect(f'file:{ORIGEN}?mode=ro', uri=True)
dst = sqlite3.connect(COPIA)
src.backup(dst)
src.close()
dst.close()
print(f'copia: {os.path.getsize(COPIA)/1e6:.0f} MB en {time.time()-t0:.1f}s')

sys.path.insert(0, '/home/flox/sacbinance/backend')
from src.evaluacion.almacen import AlmacenRecorridos      # noqa: E402

conn = sqlite3.connect(COPIA)
antes = {r[0]: r[1] for r in conn.execute(
    """SELECT r.plan_id, r.resultado_pct FROM plan_recorrido r
       WHERE r.resultado_pct IS NOT NULL""")}
abiertas = conn.execute(
    'SELECT COUNT(*) FROM plan_recorrido WHERE completa = 0').fetchone()[0]
print(f'recorridos con resultado: {len(antes)} | ventanas abiertas: {abiertas}')

# El escenario que hoy no existe: el operador sube el coste al 0,8 %.
ahora_ms = int(time.time() * 1000)
caro = AlmacenRecorridos(conn, coste_pct=0.8, max_por_pasada=5000)
res = caro.evaluar_pendientes(ahora_ms)
conn.commit()
print(f'reevaluados con coste global 0,8 %: {res}')

despues = {r[0]: r[1] for r in conn.execute(
    """SELECT r.plan_id, r.resultado_pct FROM plan_recorrido r
       WHERE r.resultado_pct IS NOT NULL""")}

movidos = [(p, antes[p], despues[p]) for p in antes
           if p in despues and antes[p] != despues[p]]
print()
print(f'planes cuyo resultado neto CAMBIO al subir el coste global: {len(movidos)}')
for p, a, b in movidos[:10]:
    print(f'   plan {p}: {a} -> {b}')
nuevos = [p for p in despues if p not in antes]
print(f'planes que cerraron en esta pasada (resultado nuevo, no reescrito): {len(nuevos)}')
if nuevos:
    fila = conn.execute(
        'SELECT r.resultado_pct, p.coste_pct FROM plan_recorrido r '
        'JOIN planes p ON p.plan_id = r.plan_id WHERE r.plan_id = ?',
        (nuevos[0],)).fetchone()
    print(f'   ejemplo: resultado {fila[0]} con el coste del plan {fila[1]} %')
conn.close()
print()
print('VEREDICTO:', 'ningun resultado reescrito' if not movidos
      else f'{len(movidos)} resultados reescritos — R4 SIGUE VIVO')
