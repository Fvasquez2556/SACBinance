"""
Donde viven las lecturas de los dos motores, y por que se guardan asi.

Tres tablas, esquema v19, todo aditivo y en sombra:

    motor_lecturas      una fila por lectura que merece guardarse
    motor_transiciones  cada cambio de estado del motor de caida, con su motivo
    motor_estado        el estado por simbolo, para que reiniciar no lo pierda

La poblacion es el punto
------------------------
Si solo se guardara lo que ya paso el filtro comprador, cualquier tasa medida
despues estaria condicionada a ese mismo filtro — se estaria evaluando el
filtro con datos que el filtro eligio. Por eso `origen` distingue cuatro
razones para escribir una fila:

    TRANSICION  el veredicto o el estado cambio respecto a la vez anterior
    ALERTA      en ese instante el sistema emitio una alerta
    VETO        en ese instante un candidato quedo bloqueado
    MUESTRA     el simbolo cayo en la muestra periodica del universo, mire lo
                que mire y haya pasado lo que haya pasado

La muestra es la unica de las cuatro que no depende de que haya ocurrido nada.
Es la referencia contra la que se miden las otras tres.

Volumen
-------
Escribir una fila por par y minuto serian ~360.000 filas al dia, que es una
forma cara de guardar «no pasa nada». Con deduplicacion por cambio de veredicto
mas una muestra de 12 pares cada 5 minutos, son unos pocos miles al dia.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from src.motores.caida import EstadoCaida
from src.motores.contrato import Lectura

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


class AlmacenMotores:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.db = conn

    # --- Lecturas -----------------------------------------------------------

    def guardar(self, lectura: Lectura, origen: str, *,
                alerta_id: Optional[int] = None, plan_id: Optional[int] = None,
                episode_id: Optional[int] = None) -> int:
        f = lectura.como_fila()
        cur = self.db.execute(
            """INSERT INTO motor_lecturas
               (ts_ms, symbol, motor, version, origen, veredicto, familia, estado,
                estado_desde_ms, disparador, razones, faltantes, datos, precio,
                entrada, objetivo, stop, alerta_id, plan_id, episode_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f["ts_ms"], f["symbol"], f["motor"], f["version"], origen,
             f["veredicto"], f["familia"], f["estado"], f["estado_desde_ms"],
             f["disparador"], json.dumps(f["razones"], ensure_ascii=False),
             json.dumps(f["faltantes"], ensure_ascii=False),
             json.dumps(f["datos"], ensure_ascii=False, default=str),
             f["precio"], f["entrada"], f["objetivo"], f["stop"],
             alerta_id, plan_id, episode_id))
        return int(cur.lastrowid)

    def transicion(self, symbol: str, motor: str, desde: Optional[str],
                   hasta: str, motivo: str, ts_ms: int,
                   precio: Optional[float] = None, datos: Optional[dict] = None) -> None:
        self.db.execute(
            """INSERT INTO motor_transiciones
               (ts_ms, symbol, motor, desde, hasta, motivo, precio, datos)
               VALUES (?,?,?,?,?,?,?,?)""",
            (ts_ms, symbol, motor, desde, hasta, motivo, precio,
             json.dumps(datos or {}, ensure_ascii=False, default=str)))

    # --- Estado por simbolo -------------------------------------------------

    def cargar_estados_caida(self) -> dict:
        """Recupera el estado del motor de caida. En tabla, no en memoria."""
        out = {}
        for symbol, datos in self.db.execute(
                "SELECT symbol, datos FROM motor_estado WHERE motor = 'caida'"):
            try:
                out[symbol] = EstadoCaida.desde_dict(json.loads(datos))
            except Exception:
                continue
        return out

    def guardar_estado_caida(self, est: EstadoCaida, ts_ms: int) -> None:
        self.db.execute(
            """INSERT INTO motor_estado (symbol, motor, estado, datos, ts_ms)
               VALUES (?, 'caida', ?, ?, ?)
               ON CONFLICT(symbol, motor) DO UPDATE SET
                   estado = excluded.estado, datos = excluded.datos,
                   ts_ms = excluded.ts_ms""",
            (est.symbol, est.estado,
             json.dumps(est.como_dict(), ensure_ascii=False), ts_ms))

    # --- Lectura para informes ---------------------------------------------

    def resumen(self, desde_ms: int = 0) -> dict:
        """Para comprobar el despliegue sin abrir la base a mano."""
        def filas(sql, args=()):
            cur = self.db.execute(sql, args)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

        return {
            "por_motor_veredicto": filas(
                """SELECT motor, veredicto, origen, COUNT(*) AS n
                   FROM motor_lecturas WHERE ts_ms >= ?
                   GROUP BY 1,2,3 ORDER BY n DESC""", (desde_ms,)),
            "familias": filas(
                """SELECT familia, veredicto, COUNT(*) AS n FROM motor_lecturas
                   WHERE ts_ms >= ? AND motor = 'continuacion' AND familia IS NOT NULL
                   GROUP BY 1,2 ORDER BY n DESC""", (desde_ms,)),
            "estados_caida": filas(
                """SELECT estado, COUNT(*) AS n FROM motor_lecturas
                   WHERE ts_ms >= ? AND motor = 'caida' AND estado IS NOT NULL
                   GROUP BY 1 ORDER BY n DESC""", (desde_ms,)),
            "transiciones": filas(
                """SELECT desde, hasta, motivo, COUNT(*) AS n
                   FROM motor_transiciones WHERE ts_ms >= ?
                   GROUP BY 1,2,3 ORDER BY n DESC""", (desde_ms,)),
            "candidatos": filas(
                """SELECT motor, familia, estado, symbol, ts_ms, entrada, objetivo, stop
                   FROM motor_lecturas
                   WHERE ts_ms >= ? AND veredicto = 'CANDIDATO'
                   ORDER BY ts_ms DESC LIMIT 50""", (desde_ms,)),
            "vivos": filas(
                """SELECT estado, COUNT(*) AS n FROM motor_estado
                   WHERE motor = 'caida' GROUP BY 1 ORDER BY n DESC"""),
        }
