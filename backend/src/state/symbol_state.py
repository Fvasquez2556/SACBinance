"""
Estado completo por moneda: buffers multi-TF, FSM 1m, gate macro, historial.
Extiende el patron de v2 con capas de confirmacion y contexto macro.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional

import numpy as np

from src.config.settings import get_settings
from src.flow.aggtrade_flow import FlowSnapshot, FlowState
from src.indicators.calculator import IndSnap, indicators_from_candles
from src.state.adaptive import AdaptiveStats


# --- Candle -------------------------------------------------------------------

@dataclass
class Candle:
    t: int
    o: float
    h: float
    l: float
    c: float
    v: float


# --- Metricas 1m (para FSM) ---------------------------------------------------

@dataclass
class Metrics:
    price: float = 0.0
    ret_1m: float = 0.0
    cum_ret_drop: float = 0.0
    cum_ret_rise: float = 0.0
    z_drop: float = 0.0
    z_rise: float = 0.0
    velocity: float = 0.0
    sigma: float = 0.0
    vol_ratio: float = 1.0
    drawdown_from_peak: float = 0.0


# --- Display states (legibles para el usuario) --------------------------------

DISPLAY_CAYENDO = "CAYENDO"
DISPLAY_TOCO_FONDO = "TOCÓ_FONDO"
DISPLAY_CONSOLIDANDO = "CONSOLIDANDO"
DISPLAY_SUBIENDO = "SUBIENDO"
DISPLAY_BREAKOUT = "BREAKOUT_INCIPIENTE"
DISPLAY_NEUTRAL = "NEUTRAL"


def _cum_return(closes: list, window: int) -> float:
    if len(closes) <= window:
        return 0.0
    then = closes[-1 - window]
    if then <= 0:
        return 0.0
    return closes[-1] / then - 1.0


def _velocity(closes: list, sigma: float, k: int = 5) -> float:
    n = min(k, len(closes))
    if n < 3 or sigma <= 0:
        return 0.0
    arr = np.asarray(closes[-n:], dtype=float)
    if np.any(arr <= 0):
        return 0.0
    slope = np.polyfit(np.arange(n, dtype=float), np.log(arr), 1)[0]
    return float(slope / sigma)


def _drawdown(closes: list, highs: list, window: int = 30) -> float:
    n = min(window, len(highs))
    if n < 2:
        return 0.0
    peak = max(highs[-n:])
    if peak <= 0:
        return 0.0
    return (closes[-1] - peak) / peak


# --- Estado principal ---------------------------------------------------------

class SymbolState:
    def __init__(self, symbol: str) -> None:
        s = get_settings()
        self.symbol = symbol

        # Buffer 1m (FSM reactiva)
        self.candles: Deque[Candle] = deque(maxlen=s.candle_buffer_1m)

        # Buffers TF superiores (contexto macro)
        self.candles_5m: Deque[Candle] = deque(maxlen=s.candle_buffer_5m)
        self.candles_15m: Deque[Candle] = deque(maxlen=s.candle_buffer_15m)
        self.candles_1h: Deque[Candle] = deque(maxlen=s.candle_buffer_1h)
        self.candles_4h: Deque[Candle] = deque(maxlen=s.candle_buffer_4h)
        self.candles_1d: Deque[Candle] = deque(maxlen=s.candle_buffer_1d)

        # Estadisticas adaptativas (1m)
        self.stats = AdaptiveStats(alpha=s.ewma_alpha, sigma_min=s.sigma_min)
        self.metrics = Metrics()
        self.live_metrics: Optional[Metrics] = None
        self.live_ts: int = 0
        self.last_early: Optional[str] = None

        # Indicadores tecnicos (calculados al cerrar vela 1m)
        self.ind: Optional[IndSnap] = None

        # Flujo agresor (aggTrade) — solo activo para el top-40 shortlist
        self.flow = FlowState()
        self.flow_snap = FlowSnapshot()

        # Estado FSM interno
        self.fsm_state: str = "NEUTRAL"
        self.prev_fsm_state: str = "NEUTRAL"
        self.fsm_since_ms: int = 0
        self.peak_drop_velocity: float = 0.0
        self.stabilize_count: int = 0
        self.calm_count: int = 0
        self.candles_in_fsm: int = 0
        self._warmup = s.warmup_candles

        # Estado visible al usuario (5 estados legibles)
        self.display_state: str = DISPLAY_NEUTRAL
        self.score: int = 0
        self.prev_score: int = 0
        self.tier: str = "NINGUNO"
        self.score_since_ms: int = 0
        self.pos_en_rango: float = 0.5      # posicion del precio en el rango 15m
        self.last_interesting_ms: int = 0   # ultima vez que fue "interesante"

        # Tendencias macro por TF y gate
        self.macro_trends: Dict[str, str] = {
            "15m": "NEUTRAL",
            "1h": "NEUTRAL",
            "4h": "NEUTRAL",
            "1d": "NEUTRAL",
        }
        self.macro_global: str = "NEUTRAL"
        self.macro_gate_mult: float = 1.0

        # Slopes (ultimos calculados por TF)
        self.slopes: Dict[str, dict] = {}

        # Niveles de trading, consolidacion y soporte/resistencia
        self.trade_levels: dict = {}
        self.consolidation_info: dict = {}
        self.sr_levels: dict = {}

        # Regimen BTC aplicado al ultimo scoring
        self.btc_regime: str = "NEUTRAL"

        # Tracking de fakeout (breakout fallido)
        self.last_breakout_ms: int = 0
        self.last_breakout_level: float = 0.0
        self.fakeout_until_ms: int = 0

        # Historial de cambios de estado (persistido en SQLite)
        self.state_history: List[dict] = []

        # Lock para acceso concurrente desde WS-A y WS-B
        self._lock: asyncio.Lock = asyncio.Lock()

    # --- Buffers por TF -------------------------------------------------------

    def get_candles_tf(self, tf: str) -> Deque[Candle]:
        return {
            "1m": self.candles,
            "5m": self.candles_5m,
            "15m": self.candles_15m,
            "1h": self.candles_1h,
            "4h": self.candles_4h,
            "1d": self.candles_1d,
        }.get(tf, self.candles)

    def add_candle_htf(self, tf: str, candle: Candle) -> None:
        self.get_candles_tf(tf).append(candle)

    # --- Computacion de metricas 1m -------------------------------------------

    def _compute(self, extra: Optional[Candle], ret_1m: float) -> Metrics:
        s = get_settings()
        closes = [c.c for c in self.candles]
        highs = [c.h for c in self.candles]
        if extra is not None:
            closes = closes + [extra.c]
            highs = highs + [extra.h]
            price, vol = extra.c, extra.v
        else:
            price = self.candles[-1].c if self.candles else 0.0
            vol = self.candles[-1].v if self.candles else 0.0

        m = Metrics()
        m.price = price
        m.ret_1m = ret_1m
        m.sigma = self.stats.sigma
        m.cum_ret_drop = _cum_return(closes, s.drop_window)
        m.cum_ret_rise = _cum_return(closes, s.rise_window)
        m.z_drop = self.stats.z(m.cum_ret_drop, s.drop_window)
        m.z_rise = self.stats.z(m.cum_ret_rise, s.rise_window)
        m.velocity = _velocity(closes, self.stats.sigma)
        m.vol_ratio = self.stats.vol_ratio(vol)
        m.drawdown_from_peak = _drawdown(closes, highs)
        return m

    def add_closed_candle(self, c: Candle) -> bool:
        """Vela 1m cerrada: muta buffer + estadistica adaptativa. Retorna True si warm."""
        prev_close = self.candles[-1].c if self.candles else None
        self.candles.append(c)
        if prev_close and prev_close > 0:
            ret_1m = c.c / prev_close - 1.0
            self.stats.update(ret_1m=ret_1m, volume_1m=c.v)
        else:
            ret_1m = 0.0
        self.metrics = self._compute(None, ret_1m)
        self.ind = indicators_from_candles(self.candles)
        self.live_metrics = None
        self.live_ts = c.t
        self.candles_in_fsm += 1
        return self.stats.ready_n >= self._warmup

    def update_live(self, c: Candle) -> bool:
        """Vela 1m en formacion: metricas provisionales (no muta buffer)."""
        if not self.candles or self.stats.ready_n < self._warmup:
            return False
        last_close = self.candles[-1].c
        ret_1m = (c.c / last_close - 1.0) if last_close > 0 else 0.0
        self.live_metrics = self._compute(c, ret_1m)
        self.live_ts = c.t
        return True

    # --- Flujo y transicion FSM -----------------------------------------------

    def refresh_flow(self, now_ms: int) -> None:
        self.flow_snap = self.flow.snapshot(now_ms)

    def set_fsm_state(self, new_state: str) -> Optional[str]:
        if new_state == self.fsm_state:
            return None
        self.prev_fsm_state = self.fsm_state
        self.fsm_state = new_state
        self.fsm_since_ms = self.candles[-1].t if self.candles else 0
        self.candles_in_fsm = 0
        return new_state

    # --- Historial de estados --------------------------------------------------

    def push_state_history(self, timestamp_ms: int, display_state: str, score: int, tier: str) -> None:
        self.state_history.append({
            "ts": timestamp_ms,
            "state": display_state,
            "score": score,
            "tier": tier,
            "macro": self.macro_global,
            "fsm": self.fsm_state,
        })
        if len(self.state_history) > 200:
            self.state_history = self.state_history[-200:]

    # --- Snapshot para API/WS -------------------------------------------------

    def snapshot(self) -> dict:
        m = self.live_metrics if (
            self.live_metrics is not None
            and self.live_ts >= (self.candles[-1].t if self.candles else 0)
        ) else self.metrics

        # "fading": dejo de ser interesante pero sigue visible perdiendo fuerza
        s = get_settings()
        _interesting = {
            DISPLAY_TOCO_FONDO, DISPLAY_CONSOLIDANDO, DISPLAY_SUBIENDO, DISPLAY_BREAKOUT,
        }
        _now = int(time.time() * 1000)
        fading = (
            self.display_state not in _interesting
            and self.last_interesting_ms > 0
            and _now - self.last_interesting_ms < s.dashboard_retention_minutes * 60_000
        )

        return {
            "symbol": self.symbol,
            "display_state": self.display_state,
            "fsm_state": self.fsm_state,
            "prev_fsm_state": self.prev_fsm_state,
            "score": self.score,
            "score_trend": self.score - self.prev_score,
            "tier": self.tier,
            "pos_en_rango": round(self.pos_en_rango, 2),
            "macro_global": self.macro_global,
            "macro_gate_mult": round(self.macro_gate_mult, 2),
            "macro_trends": dict(self.macro_trends),
            "slopes": {
                tf: {k: v for k, v in d.items() if k.startswith("slope_") or k == "tendencia"}
                for tf, d in self.slopes.items()
            },
            "price": round(m.price, 8),
            "ret_1m_pct": round(m.ret_1m * 100, 3),
            "z_drop": round(m.z_drop, 2),
            "z_rise": round(m.z_rise, 2),
            "velocity": round(m.velocity, 2),
            "vol_ratio": round(m.vol_ratio, 2),
            "drawdown_pct": round(m.drawdown_from_peak * 100, 2),
            "sigma_pct": round(m.sigma * 100, 3),
            "buy_ratio_30s": round(self.flow_snap.buy_ratio_30s, 3),
            "flow_trades_30s": self.flow_snap.trades_30s,
            "flow_confirm": self.flow_snap.buy_dominant,
            "rsi5": round(self.ind.rsi5, 1) if self.ind else None,
            "macd_rising": self.ind.macd_rising if self.ind else None,
            "trend_up": self.ind.trend_up if self.ind else None,
            "n_candles_1m": len(self.candles),
            "fsm_since_ms": self.fsm_since_ms,
            "score_since_ms": self.score_since_ms,
            "trade_levels": dict(self.trade_levels),
            "consolidation": dict(self.consolidation_info),
            "sr_levels": dict(self.sr_levels),
            "btc_regime": self.btc_regime,
            "is_fakeout": _now < self.fakeout_until_ms,
            "fading": fading,
        }
