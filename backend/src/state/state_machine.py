"""
FSM adaptativa de 1m: NEUTRAL / DROPPING / BOTTOMING / VALLEY / RISING / EXHAUSTED.
Portado de v2 — solo transiciones de estado, sin scoring (eso va en analysis/scoring.py).
"""
from __future__ import annotations

from typing import Optional

from src.config.settings import get_settings

FSM_NEUTRAL = "NEUTRAL"
FSM_DROPPING = "DROPPING"
FSM_BOTTOMING = "BOTTOMING"
FSM_VALLEY = "VALLEY"
FSM_RISING = "RISING"
FSM_EXHAUSTED = "EXHAUSTED"

ALL_STATES = (FSM_NEUTRAL, FSM_DROPPING, FSM_BOTTOMING, FSM_VALLEY, FSM_RISING, FSM_EXHAUSTED)


def evaluate(st) -> Optional[str]:
    """
    Evalua las metricas actuales del SymbolState y retorna el nuevo estado FSM
    si hubo transicion (None si no cambio).

    Modifica directamente: st.fsm_state, st.stabilize_count, st.calm_count,
    st.peak_drop_velocity, st.candles_in_fsm, st.last_peak.
    """
    s = get_settings()
    m = st.metrics

    # Blow-off / agotamiento (maxima prioridad)
    if m.z_rise >= s.blowoff_z and m.vol_ratio >= s.blowoff_vol_ratio:
        st.calm_count = 0
        return _transition(st, FSM_EXHAUSTED)

    calm = abs(m.z_rise) < 1.0 and abs(m.z_drop) < 1.0 and abs(m.velocity) < 0.5

    if st.fsm_state == FSM_EXHAUSTED:
        st.calm_count = st.calm_count + 1 if calm else 0
        if st.calm_count >= s.neutral_decay_candles:
            st.calm_count = 0
            return _transition(st, FSM_NEUTRAL)
        return None

    # Caida brusca
    if m.z_drop <= s.drop_z and m.velocity < 0:
        if st.fsm_state != FSM_DROPPING:
            st.peak_drop_velocity = m.velocity
            st.stabilize_count = 0
            return _transition(st, FSM_DROPPING)
        st.peak_drop_velocity = min(getattr(st, "peak_drop_velocity", m.velocity), m.velocity)
        return None

    # Subida fuerte
    if (
        m.z_rise >= s.rise_z
        and m.velocity > 0
        and not st.flow_snap.sell_dominant
    ):
        st.calm_count = 0
        return _transition(st, FSM_RISING)

    # DROPPING → BOTTOMING (desaceleracion detectada)
    if st.fsm_state == FSM_DROPPING:
        peak = getattr(st, "peak_drop_velocity", m.velocity)
        decelerated = peak < 0 and m.velocity >= s.bottoming_decel * peak
        if decelerated and m.z_drop > s.drop_z:
            st.stabilize_count = 0
            return _transition(st, FSM_BOTTOMING)
        return None

    # BOTTOMING → VALLEY (estabilizacion)
    if st.fsm_state == FSM_BOTTOMING:
        stable_tick = (
            abs(m.ret_1m) < s.valley_band_sigma * m.sigma
            and m.velocity > -0.5
        )
        st.stabilize_count = st.stabilize_count + 1 if stable_tick else 0
        if (
            st.stabilize_count >= s.valley_stabilize_candles
            and not st.flow_snap.sell_dominant
        ):
            return _transition(st, FSM_VALLEY)
        if calm:
            st.calm_count = getattr(st, "calm_count", 0) + 1
            if st.calm_count >= s.neutral_decay_candles:
                st.calm_count = 0
                return _transition(st, FSM_NEUTRAL)
        return None

    # Decaimiento a NEUTRAL desde RISING / VALLEY
    if st.fsm_state in (FSM_RISING, FSM_VALLEY):
        st.calm_count = getattr(st, "calm_count", 0)
        st.calm_count = st.calm_count + 1 if calm else 0
        if st.calm_count >= s.neutral_decay_candles:
            st.calm_count = 0
            return _transition(st, FSM_NEUTRAL)
        return None

    return None


def provisional_state(m, s=None) -> Optional[str]:
    """
    Estado provisional desde la vela 1m EN FORMACION (no cerrada).
    Solo disparadores instantaneos. No muta estado ni estadisticas.
    """
    s = s or get_settings()
    if m.z_rise >= s.blowoff_z and m.vol_ratio >= s.blowoff_vol_ratio:
        return FSM_EXHAUSTED
    if m.z_drop <= s.drop_z and m.velocity < 0:
        return FSM_DROPPING
    if m.z_rise >= s.rise_z and m.velocity > 0:
        return FSM_RISING
    return None


def _transition(st, new_state: str) -> Optional[str]:
    return st.set_fsm_state(new_state)
