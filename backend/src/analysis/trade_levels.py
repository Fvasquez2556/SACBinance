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
    ruido_1m_pct: Optional[float] = None
    nearest_resistance: Optional[float] = None
    tp_blocked_by_resistance: bool = False
    # ¿El TP que ofrece llega siquiera al objetivo del operador? El TP sale de
    # riesgo × rr_target, asi que en pares tranquilos se queda corto: en la
    # muestra del 5-7 sep, el 57% ofrecia menos de +3.2%.
    objetivo_alcanzable: bool = False
    reward_neto_pct: float = 0.0
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
            "ruido_1m_pct": self.ruido_1m_pct,
            "objetivo_alcanzable": self.objetivo_alcanzable,
            "reward_neto_pct": self.reward_neto_pct,
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


def _ruido_pullback_pct(candles_1m: list, tramo: int, paso: int) -> Optional[float]:
    """
    Retroceso tipico del par: mediana de la caida maxima pico->valle dentro de
    ventanas moviles de `tramo` minutos.

    Por que no basta el ATR de 15m: el ATR mide el tamano de la vela, no cuanto
    se aleja el precio en contra mientras aguantas la operacion. Medido sobre
    699 senales del 5 al 7 de septiembre de 2026, el |MAE| mediano fue 1.83%
    mientras el SL mediano era 1.26%: el stop vivia dentro del ruido y saltaba
    antes del objetivo en el 33% de las senales que SI lo alcanzaban.
    """
    if len(candles_1m) < tramo + paso:
        return None
    caidas = []
    for ini in range(0, len(candles_1m) - tramo + 1, paso):
        seg = candles_1m[ini:ini + tramo]
        pico = 0.0
        peor = 0.0
        for c in seg:
            if c.h > pico:
                pico = c.h
            if pico > 0:
                dd = (pico - c.l) / pico * 100.0
                if dd > peor:
                    peor = dd
        caidas.append(peor)
    if not caidas:
        return None
    caidas.sort()
    n = len(caidas)
    return caidas[n // 2] if n % 2 else (caidas[n // 2 - 1] + caidas[n // 2]) / 2.0


def calcular_niveles(
    price: float,
    candles_15m: list,
    display_state: str,
    niveles_sr=None,
    candles_1m: Optional[list] = None,
) -> TradeLevels:
    """
    price: precio actual (cierre 1m mas reciente)
    candles_15m: buffer de velas 15m (.l, .h, .c)
    display_state: estado visible del par
    niveles_sr: NivelesResult opcional (soportes/resistencias) de levels.py
    candles_1m: buffer de velas 1m, para medir el ruido real del par
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

    # Riesgo minimo: el SL tiene que quedar FUERA del ruido del par, no solo
    # despegado del precio. Dos suelos, se toma el mas exigente:
    #   a) multiplo del ATR de 15m
    #   b) el retroceso tipico del par medido en 1m (ver _ruido_pullback_pct)
    min_risk = atr_abs * s.min_risk_atr
    base_min = "ATR"
    if candles_1m:
        ruido = _ruido_pullback_pct(list(candles_1m),
                                    s.sl_ruido_tramo_1m, s.sl_ruido_paso_1m)
        if ruido is not None:
            res.ruido_1m_pct = round(ruido, 2)
            ruido_abs = entry * ruido * s.sl_ruido_mult / 100.0
            if ruido_abs > min_risk:
                min_risk, base_min = ruido_abs, "ruido 1m"
    if risk < min_risk:
        risk = min_risk
        stop_loss = entry - risk
        res.sl_basis = f"riesgo minimo ({base_min})"

    # Riesgo maximo. Antes se acotaba en silencio, y ese recorte volvia a meter
    # el stop dentro del ruido: el par pedia mas margen del permitido y se le
    # daba igual un stop que no aguanta. Si no cabe, no se emite.
    max_risk = entry * s.max_risk_pct / 100.0
    if risk > max_risk:
        res.risk_pct = round(risk / entry * 100.0, 2)
        res.reason = (f"SL fuera del ruido exigiria {res.risk_pct}% de riesgo, "
                      f"por encima del maximo {s.max_risk_pct}% — no se emite")
        return res

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
    # NETO, no bruto. Cobrar un TP de +2.5% con 0.5% de costes deja +2.0%, y
    # el objetivo del operador son +3.2%. Comparar el bruto con el objetivo
    # hacia pasar por "alcanzable" a señales que no podian serlo.
    res.reward_neto_pct = round(res.reward_pct - s.coste_operacion_pct, 2)
    res.objetivo_alcanzable = res.reward_neto_pct >= s.objetivo_operador_pct

    aviso = " | OJO: resistencia antes del TP" if res.tp_blocked_by_resistance else ""
    res.reason = (
        f"SL: {res.sl_basis} | ATR15m={atr_pct:.2f}% | "
        + (f"ruido1m={res.ruido_1m_pct}% | " if res.ruido_1m_pct is not None else "") +
        f"riesgo={res.risk_pct}% beneficio={res.reward_pct}% "
        f"(neto {res.reward_neto_pct}%) R:R={res.risk_reward}{aviso}"
    )
    return res
