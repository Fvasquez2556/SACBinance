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

        # Vela HTF EN FORMACION por TF (no entra al buffer cerrado)
        self.live_htf: Dict[str, Optional[Candle]] = {
            "5m": None, "15m": None, "1h": None, "4h": None, "1d": None,
        }
        self.live_htf_ts: Dict[str, int] = {}

        # Indicadores tecnicos 1m (calculados al cerrar vela 1m)
        self.ind: Optional[IndSnap] = None

        # Indicadores por TF superior. Antes solo existian los de 1m y se
        # publicaban como "rsi5"/"macd_rising", lo que jamas podia coincidir
        # con el RSI(6) de 15m que el usuario ve en Binance: son metricas
        # distintas, no un desfase.
        self.ind_htf: Dict[str, Optional[IndSnap]] = {}

        # Timestamps de ultimo recalculo (throttling)
        self.last_heavy_ms: int = 0
        self.last_htf_live_calc: Dict[str, float] = {}

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

        # Ancla diaria fija (00:00 UTC) y perfiles de subida
        self.daily: dict = {}
        self.grind: dict = {}
        self.ignition: dict = {}
        self.compresion: dict = {}
        self.taxonomia: dict = {}
        self.prev_consolidando: bool = False

        # Fuerza del impulso (derivada) y alerta congelada viva, si la hay
        self.impulso: dict = {}
        self.base_rebote: dict = {}
        self.retroceso: dict = {}
        # Cuanto se movio el par en los 60 min previos. Es la variable que
        # mejor separo el resultado en research/caida_profunda.py: con rango
        # <1% llega a la meta el 40.6% y con 3.5-6% el 75.6%. Se guarda en el
        # outcome para poder regresar sobre ella.
        self.rango_1h_pct: float | None = None
        # La enesima señal de este par. La 1a llega el 58.8% y la 5a o mas el
        # 49.0% (research/contexto_limpio.py).
        self.senal_n: int = 0
        # Entry de la PRIMERA señal del episodio actual. Felix pidio medir el
        # "superado" desde ahi y no desde la señal en curso: si la quinta entra
        # mas abajo y sube 4.2% desde su propio entry, puede seguir por debajo
        # del precio de la primera. Medido desde la primera, no engaña.
        # Se reinicia cuando el par lleva mas de una ventana sin señales.
        self.primer_entry: float | None = None
        self.primer_entry_ts: int = 0
        self.alerta: dict = {}

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
        buf = self.get_candles_tf(tf)
        # Idempotente: si la vela viva ya se habia adelantado, no duplicar
        if buf and buf[-1].t == candle.t:
            buf[-1] = candle
        else:
            buf.append(candle)
        # La vela viva de ese TF queda obsoleta al cerrar
        self.live_htf[tf] = None

    def fusionar_velas_htf(self, tf: str, velas) -> int:
        """
        Igual que `fusionar_velas`, para un marco superior.

        `preload_htf` hacia `buf.append(c)` sin mirar: cada reparacion periodica
        volvia a meter las mismas velas de 15m y 1h. El buffer es un deque
        acotado, asi que el efecto no era crecer sino EXPULSAR historia real por
        copias — 260 huecos de 15m se convertian en 130 velas distintas y 130
        repetidas, y las medias largas se calculaban sobre la mitad del tiempo
        que creian cubrir.
        """
        buf = self.get_candles_tf(tf)
        nuevas = [c for c in velas if c is not None]
        if not nuevas:
            return 0
        fusion = {c.t: c for c in buf}
        antes = len(fusion)
        for c in nuevas:
            fusion[c.t] = c
        ordenadas = [fusion[t] for t in sorted(fusion)][-buf.maxlen:] if buf.maxlen else [fusion[t] for t in sorted(fusion)]
        buf.clear()
        buf.extend(ordenadas)
        return max(0, len(fusion) - antes)

    def set_live_htf(self, tf: str, candle: Candle) -> None:
        """Vela HTF en formacion (k['x'] == False). No toca el buffer cerrado."""
        if tf in self.live_htf:
            self.live_htf[tf] = candle
            self.live_htf_ts[tf] = candle.t

    def candles_tf_live(self, tf: str) -> list:
        """
        Buffer del TF + la vela EN FORMACION al final, si existe y es posterior
        a la ultima cerrada. Esto es lo que dibuja Binance.
        """
        base = list(self.get_candles_tf(tf))
        live = self.live_htf.get(tf)
        if live is None:
            return base
        if base and live.t <= base[-1].t:
            return base
        return base + [live]

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
        """
        Vela 1m cerrada: muta buffer + estadistica adaptativa. True si warm.

        Idempotente por apertura de vela. El mismo minuto llega dos veces cada
        vez que el WS reconecta, y la reparacion por REST repite tramos que ya
        habian entrado: contarlo dos veces mete su retorno dos veces en la EWMA
        —que es la escala con la que se miden TODOS los z-scores— y adelanta
        `candles_in_fsm` sin que haya pasado un minuto. Una vela repetida
        refresca los valores sin volver a alimentar la estadistica; una
        anterior a la ultima no entra por aqui (ver `fusionar_velas`).
        """
        if self.candles and c.t <= self.candles[-1].t:
            warm = self.stats.ready_n >= self._warmup
            if c.t == self.candles[-1].t:
                self.candles[-1] = c
                self.ind = indicators_from_candles(self.candles)
                self.live_metrics = None
            return warm

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

    def fusionar_velas(self, velas) -> int:
        """
        Mete un lote de velas 1m en el buffer sin duplicar y en orden.

        Es el camino de la REPARACION, distinto del de la vela en vivo. Un
        hueco interno —un minuto que el WS no trajo y el REST recupera despues—
        cae por debajo del final del buffer, y `add_closed_candle` lo
        rechazaria por atrasado. Aqui se reconstruye el buffer entero por
        apertura de vela, que es la identidad unica del minuto.

        La estadistica adaptativa NO se realimenta con lo insertado por el
        medio: su EWMA es secuencial y reinyectarla fuera de orden desplazaría
        sigma sin que el mercado haya hecho nada. Lo que se recupera es la
        CONTINUIDAD del buffer, que es lo que leen los indicadores y lo que
        decide si una ventana se puede sostener. Devuelve cuantas velas
        faltaban de verdad.
        """
        nuevas = [c for c in velas if c is not None]
        if not nuevas:
            return 0
        if not self.candles:
            insertadas = 0
            for c in sorted(nuevas, key=lambda x: x.t):
                self.add_closed_candle(c)
                insertadas += 1
            return insertadas

        tope = self.candles[-1].t
        posteriores = sorted((c for c in nuevas if c.t > tope), key=lambda x: x.t)
        internas = {c.t: c for c in nuevas if c.t <= tope}

        insertadas = 0
        conocidas = {c.t for c in self.candles}
        faltantes = {t: c for t, c in internas.items() if t not in conocidas}
        if faltantes:
            fusion = {c.t: c for c in self.candles}
            fusion.update(faltantes)
            ordenadas = [fusion[t] for t in sorted(fusion)][-self.candles.maxlen:]
            self.candles.clear()
            self.candles.extend(ordenadas)
            insertadas += len(faltantes)

        for c in posteriores:
            self.add_closed_candle(c)
            insertadas += 1

        if insertadas:
            self.ind = indicators_from_candles(self.candles)
        return insertadas

    def huecos_1m(self, desde_ms: int = 0) -> int:
        """
        Minutos ausentes ENTRE la primera y la ultima vela del buffer.

        El detector de reparacion miraba solo el ultimo minuto: en cuanto el
        stream volvia, el hueco dejaba de ser visible y se quedaba dentro para
        siempre. En la copia del 10-sep quedaban 2.344 minutos-par ausentes en
        224 simbolos, todos internos, todos invisibles para ese detector.
        """
        velas = [c for c in self.candles if c.t >= desde_ms]
        if len(velas) < 2:
            return 0
        esperados = (velas[-1].t - velas[0].t) // 60_000 + 1
        return max(0, int(esperados) - len(velas))

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
            # Indicadores 1m (los de siempre — nombres conservados por el frontend)
            "rsi5": round(self.ind.rsi5, 1) if self.ind else None,
            "macd_rising": self.ind.macd_rising if self.ind else None,
            "trend_up": self.ind.trend_up if self.ind else None,
            "rsi14_1m": round(self.ind.rsi14, 1) if self.ind else None,
            # Indicadores por TF superior — estos SI son comparables con Binance
            "ind_htf": {
                tf: {
                    "rsi14": round(snap.rsi14, 1),
                    "rsi5": round(snap.rsi5, 1),
                    "macd_hist": round(snap.macd_hist, 8),
                    "macd_rising": snap.macd_rising,
                    "trend_up": snap.trend_up,
                    "bb_position": round(snap.bb_position, 3),
                    "atr_pct": round(snap.atr_pct, 3),
                    "ema7": snap.ema7,
                    "ema25": snap.ema25,
                    "ema99": snap.ema99,
                }
                for tf, snap in self.ind_htf.items()
                if snap is not None and snap.valid
            },
            "htf_live_age_ms": {
                tf: max(0, _now - ts) for tf, ts in self.live_htf_ts.items()
            },
            "n_candles_1m": len(self.candles),
            "fsm_since_ms": self.fsm_since_ms,
            "score_since_ms": self.score_since_ms,
            "daily": dict(self.daily),
            "grind": dict(self.grind),
            "ignition": dict(self.ignition),
            "compresion": dict(self.compresion),
            "taxonomia": dict(self.taxonomia),
            "impulso": dict(self.impulso),
            "base_rebote": dict(self.base_rebote),
            "retroceso": dict(self.retroceso),
            "rango_1h_pct": self.rango_1h_pct,
            "senal_n": self.senal_n,
            "primer_entry": self.primer_entry,
            "alerta": dict(self.alerta),
            "trade_levels": dict(self.trade_levels),
            "consolidation": dict(self.consolidation_info),
            "sr_levels": dict(self.sr_levels),
            "btc_regime": self.btc_regime,
            "is_fakeout": _now < self.fakeout_until_ms,
            "fading": fading,
        }
