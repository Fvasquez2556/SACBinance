"""
Ingesta de historico desde Binance Data Vision -> SQLite.

Por que no se usa la DB de produccion
-------------------------------------
La tabla `klines` del sistema en vivo no sirve como base de un backtest:
purga 1m/5m/15m a los 3 dias, solo contiene pares que pasaron el filtro de
liquidez del universo en su momento (sesgo de seleccion), tiene huecos por
caidas del servidor, y su columna de volumen esta contaminada por la mezcla
base/quote anterior al fix. Esto descarga historia limpia y completa.

Fuente
------
https://data.binance.vision — archivos publicos, gratuitos, sin rate limit.
    mensual: /data/spot/monthly/klines/{SYM}/{TF}/{SYM}-{TF}-{YYYY-MM}.zip
    diario:  /data/spot/daily/klines/{SYM}/{TF}/{SYM}-{TF}-{YYYY-MM-DD}.zip
Cada .zip tiene su .CHECKSUM (SHA256) al lado.

Trampas reales que este script maneja
-------------------------------------
1. TIMESTAMPS EN MICROSEGUNDOS. Binance migro los archivos a precision de
   microsegundos. Los archivos viejos vienen en ms y los nuevos en us. Si no
   se normaliza, las fechas quedan en el ano 57000 y el join por dia falla.
2. CABECERA OPCIONAL. Los archivos recientes traen fila de encabezado; los
   viejos no. Se detecta por si el primer campo parsea como numero.
3. 404 LEGITIMO. Un par que no cotizaba ese mes devuelve 404. No es un error.
4. VOLUMEN. Se guardan las cuatro columnas (base, quote, taker buy base,
   taker buy quote) y el numero de trades. La lección del bug base/quote:
   nunca guardar solo una y tener que adivinar despues cual era.

Uso
---
    python -m research.datavision --symbols BTCUSDT,ETHUSDT \\
        --interval 1m --start 2026-03 --end 2026-08

    python -m research.datavision --symbols-file pares.txt \\
        --interval 1m --start 2026-01 --end 2026-08 --workers 8

    python -m research.datavision --symbols BTCUSDT --interval 1m \\
        --start 2026-08 --end 2026-09 --dry-run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import sqlite3
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://data.binance.vision/data/spot"
UA = {"User-Agent": "sacbinance-research/1.0"}

# Umbral para distinguir ms de us. 1e14 ms = ano 5138; ningun timestamp en ms
# legitimo lo supera, y todo timestamp en us actual si.
_US_THRESHOLD = 1e14


# =============================================================================
#  Esquema
# =============================================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS klines (
    symbol          TEXT    NOT NULL,
    interval        TEXT    NOT NULL,
    open_time       INTEGER NOT NULL,      -- ms UTC, normalizado
    open            REAL    NOT NULL,
    high            REAL    NOT NULL,
    low             REAL    NOT NULL,
    close           REAL    NOT NULL,
    volume          REAL,                  -- base asset
    close_time      INTEGER,
    quote_volume    REAL,                  -- quote asset (USDT)
    trades          INTEGER,
    taker_buy_base  REAL,
    taker_buy_quote REAL,
    PRIMARY KEY (symbol, interval, open_time)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_kl_time ON klines (interval, open_time);

-- Control de reanudacion: que (symbol, interval, periodo) ya se ingirio.
CREATE TABLE IF NOT EXISTS ingest_log (
    symbol     TEXT    NOT NULL,
    interval   TEXT    NOT NULL,
    period     TEXT    NOT NULL,           -- 'YYYY-MM' o 'YYYY-MM-DD'
    kind       TEXT    NOT NULL,           -- 'monthly' | 'daily'
    rows       INTEGER,
    status     TEXT,                       -- 'OK' | 'MISSING' | 'ERROR'
    ts_ms      INTEGER,
    PRIMARY KEY (symbol, interval, period)
);
"""


def abrir_db(path: str | Path) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# =============================================================================
#  Descarga
# =============================================================================

@dataclass
class Tarea:
    symbol: str
    interval: str
    period: str        # 'YYYY-MM' o 'YYYY-MM-DD'
    kind: str          # 'monthly' | 'daily'

    @property
    def filename(self) -> str:
        return f"{self.symbol}-{self.interval}-{self.period}.zip"

    @property
    def url(self) -> str:
        return f"{BASE}/{self.kind}/klines/{self.symbol}/{self.interval}/{self.filename}"

    @property
    def checksum_url(self) -> str:
        return self.url + ".CHECKSUM"


def _get(url: str, timeout: int = 90) -> Optional[bytes]:
    """Devuelve el cuerpo, o None si es 404 (recurso inexistente, no error)."""
    try:
        with urlopen(Request(url, headers=UA), timeout=timeout) as r:
            return r.read()
    except HTTPError as e:
        if e.code == 404:
            return None
        raise


