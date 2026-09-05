"""
Persistencia SQLite: historial de estados (rolling 24h), log de analisis,
metadata de pares.

No Redis — innecesario para servidor local (latencia I/O extra sin beneficio).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from src.config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_CREATE_SYMBOL_STATES = """
CREATE TABLE IF NOT EXISTS symbol_states (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT    NOT NULL,
    ts_ms      INTEGER NOT NULL,
    state      TEXT    NOT NULL,
    fsm_state  TEXT,
    score      INTEGER,
    tier       TEXT,
    macro      TEXT,
    price      REAL
);
CREATE INDEX IF NOT EXISTS idx_sym_ts ON symbol_states (symbol, ts_ms DESC);
"""

_CREATE_ANALYSIS_LOG = """
CREATE TABLE IF NOT EXISTS analysis_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_ms   INTEGER NOT NULL,
    symbol  TEXT,
    level   TEXT,
    message TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_ts ON analysis_log (ts_ms DESC);
"""

_CREATE_PAIR_META = """
CREATE TABLE IF NOT EXISTS pair_metadata (
    symbol    TEXT PRIMARY KEY,
    vol_24h   REAL,
    updated   INTEGER
);
"""

_CREATE_KLINES = """
CREATE TABLE IF NOT EXISTS klines (
    symbol    TEXT    NOT NULL,
    tf        TEXT    NOT NULL,
    open_time INTEGER NOT NULL,
    o REAL, h REAL, l REAL, c REAL, v REAL,
    PRIMARY KEY (symbol, tf, open_time)
);
"""

_CREATE_OUTCOMES = """
CREATE TABLE IF NOT EXISTS outcomes (
    signal_id     INTEGER PRIMARY KEY,
    symbol        TEXT    NOT NULL,
    ts_open       INTEGER NOT NULL,
    ts_last       INTEGER,
    entry         REAL    NOT NULL,
    take_profit   REAL,
    stop_loss     REAL,
    tp_pct        REAL,
    sl_pct        REAL,
    display_state TEXT,
    tier          TEXT,
    score         INTEGER,
    macro         TEXT,
    taxonomia     TEXT,
    -- Excursiones maximas dentro de la ventana
    mfe_pct       REAL    DEFAULT 0,
    mae_pct       REAL    DEFAULT 0,
    ms_mfe        INTEGER,
    ms_mae        INTEGER,
    -- Primer cruce de cada umbral, en ms desde la apertura. NULL = no llego.
    ms_up_1       INTEGER, ms_up_12 INTEGER, ms_up_2  INTEGER,
    ms_up_32      INTEGER, ms_up_42 INTEGER, ms_up_5  INTEGER,
    ms_up_10      INTEGER,
    ms_dn_1       INTEGER, ms_dn_12 INTEGER, ms_dn_2  INTEGER,
    ms_dn_32      INTEGER, ms_dn_42 INTEGER, ms_dn_5  INTEGER,
    ms_dn_10      INTEGER,
    ms_tp         INTEGER, ms_sl    INTEGER,
    -- Camino hasta +3.2%
    dip_antes_obj REAL,
    forma         TEXT,
    n_velas       INTEGER DEFAULT 0,
    cerrado       INTEGER DEFAULT 0,
    -- 1 = señal que el gate macro suprimio. Se mide pero NO se alerta:
    -- sin esto no hay forma de saber si el gate protege o cuesta dinero.
    sombra        INTEGER DEFAULT 0,
    -- Liquidez en el momento de la señal. Las metricas de impulso son
    -- todas RATIOS, y un ratio no tiene escala: "volumen 1.77x" sobre
    -- 1.195 USDT/min no es el mismo suceso que 1.59x sobre 40.048.
    vol_24h       REAL,
    vol_1m_medio  REAL
);
CREATE INDEX IF NOT EXISTS idx_out_cerrado ON outcomes (cerrado, ts_open DESC);
CREATE INDEX IF NOT EXISTS idx_out_symbol  ON outcomes (symbol, ts_open DESC);
"""

_CREATE_META = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# Version del esquema/semantica de datos. Se sube cuando un cambio hace que
# las filas ya guardadas sean incompatibles con las nuevas.
#   1 -> 2: `klines.v` paso de volumen BASE (kline[5]) a volumen QUOTE
#           (kline[7]), para cuadrar con lo que entrega el WebSocket (k["q"]).
#   2 -> 3: se marcan STALE las señales calificadas contra un precio muy
#           posterior a su apertura (el sistema estuvo apagado en medio).
#   3 -> 4: outcomes.sombra — mide las señales que el gate macro suprime.
#   4 -> 5: outcomes.vol_24h / vol_1m_medio — liquidez en la señal.
#   5 -> 6: umbrales 1.2% y 4.2% (marcadores amarillo y morado del tablero).
SCHEMA_VERSION = 6

_CREATE_SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT    NOT NULL,
    ts_open      INTEGER NOT NULL,
    display_state TEXT,
    tier         TEXT,
    score        INTEGER,
    entry        REAL,
    take_profit  REAL,
    stop_loss    REAL,
    risk_reward  REAL,
    macro        TEXT,
    status       TEXT    NOT NULL DEFAULT 'OPEN',
    ts_close     INTEGER,
    result_pct   REAL
);
CREATE INDEX IF NOT EXISTS idx_sig_status ON signals (status, symbol);
CREATE INDEX IF NOT EXISTS idx_sig_open ON signals (ts_open DESC);
"""


