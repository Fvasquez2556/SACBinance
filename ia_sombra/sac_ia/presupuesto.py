"""
El gasto en la API, con tope duro. Se reserva ANTES de llamar y se liquida despues.

La reserva es el peor caso: entrada estimada por lo alto mas el maximo de
salida que se permite al modelo. Si no cabe en el tope del dia o en el total,
no se llama. Una llamada que se corta sin saber si se cobro queda INCIERTA y
conserva su reserva: dudar a favor del tope, no del gasto.

El tope ultimo no es este: son los creditos prepagados de OpenAI con la recarga
automatica apagada. Esto evita llegar ahi por un bucle.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sac_ia import registro
from sac_ia.almacen import Almacen

MICRO = 1_000_000


def dia_utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def coste_usd(modelo: str, entrada: int, cache: int, salida: int) -> float:
    t = registro.TARIFAS[modelo]
    return ((entrada - cache) * t["entrada"] + cache * t["cache"]
            + salida * t["salida"]) / MICRO


def reserva_usd(modelo: str, texto_entrada: str, max_salida: int) -> float:
    """Tokens de entrada acotados por BYTES: ningun tokenizador da mas tokens que bytes."""
    entrada = len(texto_entrada.encode("utf-8")) + 500
    return coste_usd(modelo, entrada, 0, max_salida)


class Presupuesto:
    def __init__(self, almacen: Almacen, tope_diario_usd: float, tope_total_usd: float) -> None:
        self.a = almacen
        self.tope_dia = int(tope_diario_usd * MICRO)
        self.tope_total = int(tope_total_usd * MICRO)

    def _comprometido(self, dia: str | None = None) -> int:
        sql = ("SELECT COALESCE(SUM(CASE WHEN estado = 'LIQUIDADO' THEN consumido_micro "
               "ELSE reservado_micro END), 0) FROM gasto WHERE estado != 'LIBERADO'")
        args = ()
        if dia:
            sql += " AND dia_utc = ?"
            args = (dia,)
        return int(self.a.uno(sql, args) or 0)

    def reservar(self, request_id: str, caso_id: int, brazo: str, modelo: str,
                 monto_usd: float, ahora_ms: int) -> bool:
        if modelo not in registro.TARIFAS:
            return False
        monto = int(monto_usd * MICRO) + 1
        dia = dia_utc(ahora_ms)
        with self.a.lock:
            self.a.db.execute("BEGIN IMMEDIATE")
            try:
                if (self._comprometido(dia) + monto > self.tope_dia
                        or self._comprometido() + monto > self.tope_total):
                    self.a.db.execute("ROLLBACK")
                    return False
                self.a.db.execute(
                    "INSERT INTO gasto VALUES (?, ?, ?, ?, ?, ?, NULL, 'RESERVADO', ?)",
                    (request_id, caso_id, brazo, modelo, dia, monto, ahora_ms))
                self.a.db.execute("COMMIT")
                return True
            except Exception:
                self.a.db.execute("ROLLBACK")
                raise

    def liquidar(self, request_id: str, consumido_usd: float) -> None:
        self.a.ejecutar("UPDATE gasto SET estado = 'LIQUIDADO', consumido_micro = ? "
                        "WHERE request_id = ?", (int(round(consumido_usd * MICRO)), request_id))

    def liberar(self, request_id: str) -> None:
        """Solo cuando consta que la peticion no salio (fallo antes de enviar)."""
        self.a.ejecutar("UPDATE gasto SET estado = 'LIBERADO', consumido_micro = 0 "
                        "WHERE request_id = ?", (request_id,))

    def incierto(self, request_id: str) -> None:
        self.a.ejecutar("UPDATE gasto SET estado = 'INCIERTO' WHERE request_id = ?",
                        (request_id,))

    def resumen(self, ahora_ms: int) -> dict:
        return {"hoy_usd": self._comprometido(dia_utc(ahora_ms)) / MICRO,
                "total_usd": self._comprometido() / MICRO,
                "tope_dia_usd": self.tope_dia / MICRO, "tope_total_usd": self.tope_total / MICRO}
