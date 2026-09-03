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
        logger.info(f"SQLite inicializado: {path}")

    def _init_schema(self) -> None:
        for ddl in (
            _CREATE_SYMBOL_STATES, _CREATE_ANALYSIS_LOG, _CREATE_PAIR_META,
            _CREATE_SIGNALS, _CREATE_KLINES,
        ):
            self._conn.executescript(ddl)
        self._conn.commit()

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
        self._conn.commit()

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
        self._conn.commit()

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
        """Guarda/actualiza una vela cerrada (idempotente)."""
        self._conn.execute(
            """INSERT OR REPLACE INTO klines (symbol, tf, open_time, o, h, l, c, v)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, tf, candle.t, candle.o, candle.h, candle.l, candle.c, candle.v),
        )
        self._conn.commit()

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