def descargar(t: Tarea, verificar: bool = True, reintentos: int = 3) -> Optional[bytes]:
    ultimo_error: Optional[Exception] = None
    for intento in range(reintentos):
        try:
            blob = _get(t.url)
            if blob is None:
                return None  # 404: el par no cotizaba ese periodo
            if verificar:
                chk = _get(t.checksum_url)
                if chk:
                    esperado = chk.decode("utf-8", "replace").split()[0].strip().lower()
                    real = hashlib.sha256(blob).hexdigest()
                    if esperado != real:
                        raise ValueError(f"checksum SHA256 no coincide para {t.filename}")
            return blob
        except (URLError, HTTPError, ValueError, TimeoutError) as e:
            ultimo_error = e
            if intento < reintentos - 1:
                time.sleep(2 ** intento)
    raise RuntimeError(f"fallo tras {reintentos} intentos: {t.filename}: {ultimo_error}")


# =============================================================================
#  Parseo
# =============================================================================

def _normalizar_ts(v: float) -> int:
    """Archivos viejos en ms, nuevos en microsegundos. Normaliza todo a ms."""
    return int(v // 1000) if v >= _US_THRESHOLD else int(v)


def _es_cabecera(fila: Sequence[str]) -> bool:
    if not fila:
        return True
    try:
        float(fila[0])
        return False
    except (ValueError, TypeError):
        return True


def parsear_zip(blob: bytes, symbol: str, interval: str) -> List[tuple]:
    """ZIP de Data Vision -> filas listas para insertar."""
    filas: List[tuple] = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        nombres = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not nombres:
            return filas
        with z.open(nombres[0]) as fh:
            texto = io.TextIOWrapper(fh, encoding="utf-8", newline="")
            for fila in csv.reader(texto):
                if len(fila) < 11 or _es_cabecera(fila):
                    continue
                try:
                    filas.append((
                        symbol, interval,
                        _normalizar_ts(float(fila[0])),   # open_time
                        float(fila[1]), float(fila[2]),   # open, high
                        float(fila[3]), float(fila[4]),   # low, close
                        float(fila[5]),                   # volume (base)
                        _normalizar_ts(float(fila[6])),   # close_time
                        float(fila[7]),                   # quote_volume
                        int(float(fila[8])),              # trades
                        float(fila[9]),                   # taker_buy_base
                        float(fila[10]),                  # taker_buy_quote
                    ))
                except (ValueError, IndexError):
                    continue
    return filas


# =============================================================================
#  Periodos
# =============================================================================

def _mes_siguiente(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def generar_periodos(start: str, end: str) -> List[Tuple[str, str]]:
    """
    Devuelve [(kind, period)] cubriendo [start, end].

    Usa archivos MENSUALES para los meses completos (mucho menos requests) y
    DIARIOS para el mes en curso, que aun no tiene archivo mensual publicado.
    """
    hoy = datetime.now(timezone.utc).date()
    ini = datetime.strptime(start, "%Y-%m").date().replace(day=1)
    fin = datetime.strptime(end, "%Y-%m").date().replace(day=1)
    mes_actual = hoy.replace(day=1)

    periodos: List[Tuple[str, str]] = []
    cur = ini
    while cur <= fin:
        if cur < mes_actual:
            periodos.append(("monthly", cur.strftime("%Y-%m")))
        else:
            # Mes en curso: dias sueltos hasta ayer (hoy aun no esta cerrado)
            d = cur
            while d < hoy:
                periodos.append(("daily", d.strftime("%Y-%m-%d")))
                d += timedelta(days=1)
        cur = _mes_siguiente(cur)
    return periodos


# =============================================================================
#  Orquestacion
# =============================================================================

def _ya_ingerido(conn: sqlite3.Connection, t: Tarea) -> bool:
    cur = conn.execute(
        "SELECT status FROM ingest_log WHERE symbol=? AND interval=? AND period=?",
        (t.symbol, t.interval, t.period),
    )
    row = cur.fetchone()
    return row is not None and row[0] in ("OK", "MISSING")


def _marcar(conn: sqlite3.Connection, t: Tarea, filas: int, status: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO ingest_log
           (symbol, interval, period, kind, rows, status, ts_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (t.symbol, t.interval, t.period, t.kind, filas, status,
         int(time.time() * 1000)),
    )


def ingerir(
    symbols: Sequence[str],
    interval: str,
    start: str,
    end: str,
    db_path: str,
    workers: int = 6,
    verificar: bool = True,
    forzar: bool = False,
    dry_run: bool = False,
) -> dict:
    conn = abrir_db(db_path)
    periodos = generar_periodos(start, end)

    tareas = [
        Tarea(sym, interval, per, kind)
        for sym in symbols
        for kind, per in periodos
    ]
    if not forzar:
        tareas = [t for t in tareas if not _ya_ingerido(conn, t)]

    total = len(tareas)
    print(f"Simbolos: {len(symbols)} | periodos: {len(periodos)} | "
          f"descargas pendientes: {total}")
    if dry_run:
        for t in tareas[:20]:
            print("  ", t.url)
        if total > 20:
            print(f"   ... y {total - 20} mas")
        return {"tareas": total, "dry_run": True}
    if total == 0:
        print("Nada nuevo que descargar.")
        return {"tareas": 0}

    stats = {"ok": 0, "missing": 0, "error": 0, "filas": 0}
    t0 = time.monotonic()
    hechas = 0

    def trabajo(t: Tarea):
        blob = descargar(t, verificar=verificar)
        if blob is None:
            return t, None
        return t, parsear_zip(blob, t.symbol, t.interval)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futuros = {pool.submit(trabajo, t): t for t in tareas}
        for fut in as_completed(futuros):
            t = futuros[fut]
            hechas += 1
            try:
                _, filas = fut.result()
            except Exception as e:
                stats["error"] += 1
                _marcar(conn, t, 0, "ERROR")
                print(f"  ✗ {t.filename}: {e}")
                continue

            if filas is None:
                stats["missing"] += 1
                _marcar(conn, t, 0, "MISSING")
            else:
                conn.executemany(
                    """INSERT OR REPLACE INTO klines
                       (symbol, interval, open_time, open, high, low, close,
                        volume, close_time, quote_volume, trades,
                        taker_buy_base, taker_buy_quote)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    filas,
                )
                stats["ok"] += 1
                stats["filas"] += len(filas)

            if hechas % 25 == 0 or hechas == total:
                conn.commit()
                el = time.monotonic() - t0
                print(f"  {hechas}/{total} ({hechas/total*100:.0f}%) | "
                      f"{stats['filas']:,} velas | {el:.0f}s")

    conn.commit()
    el = time.monotonic() - t0
    print(f"\nListo en {el:.0f}s — {stats['ok']} archivos, "
          f"{stats['missing']} inexistentes (404), {stats['error']} errores, "
          f"{stats['filas']:,} velas insertadas")
    return stats


def resumen(db_path: str) -> None:
    conn = abrir_db(db_path)
    cur = conn.execute("""
        SELECT interval, COUNT(DISTINCT symbol), COUNT(*),
               MIN(open_time), MAX(open_time)
        FROM klines GROUP BY interval
    """)
    filas = cur.fetchall()
    if not filas:
        print("La base esta vacia.")
        return
    print(f"{'TF':<6} {'pares':>7} {'velas':>14}  rango")
    for tf, npares, nvelas, tmin, tmax in filas:
        d0 = datetime.fromtimestamp(tmin / 1000, timezone.utc).strftime("%Y-%m-%d")
        d1 = datetime.fromtimestamp(tmax / 1000, timezone.utc).strftime("%Y-%m-%d")
        print(f"{tf:<6} {npares:>7} {nvelas:>14,}  {d0} → {d1}")

    tam = Path(db_path).stat().st_size / 1e6
    print(f"\nTamano: {tam:,.0f} MB")


# =============================================================================
#  CLI
# =============================================================================

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Ingesta Binance Data Vision -> SQLite")
    ap.add_argument("--symbols", help="lista separada por comas: BTCUSDT,ETHUSDT")
    ap.add_argument("--symbols-file", help="archivo con un simbolo por linea")
    ap.add_argument("--interval", default="1m",
                    help="1s,1m,3m,5m,15m,1h,4h,1d (default: 1m)")
    ap.add_argument("--start", help="mes inicial YYYY-MM")
    ap.add_argument("--end", help="mes final YYYY-MM")
    ap.add_argument("--db", default="research/data/history.db")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-checksum", action="store_true",
                    help="omitir verificacion SHA256 (mas rapido, menos seguro)")
    ap.add_argument("--force", action="store_true", help="reingerir aunque ya exista")
    ap.add_argument("--dry-run", action="store_true", help="solo listar URLs")
    ap.add_argument("--summary", action="store_true", help="resumen de lo ya ingerido")
    a = ap.parse_args(argv)

    if a.summary:
        resumen(a.db)
        return 0

    symbols: List[str] = []
    if a.symbols:
        symbols = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    elif a.symbols_file:
        symbols = [
            l.strip().upper()
            for l in Path(a.symbols_file).read_text().splitlines()
            if l.strip() and not l.startswith("#")
        ]
    if not symbols:
        ap.error("hace falta --symbols o --symbols-file")
    if not a.start or not a.end:
        ap.error("hacen falta --start y --end (formato YYYY-MM)")

    ingerir(
        symbols=symbols, interval=a.interval, start=a.start, end=a.end,
        db_path=a.db, workers=a.workers, verificar=not a.no_checksum,
        forzar=a.force, dry_run=a.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
