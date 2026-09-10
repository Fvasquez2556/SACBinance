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
# Tokens apalancados: son SUFIJOS sobre un subyacente (BTCUP, ETHDOWN, ADABULL,
# BTC3L...). Antes se buscaba el marcador como SUBCADENA en cualquier posicion,
# y "UP" esta dentro de SUPER, JUP y SYRUP: tres monedas normales, con par USDT
# spot activo, quedaban fuera del escaner sin ninguna razon de mercado.
_LEVERAGED_SUFIJOS = ("UP", "DOWN", "BEAR", "BULL", "3L", "3S", "5L", "5S")

# El sufijo solo no basta: SYRUP acaba en "UP" con un prefijo de 3 letras, igual
# que BTCUP. No hay forma de distinguirlos por la forma del nombre, asi que las
# excepciones van explicitas. Si aparece otra moneda legitima con esta forma, se
# añade aqui y se le pone su prueba en comprobar_universo.py.
_NO_APALANCADOS: Set[str] = {
    "SYRUP",   # Maple Finance
    "JUP",     # Jupiter
    "SUPER",   # SuperVerse — ya se salvaba por el sufijo, va por seguridad
    "PUMP",    # Pump.fun
    "BUP",
}

# Prefijo minimo para que el sufijo cuente como apalancamiento. Con 2, "JUP"
# (prefijo "J") queda descartado por si acaso alguien lo saca de la lista.
_PREFIJO_MIN = 2


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
    """
    True si el nombre corresponde a un token apalancado.

    Se exige que el marcador este AL FINAL y que quede delante un subyacente
    plausible. La version anterior usaba `m in base`, que excluia SUPER, JUP y
    SYRUP por llevar "UP" en medio.
    """
    if base in _NO_APALANCADOS:
        return False
    for suf in _LEVERAGED_SUFIJOS:
        if base.endswith(suf) and len(base) - len(suf) >= _PREFIJO_MIN:
            return True
    return False


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
    bases_lev: Set[str] = set()
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
            bases_lev.add(base_asset)
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
    if bases_lev:
        # A nivel INFO a proposito: un filtro que descarta monedas en silencio
        # es un filtro que nadie revisa. Asi salio que SUPER, JUP y SYRUP
        # llevaban dias fuera del escaner.
        logger.info(f"   apalancados descartados: {', '.join(sorted(bases_lev))}")
    return symbols


# Alias para compatibilidad con main.py
get_usdt_pairs = fetch_universe
