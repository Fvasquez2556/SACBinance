"""
API REST: endpoints para el frontend React.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

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
