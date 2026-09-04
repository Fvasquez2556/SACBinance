"""
CAPA 1 — Taxonomia exhaustiva del universo.

Principio de diseno
-------------------
Esta capa NO filtra. Clasifica TODA moneda, SIEMPRE, en exactamente uno de
siete estados. Es una particion: ninguna moneda queda fuera, ninguna cae en
dos. Eso permite navegar el tablero por estado y ver las monedas que hoy no
se ven — las que estan comprimidas, las que estan cayendo, las que hacen
base — y no solo las que ya estan subiendo.

Esto es la mitad "alta recall" del esquema de meta-labeling: la capa 1
captura todo, la capa 2 (triple barrera + probabilidades) decide en cuales
actuar y con cuanto. Combinar ambas decisiones en un solo modelo es lo que
producia el sistema anterior, que solo emitia alerta cuando ya habia
explosion y por eso empujaba a entrar tarde.

Los siete estados
-----------------
    IGNICION          arranque explosivo en curso
    TENDENCIA         subida lenta y sostenida (grind)
    AGOTAMIENTO       subida perdiendo fuerza / blow-off
    COMPRIMIDA        base que se estrecha, sin caida previa
    BASE_POST_CAIDA   base que se estrecha DESPUES de una caida
    CAIDA             cayendo activamente
    NEUTRAL           residual: nada de lo anterior

SESGO DE DIRECCION
------------------
Solo IGNICION, TENDENCIA (alcista), AGOTAMIENTO y CAIDA (bajista) llevan
direccion. Los dos estados de compresion llevan `direccion_sesgo =
"INDEFINIDA"` por diseno: la compresion anticipa CUANDO habra movimiento, no
hacia donde. Estan en el tablero para vigilancia, no para compra.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.config.settings import get_settings

# --- Estados -----------------------------------------------------------------
IGNICION = "IGNICION"
TENDENCIA = "TENDENCIA"
AGOTAMIENTO = "AGOTAMIENTO"
COMPRIMIDA = "COMPRIMIDA"
BASE_POST_CAIDA = "BASE_POST_CAIDA"
CAIDA = "CAIDA"
NEUTRAL = "NEUTRAL"

TODOS = (IGNICION, TENDENCIA, AGOTAMIENTO, COMPRIMIDA,
         BASE_POST_CAIDA, CAIDA, NEUTRAL)

# Orden de resolucion. AGOTAMIENTO va PRIMERO por seguridad: si una subida ya
# esta agotada, no debe clasificarse como ignicion ni como tendencia aunque
# esos detectores tambien disparen.
PRIORIDAD = (AGOTAMIENTO, IGNICION, TENDENCIA, BASE_POST_CAIDA,
             COMPRIMIDA, CAIDA, NEUTRAL)

ALCISTA = "ALCISTA"
BAJISTA = "BAJISTA"
INDEFINIDA = "INDEFINIDA"

_DIRECCION = {
    IGNICION: ALCISTA, TENDENCIA: ALCISTA,
    AGOTAMIENTO: BAJISTA, CAIDA: BAJISTA,
    COMPRIMIDA: INDEFINIDA, BASE_POST_CAIDA: INDEFINIDA,
    NEUTRAL: INDEFINIDA,
}


@dataclass
class TaxonomyResult:
    estado: str = NEUTRAL
    score: int = 0
    direccion_sesgo: str = INDEFINIDA
    reason: str = ""
    # Todos los detectores que dispararon, con su score. Sirve para depurar
    # por que una moneda quedo en un estado y no en otro.
    candidatos: dict = field(default_factory=dict)
    # Niveles operativos cuando el estado es de compresion
    pivot: Optional[float] = None
    piso: Optional[float] = None
    dist_pivot_pct: Optional[float] = None
    vigilancia: bool = False   # True en estados de compresion: esperar expansion

    def to_dict(self) -> dict:
        return {
            "estado": self.estado, "score": self.score,
            "direccion_sesgo": self.direccion_sesgo, "reason": self.reason,
            "candidatos": dict(self.candidatos),
            "pivot": self.pivot, "piso": self.piso,
            "dist_pivot_pct": self.dist_pivot_pct,
            "vigilancia": self.vigilancia,
        }


def clasificar(
    grind,                 # GrindResult
    ignition,              # IgnitionResult
    compresion,            # CompressionResult
    fsm_state: str,
    metrics,
    macro_trends: dict,
    daily: Optional[dict] = None,
) -> TaxonomyResult:
    """
    Resuelve el estado unico de la moneda. Nunca devuelve None: si nada
    dispara, el estado es NEUTRAL, que tambien es informacion.
    """
    s = get_settings()
    res = TaxonomyResult()

    # --- Candidatos: que detectores dispararon y con cuanto -----------------
    cand: dict = {}
    if ignition.detected:
        cand[IGNICION] = ignition.score
    if grind.detected:
        cand[TENDENCIA] = grind.score
    if compresion.detected:
        # Comprimida CON caida previa reciente = base post-caida.
        # Es el patron flush -> base -> reclaim: mismo estrechamiento, pero el
        # contexto cambia la lectura (oferta forzada vs acumulacion tranquila).
        venia_cayendo = fsm_state in ("DROPPING", "BOTTOMING", "VALLEY")
        cayo_en_el_dia = bool(
            daily and daily.get("valid")
            and (daily.get("pct_desde_open_diario") or 0) <= s.taxonomia_caida_dia_pct
        )
        clave = BASE_POST_CAIDA if (venia_cayendo or cayo_en_el_dia) else COMPRIMIDA
        cand[clave] = compresion.score

    # Agotamiento: la FSM ya marco blow-off / techo parabolico.
    # (El veto de `ignition` no se consulta aparte: se dispara exactamente
    # cuando fsm_state == EXHAUSTED, porque es ese mismo estado el que se le
    # pasa como `blow_off`. Seria una rama inalcanzable.)
    if fsm_state == "EXHAUSTED":
        cand[AGOTAMIENTO] = 85

    # Caida activa
    if fsm_state == "DROPPING" and BASE_POST_CAIDA not in cand:
        cand[CAIDA] = min(100, 50 + int(abs(getattr(metrics, "z_drop", 0.0)) * 10))

    res.candidatos = dict(cand)

    # --- Resolucion por prioridad -------------------------------------------
    for estado in PRIORIDAD:
        if estado in cand:
            res.estado = estado
            res.score = int(cand[estado])
            break
    else:
        res.estado = NEUTRAL
        res.score = 0

    res.direccion_sesgo = _DIRECCION[res.estado]
    res.vigilancia = res.estado in (COMPRIMIDA, BASE_POST_CAIDA)

    # --- Niveles operativos de la base --------------------------------------
    if res.vigilancia:
        res.pivot = compresion.pivot
        res.piso = compresion.piso
        res.dist_pivot_pct = compresion.dist_pivot_pct

    # --- Explicacion ---------------------------------------------------------
    detalle = {
        IGNICION: ignition.reason,
        TENDENCIA: grind.reason,
        COMPRIMIDA: compresion.reason,
        BASE_POST_CAIDA: compresion.reason,
    }.get(res.estado, "")

    otros = [f"{k}:{v}" for k, v in cand.items() if k != res.estado]
    sufijo = f" | tambien: {', '.join(otros)}" if otros else ""

    if res.estado == NEUTRAL:
        res.reason = "sin patron reconocible"
    elif res.vigilancia:
        res.reason = (f"VIGILANCIA (direccion indefinida) — {detalle}{sufijo}")
    else:
        res.reason = f"{detalle}{sufijo}" if detalle else f"FSM={fsm_state}{sufijo}"

    return res
