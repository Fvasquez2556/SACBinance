"""
Orquestador principal: recibe velas cerradas/live de todos los TFs,
corre FSM 1m, aplica gate macro + gate BTC, detecta consolidacion, breakout
y fakeout, calcula soporte/resistencia y niveles de trading, mapea a display
state, evalua señales y emite eventos.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Dict, List, Optional

from src.analysis.breakout import detectar_breakout
from src.analysis.consolidation import detectar_consolidacion
from src.analysis.daily_anchor import calcular_ancla
from src.analysis.compression import detectar_compresion
from src.analysis.momentum_profile import evaluar_grind, evaluar_ignicion
from src.analysis.taxonomy import clasificar as clasificar_taxonomia
from src.analysis.levels import detectar_niveles
from src.analysis.ma_slopes import analizar_tf
from src.analysis.macro_gate import aplicar_gate, calcular_tendencia_global
from src.analysis.scoring import score_and_tier
from src.analysis.impulse import medir_impulso
from src.analysis.outcome_tracker import OutcomeTracker
from src.analysis.signal_tracker import abrir_senal, evaluar_senales
from src.analysis.trade_levels import calcular_niveles
from src.config.settings import get_settings
from src.indicators.calculator import indicators_from_candles
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
from src.state.active_alert import AlertManager
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
        self._outcomes: Optional[OutcomeTracker] = None
        self._alertas = AlertManager()
        # Caches del analisis pesado (ver throttling en on_closed_candle)
        self._sr_cache: Dict[str, object] = {}
        self._cons_cache: Dict[str, object] = {}
        self._grind_cache: Dict[str, object] = {}
        self._compresion_cache: Dict[str, object] = {}
        self._closed_seen: int = 0
        # Cooldown por (symbol, tipo_alerta) -> ts_ms del ultimo envio
        self._alert_cooldown: Dict[tuple, int] = {}

    def set_emit(self, emit: EmitFn) -> None:
        self._emit = emit

    def set_db(self, db) -> None:
        self._db = db
        # El tracker de outcomes vive junto a la DB: al reanudar recupera las
        # señales que seguia antes del reinicio.
        self._outcomes = OutcomeTracker(db)
        self._outcomes.cargar()

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

    def _update_macro(self, st: SymbolState, only_tf: Optional[str] = None) -> None:
        """
        Recalcula pendientes/tendencia. Usa candles_tf_live(), que incluye la
        vela EN FORMACION: asi la tendencia 15m refleja el minuto actual y no
        el cierre de hace hasta 15 minutos.
        """
        s = get_settings()
        tfs = (only_tf,) if only_tf else _MACRO_TFS
        for tf in tfs:
            if tf not in st.macro_trends:
                continue
            candles = st.candles_tf_live(tf) if s.htf_live_enabled else list(st.get_candles_tf(tf))
            result = analizar_tf(candles, s.slope_lookback)
            if result.get("valid"):
                st.slopes[tf] = result
                st.macro_trends[tf] = result["tendencia"]
        st.macro_global = calcular_tendencia_global(st.macro_trends)

    def _update_ind_htf(self, st: SymbolState, tf: str) -> None:
        """Indicadores tecnicos calculados SOBRE EL TF, no sobre 1m."""
        s = get_settings()
        candles = st.candles_tf_live(tf) if s.htf_live_enabled else list(st.get_candles_tf(tf))
        snap = indicators_from_candles(candles)
        if snap is not None:
            st.ind_htf[tf] = snap

    async def on_htf_live(self, symbol: str, tf: str, candle: Candle) -> None:
        """
        Vela HTF en formacion. Throttled por par/TF: recalcular la macro de
        250 pares en cada tick de 15m/1h saturaria el loop sin aportar nada.
        """
        s = get_settings()
        if not s.htf_live_enabled or tf not in s.htf_live_tfs_list:
            return
        st = self.states.get(symbol)
        if st is None:
            return

        st.set_live_htf(tf, candle)

        now = time.monotonic()
        if now - st.last_htf_live_calc.get(tf, 0.0) < s.htf_live_min_interval:
            return
        st.last_htf_live_calc[tf] = now

        if tf in _MACRO_TFS:
            self._update_macro(st, only_tf=tf)
        self._update_ind_htf(st, tf)

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
        if tf in get_settings().htf_live_tfs_list:
            self._update_ind_htf(st, tf)

    # --- 1m (FSM reactiva) ----------------------------------------------------

    async def on_closed_candle(
        self, symbol: str, t: int, o: float, h: float, l: float, c: float, v: float
    ) -> None:
        st = self._get(symbol)
        candle = Candle(t=t, o=o, h=h, l=l, c=c, v=v)
        ready = st.add_closed_candle(candle)

        # Al segundo 0 de cada minuto cierran las ~250 velas 1m a la vez.
        # Ceder el loop cada N evita que el lector del WebSocket se quede sin
        # turno durante toda la rafaga (con la consiguiente cola de mensajes).
        self._closed_seen += 1
        if self._closed_seen % max(1, get_settings().engine_yield_every) == 0:
            await asyncio.sleep(0)

        # Checkpoint: persistir la vela 1m cerrada
        if self._db is not None:
            try:
                self._db.save_kline(symbol, "1m", candle)
            except Exception:
                pass

        # Seguimiento del camino completo (independiente de TP/SL: mide que
        # paso DESPUES del stop, que es lo que evaluar_senales no puede ver)
        if self._outcomes is not None:
            try:
                self._outcomes.on_candle(symbol, t, h, l, c)
            except Exception as e:
                logger.debug(f"[{symbol}] outcome_tracker error: {e}")

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

        # --- Analisis pesado (S/R sobre 1h + consolidacion sobre 15m) ---
        # Ninguno de los dos puede cambiar de forma relevante en 60 segundos,
        # pero antes se recalculaban en CADA vela 1m de CADA uno de los ~250
        # pares. detectar_consolidacion es O(n*period) sobre 260 velas: era la
        # mayor fuente de carga en rafaga del minuto cerrado.
        # Los pares que ya son interesantes se siguen recalculando siempre.
        es_interesante = (
            st.fsm_state != FSM_NEUTRAL
            or st.display_state in _INTERESTING_DISPLAY
            or st.score >= s.score_min_dashboard
        )
        recalcular_pesado = (
            es_interesante
            or not st.sr_levels
            or (now_ms - st.last_heavy_ms) >= s.heavy_analysis_interval * 1000
        )

        if recalcular_pesado:
            st.last_heavy_ms = now_ms
            sr = detectar_niveles(list(st.candles_1h), st.metrics.price)
            st.sr_levels = sr.to_dict()
            self._sr_cache[symbol] = sr

            slopes_15m = st.slopes.get("15m", {})
            cons = detectar_consolidacion(
                st.candles_tf_live("15m") if s.htf_live_enabled else list(st.candles_15m),
                "15m", slopes_15m,
            )
            self._cons_cache[symbol] = cons
            st.consolidation_info = {
                "consolidating": cons.consolidating,
                "atr_pct": cons.atr_pct,
                "atr_percentile": cons.atr_percentile,
                "ma_convergent": cons.ma_convergent,
                "vol_declining": cons.vol_declining,
                "candles_in_state": cons.candles_in_state,
            }
        else:
            sr = self._sr_cache.get(symbol)
            cons = self._cons_cache.get(symbol)
            if cons is None:
                cons = detectar_consolidacion([], "15m", {})
            if sr is None:
                # Cache perdido (no deberia pasar: la primera vela siempre
                # recalcula). Recalcular una vez es preferible a publicar
                # niveles sin soporte/resistencia.
                sr = detectar_niveles(list(st.candles_1h), st.metrics.price)
                st.sr_levels = sr.to_dict()
                self._sr_cache[symbol] = sr
        consolidating = cons.consolidating

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
        pos_rango = _pos_en_rango(
            st.candles_tf_live("15m") if s.htf_live_enabled else list(st.candles_15m),
            st.metrics.price,
        )
        st.pos_en_rango = pos_rango
        trend_15m = st.macro_trends.get("15m", "NEUTRAL")

        # --- Ancla diaria fija (00:00 UTC) ---
        if s.daily_anchor_enabled:
            st.daily = calcular_ancla(st, st.metrics.price, now_ms).to_dict()

        # --- Perfiles de subida: tendencia sostenida vs ignicion ---
        # `grind` mira 4 horas de velas 15m: no puede cambiar de forma
        # relevante en 60s, asi que sigue el mismo throttling que el resto del
        # analisis pesado. `ignition` NO se throttlea: detecta la explosion en
        # la vela de 1m y llegar tarde es justo lo que intenta evitar.
        if recalcular_pesado:
            grind = evaluar_grind(
                st.candles_tf_live("15m") if s.htf_live_enabled else list(st.candles_15m),
                st.macro_trends,
            )
            self._grind_cache[symbol] = grind
            st.grind = grind.to_dict()
        else:
            grind = self._grind_cache.get(symbol)
            if grind is None:
                grind = evaluar_grind([], st.macro_trends)

        ignition = evaluar_ignicion(
            list(st.candles),
            st.metrics,
            flow=st.flow_snap,
            consolidando_antes=st.prev_consolidando,
            ind=st.ind,
            blow_off=(st.fsm_state == FSM_EXHAUSTED),
            daily=st.daily,
        )
        st.ignition = ignition.to_dict()
        st.prev_consolidando = consolidating

        # --- CAPA 1: compresion + taxonomia exhaustiva ---
        # detectar_compresion recorre 96 velas 15m buscando pivotes fractales:
        # ~0.5ms por par, 116ms por rafaga de 250. Es analisis pesado y va con
        # los demas, o desharia el ahorro que persigue el throttling de arriba.
        if recalcular_pesado:
            compresion = detectar_compresion(
                st.candles_tf_live("15m") if s.htf_live_enabled else list(st.candles_15m),
                atr_percentil=(cons.atr_percentile if cons is not None else None),
            )
            self._compresion_cache[symbol] = compresion
            st.compresion = compresion.to_dict()
        else:
            compresion = self._compresion_cache.get(symbol)
            if compresion is None:
                compresion = detectar_compresion([])

        taxo = clasificar_taxonomia(
            grind=grind, ignition=ignition, compresion=compresion,
            fsm_state=st.fsm_state, metrics=st.metrics,
            macro_trends=st.macro_trends, daily=st.daily,
        )
        st.taxonomia = taxo.to_dict()

        # --- Fuerza del impulso (derivada: ¿sigue subiendo o se apaga?) ---
        # Va sin throttling: es la señal que decide emitir o retirar una
        # alerta, y llegar tarde aqui es justo el fallo que corrige.
        impulso = medir_impulso(list(st.candles), ind=st.ind)
        st.impulso = impulso.to_dict()

        # Display state (FSM 1m VALIDADA con contexto)
        display = _fsm_to_display(st.fsm_state, consolidating, breakout, pos_rango, trend_15m)

        # Niveles de trading (con soporte/resistencia)
        levels = calcular_niveles(
            st.metrics.price,
            st.candles_tf_live("15m") if s.htf_live_enabled else list(st.candles_15m),
            display, sr,
        )
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

        # --- Modo sombra: medir lo que el gate macro suprime ---
        # El gate multiplica el score (x0.10 con macro BAJISTA), asi que un 86
        # queda en 8.6 y jamas alcanza el umbral: SUBIENDO + BAJISTA dio 0 de
        # 82 el 4-sep. No se alerta — la decision de no operar contra la macro
        # se respeta — pero SI se mide, o nunca se sabra si el muro protege.
        if (self._outcomes is not None
                and display in _INTERESTING_DISPLAY
                and tier == "NINGUNO"
                and 0 < mult < 1
                and st.trade_levels.get("valid")):
            val_sin_gate = int(min(100, val / mult))
            if val_sin_gate >= s.score_min_dashboard:
                try:
                    self._outcomes.abrir_sombra(
                        symbol, now_ms, st.snapshot(), st.trade_levels, val_sin_gate
                    )
                except Exception as e:
                    logger.debug(f"[{symbol}] abrir_sombra error: {e}")

        # --- Alerta viva: refrescar contra sus niveles CONGELADOS ---
        # Se hace antes de decidir una emision nueva: si el par ya tiene una
        # alerta viva, no puede volver a emitir mas arriba.
        if s.alerta_congelada_enabled:
            cambio = self._alertas.actualizar(symbol, now_ms, h, l, c, impulso)
            if cambio is not None and self._emit:
                await self._emit({
                    "type": "alerta_cambio",
                    "ts": now_ms,
                    "symbol": symbol,
                    "alerta": cambio.to_dict(),
                })
            st.alerta = (
                a.to_dict() if (a := self._alertas.get(symbol)) is not None else {}
            )

        if alertable and (state_changed or tier_changed):
            emitir = True
            if s.alerta_congelada_enabled:
                emitir, motivo = self._alertas.puede_emitir(
                    symbol, impulso, now_ms, display_state=display
                )
                if not emitir:
                    logger.debug(f"[{symbol}] alerta no emitida: {motivo}")
                    self._log_db(symbol, "VETO_ALERTA", f"{display} score={val} — {motivo}")

            if emitir:
                self._last_tier[symbol] = tier
                snap = st.snapshot()

                # Auto-evaluacion: registrar la señal para medir su resultado
                sig_id = abrir_senal(symbol, snap, self._db)
                if sig_id is not None and self._outcomes is not None:
                    try:
                        self._outcomes.abrir(sig_id, symbol, now_ms, snap, st.trade_levels)
                    except Exception as e:
                        logger.debug(f"[{symbol}] abrir outcome error: {e}")

                tl = st.trade_levels
                if s.alerta_congelada_enabled:
                    alerta = self._alertas.emitir(
                        symbol, sig_id, now_ms, snap, tl, impulso
                    )
                    if alerta is not None:
                        st.alerta = alerta.to_dict()
                        snap = st.snapshot()

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
        # --- Alertas de perfil (independientes del tier clasico) ---
        for kind, perfil, etiqueta in (
            ("alert_tendencia", grind, "TENDENCIA SOSTENIDA"),
            ("alert_ignicion", ignition, "IGNICION"),
        ):
            if not perfil.detected:
                continue
            key = (symbol, kind)
            ultimo = self._alert_cooldown.get(key, 0)
            if now_ms - ultimo < s.alert_cooldown_minutes * 60_000:
                continue
            self._alert_cooldown[key] = now_ms

            pct_dia = st.daily.get("pct_desde_open_diario")
            pct_txt = f" | dia {pct_dia:+.2f}%" if pct_dia is not None else ""
            logger.info(
                f"[{symbol}] ALERTA {etiqueta} | score={perfil.score}"
                f"{pct_txt} | {perfil.reason}"
            )
            self._log_db(symbol, etiqueta.split()[0], f"score={perfil.score} | {perfil.reason}")
            if self._emit:
                await self._emit({
                    "type": kind,
                    "ts": now_ms,
                    "perfil": etiqueta,
                    "perfil_score": perfil.score,
                    "perfil_reason": perfil.reason,
                    **st.snapshot(),
                })

        if not alertable or not (state_changed or tier_changed):
            if transition and self._emit:
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
