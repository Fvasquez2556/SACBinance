"""
Motor de scoring 0-100 adaptado de v1/v2 con gate macro integrado.

El score base viene del estado FSM (z-scores + indicadores tecnicos).
El gate macro aplica un multiplicador segun si la senal va con o contra
la tendencia de los TFs superiores.
"""
from __future__ import annotations
from typing import Optional, Tuple

from src.config.settings import get_settings
from src.analysis.macro_gate import aplicar_gate, score_minimo_requerido

TIER_NONE = "NINGUNO"
TIER_VIGILANCIA = "VIGILANCIA"
TIER_MODERADA = "MODERADA"
TIER_FUERTE = "FUERTE"
TIER_EXTRA = "EXTRA-FUERTE"

TIER_ORDER = {
    TIER_NONE: 0,
    TIER_VIGILANCIA: 1,
    TIER_MODERADA: 2,
    TIER_FUERTE: 3,
    TIER_EXTRA: 4,
}


def score_and_tier(
    fsm_state: str,
    metrics,
    macro_global: str,
    stabilize_count: int = 0,
    flow=None,
    ind=None,
) -> Tuple[int, str]:
    """
    Score 0-100 + tier, con gate macro integrado.

    1. Calcula score base segun estado FSM (hereda logica de v2)
    2. Aplica multiplicador del gate macro
    3. Clasifica en tier (VIGILANCIA/MODERADA/FUERTE/EXTRA-FUERTE)
    """
    s = get_settings()

    if fsm_state == "EXHAUSTED":
        return 0, TIER_NONE

    if fsm_state == "RISING":
        val = 48
        val += min(int((metrics.z_rise - s.rise_z) * 10), 22)
        val += min(int(max(metrics.velocity, 0) * 7), 10)
        if 1.3 <= metrics.vol_ratio <= 4.0:
            val += 6
        elif metrics.vol_ratio > 6.0:
            val -= 10

    elif fsm_state == "VALLEY":
        val = 48
        dd = abs(metrics.drawdown_from_peak) * 100
        if 3.0 <= dd <= 9.0:
            val += 14
        elif dd < 3.0:
            val += 5
        val += min(stabilize_count * 3, 10)
        if metrics.velocity > 0:
            val += 8
        if 1.2 <= metrics.vol_ratio <= 4.0:
            val += 5

    elif fsm_state == "BOTTOMING":
        val = 45

    else:
        return 0, TIER_NONE

    # Confirmacion multifactor (indicadores tecnicos)
    if ind is not None and ind.valid and fsm_state in ("RISING", "VALLEY"):
        if ind.trend_up:
            val += 8
        if 50.0 <= ind.rsi5 <= 70.0:
            val += 6
        elif ind.rsi5 > 78.0:
            val -= 8
        if ind.macd_rising:
            val += 5
        if ind.rsi5 < 45.0 and not ind.trend_up:
            val -= 10

    # Flujo agresor
    confirmed = (
        flow is not None
        and flow.trades_30s >= s.flow_min_trades
        and flow.buy_dominant
    )
    if flow is not None and flow.trades_30s >= s.flow_min_trades:
        if flow.buy_dominant:
            val += 14
        elif flow.sell_dominant:
            val -= 22
    if not confirmed and fsm_state != "BOTTOMING":
        val = min(val, s.tier_fuerte - 1)

    val = max(0, min(100, val))

    # Gate macro: multiplica el score segun tendencia global
    val, _mult = aplicar_gate(val, fsm_state, macro_global)

    # Clasificar en tier
    score_min = score_minimo_requerido(macro_global)
    if val < score_min:
        return val, TIER_NONE

    if val >= s.tier_extra:
        tier = TIER_EXTRA
    elif val >= s.tier_fuerte:
        tier = TIER_FUERTE
    elif val >= s.tier_moderada:
        tier = TIER_MODERADA
    elif val >= s.tier_vigilancia:
        tier = TIER_VIGILANCIA
    else:
        tier = TIER_NONE

    return val, tier
