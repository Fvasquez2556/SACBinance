"""
Los dos caminos por los que puede llegar una vela, con una sola regla detras.

`SeguimientoStreaming` recibe velas segun se cierran; `replay` las lee de la
base. Ninguno de los dos contiene logica de medicion: los dos llaman a
`avanzar()`. Esa es toda la gracia — la equivalencia entre replay y streaming
deja de ser una promesa del diseño y pasa a ser una consecuencia de que solo
exista una funcion, y una prueba lo comprueba con secuencias desordenadas,
repetidas y partidas en dos.
"""
from __future__ import annotations

import sqlite3
from typing import Iterable, Optional

from src.evaluacion.recorrido import (
    Estado,
    Plan,
    Vela,
    avanzar,
    cerrar_por_reloj,
    cobertura,
)


class SeguimientoStreaming:
    """Un plan vivo al que se le van dando velas cerradas."""

    def __init__(self, plan: Plan, estado: Optional[Estado] = None) -> None:
        self.plan = plan
        self.estado = estado or Estado()

    def on_vela(self, vela: Vela) -> Estado:
        self.estado = avanzar(self.plan, self.estado, vela)
        return self.estado

    def on_reloj(self, ahora_ms: int) -> Estado:
        self.estado = cerrar_por_reloj(self.plan, self.estado, ahora_ms)
        return self.estado

    def cobertura(self, ahora_ms: int) -> float:
        return cobertura(self.plan, self.estado, ahora_ms)

    # Serializar y recuperar es lo que hace que un reinicio no pierda el hilo.
    def como_dict(self) -> dict:
        return self.estado.como_dict()

    @classmethod
    def desde_dict(cls, plan: Plan, d: dict) -> "SeguimientoStreaming":
        return cls(plan, Estado.desde_dict(d))


def replay(plan: Plan, velas: Iterable[Vela], ahora_ms: Optional[int] = None,
           estado: Optional[Estado] = None) -> Estado:
    """Reconstruye el recorrido desde una secuencia ya ordenada."""
    e = estado or Estado()
    for vela in velas:
        e = avanzar(plan, e, vela)
    return cerrar_por_reloj(plan, e, ahora_ms) if ahora_ms is not None else e


def velas_de_db(conn: sqlite3.Connection, symbol: str, desde_ms: int,
                hasta_ms: int) -> list[Vela]:
    return [Vela(t, o, h, l, c) for t, o, h, l, c in conn.execute(
        """SELECT open_time, o, h, l, c FROM klines
           WHERE symbol = ? AND tf = '1m' AND open_time >= ? AND open_time <= ?
           ORDER BY open_time""", (symbol, desde_ms, hasta_ms))]


def replay_desde_db(conn: sqlite3.Connection, plan: Plan, symbol: str,
                    ahora_ms: int, estado: Optional[Estado] = None) -> Estado:
    desde = plan.inicio_ms
    if estado is not None and estado.t_ultima is not None:
        desde = estado.t_ultima + 1
    velas = velas_de_db(conn, symbol, desde, min(ahora_ms, plan.fin_ms))
    return replay(plan, velas, ahora_ms, estado)
