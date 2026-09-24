"""
API REST: endpoints para el frontend React.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.analysis.pair_report import normalizar_symbol, obtener_informe
from src.operaciones import ErrorDiario
from src.presentacion import contrato_de_lectura, oportunidades_vivas
from src.presentacion.resultados import POBLACIONES, todas_las_poblaciones
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


@router.get("/pair/{symbol}/referencias")
async def get_pair_referencias(
    symbol: str,
    desde_ms: int = Query(default=0, ge=0),
):
    """
    Primera alerta del dia y episodio vigente de un par.

    El dia lo define el cliente con `desde_ms` (su medianoche local). Si no lo
    manda, se usan las ultimas 24 h, que es una ventana honesta aunque no sea
    "el dia".
    """
    import time as _t
    desde = desde_ms or int(_t.time() * 1000) - 86_400_000
    return get_db().referencias_par(symbol, desde)


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


# --- Diario de operaciones (fase 3) -----------------------------------------
#
# Aqui solo entra lo que el usuario declara. Ningun proceso automatico abre una
# operacion: ni la emision de una alerta, ni el envio a Telegram, ni que el
# precio toque la entrada. Si el diario se llenara solo, dejaria de responder a
# la pregunta para la que existe — que tomaste tu.


class NuevaOperacion(BaseModel):
    symbol: str
    precio_entrada: float = Field(gt=0)
    tipo: str = "SIMULADA"
    plan_id: int | None = None
    cantidad: float | None = Field(default=None, gt=0)
    objetivo: float | None = None
    stop: float | None = None
    nota: str | None = None
    ts_ms: int | None = None


class SalidaOperacion(BaseModel):
    precio: float = Field(gt=0)
    cantidad: float | None = Field(default=None, gt=0)
    motivo: str = "MANUAL"
    ts_ms: int | None = None


class NotaOperacion(BaseModel):
    nota: str
    ts_ms: int | None = None


def _ahora(ts_ms: int | None) -> int:
    import time as _t
    return ts_ms or int(_t.time() * 1000)


def _precio_vivo(symbol: str):
    if _engine is None:
        return None
    st = _engine.get_symbol(symbol.upper())
    return getattr(getattr(st, "metrics", None), "price", None) if st else None


@router.get("/operaciones/resumen")
async def get_operaciones_resumen():
    """Cuentas por tipo. Simulado y declarado no se suman entre si."""
    return get_db().diario_operaciones().resumen()


@router.get("/operaciones")
async def get_operaciones(
    estado: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    limite: int = Query(default=100, ge=1, le=500),
):
    diario = get_db().diario_operaciones()
    filas = [diario.con_precio(op, _precio_vivo(op["symbol"]))
             for op in diario.listar(estado=estado, symbol=symbol, limite=limite)]
    return {"operaciones": filas, "resumen": diario.resumen()}


@router.get("/operaciones/{operacion_id}")
async def get_operacion(operacion_id: int):
    diario = get_db().diario_operaciones()
    op = diario.operacion(operacion_id)
    if op is None:
        raise HTTPException(404, "operacion no encontrada")
    return diario.con_precio(op, _precio_vivo(op["symbol"]))


@router.post("/operaciones")
async def post_operacion(cuerpo: NuevaOperacion):
    """«Tomé esta entrada». Es el unico sitio donde nace una operacion."""
    try:
        return get_db().diario_operaciones().abrir(
            symbol=cuerpo.symbol, ts_ms=_ahora(cuerpo.ts_ms),
            precio_entrada=cuerpo.precio_entrada, tipo=cuerpo.tipo,
            plan_id=cuerpo.plan_id, cantidad=cuerpo.cantidad,
            objetivo=cuerpo.objetivo, stop=cuerpo.stop, nota=cuerpo.nota)
    except ErrorDiario as e:
        raise HTTPException(400, str(e))


@router.post("/operaciones/{operacion_id}/cierre")
async def post_cierre(operacion_id: int, cuerpo: SalidaOperacion):
    try:
        return get_db().diario_operaciones().cerrar(
            operacion_id, _ahora(cuerpo.ts_ms), cuerpo.precio, cuerpo.motivo)
    except ErrorDiario as e:
        raise HTTPException(400, str(e))


@router.post("/operaciones/{operacion_id}/parcial")
async def post_parcial(operacion_id: int, cuerpo: SalidaOperacion):
    if cuerpo.cantidad is None:
        raise HTTPException(400, "un parcial necesita cantidad")
    try:
        return get_db().diario_operaciones().parcial(
            operacion_id, _ahora(cuerpo.ts_ms), cuerpo.precio, cuerpo.cantidad)
    except ErrorDiario as e:
        raise HTTPException(400, str(e))


@router.post("/operaciones/{operacion_id}/cancelar")
async def post_cancelar(operacion_id: int, cuerpo: NotaOperacion):
    try:
        return get_db().diario_operaciones().cancelar(
            operacion_id, _ahora(cuerpo.ts_ms), cuerpo.nota)
    except ErrorDiario as e:
        raise HTTPException(400, str(e))


@router.post("/operaciones/{operacion_id}/nota")
async def post_nota(operacion_id: int, cuerpo: NotaOperacion):
    try:
        return get_db().diario_operaciones().anotar(
            operacion_id, _ahora(cuerpo.ts_ms), cuerpo.nota)
    except ErrorDiario as e:
        raise HTTPException(400, str(e))


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


@router.get("/contrato")
async def get_contrato():
    """
    Que significa cada porcentaje que aparece en pantalla.

    Existe porque el numero 3,2 hacia dos trabajos distintos —objetivo NETO del
    operador y hito BRUTO de medicion— y la interfaz los pintaba igual, con el
    valor escrito a mano en quince sitios. Ahora sale de aqui.
    """
    return contrato_de_lectura()


@router.get("/oportunidades")
async def get_oportunidades(
    solo_avisadas: bool = Query(default=False,
                                description="solo las que se enviaron a Telegram"),
):
    """
    Las alertas vivas con todo lo necesario para elegir entre ellas.

    Con una sola posicion se toman dos de cada diecisiete avisos: el cuello de
    botella es cual tomar, y hasta ahora los datos para decidirlo —episodio,
    motores, conflicto entre marcos, techo de por medio— solo existian en la
    base de datos.
    """
    if _engine is None:
        raise HTTPException(503, "Engine no inicializado")
    db = None
    try:
        db = get_db()._conn
    except Exception:
        db = None
    return oportunidades_vivas(_engine, db, solo_avisadas=solo_avisadas)


@router.get("/resultados")
async def get_resultados(desde_ms: Optional[int] = Query(default=None)):
    """
    Lo medido, por poblacion, con horizonte y coste al lado.

    «¿Cuanto acierta el sistema?» no tiene una respuesta: tiene cuatro. Darlas
    juntas evita elegir en silencio la mas grande, que es la que mejor suena y
    menos significa.
    """
    try:
        conn = get_db()._conn
    except Exception:
        raise HTTPException(503, "Base de datos no disponible")
    return todas_las_poblaciones(conn, desde_ms)


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
