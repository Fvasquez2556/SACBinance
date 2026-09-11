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

    async def aplicar_streams(self, añadir: List[str], quitar: List[str]) -> bool:
        """
        Cambia los streams de ESTA conexion sin reconectarla.

        Binance acepta SUBSCRIBE y UNSUBSCRIBE sobre una conexion combinada ya
        abierta. Usarlo evita el motivo por el que existia el freno de churn:
        cada cambio de shortlist costaba tirar WS-A y rehacer los ~500 streams
        de todos los pares para mover cuatro suscripciones de aggTrade — 126
        reconexiones en 6.4 horas en el tramo auditado.

        `self.streams` se actualiza siempre, este el socket arriba o no, para
        que la proxima conexion salga ya con la lista correcta. Devuelve True
        si el cambio se pudo mandar en caliente.
        """
        vigentes = [s for s in self.streams if s not in set(quitar)]
        vistos = set(vigentes)
        for s in añadir:
            if s not in vistos:
                vistos.add(s)
                vigentes.append(s)
        self.streams = vigentes

        ws = self._ws
        if ws is None:
            return False
        try:
            if quitar:
                await ws.send(json.dumps({
                    "method": "UNSUBSCRIBE", "params": list(quitar), "id": 1}))
            if añadir:
                await ws.send(json.dumps({
                    "method": "SUBSCRIBE", "params": list(añadir), "id": 2}))
            return True
        except Exception as e:
            # Si el envio falla la conexion ya esta cayendo; al reconectar se
            # usara `self.streams`, que aqui arriba quedo correcto.
            logger.warning(f"[{self.name}] cambio de streams no aplicado: {e}")
            return False

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
        # Universo DESEADO (lo ultimo que pidio el refresco) y universo
        # realmente SUSCRITO. Eran la misma variable, y ahi estaba el fallo:
        # cuando un cambio pequeño no pasaba el freno de churn, `self.symbols`
        # se actualizaba igual, asi que la comparacion siguiente ya creia
        # aplicado lo que nunca se suscribio y el par nuevo no entraba jamas.
        self.symbols = list(symbols)
        self._suscritos: Set[str] = set(symbols)
        # Delta pedida y todavia no aplicada, para poder acumularla.
        self._pendiente: Set[str] = set()
        self.engine = engine
        self._shortlist: Set[str] = set()
        # Pares que ya no estan en el universo pero tienen una operacion en
        # seguimiento. Siguen recibiendo velas hasta que su ventana cierre: si
        # se les corta el stream, el outcome queda colgado y el cierre acaba
        # llegando por reloj sin haber medido nada del tramo final.
        self._fijados: Set[str] = set()
        self._ws_a: Optional[_WSConnection] = None
        self._ws_b: Optional[_WSConnection] = None
        self._task_a: Optional[asyncio.Task] = None
        self._task_b: Optional[asyncio.Task] = None

    def _todos(self) -> List[str]:
        """Universo SUSCRITO mas los pares con seguimiento vivo, sin repetir."""
        vistos, out = set(), []
        en_orden = [s for s in self.symbols if s in self._suscritos]
        en_orden += sorted(self._suscritos - set(en_orden))
        for sym in en_orden + sorted(self._fijados):
            if sym not in vistos:
                vistos.add(sym)
                out.append(sym)
        return out

    def _build_streams_a(self) -> List[str]:
        streams = []
        for sym in self._todos():
            streams.append(_kline_stream(sym, "1m"))
            streams.append(_kline_stream(sym, "5m"))
        for sym in self._shortlist:
            streams.append(_agg_stream(sym))
        return streams

    def _build_streams_b(self) -> List[str]:
        streams = []
        for sym in self._todos():
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
            elif interval == "5m":
                if closed:
                    self.engine.on_htf_candle(symbol, "5m", candle)
                elif "5m" in get_settings().htf_live_tfs_list:
                    # Por defecto htf_live_tfs = "15m,1h", asi que 5m no entra.
                    # Se filtra aqui y no dentro de on_htf_live para no crear
                    # ~250 corrutinas por segundo que solo hacen `return`.
                    await self.engine.on_htf_live(symbol, "5m", candle)

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
        if not k:
            return

        symbol = k.get("s", "")
        interval = k.get("i", "")
        if interval not in ("15m", "1h"):
            return

        candle = Candle(
            t=int(k["t"]),
            o=float(k["o"]),
            h=float(k["h"]),
            l=float(k["l"]),
            c=float(k["c"]),
            v=float(k["q"]),
        )
        if k.get("x", False):
            self.engine.on_htf_candle(symbol, interval, candle)
        else:
            # Vela en formacion: es lo que Binance dibuja y sobre lo que
            # recalcula sus indicadores. Descartarla era la causa del desfase.
            await self.engine.on_htf_live(symbol, interval, candle)

    async def update_shortlist(self, symbols: List[str]) -> Set[str]:
        """
        Actualiza la shortlist de aggTrade. Devuelve la que queda SUSCRITA.

        Ya no reconecta: manda SUBSCRIBE / UNSUBSCRIBE sobre WS-A. Con eso
        desaparece el motivo del freno de churn, y con el freno desaparece el
        fallo que tapaba: el motor recibia la shortlist PEDIDA mientras el
        gestor se quedaba con la anterior, asi que `flow_disponible` marcaba
        disponible un par que no tenia stream. Sustituir 1 par de 40 no llegaba
        al 25% de churn y reproducia la divergencia.

        El valor devuelto es lo unico que el motor debe creerse: lo que de
        verdad esta suscrito, no lo que se pidio.
        """
        new_set = set(symbols)
        if new_set == self._shortlist:
            return set(self._shortlist)

        entran = new_set - self._shortlist
        salen = self._shortlist - new_set
        self._shortlist = new_set

        if self._ws_a is not None:
            en_caliente = await self._ws_a.aplicar_streams(
                [_agg_stream(x) for x in sorted(entran)],
                [_agg_stream(x) for x in sorted(salen)],
            )
        else:
            en_caliente = False
        logger.info(
            f"Shortlist aggTrade actualizada: {len(new_set)} pares "
            f"(+{len(entran)} / -{len(salen)}) — "
            + ("en caliente, sin reconectar" if en_caliente
               else "se aplicara en la proxima conexion de WS-A")
        )
        return set(self._shortlist)

    async def update_symbols(self, symbols: List[str], fijados=None) -> bool:
        """
        Cambia el universo suscrito. Devuelve True si hubo reconexion.

        `universe_refresh_seconds` llevaba declarado desde el principio sin que
        nadie lo usara: el universo y su volumen quedaban congelados en el
        arranque. Un par que entraba en volumen o se listaba no llegaba nunca
        al escaner, y el volumen de pair_metadata se quedaba con 16 horas de
        antiguedad.

        Reconectar los dos WS es caro, asi que un cambio por debajo del umbral
        de churn se aplaza. Aplazar no es descartar: la delta pendiente se
        guarda y se aplica en cuanto el refresco siguiente vuelve a pedirla.
        """
        s = get_settings()
        nuevos = list(symbols or ())
        if not nuevos:
            return False
        self._fijados = set(fijados or ())
        # El universo deseado se apunta siempre; lo que se frena es la
        # suscripcion, y por eso la comparacion va contra lo SUSCRITO.
        self.symbols = nuevos
        actual = set(self._suscritos)
        entran = set(nuevos) - actual
        salen = actual - set(nuevos) - self._fijados
        delta = entran | salen
        if not delta:
            self._pendiente = set()
            return False

        churn = len(delta) / max(len(actual), 1)
        # Un cambio pequeño se aplaza UNA vez, no para siempre: si el refresco
        # siguiente vuelve a pedir lo mismo, ya no es un parpadeo del listado y
        # se aplica aunque no llegue al umbral. Antes un par nuevo de cada 100
        # no se suscribia nunca, y como `self.symbols` se actualizaba igual, la
        # comparacion siguiente lo daba por hecho.
        confirmada = bool(self._pendiente) and delta <= self._pendiente
        if churn < s.universe_min_churn and not confirmada:
            logger.info(
                f"Universo: churn {churn:.0%} < umbral, aplazo "
                f"{len(delta)} cambios al proximo refresco"
            )
            self._pendiente = delta
            return False

        self._pendiente = set()
        self._suscritos = (actual | entran) - salen
        logger.info(
            f"Universo actualizado: {len(nuevos)} pares "
            f"(+{len(entran)} / -{len(salen)}) — reconectando los dos WS"
        )
        if entran:
            logger.info(f"   entran: {', '.join(sorted(entran)[:12])}"
                        + (" ..." if len(entran) > 12 else ""))
        if salen:
            logger.info(f"   salen : {', '.join(sorted(salen)[:12])}"
                        + (" ..." if len(salen) > 12 else ""))
        if self._fijados:
            logger.info(f"   se mantienen por seguimiento vivo: {len(self._fijados)}")

        for ws, task in ((self._ws_a, self._task_a), (self._ws_b, self._task_b)):
            if ws:
                ws.stop()
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._start_ws_a()
        self._start_ws_b()
        return True

    def suscritos(self) -> Set[str]:
        """El universo que de verdad tiene stream, no el que se pidio."""
        return set(self._suscritos) | set(self._fijados)

    def shortlist_suscrita(self) -> Set[str]:
        """Los pares que de verdad tienen aggTrade."""
        return set(self._shortlist)

    def _start_ws_a(self) -> None:
        streams = self._build_streams_a()
        self._ws_a = _WSConnection("WS-A", streams, self._handle_a)
        self._task_a = asyncio.create_task(self._ws_a.run())

    def _start_ws_b(self) -> None:
        streams = self._build_streams_b()
        self._ws_b = _WSConnection("WS-B", streams, self._handle_b)
        self._task_b = asyncio.create_task(self._ws_b.run())

    async def start(self) -> None:
        self._suscritos = set(self.symbols)
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
