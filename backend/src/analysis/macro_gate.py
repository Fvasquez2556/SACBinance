"""
Gate macro: combina las tendencias de 15m/1h/4h/1d en una tendencia global
ponderada y calcula el multiplicador que se aplica al score base de la FSM.

Esta es la pieza que faltaba en v2: el gate no solo MIDE, sino que ajusta el
score para que la pantalla del usuario refleje correctamente si una senal de
RISING en 1m va CON o CONTRA la tendencia macro.
"""
from __future__ import annotations

from typing import Dict

from src.config.settings import get_settings


_TENDENCIA_NUM = {"ALCISTA": 1.0, "NEUTRAL": 0.0, "BAJISTA": -1.0}


def calcular_tendencia_global(tendencias_tf: Dict[str, str]) -> str:
    """
    Combina tendencias de multiples TFs con pesos configurados.
    Devuelve 'ALCISTA', 'NEUTRAL' o 'BAJISTA'.

    tendencias_tf: {'15m': 'ALCISTA', '1h': 'NEUTRAL', '4h': 'BAJISTA', '1d': 'BAJISTA'}
    """
    s = get_settings()
    pesos = {
        "1d": s.macro_weight_1d,
        "4h": s.macro_weight_4h,
        "1h": s.macro_weight_1h,
        "15m": s.macro_weight_15m,
    }

    total_peso = 0.0
    score = 0.0
    for tf, tendencia in tendencias_tf.items():
        peso = pesos.get(tf, 0.0)
        score += _TENDENCIA_NUM.get(tendencia, 0.0) * peso
        total_peso += peso

    if total_peso <= 0:
        return "NEUTRAL"

    score_norm = score / total_peso

    # Umbral: > 0.15 = ALCISTA, < -0.15 = BAJISTA
    if score_norm > 0.15:
        return "ALCISTA"
    if score_norm < -0.15:
        return "BAJISTA"
    return "NEUTRAL"


def aplicar_gate(score_base: int, fsm_state: str, macro_global: str) -> tuple:
    """
    Aplica el multiplicador del gate macro al score base.
    Devuelve (score_ajustado, mult_aplicado).

    fsm_state: estado de la FSM de 1m (RISING, VALLEY, BOTTOMING, DROPPING, NEUTRAL)
    macro_global: tendencia global calculada por calcular_tendencia_global()
    """
    s = get_settings()

    if fsm_state in ("RISING",):
        if macro_global == "BAJISTA":
            mult = s.gate_bajista_rising_mult
        elif macro_global == "ALCISTA":
            mult = s.gate_alcista_rising_mult
        else:
            mult = 1.0
    elif fsm_state in ("VALLEY", "BOTTOMING"):
        if macro_global == "BAJISTA":
            mult = s.gate_bajista_valley_mult
        elif macro_global == "ALCISTA":
            mult = s.gate_alcista_valley_mult
        else:
            mult = 1.0
    else:
        mult = 1.0

    score_ajustado = max(0, min(100, int(score_base * mult)))
    return score_ajustado, mult


def score_minimo_requerido(macro_global: str) -> int:
    """
    Cuando la macro es NEUTRAL, el umbral de alerta sube (mas exigente).
    Cuando la macro es ALCISTA, se usa el umbral normal.
    """
    s = get_settings()
    if macro_global == "NEUTRAL":
        return s.gate_neutral_score_floor
    if macro_global == "BAJISTA":
        # Antes devolvia score_min_dashboard (60), es decir un piso MAS BAJO
        # que el de NEUTRAL (75). Ir contra la tendencia macro debe ser lo
        # mas exigente, no lo mas permisivo.
        return s.gate_bajista_score_floor
    return s.score_min_dashboard
