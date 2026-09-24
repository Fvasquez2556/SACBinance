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

from src.analysis import grupos, hoyo
from src.config.settings import get_settings
from src.utils import procedencia
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Escalera fija de umbrales, en %. El 3.2 es el objetivo de referencia.
# El 1.2 y el 4.2 estan para los marcadores del tablero (ver `marcadores`).
ESCALERA = (1.0, 1.2, 2.0, 3.2, 4.2, 5.0, 10.0)
_SUFIJO = {1.0: "1", 1.2: "12", 2.0: "2", 3.2: "32",
           4.2: "42", 5.0: "5", 10.0: "10"}

OBJETIVO = 3.2  # umbral sobre el que se clasifica la forma del camino

# Duracion de la vela con la que se mide (1m). El camino de una señal se mide
# por INTERVALOS COMPLETOS: una vela solo cuenta si su minuto entero cae dentro
# de la ventana. La que empieza antes del vencimiento y cierra despues tiene su
# maximo en un instante desconocido, que puede ser posterior al vencimiento;
# concederle el TP era atribuir a la señal un precio de fuera de su ventana.
VELA_MS = 60_000

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


def _contexto(snapshot: dict, trade_levels: dict) -> dict:
    """
    Saca del snapshot las variables que hasta la v7 se tiraban.

    El engine calcula unas 40 por vela y `outcomes` guardaba 7. Sin las otras
    no hay con que responder la pregunta que queda abierta: que distingue una
    señal que llega de una que no. Nada de esto cambia una decision del
    sistema — solo deja de tirar la medicion.

    Todo va con .get() y sin excepciones: si un campo falta se guarda NULL, que
    es mejor que perder la fila entera.
    """
    imp = snapshot.get("impulso") or {}
    ret = snapshot.get("retroceso") or {}
    sr = snapshot.get("sr_levels") or {}
    cons = snapshot.get("consolidation") or {}
    ind = snapshot.get("ind_htf") or {}
    htf15 = (ind.get("15m") or {}) if isinstance(ind, dict) else {}
    return {
        "pos_en_rango": snapshot.get("pos_en_rango"),
        "dist_soporte_pct": sr.get("dist_soporte_pct"),
        "dist_resistencia_pct": sr.get("dist_resistencia_pct"),
        "z_drop": snapshot.get("z_drop"),
        "z_rise": snapshot.get("z_rise"),
        "velocity": snapshot.get("velocity"),
        "ret_1m_pct": snapshot.get("ret_1m_pct"),
        "drawdown_pct": snapshot.get("drawdown_pct"),
        "rango_1h_pct": snapshot.get("rango_1h_pct"),
        "sigma_pct": snapshot.get("sigma_pct"),
        "atr_pct": trade_levels.get("atr_pct"),
        "ruido_1m_pct": trade_levels.get("ruido_1m_pct"),
        "atr_percentile": cons.get("atr_percentile"),
        "vol_ratio": snapshot.get("vol_ratio"),
        "buy_ratio_30s": snapshot.get("buy_ratio_30s"),
        "flow_trades_30s": snapshot.get("flow_trades_30s"),
        # 1 si el par estaba suscrito a aggTrade, 0 si no. Sin esto, "no habia
        # compradores" y "no habia datos" son el mismo 0: el 92.8% de las filas
        # con contexto tenian trades=0 y buy_ratio=0.5 exacto, que es el valor
        # por defecto de un flujo que nunca se actualizo.
        "flow_disponible": 1 if snapshot.get("flow_disponible") else 0,
        "rsi5": snapshot.get("rsi5"),
        # Con el TF en el nombre. Antes se pedia snapshot["rsi14"],
        # snapshot["macd_hist"] y snapshot["bb_position"], y el snapshot no
        # tiene esas claves: el de 1m se llama rsi14_1m y los de TF superior
        # viven en ind_htf[tf]. Las tres columnas salieron NULL en las 2.790
        # filas, y con ellas se fue la posibilidad de saber si esos
        # indicadores ayudan a elegir.
        "rsi14_1m": snapshot.get("rsi14_1m"),
        "rsi14_15m": htf15.get("rsi14"),
        "macd_hist_15m": htf15.get("macd_hist"),
        "bb_position_15m": htf15.get("bb_position"),
        "fase_impulso": imp.get("fase"),
        "fuerza_impulso": imp.get("fuerza"),
        "consumido_pct": imp.get("consumido_pct"),
        "retro_caida_pct": ret.get("caida_pct"),
        "retro_rebote_pct": ret.get("rebote_pct"),
        "retro_confirmado": 1 if ret.get("confirmado") else 0,
        "btc_regime": snapshot.get("btc_regime"),
        "macro_gate_mult": snapshot.get("macro_gate_mult"),
        "score_trend": snapshot.get("score_trend"),
        "es_fakeout": 1 if snapshot.get("is_fakeout") else 0,
        "senal_n": snapshot.get("senal_n"),
    }


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
            # El contador de sombras tiene que continuar por debajo del minimo
            # de TODA la tabla, no solo de las que siguen abiertas. Si se mira
            # solo lo abierto, en cuanto se cierran todas el contador vuelve a
            # 0, choca con un id ya usado, y como el INSERT es OR IGNORE la
            # sombra desaparece sin dar error.
            self._sombra_id = min(self._sombra_id, self._db.min_signal_id())
        except Exception as e:
            logger.warning(f"No se pudieron cargar outcomes abiertos: {e}")
            return 0
        n = len(self._abiertos)
        if n:
            logger.info(f"Outcomes en seguimiento recuperados: {n}")
        return n

    def _registrar_memoria(self, row: dict) -> None:
        sid = row["signal_id"]
        # Marca de idempotencia, SOLO en memoria: la apertura de la ultima vela
        # ya contada. No es una columna — `abrir_outcome` arma el INSERT con las
        # claves de la fila — y no hace falta que lo sea: `ts_last` ya la
        # guarda. Una fila recien abierta no ha contado ninguna vela (n_velas=0)
        # y arranca en None; una que vuelve de la base reanuda donde se quedo.
        row["ts_vela"] = row.get("ts_last") if row.get("n_velas") else None
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

    def _siguiente_id_sombra(self):
        """
        El siguiente id negativo libre, garantizado.

        La invariante vive aqui y no en `cargar()` a proposito: antes el
        contador solo se recuperaba si alguien llamaba a cargar() ANTES de la
        primera sombra, y si no, arrancaba en 0, chocaba con un id ya usado y
        la fila desaparecia sin ruido (INSERT OR IGNORE). Una invariante que
        depende del orden de las llamadas se rompe sola tarde o temprano.
        """
        if self._sombra_id >= 0:
            try:
                self._sombra_id = min(0, self._db.min_signal_id())
            except Exception as e:
                logger.warning(f"No se pudo leer el minimo signal_id: {e}")
                return None
        self._sombra_id -= 1
        return self._sombra_id

    def abrir_sombra(self, symbol: str, ts_open: int, snapshot: dict,
                     trade_levels: dict, score_estimado: int,
                     motivo: str = "GATE_MACRO",
                     conservar_tier: bool = False) -> None:
        """
        Sigue una señal que el sistema NO llego a emitir, sin alertarla.

        Dos casos, y los dos eran puntos ciegos:

        GATE_MACRO — el gate multiplica el score y lo deja bajo el umbral. El
            4-sep, SUBIENDO con macro BAJISTA dio 0 de 82 por encima del
            umbral, y ese mismo dia TUTUSDT (+12%) y MITOUSDT (+8.4%) cayeron
            ahi, sin datos para saber si el muro protegia o costaba.

        VETO — los filtros de alerta la rechazan. Es el caso mas grave porque
            es el mas frecuente: el 9-sep KATUSDT subio 29.79% con 46 vetos y
            CERO filas en outcomes, y IOSTUSDT hizo +169.8% con 169 vetos y
            ninguna señal. Todo el analisis de esa semana se hizo sobre las
            señales emitidas, es decir, sobre la mitad de la pelicula.

        Una sombra por par a la vez: si no, un par vetado cuarenta veces en un
        dia mete cuarenta filas del mismo momento.

        Los ids de sombra son negativos para no chocar con los de signals.
        """
        if self._db is None or symbol in self._sombra_activa:
            return
        sid = self._siguiente_id_sombra()
        if sid is None:
            return
        snap = dict(snapshot)
        snap["score"] = score_estimado          # el score SIN el gate
        # En los vetos el tier real importa —KAT llego a FUERTE antes de que la
        # vetaran— asi que se conserva. En el gate macro no hay tier que
        # conservar: el gate ya lo dejo en NINGUNO.
        if not conservar_tier:
            snap["tier"] = "SOMBRA"
        self.abrir(sid, symbol, ts_open, snap, trade_levels,
                   sombra=True, sombra_motivo=motivo)
        if sid in self._abiertos:
            self._sombra_activa.add(symbol)

    def abrir(self, signal_id: int, symbol: str, ts_open: int,
              snapshot: dict, trade_levels: dict, sombra: bool = False,
              sombra_motivo: Optional[str] = None) -> None:
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
            # Por que no se emitio: GATE_MACRO, o el texto del veto. NULL en
            # las señales reales.
            "sombra_motivo": (sombra_motivo or None) if sombra else None,
            "vol_24h": snapshot.get("vol_24h"),
            "vol_1m_medio": snapshot.get("vol_1m_medio"),
            # Lo que queda del TP despues de costes, y si con eso llega al
            # objetivo del operador. El bruto hacia pasar por alcanzables
            # señales que no podian serlo.
            "reward_neto_pct": trade_levels.get("reward_neto_pct"),
            "objetivo_alcanzable": 1 if trade_levels.get("objetivo_alcanzable") else 0,
        }
        # Objetivo por grupo de moneda, EN SOMBRA: se guarda cual le tocaria y
        # luego se mide si lo alcanza. No cambia el TP ofrecido ni nada de lo
        # que el sistema decide. Ver src/analysis/grupos.py.
        row.update(grupos.campos(snapshot.get("vol_previa_pct")))
        row.update(_contexto(snapshot, trade_levels))
        row["strategy_version"] = procedencia.version()
        row["config_hash"] = procedencia.config_hash()
        row.update(hoyo.inicial(sl))
        try:
            if not self._db.abrir_outcome(row):
                # Nunca deberia pasar: el id ya existia. A nivel WARNING porque
                # el modo de fallo es una fila que se pierde en silencio.
                logger.warning(
                    f"[{symbol}] outcome #{signal_id} NO se guardo: ese id ya "
                    f"existe en la tabla"
                )
                return
        except Exception as e:
            logger.warning(f"[{symbol}] abrir_outcome error: {e}")
            return

        # La fila en memoria necesita todas las columnas de cruce a None
        for u in ESCALERA:
            row[f"ms_up_{_SUFIJO[u]}"] = None
            row[f"ms_dn_{_SUFIJO[u]}"] = None
        row["ms_tp"] = row["ms_sl"] = None
        # Igual que el resto de la escalera: la fila en memoria arranca con
        # TODAS las columnas de cruce a None. Si no, leerlas antes del primer
        # cruce revienta con KeyError en vez de decir "todavia no".
        row["ms_objetivo_grupo"] = None
        row["ms_mfe"] = row["ms_mae"] = None
        row["dip_antes_obj"] = None
        row["forma"] = None
        row.update(hoyo.campos_memoria())
        self._registrar_memoria(row)

    def cerrar_vencidos(self, now_ms: int) -> int:
        """
        Cierra los outcomes cuya ventana caduco, aunque no lleguen mas velas.

        Antes el cierre dependia de que llegara una vela del par. Si el par
        salia del universo o se cortaba su stream, el seguimiento quedaba
        colgado indefinidamente: la duracion mas larga observada fue de 117.92
        horas sobre una ventana nominal de 24. Ahora manda el reloj.

        Se llama desde el bucle de volcado, no desde el camino de la vela.
        """
        if self._db is None:
            return 0
        ventana_ms = get_settings().outcome_window_hours * 3600_000
        dip_umbral = get_settings().forma_dip_umbral
        n = 0
        for sid, row in list(self._abiertos.items()):
            if now_ms - row["ts_open"] < ventana_ms:
                continue
            row["forma"] = _clasificar_forma(row, dip_umbral)
            row["cobertura_velas"] = _cobertura(row)
            row["cerrado"] = 1
            try:
                self._db.guardar_outcome(sid, {"forma": row["forma"], "cerrado": 1,
                                               "cobertura_velas": row["cobertura_velas"]})
            except Exception as e:
                logger.debug(f"[{row['symbol']}] cerrar vencido: {e}")
            self._abiertos.pop(sid, None)
            ids = self._por_symbol.get(row["symbol"])
            if ids and sid in ids:
                ids.remove(sid)
                if not ids:
                    self._por_symbol.pop(row["symbol"], None)
            if sid < 0:
                self._sombra_activa.discard(row["symbol"])
            n += 1
        if n:
            logger.info(f"Outcomes cerrados por fin de ventana sin velas: {n}")
        return n

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

            # Una vela que abrio ANTES de la emision no es parte del camino de
            # esta señal: su maximo y su minimo son de un precio que el sistema
            # todavia no habia propuesto. Contarla producia tiempos negativos
            # —97 filas los tenian— y metia en el MFE/MAE movimiento previo.
            if transcurrido < 0:
                continue

            # Y una posterior al cierre de la ventana tampoco. Habia 33 filas
            # con eventos mas alla de las 24h y una de 117.92h: movimiento de
            # dias despues atribuido a la señal.
            if transcurrido > ventana_ms:
                if not row.get("cerrado"):
                    row["forma"] = _clasificar_forma(row, dip_umbral)
                    row["cobertura_velas"] = _cobertura(row)
                    row["cerrado"] = 1
                    try:
                        self._db.guardar_outcome(
                            sid, {"forma": row["forma"], "cerrado": 1,
                                  "cobertura_velas": row["cobertura_velas"]})
                    except Exception as e:
                        logger.debug(f"[{symbol}] cerrar fuera de ventana: {e}")
                    cerrados.append(dict(row))
                self._abiertos.pop(sid, None)
                if sid in ids:
                    ids.remove(sid)
                if sid < 0:
                    self._sombra_activa.discard(symbol)
                continue

            # La vela que CIERRA despues del vencimiento tampoco entra, aunque
            # haya abierto antes. Su maximo puede ocurrir en cualquier instante
            # del minuto, incluido uno posterior al vencimiento, y una prueba
            # le concedia el TP con el maximo fuera de ventana. Se salta sin
            # cerrar: el cierre lo da el reloj (`cerrar_vencidos`) o la
            # siguiente vela, que ya cae entera fuera.
            if transcurrido + VELA_MS > ventana_ms:
                continue

            # Idempotencia. La misma vela llega dos veces cuando el WS
            # reconecta o cuando la reparacion por REST repite un minuto ya
            # recibido; y una reparacion puede traerla atrasada. Contarla dos
            # veces inflaba `n_velas` — y con el la cobertura, que es
            # justamente el dato con el que se decide si una fila se puede
            # leer — y una atrasada hacia retroceder `ts_last`.
            ultima_vela = row.get("ts_vela")
            if ultima_vela is not None and ts <= ultima_vela:
                continue

            cambios: dict = {"ts_last": ts, "n_velas": row["n_velas"] + 1}
            row["n_velas"] += 1
            row["ts_last"] = ts
            row["ts_vela"] = ts

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

            # --- Objetivo por grupo (sombra) ---
            # Mismo criterio que la escalera: primer cruce, y ya no se toca.
            obj_grupo = row.get("objetivo_grupo_pct")
            if obj_grupo and row.get("ms_objetivo_grupo") is None and up_pct >= obj_grupo:
                row["ms_objetivo_grupo"] = cambios["ms_objetivo_grupo"] = transcurrido

            # --- TP / SL ofrecidos por el sistema ---
            tp, sl = row.get("take_profit"), row.get("stop_loss")
            if row.get("ms_tp") is None and tp and high >= tp:
                row["ms_tp"] = cambios["ms_tp"] = transcurrido
            if row.get("ms_sl") is None and sl and low <= sl:
                row["ms_sl"] = cambios["ms_sl"] = transcurrido

            # --- Sombra: la regla de entrar en el hoyo ---
            # No decide nada; solo anota que habria pasado entrando abajo.
            hoyo.actualizar(row, cambios, transcurrido, high, low, close)

            # --- Peor caida ANTES de alcanzar el objetivo ---
            # Es el dato que responde "¿bajo primero y despues subio?".
            # Se congela en el momento en que se toca +3.2% por primera vez.
            if row.get("dip_antes_obj") is None:
                if row.get(f"ms_up_{_SUFIJO[OBJETIVO]}") is not None:
                    row["dip_antes_obj"] = cambios["dip_antes_obj"] = row["mae_pct"]

            # El cierre por fin de ventana ya no ocurre aqui. Al exigir que la
            # vela caiga ENTERA dentro de la ventana, ninguna que se procese
            # puede llegar al vencimiento: la ultima que cuenta cierra un minuto
            # antes. Cierran, por ese orden, el reloj (`cerrar_vencidos`, cada
            # `db_flush_interval`) o la primera vela que ya cae fuera.

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


def _cobertura(row: dict) -> float:
    """
    Que fraccion de los minutos de la ventana llego de verdad.

    Los 239 pares con velas de 1m tenian huecos internos: 47.249 minutos-par
    ausentes, y ninguna ventana alcanzaba el 98% de cobertura. Un hueco puede
    cambiar QUE ocurre primero, si el stop o el objetivo, asi que una fila con
    cobertura baja no se puede leer igual que una completa.

    Se guarda al cerrar. No arregla el hueco — eso lo hace la reparacion por
    REST — pero permite excluir del analisis lo que no se puede sostener.
    """
    # El denominador son las velas que PUEDEN entrar, no los minutos de la
    # ventana: la que cierra despues del vencimiento ya no cuenta, asi que en
    # una ventana de 24h el maximo alcanzable son 1.439 velas y no 1.440. Con
    # el denominador antiguo, una cobertura perfecta se leia como 99.93%.
    esperados = get_settings().outcome_window_hours * 3600_000 // VELA_MS - 1
    if esperados <= 0:
        return 0.0
    return round(min(1.0, (row.get("n_velas") or 0) / esperados), 4)


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
