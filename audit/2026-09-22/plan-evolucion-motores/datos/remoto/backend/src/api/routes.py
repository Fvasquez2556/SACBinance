"""
API REST: endpoints para el frontend React.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.analysis.pair_report import normalizar_symbol, obtener_informe
from src.config.settings import get_settings
from src.persistence.db import get_db
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api")

# El engine se inyecta desde main.py
_engine = None


def set_engine(engine) -> None:
    global _engine
    _engine = engine


@router.get("/pairs")
async def get_pairs(
    min_score: int = Query(default=0, ge=0, le=100),
    state: Optional[str] = Query(default=None),
    tier: Optional[str] = Query(default=None),
):
    """
    Lista de pares con score >= min_score.
    Filtros opcionales: state (display_state), tier.
    """
    if _engine is None:
        raise HTTPException(503, "Engine no inicializado")

    s = get_settings()
    threshold = max(min_score, s.score_min_dashboard)
    pairs = _engine.snapshot_all(min_score=threshold)

    if state:
        pairs = [p for p in pairs if p.get("display_state") == state]
    if tier:
        pairs = [p for p in pairs if p.get("tier") == tier]

    return {"count": len(pairs), "pairs": pairs}


@router.get("/pair/{symbol}/history")
async def get_pair_history(symbol: str, hours: int = Query(default=24, ge=1, le=720)):
    """Historial de cambios de estado de un par (ultimas N horas)."""
    db = get_db()
    history = db.get_history(symbol.upper(), hours=hours)
    if not history:
        # Si no hay en DB, retornar el historial en memoria si existe
        if _engine:
            st = _engine.get_symbol(symbol.upper())
            if st:
                return {"symbol": symbol.upper(), "history": st.state_history[-50:]}
    return {"symbol": symbol.upper(), "history": history}


@router.get("/pair/{symbol}/analisis")
async def get_pair_analisis(symbol: str):
    """
    Ruptura y plan de un par, marco por marco (5m, 15m, 1h, 4h).

    Funciona con cualquier par USDT, este o no en el universo en vivo: si no
    esta, sus velas se bajan de Binance en el momento. Acepta "btc" igual que
    "BTCUSDT".

    Es una lectura de estructura, no un pronostico ni una orden. Cada marco
    dice que nivel se rompio, cuantas velas lleva sostenido, y que rango de
    entrada / SL / TP sale de esa estructura. El informe viene con sus propias
    advertencias en `advertencias`, y hay que enseñarlas.
    """
    limpio = normalizar_symbol(symbol)
    if limpio is None:
        raise HTTPException(400, f"{symbol} no tiene forma de par USDT")
    try:
        informe = await obtener_informe(limpio, _engine)
    except Exception as exc:
        logger.warning(f"[{limpio}] informe por marcos fallo: {exc}")
        raise HTTPException(502, "No se pudo construir el analisis del par")
    if informe is None:
        raise HTTPException(404, f"{limpio} no existe en Binance o no devolvio velas")
    return informe


@router.get("/pair/{symbol}")
async def get_pair(symbol: str):
    """Estado actual de un par especifico."""
    if _engine is None:
        raise HTTPException(503, "Engine no inicializado")
    st = _engine.get_symbol(symbol.upper())
    if st is None:
        raise HTTPException(404, f"{symbol} no encontrado")
    return st.snapshot()


@router.get("/logs")
async def get_logs(limit: int = Query(default=100, ge=1, le=500)):
    """Ultimos N registros del log de analisis."""
    db = get_db()
    return {"logs": db.get_logs(limit=limit)}


@router.get("/signals/stats")
async def get_signal_stats():
    """Estadisticas de auto-evaluacion: win rate, resultado promedio."""
    db = get_db()
    return db.get_signal_stats()


@router.get("/signals")
async def get_signals(limit: int = Query(default=50, ge=1, le=200)):
    """Ultimas N señales registradas con su resultado."""
    db = get_db()
    return {"signals": db.get_recent_signals(limit=limit)}


@router.get("/historial")
async def get_historial(
    limit: int = Query(default=200, ge=1, le=1000),
    symbol: Optional[str] = Query(default=None),
):
    """
    Historial de señales con su desenlace, para el panel del tablero.

    Sale de `outcomes`, que sigue las 24h enteras, y no de `signals`, que deja
    de mirar en cuanto toca TP o SL.
    """
    db = get_db()
    return {"historial": db.get_historial(limit=limit, symbol=symbol)}


@router.get("/rupturas-tf/resumen")
async def get_rupturas_tf_resumen():
    """
    Cuantas rupturas por marco lleva registradas la sombra, por marco y
    direccion. Es una comprobacion de que la sombra corre, no un resultado:
    contar detecciones no dice si aciertan.

    El analisis de verdad se hace sobre la tabla `rupturas_tf` con las tres
    puertas (dinero, habilidad, terreno nuevo) y n suficiente.
    """
    db = get_db()
    return db.get_rupturas_tf_resumen()


@router.get("/status")
async def get_status():
    """Estado del sistema: pares activos, distribucion de estados."""
    if _engine is None:
        return {"status": "iniciando", "pairs": 0}

    all_states = [st.snapshot() for st in _engine.states.values()]
    from collections import Counter
    state_dist = Counter(s["display_state"] for s in all_states)
    tier_dist = Counter(s["tier"] for s in all_states if s["tier"] != "NINGUNO")

    return {
        "status": "activo",
        "total_pairs": len(all_states),
        "state_distribution": dict(state_dist),
        "tier_distribution": dict(tier_dist),
        "interesting": sum(1 for s in all_states if s["score"] >= 60),
    }
