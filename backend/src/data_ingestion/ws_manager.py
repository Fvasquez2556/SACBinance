"""
Gestor de WebSockets Binance.

WS-A: kline_1m + kline_5m + aggTrade (top-40 shortlist dinamica)
WS-B: kline_15m + kline_1h

Binance 2025: max 1024 streams por conexion, ping/pong cada 20s obligatorio.
Con ~200 pares: WS-A ~400 streams, WS-B ~400 streams — ambas dentro del limite.

aggTrade solo para shortlist (top-40 por z-score) para no saturar la API.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Dict, List, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed

from src.config.settings import get_settings
from src.state.symbol_state import Candle
from src.utils.logger import get_logger

logger = get_logger(__name__)

_BINANCE_WS_BASE = "wss://stream.binance.com:9443/stream?streams="
_PING_INTERVAL = 20  # segundos (requisito Binance)
_RECONNECT_BASE = 2.0
_RECONNECT_MAX = 60.0


def _kline_stream(symbol: str, interval: str) -> str:
    return f"{symbol.lower()}@kline_{interval}"


def _agg_stream(symbol: str) -> str:
    return f"{symbol.lower()}@aggTrade"


class _WSConnection:
    """Una conexion WebSocket Binance multi-stream con ping/pong y reconexion."""

    def __init__(self, name: str, streams: List[str], handler) -> None:
        self.name = name
        self.streams = streams
        self._handler = handler
        self._running = False
        self._ws = None

    async def run(self) -> None:
        self._running = True
        backoff = _RECONNECT_BASE
        while self._running:
            url = _BINANCE_WS_BASE + "/".join(self.streams)
            logger.info(f"[{self.name}] conectando ({len(self.streams)} streams)")
            try:
                async with websockets.connect(
                    url,
                    ping_interval=_PING_INTERVAL,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=2**23,
                ) as ws:
                    self._ws = ws
                    backoff = _RECONNECT_BASE
                    logger.info(f"[{self.name}] conectado")
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                            await self._handler(msg)
                        except Exception as e:
                            logger.debug(f"[{self.name}] handler error: {e}")
            except ConnectionClosed as e:
                logger.warning(f"[{self.name}] desconectado: {e} | reconectando en {backoff:.0f}s")
            except Exception as e:
                logger.warning(f"[{self.name}] error: {e} | reconectando en {backoff:.0f}s")
            finally:
                self._ws = None
            if self._running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _RECONNECT_MAX)

    def stop(self) -> None:
        self._running = False
        if self._ws:
            asyncio.create_task(self._ws.close())


class WSManager:
    """
    Gestiona WS-A (1m + 5m + aggTrade shortlist) y WS-B (15m + 1h).
    El engine recibe los eventos via callbacks.
    """

    def __init__(self, symbols: List[str], engine) -> None:
        self.symbols = symbols
        self.engine = engine
        self._shortlist: Set[str] = set()
        self._ws_a: Optional[_WSConnection] = None
        self._ws_b: Optional[_WSConnection] = None
        self._task_a: Optional[asyncio.Task] = None
        self._task_b: Optional[asyncio.Task] = None

    def _build_streams_a(self) -> List[str]:
        streams = []
        for sym in self.symbols:
            streams.append(_kline_stream(sym, "1m"))
            streams.append(_kline_stream(sym, "5m"))
        for sym in self._shortlist:
            streams.append(_agg_stream(sym))
        return streams

    def _build_streams_b(self) -> List[str]:
        streams = []
        for sym in self.symbols:
            streams.append(_kline_stream(sym, "15m"))
            streams.append(_kline_stream(sym, "1h"))
        return streams

    async def _handle_a(self, msg: dict) -> None:
        data = msg.get("data", msg)
        stream = msg.get("stream", "")

        if "@kline_" in stream:
            k = data.get("k", {})
            if not k:
                return
            symbol = k.get("s", "")
            interval = k.get("i", "")
            closed = k.get("x", False)
            candle = Candle(
                t=int(k["t"]),
                o=float(k["o"]),
                h=float(k["h"]),
                l=float(k["l"]),
                c=float(k["c"]),
                v=float(k["q"]),
            )
            if interval == "1m":
                if closed:
                    await self.engine.on_closed_candle(
                        symbol, candle.t, candle.o, candle.h, candle.l, candle.c, candle.v
                    )
                else:
                    await self.engine.on_live_candle(
                        symbol, candle.t, candle.o, candle.h, candle.l, candle.c, candle.v
                    )
            elif interval == "5m" and closed:
                self.engine.on_htf_candle(symbol, "5m", candle)

        elif "@aggTrade" in stream:
            symbol = data.get("s", "")
            await self.engine.on_trade(
                symbol=symbol,
                t=int(data.get("T", 0)),
                price=float(data.get("p", 0)),
                qty=float(data.get("q", 0)),
                is_buyer_maker=bool(data.get("m", False)),
            )

    async def _handle_b(self, msg: dict) -> None:
        data = msg.get("data", msg)
        stream = msg.get("stream", "")

        if "@kline_" not in stream:
            return
        k = data.get("k", {})
        if not k or not k.get("x", False):
            return

        symbol = k.get("s", "")
        interval = k.get("i", "")
        candle = Candle(
            t=int(k["t"]),
            o=float(k["o"]),
            h=float(k["h"]),
            l=float(k["l"]),
            c=float(k["c"]),
            v=float(k["q"]),
        )
        if interval in ("15m", "1h"):
            self.engine.on_htf_candle(symbol, interval, candle)

    def update_shortlist(self, symbols: List[str]) -> None:
        """Actualiza la shortlist de aggTrade (requiere reconectar WS-A)."""
        new_set = set(symbols)
        if new_set == self._shortlist:
            return
        self._shortlist = new_set
        logger.info(f"Shortlist aggTrade actualizada: {len(new_set)} pares")
        # Reconectar WS-A para incluir/excluir streams aggTrade
        if self._task_a and not self._task_a.done():
            self._task_a.cancel()
        self._start_ws_a()

    def _start_ws_a(self) -> None:
        streams = self._build_streams_a()
        self._ws_a = _WSConnection("WS-A", streams, self._handle_a)
        self._task_a = asyncio.create_task(self._ws_a.run())

    def _start_ws_b(self) -> None:
        streams = self._build_streams_b()
        self._ws_b = _WSConnection("WS-B", streams, self._handle_b)
        self._task_b = asyncio.create_task(self._ws_b.run())

    async def start(self) -> None:
        logger.info(
            f"Iniciando WebSockets: {len(self.symbols)} pares | "
            f"WS-A={len(self._build_streams_a())} streams | "
            f"WS-B={len(self._build_streams_b())} streams"
        )
        self._start_ws_a()
        self._start_ws_b()

    async def stop(self) -> None:
        if self._ws_a:
            self._ws_a.stop()
        if self._ws_b:
            self._ws_b.stop()
        tasks = [t for t in (self._task_a, self._task_b) if t and not t.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("WebSockets detenidos")
