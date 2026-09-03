"""
SACBinance v3 — Sistema de Analisis de Mercado Binance.

Arranque secuencial:
  1. Logger + DB
  2. Universo de pares (REST)
  3. Hidratacion historica (REST, asyncio concurrente)
  4. Analisis inicial (clasifica todos los pares)
  5. WebSockets activos (WS-A: 1m+5m | WS-B: 15m+1h)
  6. REST periodico 4h+1d
  7. API lista
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket

from src.api.routes import router, set_engine
from src.api.ws_server import broadcast, broadcast_loop, set_engine as ws_set_engine, ws_endpoint
from src.config.settings import get_settings
from src.data_ingestion.hydrator import hydrate_all
from src.data_ingestion.rest_periodic import start_rest_periodic
from src.data_ingestion.universe import get_usdt_pairs
from src.data_ingestion.ws_manager import WSManager
from src.persistence.db import init_db
from src.state.engine import StateEngine
from src.utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger("main")

app = FastAPI(title="SACBinance v3", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await ws_endpoint(websocket)


# Servir el frontend compilado (frontend/dist) si existe.
# Las rutas /api/* y /ws ya estan registradas arriba -> tienen prioridad.
# html=True hace fallback a index.html (SPA).
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
    logger.info(f"Frontend servido desde {_frontend_dist}")
else:
    logger.warning(
        f"Frontend no compilado ({_frontend_dist} no existe) — "
        f"ejecuta 'npm run build' en frontend/"
    )


@app.on_event("startup")
async def startup():
    s = get_settings()
    logger.info("=" * 60)
    logger.info("SACBinance v3 iniciando...")
    logger.info("=" * 60)

    # 1. Base de datos
    db = init_db()

    # 2. Universo de pares
    logger.info("Obteniendo universo de pares USDT...")
    symbols = await get_usdt_pairs()
    if not symbols:
        logger.error("No se pudieron obtener pares — verificar conexion")
        return
    logger.info(f"{len(symbols)} pares activos")

    # Guardar metadata en DB (con volumen 24h real)
    from src.data_ingestion.universe import get_last_volumes
    volumes = get_last_volumes()
    for sym in symbols:
        db.upsert_pair_meta(sym, volumes.get(sym, 0.0))

    # 3. Engine
    engine = StateEngine(emit=broadcast)
    engine.set_db(db)
    set_engine(engine)
    ws_set_engine(engine)

    # 4. Hidratacion historica (con checkpoint SQLite)
    await hydrate_all(symbols, engine, db)

    # 5. Analisis inicial: forzar calculo de macro para todos los pares ya hidratados
    logger.info("Calculando estado inicial de todos los pares...")
    t0 = time.monotonic()
    from src.analysis.macro_gate import calcular_tendencia_global
    from src.analysis.ma_slopes import analizar_tf
    for sym in symbols:
        st = engine.get_symbol(sym)
        if st is None:
            continue
        for tf in ("15m", "1h", "4h", "1d"):
            candles = list(st.get_candles_tf(tf))
            result = analizar_tf(candles, s.slope_lookback)
            if result.get("valid"):
                st.slopes[tf] = result
                st.macro_trends[tf] = result["tendencia"]
        st.macro_global = calcular_tendencia_global(st.macro_trends)
    logger.info(f"Estado inicial calculado en {time.monotonic()-t0:.1f}s")

    # 6. WebSockets Binance
    ws_mgr = WSManager(symbols, engine)
    await ws_mgr.start()

    # 7. REST periodico 4h + 1d
    await start_rest_periodic(symbols, engine)

    # 8. Broadcast periodico al frontend
    asyncio.create_task(broadcast_loop(engine, interval=2.0))

    # 9. Purga periodica de la base de datos (rolling)
    asyncio.create_task(_prune_loop(db))

    logger.info("=" * 60)
    logger.info(f"SACBinance v3 ACTIVO | {len(symbols)} pares | API: :{s.api_port}")
    logger.info("=" * 60)


async def _prune_loop(db) -> None:
    """Purga periodica de symbol_states / analysis_log / signals (retencion rolling)."""
    s = get_settings()
    interval = s.prune_interval_minutes * 60
    while True:
        await asyncio.sleep(interval)
        try:
            db.prune_old()
        except Exception as e:
            logger.debug(f"prune_loop error: {e}")


if __name__ == "__main__":
    s = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=s.api_port,
        log_level="warning",
        reload=False,
    )
