"""
Hidratacion REST inicial CON CHECKPOINT.

En vez de re-descargar toda la historia en cada arranque, el sistema guarda
las velas en SQLite (tabla klines). Al iniciar:
  - Si hay velas guardadas y recientes -> carga el cache y descarga solo el
    "gap" (desde la ultima vela guardada hasta ahora).
  - Si no hay cache o quedo obsoleto (apagon largo) -> descarga completo.

Esto reduce drasticamente el tiempo de arranque y las llamadas REST en
reinicios frecuentes.
"""
from __future__ import annotations

import asyncio
import time
from typing import List

import aiohttp

from src.config.settings import get_settings
from src.state.symbol_state import Candle
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Milisegundos por vela de cada TF
_TF_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

_TFS_ORDER = ["1m", "5m", "15m", "1h", "4h", "1d"]

# Contadores globales del ultimo hydrate_all (para logging)
_stats = {"checkpoint": 0, "completo": 0, "velas_rest": 0, "velas_cache": 0}


def _buffer_size(s, tf: str) -> int:
    return getattr(s, f"candle_buffer_{tf}", 200)


async def _fetch_klines_raw(
    session: aiohttp.ClientSession,
    symbol: str,
    interval: str,
    limit: int,
    base_url: str,
) -> list:
    url = f"{base_url}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": min(max(limit, 1), 1000)}
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
            r.raise_for_status()
            return await r.json()
    except Exception as e:
        logger.debug(f"klines {symbol}/{interval} error: {e}")
        return []


def _raw_to_candles(raw: list) -> List[Candle]:
    out = []
    for k in raw:
        try:
            out.append(Candle(
                t=int(k[0]), o=float(k[1]), h=float(k[2]),
                l=float(k[3]), c=float(k[4]), v=float(k[5]),
            ))
        except (IndexError, ValueError):
            continue
    return out


async def _hydrate_tf(
    symbol: str, tf: str, engine, db,
    session: aiohttp.ClientSession, base_url: str,
) -> None:
    s = get_settings()
    buffer_size = _buffer_size(s, tf)
    tf_ms = _TF_MS.get(tf, 60_000)
    now_ms = int(time.time() * 1000)

    # 1. Cargar lo que haya en el checkpoint
    cached_rows = db.get_klines(symbol, tf, buffer_size) if db is not None else []
    cached = [Candle(t=r["t"], o=r["o"], h=r["h"], l=r["l"], c=r["c"], v=r["v"])
              for r in cached_rows]

    # 2. Decidir: checkpoint (solo el gap) o descarga completa
    if cached:
        last_t = cached[-1].t
        missing = int((now_ms - last_t) / tf_ms)
        if missing < buffer_size:
            fetch_n = min(max(missing + 5, 5), buffer_size)
            modo = "checkpoint"
        else:
            fetch_n = buffer_size
            modo = "completo"
    else:
        fetch_n = buffer_size
        modo = "completo"

    # 3. Descargar (solo el gap, o el buffer completo)
    raw = await _fetch_klines_raw(session, symbol, tf, fetch_n, base_url)
    nuevas = _raw_to_candles(raw)
    # Descartar la vela en curso (aun abierta)
    nuevas = [c for c in nuevas if c.t + tf_ms <= now_ms]

    # 4. Fusionar cache + nuevas (dedup por open_time)
    merged = {c.t: c for c in cached}
    for c in nuevas:
        merged[c.t] = c
    final = sorted(merged.values(), key=lambda c: c.t)[-buffer_size:]

    # 5. Persistir lo descargado en el checkpoint
    if db is not None and nuevas:
        try:
            db.save_klines(symbol, tf, nuevas)
        except Exception as e:
            logger.debug(f"[{symbol}/{tf}] save_klines error: {e}")

    # 6. Cargar al engine
    if tf == "1m":
        engine.preload_1m(symbol, final)
    else:
        engine.preload_htf(symbol, tf, final)

    _stats[modo] += 1
    _stats["velas_rest"] += len(nuevas)
    _stats["velas_cache"] += len(cached)


async def _hydrate_symbol(
    symbol: str, engine, db,
    session: aiohttp.ClientSession, sem: asyncio.Semaphore, base_url: str,
) -> None:
    async with sem:
        for tf in _TFS_ORDER:
            await _hydrate_tf(symbol, tf, engine, db, session, base_url)


async def hydrate_all(symbols: List[str], engine, db=None) -> None:
    """
    Hidrata todos los simbolos. Usa el checkpoint SQLite cuando es posible:
    descarga solo el gap desde la ultima vela guardada.
    """
    s = get_settings()
    sem = asyncio.Semaphore(s.hydration_concurrency)
    base_url = s.binance_rest_base.rstrip("/")
    total = len(symbols)
    start = time.monotonic()
    completed = 0
    errors = 0
    log_every = max(1, total // 10)

    for k in _stats:
        _stats[k] = 0

    tiene_cache = db is not None and db.last_kline_time(symbols[0], "1h") is not None if symbols else False
    logger.info(
        f"Hidratacion iniciada: {total} pares × {len(_TFS_ORDER)} TFs "
        f"({'checkpoint disponible' if tiene_cache else 'sin cache previo — descarga completa'})"
    )

    connector = aiohttp.TCPConnector(limit=s.hydration_concurrency + 10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            _hydrate_symbol(sym, engine, db, session, sem, base_url)
            for sym in symbols
        ]
        for coro in asyncio.as_completed(tasks):
            try:
                await coro
            except Exception as e:
                errors += 1
                logger.debug(f"Hidratacion error: {e}")
            completed += 1
            if completed % log_every == 0 or completed == total:
                elapsed = time.monotonic() - start
                logger.info(
                    f"Hidratacion {completed}/{total} ({completed/total*100:.0f}%) "
                    f"| {elapsed:.0f}s | errores={errors}"
                )

    elapsed = time.monotonic() - start
    logger.info(
        f"Hidratacion completa: {total} pares en {elapsed:.0f}s | "
        f"checkpoint={_stats['checkpoint']} TFs, completo={_stats['completo']} TFs | "
        f"{_stats['velas_rest']} velas REST + {_stats['velas_cache']} velas del cache | "
        f"errores={errors}"
    )
