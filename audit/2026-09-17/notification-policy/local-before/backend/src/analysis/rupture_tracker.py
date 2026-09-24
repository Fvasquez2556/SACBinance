"""Seguimiento persistente y simetrico de rupturas alcistas y bajistas."""
from __future__ import annotations

from typing import Dict, List, Optional

from src.analysis.ruptures import RUPTURA_ALCISTA
from src.config.settings import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

HORIZONTES_MIN = (5, 15, 30, 60, 240, 1440)
_VENTANA_MS = 24 * 3600_000


class RuptureTracker:
    """Mide cada ruptura desde su precio de deteccion durante 24 horas."""

    def __init__(self, db) -> None:
        self._db = db
        self._abiertas: Dict[int, dict] = {}
        self._por_symbol: Dict[str, List[int]] = {}

    def cargar(self) -> int:
        try:
            for row in self._db.get_rupturas_abiertas():
                self._registrar(row)
        except Exception as exc:
            logger.warning(f"No se pudieron recuperar rupturas abiertas: {exc}")
            return 0
        if self._abiertas:
            logger.info(f"Rupturas en seguimiento recuperadas: {len(self._abiertas)}")
        return len(self._abiertas)

    def _registrar(self, row: dict) -> None:
        row["ts_vela"] = row.get("ts_last") if row.get("n_velas") else None
        self._abiertas[row["id"]] = row
        self._por_symbol.setdefault(row["symbol"], []).append(row["id"])

    def symbols(self) -> set:
        return set(self._por_symbol)

    def abrir(self, symbol: str, direccion: str, ts_open: int, precio: float,
              snapshot: dict, razon: str) -> Optional[dict]:
        if precio <= 0:
            return None
        s = get_settings()
        ultimo = self._db.ultima_ruptura_ts(symbol, direccion)
        if ultimo is not None and ts_open - ultimo < s.telegram_ruptura_cooldown_min * 60_000:
            return None
        row = {
            "symbol": symbol,
            "direction": direccion,
            "ts_open": ts_open,
            "price_open": precio,
            "display_state": snapshot.get("display_state"),
            "reason": razon,
            "score": snapshot.get("score"),
            "z_rise": snapshot.get("z_rise"),
            "z_drop": snapshot.get("z_drop"),
            "rango_1h_pct": snapshot.get("rango_1h_pct"),
            "last_price": precio,
            "ts_last": None,
            "n_velas": 0,
            "max_up_pct": 0.0,
            "max_down_pct": 0.0,
            "mfe_direction_pct": 0.0,
            "mae_direction_pct": 0.0,
            "telegram": "pendiente",
            "telegram_detail": "",
            "closed": 0,
        }
        event_id = self._db.registrar_ruptura(row)
        row["id"] = event_id
        self._registrar(row)
        return row

    def marcar_telegram(self, row: dict, estado: str, detalle: str = "",
                        message_id: Optional[int] = None) -> None:
        row["telegram"] = estado
        row["telegram_detail"] = detalle[:200]
        if message_id is not None:
            row["telegram_message_id"] = message_id
        campos = {"telegram": row["telegram"], "telegram_detail": row["telegram_detail"]}
        if message_id is not None:
            campos["telegram_message_id"] = message_id
        self._db.guardar_ruptura(row["id"], campos)

    def on_candle(self, symbol: str, ts: int, high: float, low: float,
                  close: float) -> List[dict]:
        ids = list(self._por_symbol.get(symbol, ()))
        if not ids:
            return []
        seguimientos: List[dict] = []
        for event_id in ids:
            row = self._abiertas.get(event_id)
            if row is None or ts <= (row.get("ts_vela") or -1):
                continue
            elapsed = ts - row["ts_open"]
            if elapsed < 0:
                continue

            entry = row["price_open"]
            up_pct = (high - entry) / entry * 100.0
            down_pct = (low - entry) / entry * 100.0
            sign = 1.0 if row["direction"] == RUPTURA_ALCISTA else -1.0
            favorable = up_pct if sign > 0 else -down_pct
            adverse = down_pct if sign > 0 else -up_pct
            campos = {
                "ts_last": ts,
                "last_price": close,
                "n_velas": row["n_velas"] + 1,
            }
            row.update(campos)
            row["ts_vela"] = ts
            if up_pct > row["max_up_pct"]:
                row["max_up_pct"] = campos["max_up_pct"] = round(up_pct, 3)
            if down_pct < row["max_down_pct"]:
                row["max_down_pct"] = campos["max_down_pct"] = round(down_pct, 3)
            if favorable > row["mfe_direction_pct"]:
                row["mfe_direction_pct"] = campos["mfe_direction_pct"] = round(favorable, 3)
                row["ms_mfe_direction"] = campos["ms_mfe_direction"] = elapsed
            if adverse < row["mae_direction_pct"]:
                row["mae_direction_pct"] = campos["mae_direction_pct"] = round(adverse, 3)
                row["ms_mae_direction"] = campos["ms_mae_direction"] = elapsed

            nuevos_horizontes: List[int] = []
            ret = sign * (close - entry) / entry * 100.0
            for minutos in HORIZONTES_MIN:
                campo = f"ret_{minutos}m_pct"
                if row.get(campo) is None and elapsed >= minutos * 60_000:
                    row[campo] = campos[campo] = round(ret, 3)
                    row[f"ms_ret_{minutos}m"] = campos[f"ms_ret_{minutos}m"] = elapsed
                    nuevos_horizontes.append(minutos)

            if elapsed >= _VENTANA_MS:
                row["closed"] = campos["closed"] = 1
            self._db.guardar_ruptura(event_id, campos)
            if nuevos_horizontes:
                seguimientos.append({"ruptura": dict(row), "horizontes": nuevos_horizontes})
            if row.get("closed"):
                self._cerrar_memoria(row)
        return seguimientos

    def cerrar_vencidos(self, now_ms: int) -> int:
        cerradas = 0
        for row in list(self._abiertas.values()):
            if now_ms - row["ts_open"] < _VENTANA_MS:
                continue
            row["closed"] = 1
            self._db.guardar_ruptura(row["id"], {"closed": 1})
            self._cerrar_memoria(row)
            cerradas += 1
        if cerradas:
            logger.info(f"Rupturas cerradas por fin de ventana: {cerradas}")
        return cerradas

    def _cerrar_memoria(self, row: dict) -> None:
        self._abiertas.pop(row["id"], None)
        ids = self._por_symbol.get(row["symbol"])
        if ids and row["id"] in ids:
            ids.remove(row["id"])
            if not ids:
                self._por_symbol.pop(row["symbol"], None)
