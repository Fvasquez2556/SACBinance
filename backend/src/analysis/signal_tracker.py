"""
Auto-evaluacion de señales.

Cada vez que el sistema marca un par como oportunidad operable (estado +
niveles validos), se registra una "señal" con su entry/TP/SL. Despues, en
cada vela 1m cerrada, se comprueba si el precio toco el TP o el SL.

Tras unos dias esto da un WIN RATE real: el unico dato que dice si el
sistema acierta. Sin medicion, los umbrales son pura intuicion.
"""
from __future__ import annotations

import time
from typing import List, Optional

from src.config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Estados sobre los que se abre señal (operables en largo)
_OPERABLE = {"SUBIENDO", "BREAKOUT_INCIPIENTE", "TOCÓ_FONDO", "CONSOLIDANDO"}


def abrir_senal(symbol: str, snapshot: dict, db) -> Optional[int]:
    """
    Abre una señal nueva si: estado operable + niveles validos + no hay
    ya una señal OPEN para el simbolo. Devuelve el id, o None.
    """
    if db is None:
        return None
    if snapshot.get("display_state") not in _OPERABLE:
        return None
    tl = snapshot.get("trade_levels", {})
    if not tl.get("valid"):
        return None
    if db.has_open_signal(symbol):
        return None
    try:
        sig_id = db.open_signal(
            symbol=symbol,
            ts_open=int(time.time() * 1000),
            display_state=snapshot["display_state"],
            tier=snapshot.get("tier", "NINGUNO"),
            score=snapshot.get("score", 0),
            entry=tl["entry"],
            take_profit=tl["take_profit"],
            stop_loss=tl["stop_loss"],
            risk_reward=tl.get("risk_reward") or 0.0,
            macro=snapshot.get("macro_global", "NEUTRAL"),
        )
        logger.info(
            f"[{symbol}] SEÑAL #{sig_id} abierta | {snapshot['display_state']} "
            f"entry={tl['entry']} TP={tl['take_profit']} SL={tl['stop_loss']}"
        )
        try:
            db.log_analysis(
                symbol, "SIGNAL",
                f"Señal #{sig_id} abierta — {snapshot['display_state']} "
                f"entry={tl['entry']} TP={tl['take_profit']} SL={tl['stop_loss']}",
            )
        except Exception:
            pass
        return sig_id
    except Exception as e:
        logger.debug(f"[{symbol}] abrir_senal error: {e}")
        return None


def evaluar_senales(symbol: str, high: float, low: float, close: float, db) -> List[dict]:
    """
    Comprueba las señales OPEN de un simbolo contra la vela 1m cerrada.
    Cierra las que tocaron TP/SL o caducaron. Devuelve las señales cerradas.
    """
    if db is None:
        return []
    open_sigs = db.get_open_signals(symbol)
    if not open_sigs:
        return []

    s = get_settings()
    now_ms = int(time.time() * 1000)
    expiry_ms = s.signal_expiry_hours * 3600 * 1000
    cerradas: List[dict] = []

    for sig in open_sigs:
        entry = sig["entry"]
        tp = sig["take_profit"]
        sl = sig["stop_loss"]
        if not entry or entry <= 0:
            continue

        # La caducidad se comprueba PRIMERO. Si se mirara TP/SL antes, una
        # señal que quedo abierta mientras el sistema estuvo apagado se
        # calificaria contra el precio de hoy: al reanudar aparecian señales
        # de hace meses cerradas como TP porque el precio actual superaba un
        # objetivo puesto en su dia. Eso inflaba el win rate con ruido.
        edad_ms = now_ms - sig["ts_open"]
        if edad_ms >= expiry_ms * 2:
            # Tan vieja que el sistema no pudo estar siguiendola (estuvo
            # apagado). No sabemos que hizo el precio mientras tanto, asi que
            # se marca STALE sin resultado en vez de inventar uno: las
            # estadisticas la ignoran.
            status, exit_price = "STALE", None
        elif edad_ms >= expiry_ms:
            status, exit_price = "EXPIRED", close
        elif low <= sl:  # conservador: si toca ambos en la misma vela, gana el SL
            status, exit_price = "SL", sl
        elif high >= tp:
            status, exit_price = "TP", tp
        else:
            continue

        result_pct = (
            None if exit_price is None
            else round((exit_price - entry) / entry * 100.0, 3)
        )
        try:
            db.close_signal(sig["id"], status, result_pct, now_ms)
        except Exception as e:
            logger.debug(f"[{symbol}] close_signal error: {e}")
            continue
        logger.info(
            f"[{symbol}] SEÑAL #{sig['id']} cerrada -> {status} | resultado={result_pct}%"
        )
        try:
            db.log_analysis(
                symbol, "SIGNAL",
                f"Señal #{sig['id']} cerrada -> {status} resultado={result_pct}%",
            )
        except Exception:
            pass
        cerradas.append({**sig, "status": status, "result_pct": result_pct})

    return cerradas
