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
DESTINO = '/home/flox/.cache/sacbinance-f5/copia.db'

TABLAS = ('klines', 'signals', 'outcomes', 'alertas_emitidas', 'rupturas',
          'rupturas_tf', 'notificacion_planes', 'notificacion_eventos',
          'episodios', 'planes', 'plan_recorrido', 'plan_horizontes',
          'operaciones', 'operacion_eventos', 'symbol_states', 'analysis_log',
          'motor_lecturas', 'motor_transiciones', 'motor_estado')

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
# este ya en el servidor. Es exactamente lo que ejecuta la migracion v19->20.
SCHEMA_VERSION = 20
MOTORES_SCHEMA = """
CREATE TABLE IF NOT EXISTS experimento_registro (
    huella       TEXT PRIMARY KEY,
    version      TEXT    NOT NULL,
    declaracion  TEXT    NOT NULL,
    ts_congelado INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS experimento_resultados (
    plan_id        INTEGER NOT NULL,
    politica       TEXT    NOT NULL,
    huella         TEXT    NOT NULL,
    symbol         TEXT    NOT NULL,
    ts_creado      INTEGER NOT NULL,
    entrada        REAL    NOT NULL,
    objetivo       REAL    NOT NULL,
    stop           REAL    NOT NULL,
    tamano         REAL    NOT NULL DEFAULT 1.0,
    ms_fill        INTEGER,
    desenlace      TEXT,
    ms_desenlace   INTEGER,
    resultado_pct  REAL,
    resultado_r    REAL,
    mfe_pct        REAL,
    mae_pct        REAL,
    n_velas        INTEGER NOT NULL DEFAULT 0,
    cobertura      REAL,
    completa       INTEGER NOT NULL DEFAULT 0,
    ambiguo        INTEGER NOT NULL DEFAULT 0,
    salto          INTEGER NOT NULL DEFAULT 0,
    ts_evaluado    INTEGER NOT NULL,
    PRIMARY KEY (plan_id, politica, huella)
);
CREATE INDEX IF NOT EXISTS idx_exp_pendiente ON experimento_resultados (completa, ts_evaluado);
CREATE INDEX IF NOT EXISTS idx_exp_politica ON experimento_resultados (politica, ts_creado);
CREATE INDEX IF NOT EXISTS idx_exp_symbol ON experimento_resultados (symbol, ts_creado);
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
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'experimento_%'")]
print('tablas nuevas:', nuevas)
for t in nuevas:
    print(f'   {t}: {conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]} filas')

print('integridad:', conn.execute('PRAGMA integrity_check').fetchone()[0])
print('version final:', conn.execute(
    "SELECT value FROM schema_meta WHERE key='version'").fetchone()[0])
conn.close()
