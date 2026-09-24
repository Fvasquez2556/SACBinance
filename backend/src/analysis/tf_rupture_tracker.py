"""
Sombra de las rupturas POR MARCO: se registran y se miden, no se publican.

Por que en sombra y no en el tablero: la lectura por marco (`tf_rupture.py`)
no tiene medicion propia. Cuatro marcos por dos direcciones por
confirmada/sin-confirmar son muchas formas de contar una historia coherente a
posteriori, y este proyecto ya tiene dos ejemplos de ideas razonables que al
medirlas no valian nada — la "marea tranquila" (+1.6/+2.1/+0.1 puntos, dentro
del ruido) y la "cascada" entre monedas (por DEBAJO del azar). Hasta que pase
las tres puertas de `criterios_sabado` —dinero, habilidad, terreno nuevo— no
decide nada.

Que se guarda, y por que cada cosa:

  - El plan congelado (rango, SL, TP) en el momento de detectarla. Sin
    congelarlo, recalcularlo despues mide otro plan.
  - La CONFLUENCIA entre los cuatro marcos en ese instante. Es la variable
    que justifica la funcion entera: si mirar cuatro marcos no separa el
    resultado, sobra.
  - El recorrido desde el precio de deteccion (entrar a mercado) Y desde el
    relleno del retest, por separado. Comparar las dos entradas es lo unico
    con respaldo previo: entrar al precio de la señal midio -0.26%/op con el
    IC entero bajo cero, y comprar mas abajo mejoraba ~0.47 puntos.
  - El primer toque de TP y de SL. Sin el orden entre los dos no hay
    desenlace, solo un MFE que puede haber llegado despues del stop.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from src.analysis.tf_rupture import (
    RUPTURA_ALCISTA,
    RUPTURA_BAJISTA,
    leer_tf,
    resumir,
)
from src.analysis.trade_levels import calcular_plan_direccional
from src.config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

HORIZONTES_MIN = (5, 15, 30, 60, 240, 1440)
_VENTANA_MS = 24 * 3600_000
_TF_MS = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


class TFRuptureShadow:
    """Abre una fila por ruptura de marco y la mide 24h, sin publicar nada."""

    def __init__(self, db) -> None:
        self._db = db
        self._abiertas: Dict[int, dict] = {}
        self._por_symbol: Dict[str, List[int]] = {}
        # (symbol, tf) -> ultima direccion vista. Abre solo en el CAMBIO: sin
        # esto, cada cierre de vela con el precio aun pasado del nivel abriria
        # una fila nueva y la muestra serian copias de la misma ruptura.
        self._ultima: Dict[tuple, Optional[str]] = {}
        self._armado = False

    # --- Ciclo de vida --------------------------------------------------------

    def cargar(self) -> int:
        try:
            for row in self._db.get_rupturas_tf_abiertas():
                self._registrar(row)
        except Exception as exc:
            logger.warning(f"No se pudo recuperar la sombra por marcos: {exc}")
            return 0
        if self._abiertas:
            logger.info(f"Sombra de rupturas por marco recuperada: {len(self._abiertas)}")
        return len(self._abiertas)

    def _registrar(self, row: dict) -> None:
        row["ts_vela"] = row.get("ts_last") if row.get("n_velas") else None
        self._abiertas[row["id"]] = row
        self._por_symbol.setdefault(row["symbol"], []).append(row["id"])

    def armar(self, states: dict) -> None:
        """
        Siembra la direccion actual de cada (par, marco) sin registrarla.

        Al arrancar, medio universo esta ya al otro lado de algun nivel. Sin
        sembrar, el primer cierre de vela abriria cientos de filas de rupturas
        que ocurrieron antes de estar mirando: no son terreno nuevo.
        """
        s = get_settings()
        sembrados = 0
        t0 = time.monotonic()
        for symbol, st in states.items():
            if not st.candles:
                continue   # sin hidratar: sembrarlo aqui seria sembrar ruido
            for tf in s.informe_tfs_list:
                try:
                    lectura = leer_tf(tf, list(st.get_candles_tf(tf)),
                                      st.metrics.price, st.ind_htf.get(tf))
                except Exception:
                    continue
                self._ultima[(symbol, tf)] = (
                    lectura.direccion
                    if lectura.direccion in (RUPTURA_ALCISTA, RUPTURA_BAJISTA)
                    else None
                )
                sembrados += 1
        self._armado = True
        logger.info(f"Sombra por marcos armada sobre {sembrados} pares-marco "
                    f"en {time.monotonic() - t0:.1f}s")

    def symbols(self) -> set:
        return set(self._por_symbol)

    # --- Deteccion ------------------------------------------------------------

    def evaluar(self, symbol: str, st, tf: str, now_ms: int) -> Optional[dict]:
        """
        Se llama al CERRAR una vela de `tf`. Devuelve la fila abierta, o None.

        Solo el marco que acaba de cerrar se relee; los otros tres se leen
        unicamente cuando hay ruptura nueva, para la confluencia. En la vuelta
        normal esto es una lectura, no cuatro.
        """
        s = get_settings()
        if not s.sombra_tf_enabled or tf not in _TF_MS:
            return None
        clave = (symbol, tf)
        velas = list(st.get_candles_tf(tf))
        price = st.metrics.price
        if price <= 0:
            return None

        try:
            lectura = leer_tf(tf, velas, price, st.ind_htf.get(tf))
        except Exception as exc:
            logger.debug(f"[{symbol}/{tf}] lectura de sombra fallo: {exc}")
            return None

        direccion = (lectura.direccion
                     if lectura.direccion in (RUPTURA_ALCISTA, RUPTURA_BAJISTA)
                     else None)

        if not self._armado or clave not in self._ultima:
            self._ultima[clave] = direccion
            return None
        if direccion == self._ultima[clave]:
            return None
        self._ultima[clave] = direccion
        if direccion is None:
            return None

        # Cooldown en velas del propio marco: 6 velas son 30 min en 5m y un dia
        # en 4h. Un umbral en minutos serviria a un marco y no al otro.
        ultimo = self._db.ultima_ruptura_tf_ts(symbol, tf, direccion)
        if ultimo is not None:
            espera = s.sombra_tf_cooldown_velas * _TF_MS[tf]
            if now_ms - ultimo < espera:
                return None

        # Confluencia: aqui si se leen los cuatro marcos.
        lecturas = []
        for otro in s.informe_tfs_list:
            if otro == tf:
                lecturas.append(lectura)
                continue
            try:
                lecturas.append(leer_tf(otro, list(st.get_candles_tf(otro)),
                                        price, st.ind_htf.get(otro)))
            except Exception:
                continue
        conf = resumir(lecturas)

        plan = calcular_plan_direccional(
            direccion, price, velas, lectura.nivel_roto, tf=tf,
            niveles_sr=lectura.niveles, candles_1m=list(st.candles),
        )

        row = {
            "symbol": symbol,
            "tf": tf,
            "direction": direccion,
            "ts_open": now_ms,
            "price_open": price,
            "confirmada": int(lectura.confirmada),
            "nivel_roto": lectura.nivel_roto,
            "toques_nivel": lectura.toques_nivel,
            "velas_desde_ruptura": lectura.velas_desde_ruptura,
            "tendencia": lectura.tendencia,
            "atr_pct": lectura.atr_pct,
            "rsi14": lectura.rsi14,
            "vol_ratio": lectura.vol_ratio,
            "razon": (lectura.razon or "")[:300],
            "conf_dominante": conf["direccion_dominante"],
            "conf_tf_dominante": conf["tf_dominante"],
            "conf_alcistas": conf["n_alcistas"],
            "conf_bajistas": conf["n_bajistas"],
            "conf_confirmadas": conf["n_confirmadas"],
            "conf_en_conflicto": int(conf["en_conflicto"]),
            "plan_valid": int(plan.valid),
            "entrada_min": plan.entrada_min,
            "entrada_max": plan.entrada_max,
            "entrada_ref": plan.entrada_ref,
            "stop_loss": plan.stop_loss,
            "take_profit": plan.take_profit,
            "risk_pct": plan.risk_pct,
            "reward_pct": plan.reward_pct,
            "reward_neto_pct": plan.reward_neto_pct,
            "sl_basis": plan.sl_basis,
            "tp_bloqueado": int(plan.tp_bloqueado),
            "plan_reason": (plan.reason or "")[:300],
            "last_price": price,
            "ts_last": None,
            "n_velas": 0,
            "max_up_pct": 0.0,
            "max_down_pct": 0.0,
            "mfe_direction_pct": 0.0,
            "mae_direction_pct": 0.0,
            "mfe_fill_pct": 0.0,
            "mae_fill_pct": 0.0,
            "closed": 0,
        }
        try:
            row["id"] = self._db.registrar_ruptura_tf(row)
        except Exception as exc:
            logger.warning(f"[{symbol}/{tf}] no se pudo registrar la sombra: {exc}")
            return None
        self._registrar(row)
        return row

    # --- Medicion -------------------------------------------------------------

    def on_candle(self, symbol: str, ts: int, high: float, low: float,
                  close: float) -> int:
        """Vela 1m cerrada: actualiza cada fila viva del par. Devuelve cuantas."""
        ids = list(self._por_symbol.get(symbol, ()))
        if not ids:
            return 0
        tocadas = 0
        for event_id in ids:
            row = self._abiertas.get(event_id)
            if row is None or ts <= (row.get("ts_vela") or -1):
                continue
            elapsed = ts - row["ts_open"]
            if elapsed < 0:
                continue
            campos = self._medir(row, elapsed, high, low, close)
            campos["ts_last"] = ts
            campos["last_price"] = close
            campos["n_velas"] = row["n_velas"] + 1
            row.update(campos)
            row["ts_vela"] = ts
            if elapsed >= _VENTANA_MS:
                row["closed"] = campos["closed"] = 1
            try:
                self._db.guardar_ruptura_tf(event_id, campos)
            except Exception as exc:
                logger.debug(f"[{symbol}] guardar sombra por marco fallo: {exc}")
            if row.get("closed"):
                self._cerrar_memoria(row)
            tocadas += 1
        return tocadas

    def _medir(self, row: dict, elapsed: int, high: float, low: float,
               close: float) -> dict:
        entry = row["price_open"]
        alcista = row["direction"] == RUPTURA_ALCISTA
        sign = 1.0 if alcista else -1.0
        campos: dict = {}

        up_pct = (high - entry) / entry * 100.0
        down_pct = (low - entry) / entry * 100.0
        if up_pct > row["max_up_pct"]:
            campos["max_up_pct"] = round(up_pct, 3)
        if down_pct < row["max_down_pct"]:
            campos["max_down_pct"] = round(down_pct, 3)

        favorable = up_pct if alcista else -down_pct
        adverse = down_pct if alcista else -up_pct
        if favorable > row["mfe_direction_pct"]:
            campos["mfe_direction_pct"] = round(favorable, 3)
            campos["ms_mfe_direction"] = elapsed
        if adverse < row["mae_direction_pct"]:
            campos["mae_direction_pct"] = round(adverse, 3)
            campos["ms_mae_direction"] = elapsed

        ret = sign * (close - entry) / entry * 100.0
        for minutos in HORIZONTES_MIN:
            campo = f"ret_{minutos}m_pct"
            if row.get(campo) is None and elapsed >= minutos * 60_000:
                campos[campo] = round(ret, 3)
                campos[f"ms_ret_{minutos}m"] = elapsed

        if row.get("plan_valid"):
            campos.update(self._medir_plan(row, elapsed, high, low))
        return campos

    def _medir_plan(self, row: dict, elapsed: int, high: float,
                    low: float) -> dict:
        """
        Barreras y relleno del retest.

        TP y SL en la misma vela quedan con el mismo `elapsed`: es ambiguo y se
        guarda como tal, nunca como victoria. Lo mismo con el relleno — si la
        vela que llena el rango es la que tambien toca el stop, no se sabe el
        orden dentro del minuto y el analisis tiene que tratarlo aparte.
        """
        alcista = row["direction"] == RUPTURA_ALCISTA
        tp, sl = row.get("take_profit"), row.get("stop_loss")
        campos: dict = {}

        if row.get("ms_tp") is None and tp:
            if (high >= tp) if alcista else (low <= tp):
                campos["ms_tp"] = elapsed
        if row.get("ms_sl") is None and sl:
            if (low <= sl) if alcista else (high >= sl):
                campos["ms_sl"] = elapsed

        borde = row.get("entrada_min") if alcista else row.get("entrada_max")
        if row.get("ms_fill") is None and borde:
            if (low <= borde) if alcista else (high >= borde):
                campos["ms_fill"] = elapsed
                campos["precio_fill"] = borde
                row["precio_fill"] = borde

        fill = campos.get("precio_fill") or row.get("precio_fill")
        if fill:
            up = (high - fill) / fill * 100.0
            down = (low - fill) / fill * 100.0
            favorable = up if alcista else -down
            adverse = down if alcista else -up
            if favorable > row.get("mfe_fill_pct", 0.0):
                campos["mfe_fill_pct"] = round(favorable, 3)
            if adverse < row.get("mae_fill_pct", 0.0):
                campos["mae_fill_pct"] = round(adverse, 3)
        return campos

    def cerrar_vencidos(self, now_ms: int) -> int:
        cerradas = 0
        for row in list(self._abiertas.values()):
            if now_ms - row["ts_open"] < _VENTANA_MS:
                continue
            row["closed"] = 1
            try:
                self._db.guardar_ruptura_tf(row["id"], {"closed": 1})
            except Exception:
                pass
            self._cerrar_memoria(row)
            cerradas += 1
        if cerradas:
            logger.info(f"Sombra por marcos: {cerradas} cerradas por fin de ventana")
        return cerradas

    def _cerrar_memoria(self, row: dict) -> None:
        self._abiertas.pop(row["id"], None)
        ids = self._por_symbol.get(row["symbol"])
        if ids and row["id"] in ids:
            ids.remove(row["id"])
            if not ids:
                self._por_symbol.pop(row["symbol"], None)
