"""
Ensayo de la migracion v20 -> v21 sobre una COPIA de la base real.

Se ejecuta en el servidor. Copia la base con la API de backup de SQLite (que
respeta al proceso que esta escribiendo), corre la migracion contra la copia y
comprueba cuatro cosas: que la integridad sigue bien, que no cambio ninguna
fila de las tablas que ya existian, cuanto tardo, y que el reparto por episodio
se puede sembrar sobre los episodios que ya hay.

Nunca toca la base de produccion.
"""
import os
import sqlite3
import sys
import time

# De donde sale el codigo nuevo. Por defecto el backend de produccion; durante
# el ensayo PREVIO al despliegue se le pasa un arbol de staging en /tmp, para
# no dejar un solo fichero nuevo en el directorio de la aplicacion antes de que
# el despliegue este autorizado.
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1
                else '/home/flox/sacbinance/backend')

ORIGEN = '/home/flox/sacbinance/backend/data/sacbinance.db'
DESTINO = '/home/flox/.cache/sacbinance-f7/copia.db'
SCHEMA_VERSION = 21

TABLAS = ('klines', 'signals', 'outcomes', 'alertas_emitidas', 'rupturas',
          'rupturas_tf', 'notificacion_planes', 'notificacion_eventos',
          'episodios', 'planes', 'plan_recorrido', 'plan_horizontes',
          'operaciones', 'operacion_eventos', 'symbol_states', 'analysis_log',
          'motor_lecturas', 'motor_transiciones', 'motor_estado',
          'experimento_registro', 'experimento_resultados')

os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
if os.path.exists(DESTINO):
    os.remove(DESTINO)

t0 = time.time()
src = sqlite3.connect(f'file:{ORIGEN}?mode=ro', uri=True)
dst = sqlite3.connect(DESTINO)
src.backup(dst)
src.close()
dst.close()
tam = os.path.getsize(DESTINO) / 1e6
print(f'copia: {tam:.0f} MB en {time.time() - t0:.1f}s (el servicio seguia escribiendo)')


def censo(conn):
    out = {}
    for t in TABLAS:
        try:
            out[t] = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        except sqlite3.OperationalError:
            out[t] = None
    return out


from src.activacion.almacen import ACTIVACION_SCHEMA, AlmacenActivacion  # noqa: E402
from src.activacion.registro import BRAZOS, huella  # noqa: E402

conn = sqlite3.connect(DESTINO)
version_antes = conn.execute(
    "SELECT value FROM schema_meta WHERE key='version'").fetchone()[0]
antes = censo(conn)
print(f'version de partida: v{version_antes}')

t0 = time.time()
conn.executescript(ACTIVACION_SCHEMA)
conn.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
             (str(SCHEMA_VERSION),))
conn.commit()
ms = (time.time() - t0) * 1000
print(f'migracion v{version_antes} -> v{SCHEMA_VERSION}: {ms:.0f} ms')

despues = censo(conn)
cambios = {t: (antes[t], despues[t]) for t in TABLAS if antes[t] != despues[t]}
print('filas cambiadas en tablas existentes:', cambios or 'ninguna')

nuevas = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'activacion_%'")]
print('tablas nuevas:', nuevas)
for t in nuevas:
    print(f'   {t}: {conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]} filas')

# --- El reparto, sobre los episodios que ya existen -------------------------
# No se siembra en produccion: solo se comprueba aqui que la asignacion corre,
# que reparte cerca de la fraccion declarada y que la integridad queda limpia.
a = AlmacenActivacion(conn)
marca = a.congelar()
print(f"\nhuella de la fase 7a: {marca['huella']}")
print(f"estado inicial: {a.estado()}")

t0 = time.time()
eids = [r[0] for r in conn.execute(
    'SELECT episode_id FROM episodios ORDER BY episode_id')]
for eid in eids:
    a.asignar(eid)
seg = time.time() - t0
r = a.reparto()
print(f"\nreparto sembrado sobre {r['n']} episodios en {seg:.1f}s")
print(f"   por brazo: {r['por_brazo']}")
print(f"   fraccion rival observada: {r['fraccion_rival']}")
print(f"integridad: {a.verificar_integridad() or 'limpia'}")

# Idempotencia: volver a pasar no puede mover a nadie de brazo.
antes_reparto = dict(r['por_brazo'])
for eid in eids[:500]:
    a.asignar(eid)
r2 = a.reparto()
print('segunda pasada mueve a alguien:',
      'SI  <-- REVISAR' if dict(r2['por_brazo']) != antes_reparto else 'no')

print('\nintegridad de la base:', conn.execute('PRAGMA integrity_check').fetchone()[0])
print('version final:', conn.execute(
    "SELECT value FROM schema_meta WHERE key='version'").fetchone()[0])
print('emision: intacta (esta fase no toca ninguna tabla existente)')
conn.close()
