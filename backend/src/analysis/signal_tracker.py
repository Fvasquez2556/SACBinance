"""
Auto-evaluacion de señales.

Cada vez que el sistema marca un par como oportunidad operable (estado +
niveles validos), se registra una "señal" con su entry/TP/SL. Despues, en
cada vela 1m cerrada, se comprueba si el precio toco el TP o el SL.

Que es — y que NO es — el numero que sale de aqui
-------------------------------------------------
Lo que se mide es la FRECUENCIA CON QUE EL PRECIO TOCA EL TP ANTES QUE EL SL,
en BRUTO, sobre una operacion simulada que nadie ejecuto. No es un win rate
real y llamarlo asi era el problema:

  - No hay fill, ni spread, ni deslizamiento, ni comision. Con el coste
    configurado (`coste_operacion_pct`) el umbral de rentabilidad se mueve.
  - Una señal EXPIRED en positivo cuenta como fallo aunque hubiera dejado
    dinero; al 10-sep eran 210 de 416.
  - Cuando una misma vela contiene el TP y el SL, el orden dentro del minuto
    es desconocido.

Sirve para comparar versiones entre si con el mismo sesgo, que ya es bastante.
No sirve para decir cuanto se gana. Para eso hace falta la medicion por plan
completo, con costes y muestra separada por version.
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


def cerrar_vencidas(db, now_ms: Optional[int] = None,
                    margen_min: int = 15) -> dict:
    """
    Cierra por RELOJ las señales caducadas, lleguen velas o no.

    Por que hace falta, si la caducidad ya se comprueba
    ---------------------------------------------------
    Se comprueba dentro de `evaluar_senales()`, que solo corre cuando llega una
    vela DE ESE PAR. Si el par sale del universo, se le corta el stream o deja
    de operarse, la señal no vuelve a mirarse nunca: el 11-sep habia 24 señales
    OPEN de mas de 12h con `signal_expiry_hours=12`, y la mas vieja llevaba
    155.7 horas. Es el mismo fallo que tenian los outcomes, en la tabla que no
    se toco entonces; ahora manda el reloj, igual que en
    `OutcomeTracker.cerrar_vencidos()`.

    De donde sale el precio de salida
    ---------------------------------
    De la ultima vela guardada en o antes del vencimiento — NO del precio de
    hoy. Calificar una señal de hace seis dias contra el precio actual es lo
    que inflaba el win rate con ruido, y es la razon de que la edad se mire
    antes que TP/SL.

    Si esa vela esta a mas de `margen_min` minutos del vencimiento, no se sabe
    a que precio estaba el par cuando caduco: la señal se cierra STALE y sin
    resultado, que es lo que las estadisticas ya ignoran. Inventar un numero
    seria peor que no tenerlo.

    Se llama desde el bucle de volcado, no desde el camino de la vela.
    """
    if db is None:
        return {"expired": 0, "stale": 0}
    s = get_settings()
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    expiry_ms = s.signal_expiry_hours * 3600 * 1000
    margen_ms = margen_min * 60_000

    try:
        abiertas = db.get_open_signals()
    except Exception as e:
        logger.debug(f"cerrar_vencidas: no pude leer señales abiertas: {e}")
        return {"expired": 0, "stale": 0}

    n_exp = n_stale = 0
    for sig in abiertas:
        edad = now_ms - sig["ts_open"]
        if edad < expiry_ms:
            continue

        entry = sig.get("entry")
        vence_en = sig["ts_open"] + expiry_ms
        status, exit_price = "STALE", None

        # Demasiado vieja para que el sistema la siguiera: ni se intenta poner
        # precio. Mismo criterio que `evaluar_senales`.
        if edad < expiry_ms * 2 and entry and entry > 0:
            try:
                vela = db.kline_en(sig["symbol"], "1m", vence_en)
            except Exception:
                vela = None
            if vela is not None and vence_en - vela["open_time"] <= margen_ms:
                status, exit_price = "EXPIRED", vela["c"]

        result_pct = (
            None if exit_price is None or not entry
            else round((exit_price - entry) / entry * 100.0, 3)
        )
        try:
            db.close_signal(sig["id"], status, result_pct, now_ms)
        except Exception as e:
            logger.debug(f"[{sig['symbol']}] cerrar_vencidas: {e}")
            continue
        if status == "EXPIRED":
            n_exp += 1
        else:
            n_stale += 1

    if n_exp or n_stale:
        logger.info(
            f"Señales cerradas por reloj: {n_exp} EXPIRED con precio del "
            f"vencimiento, {n_stale} STALE sin precio conocido"
        )
    return {"expired": n_exp, "stale": n_stale}
