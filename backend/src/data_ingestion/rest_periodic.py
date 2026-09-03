"""
Polling periodico de kline_4h y kline_1d via REST.

Binance no tiene limite de conexiones en el REST publico, pero hay rate limit
de ~1200 requests/min (peso). Pedimos 1 vela (limit=2) cada cierre de vela.

Calcula el proximo cierre de cada TF y duerme hasta entonces.
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

_TF_SECONDS = {
    "4h": 4 * 3600,
    "1d": 86400,
}


def _next_close(tf_seconds: int) -> float:
    """Segundos hasta el proximo cierre de vela."""
    now = time.time()
    return tf_seconds - (now % tf_seconds)


async def _fetch_last_candle(
    session: aiohttp.ClientSession,
    symbol: str,
    interval: str,
    base_url: str,
) -> None:
    url = f"{base_url}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": 2}
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
            r.raise_for_status()
            raw = await r.json()
            if len(raw) < 2:
                return raw
            return raw
    except Exception as e:
        logger.debug(f"rest_periodic {symbol}/{interval} error: {e}")
        return []


async def _poll_tf(tf: str, symbols: List[str], engine) -> None:
    """Loop infinito: espera el proximo cierre del TF y descarga la ultima vela."""
    s = get_settings()
    tf_secs = _TF_SECONDS[tf]
    base_url = s.binance_rest_base.rstrip("/")

    while True:
        wait = _next_close(tf_secs) + 5  # +5s margen para que Binance confirme
        logger.info(f"REST {tf}: proxima actualizacion en {wait:.0f}s")
        await asyncio.sleep(wait)

        logger.info(f"REST {tf}: descargando ultima vela para {len(symbols)} pares")
        start = time.monotonic()
        updated = 0

        # Dividir en lotes para no saturar con 200 requests simultaneas
        batch_size = 50
        connector = aiohttp.TCPConnector(limit=batch_size)
        async with aiohttp.ClientSession(connector=connector) as session:
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                tasks = [
                    _fetch_last_candle(session, sym, tf, base_url)
                    for sym in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for sym, raw in zip(batch, results):
                    if isinstance(raw, Exception) or not raw:
                        continue
                    # La penultima vela es la CERRADA (la ultima puede estar aun abierta)
                    row = raw[-2] if len(raw) >= 2 else raw[-1]
                    try:
                        candle = Candle(
                            t=int(row[0]),
                            o=float(row[1]),
                            h=float(row[2]),
                            l=float(row[3]),
                            c=float(row[4]),
                            v=float(row[5]),
                        )
                        engine.on_htf_candle(sym, tf, candle)
                        updated += 1
                    except (IndexError, ValueError) as e:
                        logger.debug(f"rest_periodic parse {sym}/{tf}: {e}")

                await asyncio.sleep(0.05)  # micro-pausa entre lotes

        elapsed = time.monotonic() - start
        logger.info(f"REST {tf}: {updated}/{len(symbols)} actualizados en {elapsed:.1f}s")


async def start_rest_periodic(symbols: List[str], engine) -> None:
    """Arranca los pollers de 4h y 1d en background."""
    logger.info("REST periodico: iniciando pollers 4h + 1d")
    asyncio.create_task(_poll_tf("4h", symbols, engine))
    asyncio.create_task(_poll_tf("1d", symbols, engine))
