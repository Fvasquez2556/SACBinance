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

from src.analysis.signal_tracker import cerrar_vencidas
from src.api.routes import router, set_engine
from src.api.ws_server import broadcast, broadcast_loop, set_engine as ws_set_engine, ws_endpoint
from src.config.settings import get_settings
from src.data_ingestion.hydrator import hydrate_all, reparar_1m
from src.data_ingestion.rest_periodic import start_rest_periodic
from src.data_ingestion.universe import (fetch_universe, get_last_volumes,
                                          get_usdt_pairs)
from src.data_ingestion.ws_manager import WSManager
from src.persistence.db import init_db
from src.state.engine import StateEngine
from src.utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger("main")

app = FastAPI(title="SACBinance v3", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,  # antes estaba hardcodeado a ["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await ws_endpoint(websocket)


# Pares como maximo a los que se les piden huecos internos en cada vuelta de
# la reparacion. Un request por par: con esto la reparacion nunca pasa de 40
# peticiones cada `reparacion_velas_seconds`, muy por debajo del limite de peso
# de Binance, aunque el dia que se active haya 224 pares con huecos.
REPARACION_MAX_PARES = 40


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
    volumes = get_last_volumes()
    for sym in symbols:
        db.upsert_pair_meta(sym, volumes.get(sym, 0.0))

    # 2b. Procedencia: que codigo y que configuracion producen las filas de hoy.
    # Sin esto, un cambio de umbral y un cambio de mercado son indistinguibles
    # al leer la tabla semanas despues.
    from src.utils import procedencia
    ver, chash = procedencia.inicializar(s)
    logger.info(f"Version de estrategia: {ver} | hash de configuracion: {chash}")

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

    # 5b. Outcomes: reconstruir el camino de las señales que siguen abiertas
    # usando las velas 1m recien hidratadas (cubre el hueco de un reinicio).
    if engine._outcomes is not None:
        engine._outcomes.backfill(engine)

    # 5c. Alertas: devolver al tablero las que aun estan dentro de su ventana
    # de seguimiento. Van despues del backfill a proposito, para que recuperen
    # el MFE/MAE ya reconstruido y no empiecen de cero.
    engine._alertas.rehidratar(db, int(time.time() * 1000))

    # 5d. Telegram: comprobar credenciales al arrancar, no cuando salte el
    # primer aviso a las 3 de la manana.
    if engine._tg.activo:
        await engine._tg.probar()
        # Los hilos ya anunciados: sin esto, un reinicio dejaba a las alertas
        # vivas sin avisos de bajada, stop ni hitos hasta que caducaban.
        engine._tg.cargar_hilos()

    # 6. WebSockets Binance
    ws_mgr = WSManager(symbols, engine)
    await ws_mgr.start()

    # 7. REST periodico 4h + 1d
    await start_rest_periodic(symbols, engine)

    # 8. Shortlist aggTrade (flujo agresor) — NUEVO
    # Sin esto _shortlist quedaba vacia para siempre y toda la capa de flujo
    # agresor estaba muerta: `confirmed` nunca era True y todos los pares
    # quedaban capados a score 79.
    asyncio.create_task(_shortlist_loop(engine, ws_mgr))

    # 9. Volcado periodico de la escritura diferida a SQLite
    asyncio.create_task(_db_flush_loop(db, engine))

    # 10. Broadcast periodico al frontend
    asyncio.create_task(broadcast_loop(engine, interval=2.0))

    # 11. Purga periodica de la base de datos (rolling)
    asyncio.create_task(_prune_loop(db))
    asyncio.create_task(_universe_loop(engine, ws_mgr, db))
    asyncio.create_task(_reparacion_velas_loop(engine, db))

    logger.info("=" * 60)
    logger.info(f"SACBinance v3 ACTIVO | {len(symbols)} pares | API: :{s.api_port}")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown():
    """
    Con escritura diferida, cerrar sin volcar pierde todo lo acumulado desde el
    ultimo flush (hasta db_flush_interval de estados, logs y velas). Un
    `systemctl restart` pasa por aqui.
    """
    # Se lee el singleton directamente: get_db() crearia una conexion nueva si
    # aun no hubiera ninguna, que es justo lo que no queremos al apagar.
    # Cerrar la sesion HTTP de Telegram antes que nada: aiohttp se queja si
    # el loop muere con una sesion abierta.
    from src.api.ws_server import _engine as motor
    tg = getattr(motor, "_tg", None) if motor is not None else None
    if tg is not None:
        try:
            await tg.cerrar()
        except Exception:
            pass

    from src.persistence import db as db_mod
    db = db_mod._db
    if db is not None:
        try:
            n = db.flush()
            db.close()
            logger.info(f"DB cerrada limpiamente ({n} velas volcadas)")
        except Exception as e:
            logger.warning(f"Error cerrando la DB: {e}")


async def _shortlist_loop(engine, ws_mgr) -> None:
    """
    Recalcula periodicamente el top-N de pares por |z| y se lo pasa al WSManager
    para que abra streams aggTrade solo sobre ellos.
    """
    s = get_settings()
    while True:
        await asyncio.sleep(s.shortlist_refresh_seconds)
        try:
            ranked = sorted(
                engine.states.values(),
                key=lambda st: max(abs(st.metrics.z_rise), abs(st.metrics.z_drop)),
                reverse=True,
            )
            top = [
                st.symbol for st in ranked[: s.shortlist_max]
                if max(abs(st.metrics.z_rise), abs(st.metrics.z_drop))
                >= s.shortlist_z_threshold
            ]
            # Siempre incluir BTC: alimenta el gate de regimen global
            if s.btc_symbol not in top:
                top.append(s.btc_symbol)
            if top:
                # Al motor va lo que quedo SUSCRITO, no lo que se pidio. Es la
                # unica forma de que `flow_disponible` signifique algo: si el
                # gestor no pudo aplicar un cambio, marcar el par como
                # disponible convierte su cero de trades en "nadie compro"
                # cuando en realidad es "nunca miramos".
                suscrita = await ws_mgr.update_shortlist(top)
                engine.set_shortlist(suscrita)
        except Exception as e:
            logger.debug(f"shortlist_loop error: {e}")


async def _universe_loop(engine, ws_mgr, db) -> None:
    """
    Refresca el universo y la liquidez cada `universe_refresh_seconds`.

    El ajuste llevaba declarado desde el principio sin que nadie lo usara: el
    universo quedaba congelado en el arranque y el volumen de pair_metadata se
    quedaba con horas de antiguedad. Un par que entraba en volumen o se listaba
    no llegaba nunca al escaner.

    Tres cosas, en este orden:
      1. Refrescar el volumen 24h de todos, que es barato y no reconecta nada.
      2. Hidratar los pares nuevos ANTES de suscribirlos: un par sin historia
         no puede puntuarse, y arrancaria dando estados provisionales.
      3. Reconectar, conservando los pares con seguimiento vivo aunque hayan
         salido del universo.
    """
    s = get_settings()
    while True:
        await asyncio.sleep(s.universe_refresh_seconds)
        try:
            simbolos = await fetch_universe()
            if not simbolos:
                logger.warning("Refresco de universo: sin respuesta, lo dejo como esta")
                continue
            volumes = get_last_volumes()
            for sym in simbolos:
                db.upsert_pair_meta(sym, volumes.get(sym, 0.0))

            nuevos = [x for x in simbolos if engine.get_symbol(x) is None]
            if nuevos:
                logger.info(f"Refresco de universo: hidratando {len(nuevos)} pares nuevos")
                await hydrate_all(nuevos, engine, db)

            fijados = engine.simbolos_en_seguimiento()
            await ws_mgr.update_symbols(simbolos, fijados=fijados)
        except Exception as e:
            logger.warning(f"universe_loop error: {e}")


async def _reparacion_velas_loop(engine, db) -> None:
    """
    Rellena por REST las velas de 1m que el WebSocket no trajo.

    Los 239 pares tenian huecos internos: 47.249 minutos-par ausentes entre su
    primera y su ultima vela, y ninguna ventana de 24h llegaba al 98% de
    cobertura. Un hueco no es solo ruido: cambia QUE ocurre primero, si el
    stop o el objetivo, y los indicadores por numero de velas dejan de
    representar minutos reales.

    Se detecta de dos formas, porque una sola no basta:

      - Por ATRASO: la ultima vela del par es mas vieja que el umbral. Es lo
        que habia, y solo ve el hueco mientras el stream sigue caido.
      - Por SECUENCIA: faltan minutos ENTRE la primera y la ultima vela del
        buffer. En cuanto el stream vuelve, el hueco deja de estar al final y
        el detector por atraso ya no lo ve nunca mas. En la copia del 10-sep
        quedaban 2.344 minutos-par ausentes en 224 simbolos, todos internos.

    Cada caso se repara distinto. Un par ATRASADO puede llevar parado el
    tiempo suficiente para que le falten tambien los marcos superiores, asi
    que va por el hidratador completo. Un par con huecos INTERNOS solo
    necesita el marco de 1m: pedir los seis marcos de los 224 pares cada cinco
    minutos serian ~1.300 peticiones por vuelta, por encima del limite de peso
    de Binance y para nada. En los dos casos `preload_1m` fusiona sin duplicar.
    """
    s = get_settings()
    # Huecos que una reparacion ya intento y no pudo rellenar, por par. Binance
    # no emite vela para un minuto SIN OPERACIONES, asi que en un par iliquido
    # hay huecos que no existen y no se pueden rellenar nunca. Sin esta memoria
    # el bucle los reintentaria cada cinco minutos para siempre.
    irreparables: dict = {}
    while True:
        await asyncio.sleep(s.reparacion_velas_seconds)
        try:
            ahora = int(time.time() * 1000)
            umbral = s.reparacion_velas_umbral_min * 60_000
            atrasados, con_huecos, minutos = [], [], 0
            for sym, st in engine.states.items():
                velas = st.candles
                if not velas:
                    atrasados.append(sym)
                    continue
                if ahora - velas[-1].t > umbral:
                    atrasados.append(sym)
                    continue
                faltan = st.huecos_1m()
                if not faltan:
                    irreparables.pop(sym, None)
                    continue
                # Se reintenta solo si el hueco CAMBIO desde el ultimo intento
                if irreparables.get(sym) == faltan:
                    continue
                con_huecos.append(sym)
                minutos += faltan

            # Tope por vuelta: la reparacion no puede convertirse en una rafaga
            # de cientos de peticiones contra el limite de peso de Binance.
            if len(con_huecos) > REPARACION_MAX_PARES:
                con_huecos = con_huecos[:REPARACION_MAX_PARES]
                minutos = sum(engine.get_symbol(x).huecos_1m()
                              for x in con_huecos
                              if engine.get_symbol(x) is not None)

            if atrasados:
                logger.info(
                    f"Reparando velas: {len(atrasados)} pares con mas de "
                    f"{s.reparacion_velas_umbral_min} min sin vela"
                )
                await hydrate_all(atrasados, engine, db)
            if con_huecos:
                logger.info(
                    f"Reparando huecos internos: {len(con_huecos)} pares "
                    f"({minutos} minutos ausentes)"
                )
                await reparar_1m(con_huecos, engine, db)
                # Lo que siga faltando despues de pedirlo es, hasta nuevo aviso,
                # un minuto que Binance no tiene.
                sin_rellenar = 0
                for sym in con_huecos:
                    st = engine.get_symbol(sym)
                    if st is None:
                        continue
                    resto = st.huecos_1m()
                    if resto:
                        irreparables[sym] = resto
                        sin_rellenar += resto
                    else:
                        irreparables.pop(sym, None)
                logger.info(
                    f"Huecos internos: {minutos - sin_rellenar} minutos "
                    f"rellenados, {sin_rellenar} sin vela en Binance"
                )
        except Exception as e:
            logger.warning(f"reparacion_velas_loop error: {e}")


async def _db_flush_loop(db, engine=None) -> None:
    """
    Volcado periodico de klines/estados encolados, y cierre de los outcomes
    cuya ventana caduco.

    El cierre va aqui y no en el camino de la vela a proposito: antes dependia
    de que llegara una vela del par, asi que un par que salia del universo
    dejaba su seguimiento colgado — la duracion mas larga observada fue de
    117.92h sobre una ventana de 24.

    Lo mismo vale para las SEÑALES, que se quedaron fuera de aquel arreglo: su
    caducidad solo se miraba al llegar una vela del par. El 11-sep habia 24
    señales OPEN de mas de 12h con `signal_expiry_hours=12`, y la mas vieja
    llevaba 155.7 horas. Ahora las dos tablas tienen el mismo reloj.
    """
    s = get_settings()
    while True:
        await asyncio.sleep(s.db_flush_interval)
        try:
            db.flush()
        except Exception as e:
            logger.debug(f"db_flush_loop error: {e}")
        ahora_ms = int(time.time() * 1000)
        try:
            if engine is not None and engine._outcomes is not None:
                engine._outcomes.cerrar_vencidos(ahora_ms)
        except Exception as e:
            logger.debug(f"cerrar_vencidos error: {e}")
        try:
            cerrar_vencidas(db, ahora_ms)
        except Exception as e:
            logger.debug(f"cerrar_vencidas (señales) error: {e}")


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
