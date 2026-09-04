"""
Dos perfiles de subida, dos detectores independientes.

Por que dos y no uno
--------------------
La FSM de 1m entra a RISING con z_rise >= 2.0, donde z = retorno acumulado /
(sigma * sqrt(ventana)). Ese umbral esta calibrado para IMPULSOS. Una moneda
que sube despacio pero sin parar produce retornos pequenos EN RELACION A SU
PROPIA SIGMA, asi que su z se queda en ~0.5-0.9 y nunca dispara. El sistema
solo veia explosiones.

  ALERTA A — TENDENCIA (grind): "sube poco a poco pero no para"
      Se mide CALIDAD, no magnitud: que tan bien una recta explica el precio
      (R^2), que tan superficiales son los retrocesos, cuanto tiempo se
      mantiene sobre la EMA. Opera en 15m.
      Un volumen explosivo aqui RESTA: eso ya es el otro perfil.

  ALERTA B — IGNICION (explosion): "acaba de arrancar de golpe"
      Se mide MAGNITUD y simultaneidad: ROC corto + spike de volumen +
      flujo agresor comprador + expansion desde compresion. Opera en 1m.
      Lo dificil no es detectar la explosion, es no llegar tarde: por eso
      penaliza el recorrido ya consumido y respeta el veto de blow-off.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from src.config.settings import get_settings
from src.utils.fastmath import ema as _ema


# =============================================================================
#  ALERTA A — TENDENCIA SOSTENIDA
# =============================================================================

@dataclass
class GrindResult:
    detected: bool = False
    score: int = 0
    r2: Optional[float] = None                 # 0-1, que tan "recta" es la subida
    slope_pct_h: Optional[float] = None        # % de subida por hora
    max_pullback_pct: Optional[float] = None   # peor retroceso dentro de la ventana
    pct_above_ema: Optional[float] = None      # fraccion de cierres sobre EMA25
    green_ratio: Optional[float] = None
    vol_stability: Optional[float] = None      # vol actual / mediana (≈1 = sano)
    horas: Optional[float] = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "detected": self.detected, "score": self.score, "r2": self.r2,
            "slope_pct_h": self.slope_pct_h, "max_pullback_pct": self.max_pullback_pct,
            "pct_above_ema": self.pct_above_ema, "green_ratio": self.green_ratio,
            "vol_stability": self.vol_stability, "horas": self.horas,
            "reason": self.reason,
        }


def evaluar_grind(candles_15m: list, macro_trends: dict) -> GrindResult:
    """
    candles_15m: buffer 15m INCLUYENDO la vela en formacion (candles_tf_live).
    macro_trends: {'1h': 'ALCISTA', '4h': ..., '1d': ...} para confluencia.
    """
    s = get_settings()
    res = GrindResult()

    w = s.grind_window_15m
    if len(candles_15m) < w + 5:
        res.reason = "datos insuficientes"
        return res

    ventana = list(candles_15m)[-w:]
    closes = np.array([c.c for c in ventana], dtype=float)
    opens = np.array([c.o for c in ventana], dtype=float)
    vols = np.array([c.v for c in ventana], dtype=float)
    if np.any(closes <= 0):
        return res

    res.horas = round(w * 0.25, 2)

    # --- 1. Ajuste log-lineal: pendiente + R^2 -------------------------------
    y = np.log(closes)
    x = np.arange(w, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    res.r2 = round(max(0.0, min(1.0, r2)), 3)

    # slope es log-retorno por vela de 15m -> 4 velas = 1 hora
    res.slope_pct_h = round((float(np.exp(slope * 4.0)) - 1.0) * 100.0, 3)

    if slope <= 0:
        res.reason = "pendiente no positiva"
        return res

    # --- 2. Peor retroceso dentro de la ventana ------------------------------
    run_max = np.maximum.accumulate(closes)
    dd = (closes - run_max) / run_max
    res.max_pullback_pct = round(abs(float(dd.min())) * 100.0, 2)

    # --- 3. Persistencia sobre la EMA25 --------------------------------------
    closes_full = np.array([c.c for c in candles_15m], dtype=float)
    ema25 = _ema(closes_full, 25)[-w:]
    res.pct_above_ema = round(float(np.mean(closes > ema25)), 3)
    res.green_ratio = round(float(np.mean(closes > opens)), 3)

    # --- 4. Estabilidad de volumen (un grind sano NO tiene spikes) -----------
    med_vol = float(np.median(vols))
    res.vol_stability = round(float(vols[-1] / med_vol), 2) if med_vol > 0 else 1.0

    # --- 5. Filtros duros ----------------------------------------------------
    if res.r2 < s.grind_r2_min:
        res.reason = f"R2={res.r2} < {s.grind_r2_min} (subida erratica, no sostenida)"
        return res
    if res.slope_pct_h < s.grind_slope_min_pct_h:
        res.reason = f"pendiente {res.slope_pct_h}%/h demasiado plana"
        return res
    if res.slope_pct_h > s.grind_slope_max_pct_h:
        # Esto ya no es "lento y constante" — es el otro perfil
        res.reason = f"pendiente {res.slope_pct_h}%/h: perfil de ignicion, no de tendencia"
        return res
    if res.max_pullback_pct > s.grind_max_pullback_pct:
        res.reason = f"retroceso {res.max_pullback_pct}% rompe la constancia"
        return res
    if res.pct_above_ema < s.grind_min_above_ema:
        res.reason = f"solo {res.pct_above_ema:.0%} de cierres sobre EMA25"
        return res

    # --- 6. Score ------------------------------------------------------------
    val = 45
    val += int((res.r2 - s.grind_r2_min) / max(1e-9, 1.0 - s.grind_r2_min) * 25)
    val += int(min(res.pct_above_ema, 1.0) * 12)
    val += int(min(res.green_ratio, 1.0) * 8)
    # Retroceso superficial suma; profundo resta
    val += int(max(0.0, (s.grind_max_pullback_pct - res.max_pullback_pct)) * 3)
    # Confluencia macro de TFs superiores
    for tf, peso in (("1h", 6), ("4h", 6), ("1d", 4)):
        t = macro_trends.get(tf, "NEUTRAL")
        if t == "ALCISTA":
            val += peso
        elif t == "BAJISTA":
            val -= peso * 2
    # Un spike de volumen en un grind suele ser el final, no el principio
    if res.vol_stability > 3.0:
        val -= 12
    elif res.vol_stability > 2.0:
        val -= 5

    res.score = max(0, min(100, val))
    res.detected = res.score >= s.grind_score_min
    res.reason = (
        f"R2={res.r2} | {res.slope_pct_h}%/h durante {res.horas}h | "
        f"retroceso max {res.max_pullback_pct}% | "
        f"{res.pct_above_ema:.0%} sobre EMA25 | vol {res.vol_stability}x mediana"
    )
    return res


# =============================================================================
#  ALERTA B — IGNICION
# =============================================================================

@dataclass
class IgnitionResult:
    detected: bool = False
    score: int = 0
    roc_pct: Optional[float] = None            # % en la ventana corta
    vol_ratio: Optional[float] = None
    z_rise: Optional[float] = None
    buy_ratio: Optional[float] = None
    desde_compresion: bool = False             # venia de consolidacion
    recorrido_consumido_pct: Optional[float] = None
    pct_dia: Optional[float] = None            # % desde el ancla fija 00:00 UTC
    pos_dia: Optional[float] = None            # posicion en el rango del dia
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "detected": self.detected, "score": self.score, "roc_pct": self.roc_pct,
            "vol_ratio": self.vol_ratio, "z_rise": self.z_rise,
            "buy_ratio": self.buy_ratio, "desde_compresion": self.desde_compresion,
            "recorrido_consumido_pct": self.recorrido_consumido_pct,
            "pct_dia": self.pct_dia, "pos_dia": self.pos_dia,
            "reason": self.reason,
        }


def evaluar_ignicion(
    candles_1m: list,
    metrics,
    flow=None,
    consolidando_antes: bool = False,
    ind=None,
    blow_off: bool = False,
    daily: Optional[dict] = None,
) -> IgnitionResult:
    """
    candles_1m: buffer 1m cerrado.
    metrics: Metrics del SymbolState (z_rise, vol_ratio...).
    flow: FlowSnapshot (aggTrade). Puede venir vacio si el par no esta en la
          shortlist — entonces el flujo no suma ni resta.
    consolidando_antes: si el par venia de compresion (expansion = spring).
    """
    s = get_settings()
    res = IgnitionResult()

    if blow_off:
        res.reason = "veto: blow-off ya detectado (llegariamos tarde)"
        return res

    w = s.ignition_window_1m
    if len(candles_1m) < w + 30:
        res.reason = "datos insuficientes"
        return res

    closes = [c.c for c in candles_1m]
    ref = closes[-(w + 1)]
    if ref <= 0:
        return res

    res.roc_pct = round((closes[-1] - ref) / ref * 100.0, 3)
    res.vol_ratio = round(float(metrics.vol_ratio), 2)
    res.z_rise = round(float(metrics.z_rise), 2)
    res.desde_compresion = bool(consolidando_antes)
    if flow is not None and getattr(flow, "trades_30s", 0) >= s.flow_min_trades:
        res.buy_ratio = round(float(flow.buy_ratio_30s), 3)

    # --- Filtros duros: los tres a la vez ------------------------------------
    if res.roc_pct < s.ignition_roc_min_pct:
        res.reason = f"ROC {res.roc_pct}% < {s.ignition_roc_min_pct}%"
        return res
    if res.vol_ratio < s.ignition_vol_mult:
        res.reason = f"volumen {res.vol_ratio}x < {s.ignition_vol_mult}x (movimiento sin respaldo)"
        return res
    if res.z_rise < s.ignition_z_min:
        res.reason = f"z_rise {res.z_rise} < {s.ignition_z_min}"
        return res

    # --- Cuanto del movimiento ya se consumio --------------------------------
    # Si el precio ya esta muy por encima del rango previo, la ignicion ya
    # ocurrio y entrar aqui es comprar el techo.
    prev = closes[-(w + 31):-(w + 1)]
    if prev:
        base = float(np.median(prev))
        if base > 0:
            res.recorrido_consumido_pct = round((closes[-1] - base) / base * 100.0, 2)

    # --- Score ---------------------------------------------------------------
    val = 40
    val += int(min((res.roc_pct - s.ignition_roc_min_pct) * 8, 18))
    val += int(min((res.vol_ratio - s.ignition_vol_mult) * 4, 14))
    val += int(min((res.z_rise - s.ignition_z_min) * 6, 12))

    if res.desde_compresion:
        val += 10  # expansion desde base comprimida: el arranque mas limpio

    if res.buy_ratio is not None:
        if res.buy_ratio >= 0.60:
            val += 12
        elif res.buy_ratio <= 0.45:
            val -= 20  # sube con vendedores agresivos dominando: sospechoso

    if ind is not None and getattr(ind, "valid", False):
        if ind.rsi5 > s.ignition_rsi_max:
            val -= 15  # ya sobreextendido
        if ind.macd_rising:
            val += 5

    if res.recorrido_consumido_pct is not None:
        if res.recorrido_consumido_pct > s.ignition_max_consumido_pct:
            val -= 22  # llegamos tarde
        elif res.recorrido_consumido_pct < s.ignition_max_consumido_pct * 0.5:
            val += 8   # temprano en el movimiento

    # --- Contexto del dia (ancla fija 00:00 UTC) -----------------------------
    # El recorrido consumido de arriba solo mira 30 minutos. Una moneda que
    # lleva subiendo despacio todo el dia se le escapa a esa ventana, pero el
    # ancla diaria si la ve: si ya acumula mucho y ademas esta pegada al maximo
    # del dia, esta ignicion es probablemente el ultimo tramo, no el primero.
    if daily and daily.get("valid"):
        res.pct_dia = daily.get("pct_desde_open_diario")
        res.pos_dia = daily.get("pos_en_rango_diario")
        if res.pct_dia is not None and res.pct_dia >= s.ignition_pct_dia_alto:
            val -= 18
            if res.pos_dia is not None and res.pos_dia >= 0.95:
                val -= 10   # ademas clavada en el maximo del dia
        elif res.pct_dia is not None and res.pct_dia <= 0.0:
            val += 6        # arranca desde terreno negativo del dia: mas recorrido

    res.score = max(0, min(100, val))
    res.detected = res.score >= s.ignition_score_min
    extra = " | desde compresion" if res.desde_compresion else ""
    flujo = f" | compra {res.buy_ratio:.0%}" if res.buy_ratio is not None else " | sin flujo"
    res.reason = (
        f"ROC {res.roc_pct}% en {w}m | vol {res.vol_ratio}x | z={res.z_rise}"
        f"{flujo}{extra} | consumido {res.recorrido_consumido_pct}%"
        + (f" | dia {res.pct_dia:+.2f}% pos {res.pos_dia:.2f}"
           if res.pct_dia is not None and res.pos_dia is not None else "")
    )
    return res
