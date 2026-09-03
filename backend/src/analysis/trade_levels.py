"""
Calculo de niveles de trading: entrada, take profit, stop loss.

Filosofia:
  - Stop loss ESTRUCTURAL: debajo del soporte real mas cercano (si se conoce)
    o del swing low reciente (15m), con buffer ATR. Si la estructura queda
    demasiado lejos, se acota a max_risk_pct.
  - Take profit por R:R: TP = entry + riesgo × rr_target. Si hay una
    resistencia entre entry y TP, se avisa (el precio debera atravesarla).
  - Solo se calcula para estados alcistas/acumulacion (largo).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.analysis.ma_slopes import calcular_atr_pct
from src.config.settings import get_settings

_OPERABLE = {"SUBIENDO", "BREAKOUT_INCIPIENTE", "TOCÓ_FONDO", "CONSOLIDANDO"}


@dataclass
class TradeLevels:
    valid: bool = False
    entry: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_reward: Optional[float] = None
    risk_pct: Optional[float] = None
    reward_pct: Optional[float] = None
    atr_pct: Optional[float] = None
    nearest_resistance: Optional[float] = None
    tp_blocked_by_resistance: bool = False
    sl_basis: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "entry": self.entry,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "risk_reward": self.risk_reward,
            "risk_pct": self.risk_pct,
            "reward_pct": self.reward_pct,
            "atr_pct": self.atr_pct,
            "nearest_resistance": self.nearest_resistance,
            "tp_blocked_by_resistance": self.tp_blocked_by_resistance,
            "sl_basis": self.sl_basis,
            "reason": self.reason,
        }


def _round_price(p: float) -> float:
    if p >= 100:
        return round(p, 2)
    if p >= 1:
        return round(p, 4)
    if p >= 0.01:
        return round(p, 6)
    return round(p, 8)


def calcular_niveles(
    price: float,
    candles_15m: list,
    display_state: str,
    niveles_sr=None,
) -> TradeLevels:
    """
    price: precio actual (cierre 1m mas reciente)
    candles_15m: buffer de velas 15m (.l, .h, .c)
    display_state: estado visible del par
    niveles_sr: NivelesResult opcional (soportes/resistencias) de levels.py
    """
    s = get_settings()
    res = TradeLevels()

    if display_state not in _OPERABLE:
        res.reason = "estado no operable (solo contexto)"
        return res
    if price <= 0 or len(candles_15m) < 20:
        res.reason = "datos insuficientes"
        return res

    atr_pct = calcular_atr_pct(candles_15m, s.atr_period)
    if atr_pct is None or atr_pct <= 0:
        res.reason = "ATR no disponible"
        return res
    atr_abs = price * atr_pct / 100.0
    res.atr_pct = round(atr_pct, 3)

    entry = price

    # --- Stop loss: prioriza soporte real, si no swing low 15m ---
    soporte = None
    if niveles_sr is not None and niveles_sr.soportes:
        soporte = niveles_sr.soportes[0].precio  # mas cercano por debajo del precio

    if soporte is not None:
        stop_loss = soporte - atr_abs * s.sl_buffer_atr
        res.sl_basis = "soporte estructural"
    else:
        recent = list(candles_15m)[-s.swing_lookback_15m:]
        swing_low = min(c.l for c in recent)
        stop_loss = swing_low - atr_abs * s.sl_buffer_atr
        res.sl_basis = "swing low 15m"

    risk = entry - stop_loss

    # Riesgo minimo: evita SL pegado al precio
    min_risk = atr_abs * s.min_risk_atr
    if risk < min_risk:
        risk = min_risk
        stop_loss = entry - risk
        res.sl_basis = "riesgo minimo (ATR)"

    # Riesgo maximo: acota el SL si la estructura queda muy lejos
    max_risk = entry * s.max_risk_pct / 100.0
    if risk > max_risk:
        risk = max_risk
        stop_loss = entry - risk
        res.sl_basis = "riesgo maximo acotado"

    # --- Take profit por R:R objetivo ---
    take_profit = entry + risk * s.rr_target

    # --- Resistencia entre entry y TP ---
    if niveles_sr is not None and niveles_sr.resistencias:
        r = niveles_sr.resistencias[0].precio  # mas cercana por encima
        res.nearest_resistance = _round_price(r)
        if entry < r < take_profit:
            res.tp_blocked_by_resistance = True

    res.valid = True
    res.entry = _round_price(entry)
    res.stop_loss = _round_price(stop_loss)
    res.take_profit = _round_price(take_profit)
    res.risk_pct = round(risk / entry * 100.0, 2)
    res.reward_pct = round((take_profit - entry) / entry * 100.0, 2)
    res.risk_reward = round(s.rr_target, 2)

    aviso = " | OJO: resistencia antes del TP" if res.tp_blocked_by_resistance else ""
    res.reason = (
        f"SL: {res.sl_basis} | ATR15m={atr_pct:.2f}% | "
        f"riesgo={res.risk_pct}% beneficio={res.reward_pct}% "
        f"R:R={res.risk_reward}{aviso}"
    )
    return res
