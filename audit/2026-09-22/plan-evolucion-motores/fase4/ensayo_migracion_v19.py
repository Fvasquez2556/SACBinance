"""
Ensayo de la migracion v18 -> v19 sobre una COPIA de la base real.

Se ejecuta en el servidor. Copia la base con la API de backup de SQLite (que
respeta al proceso que esta escribiendo), corre la migracion contra la copia y
comprueba tres cosas: que la integridad sigue bien, que no cambio ninguna fila
de las tablas que ya existian, y cuanto tardo.

Nunca toca la base de produccion.
"""
import os
import sqlite3
import sys
import time

ORIGEN = '/home/flox/sacbinance/backend/data/sacbinance.db'
DESTINO = '/home/flox/.cache/sacbinance-f4/copia.db'

TABLAS = ('klines', 'signals', 'outcomes', 'alertas_emitidas', 'rupturas',
          'rupturas_tf', 'notificacion_planes', 'notificacion_eventos',
          'episodios', 'planes', 'plan_recorrido', 'plan_horizontes',
          'operaciones', 'operacion_eventos', 'symbol_states', 'analysis_log')

os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
if os.path.exists(DESTINO):
    os.remove(DESTINO)

t0 = time.time()
src = sqlite3.connect(f'file:{ORIGEN}?mode=ro', uri=True)
dst = sqlite3.connect(DESTINO)
src.backup(dst)
src.close()
tam = os.path.getsize(DESTINO) / 1e6
print(f'copia: {tam:.0f} MB en {time.time() - t0:.1f}s (el servicio seguia escribiendo)')


def censo(conn):
    out = {}
    for t in TABLAS:
        try:
            out[t] = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        except sqlite3.Error:
            out[t] = None
    return out


antes = censo(dst)
version_antes = dst.execute(
    "SELECT value FROM schema_meta WHERE key='version'").fetchone()[0]
print(f'esquema antes: v{version_antes}')
dst.close()

# El DDL va embebido a proposito: asi el ensayo NO necesita que el codigo nuevo
# este ya en el servidor. Es exactamente lo que ejecuta la migracion v18->19.
SCHEMA_VERSION = 19
MOTORES_SCHEMA = """
CREATE TABLE IF NOT EXISTS motor_lecturas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms         INTEGER NOT NULL,
    symbol        TEXT    NOT NULL,
    motor         TEXT    NOT NULL,
    version       TEXT    NOT NULL,
    origen        TEXT    NOT NULL,
    veredicto     TEXT    NOT NULL,
    familia       TEXT,
    estado        TEXT,
    estado_desde_ms INTEGER,
    disparador    INTEGER NOT NULL DEFAULT 0,
    razones       TEXT    NOT NULL DEFAULT '[]',
    faltantes     TEXT    NOT NULL DEFAULT '[]',
    datos         TEXT    NOT NULL DEFAULT '{}',
    precio        REAL,
    entrada       REAL,
    objetivo      REAL,
    stop          REAL,
    alerta_id     INTEGER,
    plan_id       INTEGER,
    episode_id    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_motor_lect_symbol ON motor_lecturas (symbol, motor, ts_ms);
CREATE INDEX IF NOT EXISTS idx_motor_lect_origen ON motor_lecturas (origen, ts_ms);
CREATE INDEX IF NOT EXISTS idx_motor_lect_veredicto ON motor_lecturas (motor, veredicto, ts_ms);

CREATE TABLE IF NOT EXISTS motor_transiciones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms       INTEGER NOT NULL,
    symbol      TEXT    NOT NULL,
    motor       TEXT    NOT NULL,
    desde       TEXT,
    hasta       TEXT    NOT NULL,
    motivo      TEXT    NOT NULL,
    precio      REAL,
    datos       TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_motor_trans ON motor_transiciones (symbol, ts_ms);

CREATE TABLE IF NOT EXISTS motor_estado (
    symbol      TEXT    NOT NULL,
    motor       TEXT    NOT NULL,
    estado      TEXT    NOT NULL,
    datos       TEXT    NOT NULL DEFAULT '{}',
    ts_ms       INTEGER NOT NULL,
    PRIMARY KEY (symbol, motor)
);
"""

conn = sqlite3.connect(DESTINO)
t0 = time.time()
conn.executescript(MOTORES_SCHEMA)
conn.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
             (str(SCHEMA_VERSION),))
conn.commit()
ms = (time.time() - t0) * 1000
print(f'migracion v{version_antes} -> v{SCHEMA_VERSION}: {ms:.0f} ms')

despues = censo(conn)
cambios = {t: (antes[t], despues[t]) for t in TABLAS if antes[t] != despues[t]}
print('filas cambiadas en tablas existentes:', cambios or 'ninguna')

nuevas = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'motor_%'")]
print('tablas nuevas:', nuevas)
for t in nuevas:
    print(f'   {t}: {conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]} filas')

print('integridad:', conn.execute('PRAGMA integrity_check').fetchone()[0])
print('version final:', conn.execute(
    "SELECT value FROM schema_meta WHERE key='version'").fetchone()[0])
conn.close()
