"""
Ensayo de la migracion v15 -> v16 sobre una base con la forma de produccion.

No toca ninguna base real: construye una temporal, la puebla, le retrocede el
numero de esquema y mide el salto. Comprueba lo unico que importa antes de
desplegar una migracion aditiva: que no pierde filas, que no rompe integridad y
que no tarda tanto como para dejar el servicio parado al arrancar.

    python audit/2026-09-22/plan-evolucion-motores/ensayo_migracion_v16.py

Resultado del 21-sep-2026: 179 MB, 200.000 alertas y 1,5 M de velas; el salto
v15->16 (dos tablas, tres indices y dos columnas nuevas) tardo 10 ms, la
integridad quedo en `ok` y ninguna fila cambio. Las columnas nuevas quedan a
NULL en las filas antiguas, que es lo esperado: la identidad empieza a
escribirse con las alertas nuevas, no reescribe el pasado.
"""
import os
import sqlite3
import sys
import time
from unittest.mock import patch

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(RAIZ, 'backend'))

from src.config.settings import get_settings          # noqa: E402
from src.persistence.db import Database               # noqa: E402

ALERTAS = 200_000
VELAS = 1_500_000


def ensayo(ruta: str) -> dict:
    if os.path.exists(ruta):
        os.remove(ruta)
    ajustes = get_settings().model_copy(update={'db_path': ruta})
    with patch('src.persistence.db.get_settings', return_value=ajustes):
        db = Database()
    c = db._conn
    c.executemany(
        """INSERT INTO alertas_emitidas
           (ts_ms, symbol, signal_id, entry, take_profit, stop_loss, telegram)
           VALUES (?,?,?,?,?,?,?)""",
        [(1_700_000_000_000 + i * 60_000, f'S{i % 300}USDT',
          i if i % 3 else None, 100.0, 106.0, 97.0, 'no_procede')
         for i in range(ALERTAS)])
    c.executemany(
        "INSERT INTO klines (symbol, tf, open_time, o, h, l, c, v) VALUES (?,?,?,?,?,?,?,?)",
        [(f'S{i % 300}USDT', '1m', 1_700_000_000_000 + i * 60_000, 1, 2, .5, 1.5, 10)
         for i in range(VELAS)])
    # Retroceder a v15: quitar lo que aporta la v16 y bajar el numero.
    c.execute("DROP TABLE episodios")
    c.execute("DROP TABLE planes")
    c.execute("ALTER TABLE alertas_emitidas DROP COLUMN episode_id")
    c.execute("ALTER TABLE alertas_emitidas DROP COLUMN plan_id")
    c.execute("INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version','15')")
    c.commit()
    antes = {n: c.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]
             for (n,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    c.close()

    tam = os.path.getsize(ruta) / 1e6
    t = time.time()
    with patch('src.persistence.db.get_settings', return_value=ajustes):
        db2 = Database()
    ms = (time.time() - t) * 1000
    c = db2._conn
    despues = {n: c.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]
               for (n,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {r[1] for r in c.execute('PRAGMA table_info(alertas_emitidas)')}
    resultado = {
        'tam_mb': round(tam),
        'ms': round(ms),
        'integridad': c.execute('PRAGMA integrity_check').fetchone()[0],
        'version': c.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0],
        'filas_cambiadas': {k: (antes[k], despues[k]) for k in antes
                            if antes[k] != despues.get(k)},
        'tablas_nuevas': sorted(set(despues) - set(antes)),
        'columnas_nuevas': sorted({'episode_id', 'plan_id'} & cols),
    }
    c.close()
    os.remove(ruta)
    return resultado


if __name__ == '__main__':
    import json
    import tempfile
    destino = os.path.join(tempfile.gettempdir(), 'ensayo_v16.db')
    print(json.dumps(ensayo(destino), ensure_ascii=False, indent=2))
