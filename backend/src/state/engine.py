"""
Orquestador principal: recibe velas cerradas/live de todos los TFs,
corre FSM 1m, aplica gate macro + gate BTC, detecta consolidacion, breakout
y fakeout, calcula soporte/resistencia y niveles de trading, mapea a display
state, evalua señales y emite eventos.
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable, Dict, List, Optional

from src.analysis.breakout import detectar_breakout
from src.analysis.consolidation import detectar_consolidacion
from src.analysis.levels import detectar_niveles
from src.analysis.ma_slopes import analizar_tf
from src.analysis.macro_gate import aplicar_gate, calcular_tendencia_global
from src.analysis.scoring import score_and_tier
from src.analysis.signal_tracker import abrir_senal, evaluar_senales
from src.analysis.trade_levels import calcular_niveles
from src.config.settings import get_settings
from src.patterns.blow_off import detect_blow_off
from src.state.state_machine import (
    FSM_BOTTOMING,
    FSM_DROPPING,
    FSM_EXHAUSTED,
    FSM_NEUTRAL,
    FSM_RISING,
    FSM_VALLEY,
    evaluate,
    provisional_state,
)
from src.state.symbol_state import (
    DISPLAY_BREAKOUT,
    DISPLAY_CAYENDO,
    DISPLAY_CONSOLIDANDO,
    DISPLAY_NEUTRAL,
    DISPLAY_SUBIENDO,
    DISPLAY_TOCO_FONDO,
    Candle,
    SymbolState,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

EmitFn = Callable[[dict], Awaitable[None]]

_EARLY_STATES = {FSM_RISING, FSM_DROPPING, FSM_EXHAUSTED}
_MACRO_TFS = ("15m", "1h", "4h", "1d")

_INTERESTING_DISPLAY = {
    DISPLAY_TOCO_FONDO,
    DISPLAY_CONSOLIDANDO,
    DISPLAY_SUBIENDO,
    DISPLAY_BREAKOUT,
}


def _pos_en_rango(candles_15m: list, price: float) -> float:
    """Posicion del precio dentro del rango 15m reciente. 0 = minimo, 1 = maximo."""
    s = get_settings()
    if not candles_15m or price <= 0:
        return 0.5
    recent = list(candles_15m)[-s.rango_lookback_15m:]
    if len(recent) < 5:
        return 0.5
    hi = max(c.h for c in recent)
    lo = min(c.l for c in recent)
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (price - lo) / (hi - lo)))


def _fsm_to_display(
    fsm_state: str,
    consolidating: bool,
    breakout: bool,
    pos_rango: float,
    trend_15m: str,
) -> str:
    """
    Mapea la FSM 1m al estado visible, VALIDADO CON CONTEXTO.

    Clave: un BOTTOMING/VALLEY de 1m solo es "TOCÓ FONDO" si el precio esta
    de verdad en la zona baja del rango 15m. Si esta arriba, un dip de 1m es
    un pullback (tendencia alcista) o distribucion post-pump (bajista) —
    nunca un fondo.
    """
    s = get_settings()
    if breakout:
        return DISPLAY_BREAKOUT
    if fsm_state in (FSM_DROPPING, FSM_EXHAUSTED):
        return DISPLAY_CAYENDO
    if fsm_state == FSM_RISING:
        return DISPLAY_SUBIENDO
    if fsm_state in (FSM_BOTTOMING, FSM_VALLEY):
        if pos_rango <= s.toco_fondo_max_pos:
            # Fondo real: precio en la zona baja del rango
            if fsm_state == FSM_VALLEY and consolidating:
                return DISPLAY_CONSOLIDANDO
            return DISPLAY_TOCO_FONDO
        # Precio en zona media/alta -> NO es un fondo
        if trend_15m == "ALCISTA":
            return DISPLAY_SUBIENDO      # pausa dentro de una subida
        if trend_15m == "BAJISTA":
            return DISPLAY_CAYENDO       # retroceso / distribucion post-pump
        return DISPLAY_NEUTRAL
    # FSM NEUTRAL: consolidacion lateral "fria" (solo si no esta en maximos)
    if consolidating and pos_rango <= 0.6:
        return DISPLAY_CONSOLIDANDO
    return DISPLAY_NEUTRAL


def _score_consolidacion(cons) -> tuple:
    """Score de calidad para consolidacion lateral con FSM en NEUTRAL (es contexto)."""
    q = 50
    if cons.atr_percentile is not None:
        q += int(max(0, 20 - cons.atr_percentile))
    q += min(cons.candles_in_state, 8)
    if cons.vol_declining:
        q += 4
    q = min(q, 68)
    return q, _tier_from_score(q)


def _tier_from_score(val: int) -> str:
    s = get_settings()
    if val >= s.tier_extra:
        return "EXTRA-FUERTE"
    if val >= s.tier_fuerte:
        return "FUERTE"
    if val >= s.tier_moderada:
        return "MODERADA"
    if val >= s.tier_vigilancia:
        return "VIGILANCIA"
    return "NINGUNO"


def _tier_order(tier: str) -> int:
    return {"NINGUNO": 0, "VIGILANCIA": 1, "MODERADA": 2, "FUERTE": 3, "EXTRA-FUERTE": 4}.get(tier, 0)


class StateEngine:
    def __init__(self, emit: Optional[EmitFn] = None) -> None:
        self.states: Dict[str, SymbolState] = {}
        self._emit = emit
        self._last_tier: Dict[str, str] = {}
        self._last_live: Dict[str, float] = {}
        self._db = None

    def set_emit(self, emit: EmitFn) -> None:
        self._emit = emit

    def set_db(self, db) -> None:
        self._db = db

    def _log_db(self, symbol: Optional[str], level: str, message: str) -> None:
        """Persiste un evento clave en analysis_log (no bloquea si falla)."""
        if self._db is None:
            return
        try:
            self._db.log_analysis(symbol, level, message)
        except Exception:
            pass

    def _get(self, symbol: str) -> SymbolState:
        st = self.states.get(symbol)
        if st is None:
            st = SymbolState(symbol)
            self.states[symbol] = st
        return st

    def is_warm(self, symbol: str) -> bool:
        st = self.states.get(symbol)
        return st is not None and len(st.candles) > 0

    def preload_1m(self, symbol: str, candles: list) -> None:
        if self.is_warm(symbol):
            return
        st = self._get(symbol)
        for c in candles:
            st.add_closed_candle(c)
        if candles:
            logger.info(f"[{symbol}] backfill {len(candles)} velas 1m (warm)")

    def preload_htf(self, symbol: str, tf: str, candles: list) -> None:
        st = self._get(symbol)
        buf = st.get_candles_tf(tf)
        for c in candles:
            buf.append(c)
        logger.debug(f"[{symbol}] backfill {len(candles)} velas {tf}")

    # --- Macro / regimen BTC --------------------------------------------------

    def _update_macro(self, st: SymbolState) -> None:
        s = get_settings()
        for tf in _MACRO_TFS:
            candles = list(st.get_candles_tf(tf))
            result = analizar_tf(candles, s.slope_lookback)
            if result.get("valid"):
                st.slopes[tf] = result
                st.macro_trends[tf] = result["tendencia"]
        st.macro_global = calcular_tendencia_global(st.macro_trends)

    def _btc_regime(self) -> str:
        """Tendencia macro global de BTC: gate de mercado por encima del gate por-par."""
        btc = self.states.get(get_settings().btc_symbol)
        return btc.macro_global if btc is not None else "NEUTRAL"

    def on_htf_candle(self, symbol: str, tf: str, candle: Candle) -> None:
        st = self.states.get(symbol)
        if st is None:
            return
        st.add_candle_htf(tf, candle)
        if self._db is not None:
            try:
                self._db.save_kline(symbol, tf, candle)
            except Exception:
                pass
        if tf in _MACRO_TFS:
            self._update_macro(st)

    # --- 1m (FSM reactiva) ----------------------------------------------------

    async def on_closed_candle(
        self, symbol: str, t: int, o: float, h: float, l: float, c: float, v: float
    ) -> None:
        st = self._get(symbol)
        candle = Candle(t=t, o=o, h=h, l=l, c=c, v=v)
        ready = st.add_closed_candle(candle)

        # Checkpoint: persistir la vela 1m cerrada
        if self._db is not None:
            try:
                self._db.save_kline(symbol, "1m", candle)
            except Exception:
                pass

        # Auto-evaluacion: la vela nueva puede tocar TP/SL de señales abiertas
        cerradas = evaluar_senales(symbol, h, l, c, self._db)
        for sig in cerradas:
            if self._emit:
                await self._emit({
                    "type": "signal_closed",
                    "ts": int(time.time() * 1000),
                    "symbol": symbol,
                    "signal": sig,
                })

        if not ready:
            return

        s = get_settings()
        now_ms = int(time.time() * 1000)
        st.refresh_flow(now_ms)

        # Veto blow-off
        bo = detect_blow_off(st.candles)
        if bo.detected:
            st.set_fsm_state(FSM_EXHAUSTED)
            st.last_early = None
            self._last_tier[symbol] = "NINGUNO"
            st.display_state = DISPLAY_CAYENDO
            st.score = 0
            st.tier = "NINGUNO"
            st.trade_levels = {}
            logger.info(f"[{symbol}] -> AGOTADO (blow-off) {bo.reason}")
            self._log_db(symbol, "VETO", f"AGOTADO (blow-off): {bo.reason}")
            if self._emit:
                await self._emit({"type": "transition", "ts": now_ms, **st.snapshot()})
            return

        # FSM
        transition = evaluate(st)

        # Macro
        if not st.slopes:
            self._update_macro(st)

        # Soporte / resistencia (sobre velas 1h)
        sr = detectar_niveles(list(st.candles_1h), st.metrics.price)
        st.sr_levels = sr.to_dict()

        # Consolidacion (independiente de la FSM 1m)
        slopes_15m = st.slopes.get("15m", {})
        cons = detectar_consolidacion(list(st.candles_15m), "15m", slopes_15m)
        consolidating = cons.consolidating
        st.consolidation_info = {
            "consolidating": cons.consolidating,
            "atr_pct": cons.atr_pct,
            "atr_percentile": cons.atr_percentile,
            "ma_convergent": cons.ma_convergent,
            "vol_declining": cons.vol_declining,
            "candles_in_state": cons.candles_in_state,
        }

        # Score base con gate macro
        val, tier = score_and_tier(
            fsm_state=st.fsm_state,
            metrics=st.metrics,
            macro_global=st.macro_global,
            stabilize_count=st.stabilize_count,
            flow=st.flow_snap,
            ind=st.ind,
        )
        _, mult = aplicar_gate(val, st.fsm_state, st.macro_global)

        # Gate BTC: el regimen del mercado por encima del gate por-par
        btc_reg = self._btc_regime()
        st.btc_regime = btc_reg
        if st.fsm_state == FSM_RISING:
            if btc_reg == "BAJISTA":
                val = max(0, int(val * s.btc_bajista_mult))
            elif btc_reg == "ALCISTA":
                val = min(100, int(val * s.btc_alcista_mult))
            tier = _tier_from_score(val)

        # Consolidacion lateral fria (FSM NEUTRAL): score de contexto
        if consolidating and st.fsm_state == FSM_NEUTRAL:
            val, tier = _score_consolidacion(cons)
            mult = 1.0

        # --- Fakeout: ¿un breakout previo fallo? ---
        if (
            st.last_breakout_ms > 0
            and st.last_breakout_level > 0
            and now_ms - st.last_breakout_ms <= s.fakeout_lookback_candles * 60_000
            and c < st.last_breakout_level
        ):
            st.fakeout_until_ms = now_ms + s.fakeout_penalty_minutes * 60_000
            st.last_breakout_ms = 0
            logger.info(f"[{symbol}] FAKEOUT: breakout fallido, penalizado {s.fakeout_penalty_minutes}min")
            self._log_db(symbol, "FAKEOUT", f"Breakout fallido — penalizado {s.fakeout_penalty_minutes}min")

        in_fakeout = now_ms < st.fakeout_until_ms
        if in_fakeout:
            val = int(val * 0.5)
            tier = _tier_from_score(val)

        # Breakout incipiente (suprimido durante penalizacion de fakeout)
        ma99_1h = st.slopes.get("1h", {}).get("ma99", 0.0)
        bo_brk = detectar_breakout(list(st.candles), ma99_1h, val)
        breakout = bo_brk.detected and not in_fakeout
        if breakout:
            st.last_breakout_ms = now_ms
            st.last_breakout_level = ma99_1h
            if _tier_order(tier) < _tier_order("FUERTE"):
                tier = "FUERTE"

        # Posicion del precio en el rango 15m (contexto para el display)
        pos_rango = _pos_en_rango(list(st.candles_15m), st.metrics.price)
        st.pos_en_rango = pos_rango
        trend_15m = st.macro_trends.get("15m", "NEUTRAL")

        # Display state (FSM 1m VALIDADA con contexto)
        display = _fsm_to_display(st.fsm_state, consolidating, breakout, pos_rango, trend_15m)

        # Niveles de trading (con soporte/resistencia)
        levels = calcular_niveles(st.metrics.price, list(st.candles_15m), display, sr)
        st.trade_levels = levels.to_dict()

        prev_display = st.display_state
        st.prev_score = st.score
        st.display_state = display
        st.score = val
        st.tier = tier
        st.macro_gate_mult = mult
        if display in _INTERESTING_DISPLAY:
            st.last_interesting_ms = now_ms

        alertable = display in _INTERESTING_DISPLAY and val >= s.score_min_dashboard
        state_changed = display != prev_display
        tier_changed = (
            alertable
            and tier != "NINGUNO"
            and _tier_order(tier) > _tier_order(self._last_tier.get(symbol, "NINGUNO"))
        )

        if state_changed:
            st.push_state_history(now_ms, display, val, tier)
            st.score_since_ms = now_ms
            logger.info(
                f"[{symbol}] {prev_display} -> {display} | fsm={st.fsm_state} "
                f"score={val} tier={tier} macro={st.macro_global} btc={btc_reg} "
                f"gate={mult:.2f}x" + (f" | BREAKOUT: {bo_brk.reason}" if breakout else "")
            )
            if self._db is not None:
                try:
                    self._db.save_state(
                        symbol, now_ms, display, st.fsm_state, val, tier,
                        st.macro_global, st.metrics.price,
                    )
                except Exception as e:
                    logger.debug(f"[{symbol}] db.save_state error: {e}")
            self._log_db(
                symbol, "STATE",
                f"{prev_display} -> {display} | score={val} tier={tier} "
                f"macro={st.macro_global} btc={btc_reg}",
            )

        if alertable and (state_changed or tier_changed):
            self._last_tier[symbol] = tier
            snap = st.snapshot()

            # Auto-evaluacion: registrar la señal para medir su resultado
            abrir_senal(symbol, snap, self._db)

            tl = st.trade_levels
            niveles_txt = ""
            if tl.get("valid"):
                niveles_txt = (
                    f" | entry={tl['entry']} TP={tl['take_profit']} "
                    f"SL={tl['stop_loss']} R:R={tl['risk_reward']}"
                )
            logger.info(
                f"[{symbol}] ALERTA {tier} | {display} | score={val} "
                f"macro={st.macro_global} btc={btc_reg}{niveles_txt}"
            )
            self._log_db(symbol, "ALERT", f"{tier} | {display} | score={val}{niveles_txt}")
            if self._emit:
                await self._emit({
                    "type": "alert",
                    "ts": now_ms,
                    "tier": tier,
                    "state_changed": state_changed,
                    **snap,
                })
        elif transition and self._emit:
            await self._emit({"type": "transition", "ts": now_ms, **st.snapshot()})

    async def on_live_candle(
        self, symbol: str, t: int, o: float, h: float, l: float, c: float, v: float
    ) -> None:
        st = self.states.get(symbol)
        if st is None:
            return

        now = time.monotonic()
        s = get_settings()
        if now - self._last_live.get(symbol, 0.0) < s.live_min_interval:
            return
        self._last_live[symbol] = now

        if not st.update_live(Candle(t=t, o=o, h=h, l=l, c=c, v=v)):
            return

        st.refresh_flow(int(time.time() * 1000))
        pm = st.live_metrics
        ps = provisional_state(pm, s)

        if ps is None or ps == st.fsm_state or ps == st.last_early:
            return
        if ps not in _EARLY_STATES:
            return

        st.last_early = ps
        val, tier = score_and_tier(
            fsm_state=ps,
            metrics=pm,
            macro_global=st.macro_global,
            stabilize_count=st.stabilize_count,
            flow=st.flow_snap,
            ind=st.ind,
        )
        kind = "early" if ps == FSM_RISING else "watch"
        logger.info(
            f"[{symbol}] {'ADELANTO' if kind == 'early' else 'VIGILANCIA'} {ps} "
            f"(provisional) | score={val} macro={st.macro_global}"
        )
        if self._emit:
            snap = st.snapshot()
            snap["prov_fsm"] = ps
            await self._emit({
                "type": kind,
                "ts": int(time.time() * 1000),
                "score": val,
                "tier": tier,
                **snap,
            })

    async def on_trade(
        self, symbol: str, t: int, price: float, qty: float, is_buyer_maker: bool
    ) -> None:
        st = self.states.get(symbol)
        if st is None:
            return
        st.flow.add_trade(t, price, qty, is_buyer_maker)

    # --- Snapshot -------------------------------------------------------------

    def snapshot_all(self, min_score: int = 0) -> List[dict]:
        s = get_settings()
        threshold = max(min_score, s.score_min_dashboard)
        now_ms = int(time.time() * 1000)
        retention_ms = s.dashboard_retention_minutes * 60_000
        out = []
        for st in self.states.values():
            interesting = st.display_state in _INTERESTING_DISPLAY
            # Retencion: sigue visible "perdiendo fuerza" tras dejar de interesar
            in_retention = (
                st.last_interesting_ms > 0
                and now_ms - st.last_interesting_ms < retention_ms
            )
            if st.score >= threshold or interesting or in_retention:
                out.append(st.snapshot())
        out.sort(key=lambda x: x.get("score", 0), reverse=True)
        return out

    def get_symbol(self, symbol: str) -> Optional[SymbolState]:
        return self.states.get(symbol)
