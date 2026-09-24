"""
La base de SACBinance, vista desde fuera y sin poder tocarla.

Dos cerrojos independientes, para que un error de este servicio no pueda
convertirse en un error de SAC:

1. La conexion se abre con `mode=ro`: el fichero se abre en solo lectura a
   nivel de sistema operativo.
2. `PRAGMA query_only=ON`: SQLite rechaza cualquier escritura aunque el primer
   cerrojo fallara.

Nunca se instancia `Database()` ni nada de `backend/src/persistence`: esas
clases crean tablas y migran. Cada consulta es corta y sin transaccion
explicita, para no retener el WAL de SAC.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000,
         "4h": 14_400_000, "1d": 86_400_000}

# Lo que tiene que existir para poder leer un aviso. Si falta, el servicio no
# intenta arreglarlo: avisa de la incompatibilidad y espera.
COLUMNAS_REQUERIDAS = {
    "alertas_emitidas": {"id", "ts_ms", "symbol", "entry", "take_profit",
                         "stop_loss", "telegram"},
    "notificacion_planes": {"alerta_id", "ts_activado", "entry", "take_profit",
                            "stop_loss", "contexto"},
    "klines": {"symbol", "tf", "open_time", "o", "h", "l", "c", "v"},
}


class IncompatibilidadFuente(RuntimeError):
    pass


def conectar_solo_lectura(ruta: Path) -> sqlite3.Connection:
    ruta = Path(ruta).resolve()
    if not ruta.is_file():
        raise FileNotFoundError(f"no existe la base de SAC: {ruta}")
    conn = sqlite3.connect(f"{ruta.as_uri()}?mode=ro", uri=True, timeout=5,
                           check_same_thread=False)
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA busy_timeout = 2000")
    return conn


def _uno(conn: sqlite3.Connection, sql: str, args: Iterable = ()):
    """Primera fila o None. `fetchall` y no `fetchone`: la sentencia termina y no
    deja abierta una transaccion de lectura que impida a SAC hacer checkpoint."""
    filas = conn.execute(sql, tuple(args)).fetchall()
    return filas[0] if filas else None


def _filas(conn: sqlite3.Connection, sql: str, args: Iterable = ()) -> list[dict]:
    cur = conn.execute(sql, tuple(args))
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


class FuenteSAC:
    def __init__(self, ruta: Path) -> None:
        self.ruta = Path(ruta)
        self.conn = conectar_solo_lectura(self.ruta)

    def cerrar(self) -> None:
        self.conn.close()

    # --- Compatibilidad -------------------------------------------------------

    def comprobar_esquema(self) -> dict:
        faltan = {}
        for tabla, cols in COLUMNAS_REQUERIDAS.items():
            hay = {r["name"] for r in _filas(self.conn, f"PRAGMA table_info({tabla})")}
            if cols - hay:
                faltan[tabla] = sorted(cols - hay)
        if faltan:
            raise IncompatibilidadFuente(f"faltan columnas en SAC: {faltan}")
        version = _uno(self.conn, "SELECT value FROM schema_meta WHERE key = 'version'")
        opcionales = {t: bool(_uno(self.conn, "SELECT 1 FROM sqlite_master "
                                              "WHERE type='table' AND name=?", (t,)))
                      for t in ("planes",)}
        return {"schema_version": version[0] if version else None, **opcionales}

    # --- Descubrimiento de avisos ------------------------------------------------

    def alertas_desde(self, ultimo_id: int, limite: int = 100) -> list[dict]:
        return _filas(self.conn,
                      "SELECT id, ts_ms, symbol, telegram FROM alertas_emitidas "
                      "WHERE id > ? ORDER BY id LIMIT ?", (ultimo_id, limite))

    def estado_telegram(self, ids: list[int]) -> dict[int, Optional[str]]:
        if not ids:
            return {}
        marcas = ",".join("?" * len(ids))
        return {r["id"]: r["telegram"] for r in _filas(
            self.conn, f"SELECT id, telegram FROM alertas_emitidas WHERE id IN ({marcas})", ids)}

    def ultimo_id(self) -> int:
        fila = _uno(self.conn, "SELECT MAX(id) FROM alertas_emitidas")
        return int(fila[0] or 0)

    # --- Un aviso completo ----------------------------------------------------------

    def aviso(self, alerta_id: int) -> Optional[dict]:
        """
        La alerta, el plan que se notifico y, si existe, el plan de la fase 1.

        `notificacion_planes` manda: son los niveles que el operador recibio y
        el momento en que se activo el aviso. `planes` aporta la identidad del
        episodio y el snapshot plano de SAC en la creacion del plan.
        """
        alerta = _filas(self.conn, "SELECT * FROM alertas_emitidas WHERE id = ?", (alerta_id,))
        notif = _filas(self.conn, "SELECT * FROM notificacion_planes WHERE alerta_id = ?",
                       (alerta_id,))
        if not alerta or not notif:
            return None
        plan = []
        try:
            plan = _filas(self.conn, "SELECT * FROM planes WHERE legacy_alerta_id = ?",
                          (alerta_id,))
        except sqlite3.OperationalError:
            pass
        return {"alerta": alerta[0], "notificacion": notif[0],
                "plan": plan[0] if plan else None}

    # --- Velas ------------------------------------------------------------------------

    def velas(self, symbol: str, tf: str, desde_ms: int, hasta_ms: int) -> list[tuple]:
        """(open_time, o, h, l, c, v) con apertura en [desde, hasta]. v es USDT."""
        return self.conn.execute(
            "SELECT open_time, o, h, l, c, v FROM klines WHERE symbol = ? AND tf = ? "
            "AND open_time >= ? AND open_time <= ? ORDER BY open_time",
            (symbol, tf, desde_ms, hasta_ms)).fetchall()

    def velas_cerradas(self, symbol: str, tf: str, as_of_ms: int, n: int) -> list[tuple]:
        """Las ultimas `n` velas CERRADAS antes de `as_of_ms`. La vela en curso nunca entra."""
        paso = TF_MS[tf]
        ultima_apertura = as_of_ms - paso      # cerrada si apertura + paso <= as_of
        filas = self.conn.execute(
            "SELECT open_time, o, h, l, c, v FROM klines WHERE symbol = ? AND tf = ? "
            "AND open_time <= ? ORDER BY open_time DESC LIMIT ?",
            (symbol, tf, ultima_apertura, n)).fetchall()
        return filas[::-1]

    def edad_ultima_vela_ms(self, ahora_ms: int) -> Optional[int]:
        """Cuanto hace que cerro la vela de 1 m mas reciente que SAC ya guardo."""
        fila = _uno(self.conn, "SELECT MAX(open_time) FROM klines WHERE tf = '1m'")
        if not fila or fila[0] is None:
            return None
        return ahora_ms - (int(fila[0]) + 60_000)
