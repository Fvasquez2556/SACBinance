"""
Seguimiento del camino completo de cada señal.

Que responde, y por que no lo responde `signal_tracker`
------------------------------------------------------
`signal_tracker` cierra la señal en cuanto el precio toca TP o SL. Eso da un
win rate, pero pierde la pregunta interesante: si toco el SL, ¿que hizo
DESPUES? ¿se hundio, o rebotó y acabo subiendo mas que el objetivo?

Este modulo sigue a cada señal durante una ventana fija (24h por defecto)
SIN cerrarla, pase lo que pase con TP/SL. Por cada una registra:

  - Si alcanzo el TP ofrecido, el SL, y cada escalon de la escalera fija
    (+1 / +2 / +3.2 / +5 / +10 %, y sus equivalentes a la baja), con el
    tiempo que tardo en cada uno.
  - MFE / MAE: lo maximo que llego a subir y a bajar desde la entrada.
  - La FORMA del camino hasta el objetivo de +3.2%:

        DIRECTO      llego sin retroceder mas de `forma_dip_umbral`
        DIP_Y_SUBE   bajo primero (cuanto: `dip_antes_obj`) y luego llego
        SOLO_BAJO    nunca llego, y ademas cayo de forma relevante
        LATERAL      nunca llego, sin caida relevante

Todo se mide en % simple desde el precio de entrada sugerido, para que sea
comparable entre monedas y directamente legible.

No es un backtest: mide las señales que el sistema emitio de verdad, en
vivo, sin conocimiento del futuro.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from src.config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Escalera fija de umbrales, en %. El 3.2 es el objetivo de referencia.
# El 1.2 y el 4.2 estan para los marcadores del tablero (ver `marcadores`).
ESCALERA = (1.0, 1.2, 2.0, 3.2, 4.2, 5.0, 10.0)
_SUFIJO = {1.0: "1", 1.2: "12", 2.0: "2", 3.2: "32",
           4.2: "42", 5.0: "5", 10.0: "10"}

OBJETIVO = 3.2  # umbral sobre el que se clasifica la forma del camino

# --- Marcadores del tablero -------------------------------------------------
# Colores, y por que cada uno:
#   VERDE     llego al objetivo de +3.2%
#   MORADO    supero +4.2% (objetivo holgado)
#   AMARILLO  cayo -1.2%, el SL medio observado en las señales que se torcieron
#   ROJO      toco el SL que el propio sistema habia fijado
# No son excluyentes a proposito: una señal puede bajar primero y luego subir
# (el caso DIP_Y_SUBE), y ver los dos marcadores a la vez es justo el dato.
MARCA_VERDE = "VERDE"
MARCA_MORADO = "MORADO"
MARCA_AMARILLO = "AMARILLO"
MARCA_ROJO = "ROJO"

MARCA_UMBRAL = {
    MARCA_VERDE: ("ms_up_32", 3.2),
    MARCA_MORADO: ("ms_up_42", 4.2),
    MARCA_AMARILLO: ("ms_dn_12", -1.2),
    MARCA_ROJO: ("ms_sl", None),
}


def marcadores(row: dict) -> list:
    """Colores que le corresponden a un outcome. Puede llevar varios."""
    return [m for m, (campo, _) in MARCA_UMBRAL.items() if row.get(campo) is not None]

FORMA_DIRECTO = "DIRECTO"
FORMA_DIP = "DIP_Y_SUBE"
FORMA_SOLO_BAJO = "SOLO_BAJO"
FORMA_LATERAL = "LATERAL"


class OutcomeTracker:
    """
    Mantiene en memoria los outcomes abiertos y los actualiza con cada vela
    1m cerrada. Persiste en SQLite via el mismo commit diferido del resto.
    """

    def __init__(self, db) -> None:
        self._db = db
        self._abiertos: Dict[int, dict] = {}
        self._por_symbol: Dict[str, List[int]] = {}
        self._sombra_id: int = 0        # ids negativos, no chocan con signals
        self._sombra_activa: set = set()

    # --- Ciclo de vida --------------------------------------------------

    def cargar(self) -> int:
        """Recupera los outcomes sin cerrar tras un reinicio."""
        if self._db is None:
            return 0
        try:
            for row in self._db.get_outcomes_abiertos():
                self._registrar_memoria(row)
        except Exception as e:
            logger.warning(f"No se pudieron cargar outcomes abiertos: {e}")
            return 0
        n = len(self._abiertos)
        if n:
            logger.info(f"Outcomes en seguimiento recuperados: {n}")
        return n

    def _registrar_memoria(self, row: dict) -> None:
        sid = row["signal_id"]
        self._abiertos[sid] = row
        self._por_symbol.setdefault(row["symbol"], []).append(sid)
        if sid < 0:
            self._sombra_id = min(self._sombra_id, sid)
            self._sombra_activa.add(row["symbol"])

    def backfill(self, engine) -> int:
        """
        Crea el outcome de las señales que estan OPEN pero no lo tienen, y
        reconstruye su camino con las velas 1m del buffer.

        Cubre dos casos: señales abiertas antes de que existiera esta medicion,
        y señales que quedaron vivas mientras el sistema estuvo apagado (al
        rehidratar, el buffer trae las velas de ese hueco). Sin esto habria que
        esperar a que caduquen para volver a medir esos simbolos.
        """
        if self._db is None:
            return 0
        try:
            pendientes = [
                s for s in self._db.get_open_signals()
                if s["id"] not in self._abiertos
            ]
        except Exception as e:
            logger.warning(f"backfill de outcomes no disponible: {e}")
            return 0

        ventana_ms = get_settings().outcome_window_hours * 3600_000
        n = 0
        for sig in pendientes:
            entry = sig.get("entry")
            if not entry or entry <= 0:
                continue
            st = engine.get_symbol(sig["symbol"])
            if st is None:
                continue

            self.abrir(
                sig["id"], sig["symbol"], sig["ts_open"],
                {
                    "display_state": sig.get("display_state"),
                    "tier": sig.get("tier"),
                    "score": sig.get("score"),
                    "macro_global": sig.get("macro"),
                    "taxonomia": {},
                },
                {
                    "entry": entry,
                    "take_profit": sig.get("take_profit"),
                    "stop_loss": sig.get("stop_loss"),
                },
            )
            if sig["id"] not in self._abiertos:
                continue

            # Replay de las velas posteriores a la apertura que ya estan en
            # el buffer: el camino queda medido de verdad, no estimado.
            velas = [
                c for c in st.candles
                if sig["ts_open"] <= c.t <= sig["ts_open"] + ventana_ms
            ]
            for c in velas:
                self.on_candle(sig["symbol"], c.t, c.h, c.l, c.c)
            n += 1

        # --- Recuperar el hueco de los outcomes que YA existian ---
        # Si el sistema estuvo parado, sus velas no se procesaron. El buffer
        # 1m cubre ~5.3h, asi que un parón corto se recupera entero en vez de
        # dejar un agujero en el MFE/MAE y en los cruces de umbral.
        recuperados = velas_replay = 0
        for sid, row in list(self._abiertos.items()):
            st = engine.get_symbol(row["symbol"])
            if st is None:
                continue
            desde = row.get("ts_last") or row["ts_open"]
            hasta = row["ts_open"] + ventana_ms
            velas = [c for c in st.candles if desde < c.t <= hasta]
            if not velas:
                continue
            for c in velas:
                self.on_candle(row["symbol"], c.t, c.h, c.l, c.c)
            recuperados += 1
            velas_replay += len(velas)

        if n:
            logger.info(f"Outcomes reconstruidos desde el buffer: {n} señales")
        if recuperados:
            logger.info(
                f"Hueco recuperado en {recuperados} outcomes ya abiertos "
                f"({velas_replay} velas 1m reprocesadas)"
            )
        return n

    def abrir_sombra(self, symbol: str, ts_open: int, snapshot: dict,
                     trade_levels: dict, score_estimado: int) -> None:
        """
        Sigue una señal que el gate macro SUPRIMIO, sin alertarla.

        Sin esto el sistema tiene un punto ciego: lo que el gate suprime nunca
        llega a ser señal, asi que no hay outcome que diga si suprimirlo fue
        acertado. El 4-sep, SUBIENDO con macro BAJISTA dio 0 de 82 por encima
        del umbral, y ese mismo dia TUTUSDT (+12%) y MITOUSDT (+8.4%) cayeron
        en esa categoria — sin datos para saber si el muro protegia o costaba.

        Los ids de sombra son negativos para no chocar con los de signals.
        """
        if self._db is None or symbol in self._sombra_activa:
            return
        self._sombra_id -= 1
        snap = dict(snapshot)
        snap["score"] = score_estimado          # el score SIN el gate
        snap["tier"] = "SOMBRA"
        self.abrir(self._sombra_id, symbol, ts_open, snap, trade_levels, sombra=True)
        if self._sombra_id in self._abiertos:
            self._sombra_activa.add(symbol)

    def abrir(self, signal_id: int, symbol: str, ts_open: int,
              snapshot: dict, trade_levels: dict, sombra: bool = False) -> None:
        """Empieza a seguir una señal recien emitida."""
        if self._db is None or signal_id in self._abiertos:
            return
        entry = trade_levels.get("entry")
        if not entry or entry <= 0:
            return

        tp = trade_levels.get("take_profit")
        sl = trade_levels.get("stop_loss")
        taxo = snapshot.get("taxonomia") or {}

        row = {
            "signal_id": signal_id,
            "symbol": symbol,
            "ts_open": ts_open,
            "ts_last": ts_open,
            "entry": float(entry),
            "take_profit": tp,
            "stop_loss": sl,
            "tp_pct": round((tp - entry) / entry * 100.0, 3) if tp else None,
            "sl_pct": round((sl - entry) / entry * 100.0, 3) if sl else None,
            "display_state": snapshot.get("display_state"),
            "tier": snapshot.get("tier"),
            "score": snapshot.get("score"),
            "macro": snapshot.get("macro_global"),
            "taxonomia": taxo.get("estado"),
            "mfe_pct": 0.0,
            "mae_pct": 0.0,
            "n_velas": 0,
            "cerrado": 0,
            "sombra": 1 if sombra else 0,
            "vol_24h": snapshot.get("vol_24h"),
            "vol_1m_medio": snapshot.get("vol_1m_medio"),
        }
        try:
            self._db.abrir_outcome(row)
        except Exception as e:
            logger.debug(f"[{symbol}] abrir_outcome error: {e}")
            return

        # La fila en memoria necesita todas las columnas de cruce a None
        for u in ESCALERA:
            row[f"ms_up_{_SUFIJO[u]}"] = None
            row[f"ms_dn_{_SUFIJO[u]}"] = None
        row["ms_tp"] = row["ms_sl"] = None
        row["ms_mfe"] = row["ms_mae"] = None
        row["dip_antes_obj"] = None
        row["forma"] = None
        self._registrar_memoria(row)

    # --- Actualizacion por vela -----------------------------------------

    def on_candle(self, symbol: str, ts: int, high: float, low: float,
                  close: float) -> List[dict]:
        """
        Actualiza los outcomes de un simbolo con una vela 1m cerrada.
        Devuelve los que se acaban de cerrar por fin de ventana.
        """
        ids = self._por_symbol.get(symbol)
        if not ids:
            return []

        s = get_settings()
        ventana_ms = s.outcome_window_hours * 3600_000
        dip_umbral = s.forma_dip_umbral
        cerrados: List[dict] = []

        for sid in list(ids):
            row = self._abiertos.get(sid)
            if row is None:
                continue

            entry = row["entry"]
            transcurrido = ts - row["ts_open"]
            cambios: dict = {"ts_last": ts, "n_velas": row["n_velas"] + 1}
            row["n_velas"] += 1
            row["ts_last"] = ts

            up_pct = (high - entry) / entry * 100.0
            dn_pct = (low - entry) / entry * 100.0

            # --- Excursiones maximas ---
            if up_pct > row["mfe_pct"]:
                row["mfe_pct"] = cambios["mfe_pct"] = round(up_pct, 3)
                row["ms_mfe"] = cambios["ms_mfe"] = transcurrido
            if dn_pct < row["mae_pct"]:
                row["mae_pct"] = cambios["mae_pct"] = round(dn_pct, 3)
                row["ms_mae"] = cambios["ms_mae"] = transcurrido

            # --- Escalera fija: primer cruce de cada escalon ---
            for u in ESCALERA:
                suf = _SUFIJO[u]
                k_up = f"ms_up_{suf}"
                if row.get(k_up) is None and up_pct >= u:
                    row[k_up] = cambios[k_up] = transcurrido
                k_dn = f"ms_dn_{suf}"
                if row.get(k_dn) is None and dn_pct <= -u:
                    row[k_dn] = cambios[k_dn] = transcurrido

            # --- TP / SL ofrecidos por el sistema ---
            tp, sl = row.get("take_profit"), row.get("stop_loss")
            if row.get("ms_tp") is None and tp and high >= tp:
                row["ms_tp"] = cambios["ms_tp"] = transcurrido
            if row.get("ms_sl") is None and sl and low <= sl:
                row["ms_sl"] = cambios["ms_sl"] = transcurrido

            # --- Peor caida ANTES de alcanzar el objetivo ---
            # Es el dato que responde "¿bajo primero y despues subio?".
            # Se congela en el momento en que se toca +3.2% por primera vez.
            if row.get("dip_antes_obj") is None:
                if row.get(f"ms_up_{_SUFIJO[OBJETIVO]}") is not None:
                    row["dip_antes_obj"] = cambios["dip_antes_obj"] = row["mae_pct"]

            # --- Fin de ventana ---
            if transcurrido >= ventana_ms:
                row["forma"] = cambios["forma"] = _clasificar_forma(row, dip_umbral)
                row["cerrado"] = cambios["cerrado"] = 1
                cerrados.append(dict(row))
                self._abiertos.pop(sid, None)
                ids.remove(sid)
                if sid < 0:
                    self._sombra_activa.discard(symbol)

            try:
                self._db.guardar_outcome(sid, cambios)
            except Exception as e:
                logger.debug(f"[{symbol}] guardar_outcome error: {e}")

        if not ids:
            self._por_symbol.pop(symbol, None)

        for row in cerrados:
            logger.info(
                f"[{row['symbol']}] OUTCOME #{row['signal_id']} cerrado | "
                f"{row['forma']} | MFE {row['mfe_pct']:+.2f}% MAE {row['mae_pct']:+.2f}% | "
                f"objetivo {OBJETIVO}%: "
                + (_fmt_dur(row.get(f"ms_up_{_SUFIJO[OBJETIVO]}"))
                   if row.get(f"ms_up_{_SUFIJO[OBJETIVO]}") is not None else "no alcanzado")
            )
        return cerrados


def _clasificar_forma(row: dict, dip_umbral: float) -> str:
    llego = row.get(f"ms_up_{_SUFIJO[OBJETIVO]}") is not None
    dip = row.get("dip_antes_obj")
    mae = row.get("mae_pct") or 0.0

    if llego:
        # Sin dato de dip (toco el objetivo en la primera vela) = directo
        if dip is None or dip > -dip_umbral:
            return FORMA_DIRECTO
        return FORMA_DIP
    if mae <= -dip_umbral:
        return FORMA_SOLO_BAJO
    return FORMA_LATERAL


def _fmt_dur(ms: Optional[int]) -> str:
    if ms is None:
        return "—"
    m = ms / 60000.0
    if m < 60:
        return f"{m:.0f}min"
    return f"{m/60:.1f}h"
