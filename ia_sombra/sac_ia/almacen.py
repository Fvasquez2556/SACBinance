"""
La base propia del servicio (`ia_sombra.db`). Nunca comparte fichero con SAC.

La evidencia es de solo añadir: un caso, su contexto, la salida de Kronos y
cada decision se escriben una vez y los disparadores impiden reescribirlos o
borrarlos. Lo unico mutable son las proyecciones operativas (pendientes,
cursor, gasto, salud) y la etiqueta mientras no es final: una etiqueta se
recalcula si SAC repara velas, y se congela al cerrarse.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Optional

ESQUEMA_VERSION = 1

ESQUEMA = """
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pendientes (
    alerta_id     INTEGER PRIMARY KEY,
    visto_ms      INTEGER NOT NULL,
    revisado_ms   INTEGER NOT NULL,
    ultimo_estado TEXT
);

CREATE TABLE IF NOT EXISTS casos (
    caso_id          INTEGER PRIMARY KEY,     -- alertas_emitidas.id de SAC
    symbol           TEXT    NOT NULL,
    ts_alerta_ms     INTEGER NOT NULL,
    as_of_ms         INTEGER NOT NULL,        -- notificacion_planes.ts_activado
    visto_ms         INTEGER NOT NULL,        -- cuando este servicio lo vio enviado
    entrada          REAL    NOT NULL,
    objetivo         REAL    NOT NULL,
    stop             REAL    NOT NULL,
    meta_precio      REAL    NOT NULL,
    plan_id          INTEGER,
    episode_id       INTEGER,
    ordinal_episodio INTEGER,
    score            INTEGER,
    escenario        TEXT,
    modo             TEXT    NOT NULL,        -- RODAJE | MEDICION
    tardio           INTEGER NOT NULL,        -- visto despues del plazo de decision
    huella           TEXT    NOT NULL,
    fuente_json      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_casos_asof ON casos (as_of_ms);

CREATE TABLE IF NOT EXISTS contextos (
    caso_id       INTEGER PRIMARY KEY,
    version       TEXT    NOT NULL,
    contexto_json TEXT    NOT NULL,
    sha256        TEXT    NOT NULL,
    creado_ms     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kronos (
    caso_id          INTEGER PRIMARY KEY,
    estado           TEXT    NOT NULL,        -- OK | FALLO | NO_EJECUTADO
    motivo           TEXT,
    modelo           TEXT,
    n_trayectorias   INTEGER,
    n_validas        INTEGER,
    n_meta           INTEGER,
    n_stop           INTEGER,
    n_ninguna        INTEGER,
    n_ambigua        INTEGER,
    p_meta           REAL,
    resumen_json     TEXT    NOT NULL DEFAULT '{}',
    artefacto        TEXT,
    artefacto_sha256 TEXT,
    latencia_ms      INTEGER,
    creado_ms        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS decisiones (
    caso_id             INTEGER NOT NULL,
    brazo               TEXT    NOT NULL,
    modelo              TEXT    NOT NULL,
    estado              TEXT    NOT NULL,
    motivo              TEXT,
    accion              TEXT,
    p_meta              REAL,
    confianza           TEXT,
    codigos_json        TEXT,
    razon               TEXT,
    solicitado_ms       INTEGER,
    recibido_ms         INTEGER,
    a_tiempo            INTEGER NOT NULL DEFAULT 0,
    tokens_entrada      INTEGER,
    tokens_cache        INTEGER,
    tokens_salida       INTEGER,
    tokens_razonamiento INTEGER,
    coste_usd           REAL,
    request_id          TEXT,
    prompt_sha256       TEXT,
    respuesta_json      TEXT,
    PRIMARY KEY (caso_id, brazo)
);

CREATE TABLE IF NOT EXISTS etiquetas (
    caso_id            INTEGER PRIMARY KEY,
    evaluador          TEXT    NOT NULL,
    cobertura          REAL    NOT NULL,
    n_velas            INTEGER NOT NULL,
    meta_primero       INTEGER NOT NULL,
    desenlace_meta     TEXT,
    resultado_meta_pct REAL,
    desenlace_tp       TEXT,
    resultado_tp_pct   REAL,
    ambiguo            INTEGER NOT NULL,
    salto              INTEGER NOT NULL,
    mfe_pct            REAL,
    mae_pct            REAL,
    final              INTEGER NOT NULL DEFAULT 0,
    evaluado_ms        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gasto (
    request_id      TEXT    PRIMARY KEY,
    caso_id         INTEGER,
    brazo           TEXT,
    modelo          TEXT,
    dia_utc         TEXT    NOT NULL,
    reservado_micro INTEGER NOT NULL,
    consumido_micro INTEGER,
    estado          TEXT    NOT NULL,         -- RESERVADO | LIQUIDADO | INCIERTO | LIBERADO
    creado_ms       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gasto_dia ON gasto (dia_utc, estado);

CREATE TABLE IF NOT EXISTS salud (
    ts_ms             INTEGER PRIMARY KEY,
    modo              TEXT    NOT NULL,
    edad_vela_ms      INTEGER,
    carga_1m          REAL,
    mem_disponible_mb REAL,
    rss_ia_mb         REAL,
    sac_pid           INTEGER,
    sac_rss_mb        REAL,
    sac_cpu_s         REAL
);

CREATE TABLE IF NOT EXISTS eventos (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms   INTEGER NOT NULL,
    tipo    TEXT    NOT NULL,
    detalle TEXT
);
"""

# La evidencia no se reescribe. Una correccion es otro estudio, no un UPDATE.
_INMUTABLES = ("casos", "contextos", "kronos", "decisiones")
DISPARADORES = "\n".join(
    f"""CREATE TRIGGER IF NOT EXISTS {t}_sin_update BEFORE UPDATE ON {t} BEGIN
        SELECT RAISE(ABORT, '{t} es evidencia: no se reescribe'); END;
    CREATE TRIGGER IF NOT EXISTS {t}_sin_delete BEFORE DELETE ON {t} BEGIN
        SELECT RAISE(ABORT, '{t} es evidencia: no se borra'); END;"""
    for t in _INMUTABLES
) + """
CREATE TRIGGER IF NOT EXISTS etiquetas_final BEFORE UPDATE ON etiquetas
    WHEN OLD.final = 1 BEGIN
    SELECT RAISE(ABORT, 'etiqueta final: no se reescribe'); END;
CREATE TRIGGER IF NOT EXISTS etiquetas_sin_delete BEFORE DELETE ON etiquetas BEGIN
    SELECT RAISE(ABORT, 'etiquetas: no se borran'); END;
"""


class Almacen:
    """Una conexion, un cerrojo. Los hilos de las llamadas a la API la comparten."""

    def __init__(self, ruta: Path) -> None:
        ruta = Path(ruta)
        if str(ruta) != ":memory:":
            ruta.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(ruta), check_same_thread=False, timeout=10,
                                  isolation_level=None)
        self.lock = threading.RLock()
        with self.lock:
            self.db.execute("PRAGMA journal_mode = WAL")
            self.db.execute("PRAGMA synchronous = NORMAL")
            self.db.executescript(ESQUEMA)
            self.db.executescript(DISPARADORES)
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('esquema', ?)",
                            (str(ESQUEMA_VERSION),))

    # --- Utilidades -----------------------------------------------------------

    def filas(self, sql: str, args: Iterable = ()) -> list[dict]:
        with self.lock:
            cur = self.db.execute(sql, tuple(args))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def uno(self, sql: str, args: Iterable = ()):
        with self.lock:
            fila = self.db.execute(sql, tuple(args)).fetchone()
            return fila[0] if fila else None

    def ejecutar(self, sql: str, args: Iterable = ()) -> int:
        with self.lock:
            return self.db.execute(sql, tuple(args)).rowcount

    # --- Meta -----------------------------------------------------------------

    def meta(self, clave: str, defecto: Optional[str] = None) -> Optional[str]:
        valor = self.uno("SELECT valor FROM meta WHERE clave = ?", (clave,))
        return defecto if valor is None else valor

    def fijar_meta(self, clave: str, valor) -> None:
        self.ejecutar("INSERT INTO meta VALUES (?, ?) ON CONFLICT(clave) "
                      "DO UPDATE SET valor = excluded.valor", (clave, str(valor)))

    def evento(self, ts_ms: int, tipo: str, detalle: str = "") -> None:
        self.ejecutar("INSERT INTO eventos (ts_ms, tipo, detalle) VALUES (?, ?, ?)",
                      (ts_ms, tipo, detalle[:2000]))

    # --- Pendientes -------------------------------------------------------------

    def agregar_pendiente(self, alerta_id: int, ahora_ms: int, estado: Optional[str]) -> None:
        self.ejecutar("INSERT OR IGNORE INTO pendientes VALUES (?, ?, ?, ?)",
                      (alerta_id, ahora_ms, ahora_ms, estado))

    def pendientes(self) -> list[dict]:
        return self.filas("SELECT * FROM pendientes ORDER BY alerta_id")

    def quitar_pendiente(self, alerta_id: int) -> None:
        self.ejecutar("DELETE FROM pendientes WHERE alerta_id = ?", (alerta_id,))

    def tocar_pendiente(self, alerta_id: int, ahora_ms: int, estado: Optional[str]) -> None:
        self.ejecutar("UPDATE pendientes SET revisado_ms = ?, ultimo_estado = ? "
                      "WHERE alerta_id = ?", (ahora_ms, estado, alerta_id))

    # --- Evidencia --------------------------------------------------------------

    def registrar_caso(self, caso: dict) -> bool:
        cols = ",".join(caso)
        marcas = ",".join("?" * len(caso))
        return self.ejecutar(f"INSERT OR IGNORE INTO casos ({cols}) VALUES ({marcas})",
                             list(caso.values())) == 1

    def caso(self, caso_id: int) -> Optional[dict]:
        filas = self.filas("SELECT * FROM casos WHERE caso_id = ?", (caso_id,))
        return filas[0] if filas else None

    def guardar_contexto(self, caso_id: int, version: str, contexto: dict,
                         sha256: str, ahora_ms: int) -> None:
        self.ejecutar("INSERT OR IGNORE INTO contextos VALUES (?, ?, ?, ?, ?)",
                      (caso_id, version, json.dumps(contexto, ensure_ascii=False,
                                                    sort_keys=True), sha256, ahora_ms))

    def guardar_kronos(self, fila: dict) -> None:
        fila = dict(fila)
        fila["resumen_json"] = json.dumps(fila.get("resumen_json") or {},
                                          ensure_ascii=False, sort_keys=True)
        cols = ",".join(fila)
        self.ejecutar(f"INSERT OR IGNORE INTO kronos ({cols}) VALUES "
                      f"({','.join('?' * len(fila))})", list(fila.values()))

    def guardar_decision(self, fila: dict) -> None:
        cols = ",".join(fila)
        self.ejecutar(f"INSERT OR IGNORE INTO decisiones ({cols}) VALUES "
                      f"({','.join('?' * len(fila))})", list(fila.values()))

    def guardar_etiqueta(self, fila: dict) -> None:
        cols = list(fila)
        actualizar = ",".join(f"{c} = excluded.{c}" for c in cols if c != "caso_id")
        self.ejecutar(
            f"INSERT INTO etiquetas ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
            f"ON CONFLICT(caso_id) DO UPDATE SET {actualizar} WHERE etiquetas.final = 0",
            [fila[c] for c in cols])

    def casos_por_etiquetar(self) -> list[dict]:
        return self.filas(
            "SELECT c.* FROM casos c LEFT JOIN etiquetas e USING (caso_id) "
            "WHERE e.caso_id IS NULL OR e.final = 0 ORDER BY c.as_of_ms")

    def guardar_salud(self, fila: dict) -> None:
        cols = ",".join(fila)
        self.ejecutar(f"INSERT OR IGNORE INTO salud ({cols}) VALUES "
                      f"({','.join('?' * len(fila))})", list(fila.values()))
