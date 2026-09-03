"""
WebSocket hacia el frontend React.

Emite actualizaciones en tiempo real (diferencial): solo pares que cambian
estado o suben de tier. El frontend mantiene el estado completo en memoria.
Ademas envia snapshot completo al conectar un nuevo cliente.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect

from src.utils.logger import get_logger

logger = get_logger(__name__)


def _json_default(o):
    """Convierte tipos no nativos (numpy scalars, etc.) a JSON-serializables."""
    if hasattr(o, "item"):  # numpy.bool_, numpy.float64, numpy.int64...
        return o.item()
    return str(o)


def _dumps(obj) -> str:
    return json.dumps(obj, default=_json_default)

# Clientes conectados
_clients: Set[WebSocket] = set()
_engine = None


def set_engine(engine) -> None:
    global _engine
    _engine = engine


async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    logger.info(f"Frontend conectado | clientes activos: {len(_clients)}")

    try:
        # Enviar snapshot inicial completo
        if _engine:
            snapshot = _engine.snapshot_all(min_score=0)
            await websocket.send_text(_dumps({
                "type": "snapshot",
                "ts": int(time.time() * 1000),
                "pairs": snapshot,
            }))

        # Mantener conexion abierta (el cliente envia pings periodicos)
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # El cliente puede enviar filtros o pings — solo loguear
                logger.debug(f"WS recibido: {data[:100]}")
            except asyncio.TimeoutError:
                # Keepalive: enviar ping al cliente
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WS error: {e}")
    finally:
        _clients.discard(websocket)
        logger.info(f"Frontend desconectado | clientes activos: {len(_clients)}")


async def broadcast(event: dict) -> None:
    """Emite un evento a todos los clientes conectados."""
    if not _clients:
        return
    msg = _dumps(event)
    dead = set()
    for ws in list(_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


async def broadcast_loop(engine, interval: float = 2.0) -> None:
    """
    Loop de broadcast periodico: envia el estado completo de pares interesantes
    cada `interval` segundos. Complementa el broadcast por evento.
    """
    from src.config.settings import get_settings
    s = get_settings()
    while True:
        await asyncio.sleep(interval)
        if not _clients:
            continue
        try:
            pairs = engine.snapshot_all(min_score=s.score_min_dashboard)
            if pairs:
                await broadcast({
                    "type": "update",
                    "ts": int(time.time() * 1000),
                    "pairs": pairs,
                })
        except Exception as e:
            logger.debug(f"broadcast_loop error: {e}")
