"""Universo de simbolos USDT spot a analizar (portado de v2)."""
from typing import List, Set

import aiohttp

from src.config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Stablecoins / fiat que NO siguen el patron de nombre USD* / *USD
# (se detectan por lista; el resto se detecta por patron — ver _is_stablecoin).
_EXCLUDED_BASES: Set[str] = {
    "DAI", "EUR", "GBP", "BRL", "AEUR", "EURI", "EURS",
    "TRY", "JPY", "ARS", "AUD", "RUB", "ZAR", "MXN", "PLN",
    "XAUT", "PAXG",  # oro tokenizado — no es trading de cripto
}
_LEVERAGED_MARKERS = ("UP", "DOWN", "BEAR", "BULL", "3L", "3S", "5L", "5S")


def _is_stablecoin(base: str) -> bool:
    """
    Detecta stablecoins. Lista estatica para las que no siguen patron, mas
    deteccion por patron: casi toda stablecoin USD empieza o termina en 'USD'
    (USDC, USDP, USDD, TUSD, FDUSD, RLUSD, XUSD, BUSD, GUSD, PYUSD, USDE...).
    """
    if base in _EXCLUDED_BASES:
        return True
    if base.startswith("USD") or base.endswith("USD"):
        return True
    return False

# Volumen 24h del ultimo fetch, por simbolo (para pair_metadata)
_last_volumes: dict = {}


def get_last_volumes() -> dict:
    """Devuelve {symbol: vol_24h} del ultimo fetch_universe()."""
    return dict(_last_volumes)


def _is_leveraged(base: str) -> bool:
    return any(m in base for m in _LEVERAGED_MARKERS)


async def fetch_universe() -> List[str]:
    """
    Devuelve simbolos USDT spot activos con volumen 24h >= min_volume_24h,
    ordenados por volumen descendente. Formato Binance: "BTCUSDT".
    """
    s = get_settings()
    base = s.binance_rest_base.rstrip("/")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{base}/api/v3/exchangeInfo", timeout=20) as r:
                r.raise_for_status()
                info = await r.json()
            async with session.get(f"{base}/api/v3/ticker/24hr", timeout=20) as r:
                r.raise_for_status()
                tickers = await r.json()
        except Exception as e:
            logger.error(f"Error obteniendo universo: {e}")
            return []

    spot_usdt: Set[str] = set()
    excluded_stable = 0
    excluded_lev = 0
    for m in info.get("symbols", []):
        if m.get("quoteAsset") != "USDT":
            continue
        if m.get("status") != "TRADING":
            continue
        if not m.get("isSpotTradingAllowed", False):
            continue
        base_asset = m.get("baseAsset", "")
        if _is_stablecoin(base_asset):
            excluded_stable += 1
            continue
        if _is_leveraged(base_asset):
            excluded_lev += 1
            continue
        spot_usdt.add(m["symbol"])

    ranked = []
    for t in tickers:
        sym = t.get("symbol")
        if sym not in spot_usdt:
            continue
        try:
            qv = float(t.get("quoteVolume", 0.0))
        except (TypeError, ValueError):
            continue
        if qv < s.min_volume_24h:
            continue
        ranked.append((sym, qv))

    ranked.sort(key=lambda x: x[1], reverse=True)
    top = ranked[: s.max_pairs_to_scan]
    symbols = [sym for sym, _ in top]

    global _last_volumes
    _last_volumes = {sym: qv for sym, qv in top}
    logger.info(
        f"Universo: {len(symbols)} pares activos (vol>={s.min_volume_24h:,.0f} USDT). "
        f"Excluidos: {excluded_stable} stablecoins, {excluded_lev} apalancados"
    )
    return symbols


# Alias para compatibilidad con main.py
get_usdt_pairs = fetch_universe