class Database:
    def __init__(self) -> None:
        s = get_settings()
        path = Path(s.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        # Escritura diferida: antes cada vela 1m de cada par hacia INSERT +
        # commit() sincronico en el event loop (~250 commits/minuto, cada uno
        # una syscall bloqueante). Ahora se acumulan y se vuelcan en lote.
        self._pending_klines: list = []
        self._dirty = False
        logger.info(f"SQLite inicializado: {path}")

    # --- Escritura diferida ------------------------------------------------

    def flush(self) -> int:
        """Vuelca klines pendientes y hace commit. Devuelve filas escritas."""
        n = 0
        if self._pending_klines:
            rows, self._pending_klines = self._pending_klines, []
            try:
                self._conn.executemany(
                    """INSERT OR REPLACE INTO klines
                       (symbol, tf, open_time, o, h, l, c, v)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
                n = len(rows)
                self._dirty = True
            except Exception as e:
                logger.debug(f"flush klines error: {e}")
        if self._dirty:
            try:
                self._conn.commit()
                self._dirty = False
            except Exception as e:
                logger.debug(f"flush commit error: {e}")
        return n

    def _init_schema(self) -> None:
        for ddl in (
            _CREATE_SYMBOL_STATES, _CREATE_ANALYSIS_LOG, _CREATE_PAIR_META,
            _CREATE_SIGNALS, _CREATE_KLINES, _CREATE_META, _CREATE_OUTCOMES,
        ):
            self._conn.executescript(ddl)
        self._conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """
        Migraciones por version de esquema.

        v1 -> v2: hasta ahora la hidratacion REST guardaba kline[5] (volumen
        BASE, en moneda) mientras que el WebSocket entrega k["q"] (volumen
        QUOTE, en USDT). Convivian en el mismo buffer y en la misma tabla. Como
        quote = base x precio, para un par de precio alto la diferencia son
        varios ordenes de magnitud: vol_ratio, blow_off y breakout comparan la
        vela actual contra la SMA del buffer, asi que la mezcla los deja sin
        sentido hasta que las velas viejas envejecen y salen.

        No se pueden convertir las filas viejas (haria falta el precio medio
        real de cada vela, que no se guardo), asi que se descartan: el
        hidratador las vuelve a bajar por REST ya en quote.
        """
        row = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
        version = int(row[0]) if row else 0

        if version == SCHEMA_VERSION:
            return

        if version < 2:
            n = self._conn.execute("SELECT COUNT(*) FROM klines").fetchone()[0]
            if n:
                self._conn.execute("DELETE FROM klines")
                logger.warning(
                    f"Migracion v{version}->2: {n} velas descartadas — estaban en "
                    "volumen base y ahora se guarda volumen quote. Se rehidrata por REST."
                )

        if version < 3:
            # Señales cerradas mucho despues de abrirse: el sistema estuvo
            # apagado y al reanudar se calificaron contra el precio del dia,
            # no contra lo que hizo el precio en su momento. Su resultado no
            # significa nada, asi que se sacan de las estadisticas.
            limite_ms = get_settings().signal_expiry_hours * 3600_000 * 2
            cur = self._conn.execute(
                """UPDATE signals SET status = 'STALE', result_pct = NULL
                   WHERE status IN ('TP','SL','EXPIRED')
                     AND ts_close IS NOT NULL
                     AND ts_close - ts_open > ?""",
                (limite_ms,),
            )
            if cur.rowcount:
                logger.warning(
                    f"Migracion v{version}->3: {cur.rowcount} señales marcadas STALE "
                    "(se cerraron con precios de mucho despues; falseaban el win rate)"
                )

        if version < 4:
            cols = [r[1] for r in self._conn.execute("PRAGMA table_info(outcomes)")]
            if "sombra" not in cols:
                self._conn.execute(
                    "ALTER TABLE outcomes ADD COLUMN sombra INTEGER DEFAULT 0"
                )
                logger.info("Migracion v3->4: columna outcomes.sombra añadida")

        if version < 5:
            cols = [r[1] for r in self._conn.execute("PRAGMA table_info(outcomes)")]
            for col in ("vol_24h", "vol_1m_medio"):
                if col not in cols:
                    self._conn.execute(f"ALTER TABLE outcomes ADD COLUMN {col} REAL")
            logger.info("Migracion v4->5: columnas de liquidez añadidas a outcomes")

        if version < 6:
            cols = [r[1] for r in self._conn.execute("PRAGMA table_info(outcomes)")]
            nuevas = [c for c in ("ms_up_12", "ms_up_42", "ms_dn_12", "ms_dn_42")
                      if c not in cols]
            for col in nuevas:
                self._conn.execute(f"ALTER TABLE outcomes ADD COLUMN {col} INTEGER")
            if nuevas:
                logger.info(
                    f"Migracion v5->6: umbrales 1.2%/4.2% añadidos ({len(nuevas)} columnas)"
                )

        self._conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self._conn.commit()
        logger.info(f"Esquema de la DB en version {SCHEMA_VERSION}")

    def save_state(
        self,
        symbol: str,
        ts_ms: int,
        state: str,
        fsm_state: str,
        score: int,
        tier: str,
        macro: str,
        price: float,
    ) -> None:
        self._conn.execute(
            """INSERT INTO symbol_states
               (symbol, ts_ms, state, fsm_state, score, tier, macro, price)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, ts_ms, state, fsm_state, score, tier, macro, price),
        )
        self._dirty = True  # commit diferido en flush()

    def get_history(self, symbol: str, hours: int = 24) -> List[dict]:
        cutoff = int((time.time() - hours * 3600) * 1000)
        cur = self._conn.execute(
            """SELECT ts_ms, state, fsm_state, score, tier, macro, price
               FROM symbol_states
               WHERE symbol = ? AND ts_ms >= ?
               ORDER BY ts_ms ASC""",
            (symbol, cutoff),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def prune_old(self) -> dict:
        """Purga rolling: symbol_states (30d), analysis_log (14d), señales cerradas (30d)."""
        s = get_settings()
        now = time.time()
        cut_states = int((now - s.history_rolling_days * 86400) * 1000)
        cut_logs = int((now - s.log_retention_days * 86400) * 1000)
        cut_sigs = int((now - s.history_rolling_days * 86400) * 1000)

        c1 = self._conn.execute("DELETE FROM symbol_states WHERE ts_ms < ?", (cut_states,))
        c2 = self._conn.execute("DELETE FROM analysis_log WHERE ts_ms < ?", (cut_logs,))
        c3 = self._conn.execute(
            "DELETE FROM signals WHERE status != 'OPEN' AND ts_open < ?", (cut_sigs,)
        )
        self._conn.commit()
        kl = self.prune_klines()
        deleted = {
            "symbol_states": c1.rowcount, "analysis_log": c2.rowcount,
            "signals": c3.rowcount, "klines": kl,
        }
        total = sum(deleted.values())
        if total:
            logger.info(
                f"SQLite purga: {deleted['symbol_states']} estados, "
                f"{deleted['analysis_log']} logs, {deleted['signals']} señales, "
                f"{deleted['klines']} velas"
            )
        return deleted

    def log_analysis(self, symbol: Optional[str], level: str, message: str) -> None:
        ts_ms = int(time.time() * 1000)
        self._conn.execute(
            "INSERT INTO analysis_log (ts_ms, symbol, level, message) VALUES (?, ?, ?, ?)",
            (ts_ms, symbol, level, message),
        )
        self._dirty = True  # commit diferido en flush()

    def get_logs(self, limit: int = 200) -> List[dict]:
        cur = self._conn.execute(
            "SELECT ts_ms, symbol, level, message FROM analysis_log ORDER BY ts_ms DESC LIMIT ?",
            (limit,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def upsert_pair_meta(self, symbol: str, vol_24h: float) -> None:
        ts = int(time.time())
        self._conn.execute(
            """INSERT INTO pair_metadata (symbol, vol_24h, updated)
               VALUES (?, ?, ?)
               ON CONFLICT(symbol) DO UPDATE SET vol_24h=excluded.vol_24h, updated=excluded.updated""",
            (symbol, vol_24h, ts),
        )
        self._conn.commit()

    def get_pair_meta(self, symbol: str) -> Optional[dict]:
        """Metadata del par (volumen 24h). None si no esta registrado."""
        cur = self._conn.execute(
            "SELECT symbol, vol_24h, updated FROM pair_metadata WHERE symbol = ?",
            (symbol,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"symbol": row[0], "vol_24h": row[1], "updated": row[2]}

    # --- Señales (auto-evaluacion) -------------------------------------------

    def has_open_signal(self, symbol: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM signals WHERE symbol = ? AND status = 'OPEN' LIMIT 1",
            (symbol,),
        )
        return cur.fetchone() is not None

    def open_signal(
        self,
        symbol: str,
        ts_open: int,
        display_state: str,
        tier: str,
        score: int,
        entry: float,
        take_profit: float,
        stop_loss: float,
        risk_reward: float,
        macro: str,
    ) -> int:
        cur = self._conn.execute(
            """INSERT INTO signals
               (symbol, ts_open, display_state, tier, score, entry,
                take_profit, stop_loss, risk_reward, macro, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')""",
            (symbol, ts_open, display_state, tier, score, entry,
             take_profit, stop_loss, risk_reward, macro),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_open_signals(self, symbol: Optional[str] = None) -> List[dict]:
        if symbol:
            cur = self._conn.execute(
                "SELECT * FROM signals WHERE status = 'OPEN' AND symbol = ?", (symbol,)
            )
        else:
            cur = self._conn.execute("SELECT * FROM signals WHERE status = 'OPEN'")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close_signal(self, signal_id: int, status: str, result_pct: float, ts_close: int) -> None:
        self._conn.execute(
            "UPDATE signals SET status = ?, result_pct = ?, ts_close = ? WHERE id = ?",
            (status, result_pct, ts_close, signal_id),
        )
        self._conn.commit()

    # --- Outcomes (seguimiento del camino de cada señal) ---------------------

    def abrir_outcome(self, row: dict) -> None:
        """Registra el outcome de una señal recien abierta (idempotente)."""
        cols = ", ".join(row.keys())
        marks = ", ".join("?" * len(row))
        self._conn.execute(
            f"INSERT OR IGNORE INTO outcomes ({cols}) VALUES ({marks})",
            tuple(row.values()),
        )
        self._dirty = True

    def get_outcomes_abiertos(self) -> List[dict]:
        cur = self._conn.execute("SELECT * FROM outcomes WHERE cerrado = 0")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def guardar_outcome(self, signal_id: int, campos: dict) -> None:
        if not campos:
            return
        sets = ", ".join(f"{k} = ?" for k in campos)
        self._conn.execute(
            f"UPDATE outcomes SET {sets} WHERE signal_id = ?",
            (*campos.values(), signal_id),
        )
        self._dirty = True

    def get_outcomes(self, solo_cerrados: bool = True, limit: int = 5000) -> List[dict]:
        cur = self._conn.execute(
            "SELECT * FROM outcomes"
            + (" WHERE cerrado = 1" if solo_cerrados else "")
            + " ORDER BY ts_open DESC LIMIT ?",
            (limit,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def get_signal_stats(self) -> dict:
        cur = self._conn.execute(
            """SELECT status, COUNT(*), AVG(result_pct)
               FROM signals GROUP BY status"""
        )
        by_status = {row[0]: {"count": row[1], "avg_pct": row[2]} for row in cur.fetchall()}
        tp = by_status.get("TP", {}).get("count", 0)
        sl = by_status.get("SL", {}).get("count", 0)
        expired = by_status.get("EXPIRED", {}).get("count", 0)
        open_n = by_status.get("OPEN", {}).get("count", 0)
        closed = tp + sl + expired
        win_rate = (tp / closed * 100.0) if closed else 0.0

        cur2 = self._conn.execute(
            "SELECT AVG(result_pct) FROM signals WHERE status IN ('TP','SL','EXPIRED')"
        )
        avg_result = cur2.fetchone()[0] or 0.0

        return {
            "total": closed + open_n,
            "open": open_n,
            "closed": closed,
            "tp": tp,
            "sl": sl,
            "expired": expired,
            "win_rate": round(win_rate, 1),
            "avg_result_pct": round(avg_result, 2),
        }

    def get_recent_signals(self, limit: int = 50) -> List[dict]:
        cur = self._conn.execute(
            "SELECT * FROM signals ORDER BY ts_open DESC LIMIT ?", (limit,)
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # --- Klines (checkpoint de velas OHLCV) ----------------------------------

    def save_kline(self, symbol: str, tf: str, candle) -> None:
        """Encola una vela cerrada (idempotente). Se escribe en flush()."""
        self._pending_klines.append(
            (symbol, tf, candle.t, candle.o, candle.h, candle.l, candle.c, candle.v)
        )
        if len(self._pending_klines) >= get_settings().db_flush_max_pending:
            self.flush()

    def save_klines(self, symbol: str, tf: str, candles: list) -> None:
        """Guarda un lote de velas (idempotente, una sola transaccion)."""
        if not candles:
            return
        self._conn.executemany(
            """INSERT OR REPLACE INTO klines (symbol, tf, open_time, o, h, l, c, v)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(symbol, tf, c.t, c.o, c.h, c.l, c.c, c.v) for c in candles],
        )
        self._conn.commit()

    def get_klines(self, symbol: str, tf: str, limit: int) -> List[dict]:
        """Ultimas N velas guardadas de un symbol/tf, en orden cronologico ascendente."""
        cur = self._conn.execute(
            """SELECT open_time, o, h, l, c, v FROM klines
               WHERE symbol = ? AND tf = ?
               ORDER BY open_time DESC LIMIT ?""",
            (symbol, tf, limit),
        )
        rows = cur.fetchall()
        rows.reverse()  # cronologico ascendente
        return [
            {"t": r[0], "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]}
            for r in rows
        ]

    def last_kline_time(self, symbol: str, tf: str) -> Optional[int]:
        """open_time de la vela mas reciente guardada (None si no hay)."""
        cur = self._conn.execute(
            "SELECT MAX(open_time) FROM klines WHERE symbol = ? AND tf = ?",
            (symbol, tf),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else None

    def prune_klines(self) -> int:
        """Purga klines viejas: 1m/5m/15m a corto plazo, 1h/4h/1d a largo plazo."""
        now = time.time()
        cortos = int((now - 3 * 86400) * 1000)     # 1m/5m/15m: 3 dias
        largos = int((now - 400 * 86400) * 1000)   # 1h/4h/1d: ~13 meses
        c1 = self._conn.execute(
            "DELETE FROM klines WHERE tf IN ('1m','5m','15m') AND open_time < ?", (cortos,)
        )
        c2 = self._conn.execute(
            "DELETE FROM klines WHERE tf IN ('1h','4h','1d') AND open_time < ?", (largos,)
        )
        self._conn.commit()
        return c1.rowcount + c2.rowcount

    def close(self) -> None:
        """Vuelca lo pendiente antes de cerrar: con escritura diferida, cerrar
        sin flush pierde todo lo acumulado desde el ultimo volcado."""
        try:
            self.flush()
        except Exception as e:
            logger.debug(f"close/flush error: {e}")
        self._conn.close()


# Instancia global (inicializada en main.py)
_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


def init_db() -> Database:
    global _db
    _db = Database()
    return _db
