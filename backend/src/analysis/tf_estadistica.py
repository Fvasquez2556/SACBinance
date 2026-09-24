"""
Lo que de verdad pasó cuando este sistema vio una ruptura como esta.

El informe por marcos describía estructura sin ningún número detrás — su propio
docstring lo decía. Mientras tanto `rupturas_tf` llevaba **49.648 rupturas por
marco registradas con su desenlace**, incluidas las que nadie miró. Este modulo
las lee y devuelve la tasa base para cada celda del informe.

Que se mide, y por que asi
--------------------------
`tp_antes_sl` es el porcentaje que toco el TP de su plan antes que el stop,
**entre las que llegaron a llenar la entrada**. Esa condicion importa y se
publica al lado: con ATR alto solo llena el 30 %, y una tasa calculada sobre
los que entraron no dice nada de los que no.

`horas_mediana` y `pct_dentro_horizonte` existen porque el sistema es
intradia. Medido: el TP de una ruptura de 5m llega en 5,05 h de mediana y el
82,5 % cabe en 12 h; el de 1h tarda 10,08 h y solo cabe el 58,1 %. Ofrecer un
plan de 4h a quien cierra el mismo dia es ofrecerle otra cosa.

Reglas de la cifra (las mismas de la adenda del plan)
-----------------------------------------------------
- Cada celda lleva su `n` y su ventana. Sin eso, un porcentaje es un adorno.
- Por debajo de `min_n` se devuelve `fiable=False` y la pantalla dice «sin
  estimacion fiable». No se rellena con una celda mas ancha en silencio.
- La ventana es movil y reciente: la tasa base de este sistema se movio 15
  puntos en una semana, asi que una calibracion vieja es desinformacion.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Optional

DIRECCIONES = ("RUPTURA_ALCISTA", "RUPTURA_BAJISTA")


def _mediana(valores: list[float]) -> Optional[float]:
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[len(ordenados) // 2]


def _celda(n: int, rellenadas: int, aciertos: int, horas: list[float],
           horizonte_h: float, min_n: int) -> dict:
    fiable = n >= min_n and rellenadas > 0
    return {
        "n": n,
        "rellenadas": rellenadas,
        "pct_fill": round(100.0 * rellenadas / n, 1) if n else None,
        "tp_antes_sl": (round(100.0 * aciertos / rellenadas, 1)
                        if fiable and rellenadas else None),
        "horas_mediana": (round(_mediana(horas), 2) if fiable and horas else None),
        "pct_dentro_horizonte": (round(100.0 * sum(1 for h in horas if h <= horizonte_h)
                                       / len(horas), 1) if fiable and horas else None),
        "fiable": bool(fiable),
    }


class EstadisticaRupturas:
    """Tasas base por marco, por confluencia y por contexto. Solo lectura."""

    def __init__(self, conn: sqlite3.Connection, *, ventana_dias: int = 14,
                 min_n: int = 50, horizonte_ms: int = 12 * 3600_000) -> None:
        self.db = conn
        self.ventana_dias = ventana_dias
        self.min_n = min_n
        self.horizonte_h = horizonte_ms / 3600_000.0

    def _filas(self, agrupar: str, desde_ms: int) -> dict:
        """Una pasada por celda: cuentas y tiempos hasta el TP."""
        cuentas = {}
        for clave, direccion, n, rellenadas, aciertos in self.db.execute(
                f"""SELECT {agrupar}, direction, COUNT(*),
                           SUM(ms_fill IS NOT NULL),
                           SUM(ms_tp IS NOT NULL AND (ms_sl IS NULL OR ms_tp < ms_sl))
                    FROM rupturas_tf
                    WHERE closed = 1 AND ts_open >= ?
                    GROUP BY {agrupar}, direction""", (desde_ms,)):
            cuentas[(clave, direccion)] = [int(n or 0), int(rellenadas or 0), int(aciertos or 0), []]
        for clave, direccion, ms_tp in self.db.execute(
                f"""SELECT {agrupar}, direction, ms_tp FROM rupturas_tf
                    WHERE closed = 1 AND ts_open >= ? AND ms_tp IS NOT NULL""", (desde_ms,)):
            fila = cuentas.get((clave, direccion))
            if fila is not None:
                fila[3].append(ms_tp / 3600_000.0)
        return {clave: _celda(*valores, self.horizonte_h, self.min_n)
                for clave, valores in cuentas.items()}

    def instantanea(self) -> dict:
        """
        Todo lo que el informe necesita, en una lectura.

        Se calcula aparte del informe a proposito: `construir_informe` es una
        funcion pura y tiene que seguir siendolo, asi que recibe esto ya hecho.
        """
        desde = int(time.time() * 1000) - self.ventana_dias * 86_400_000
        try:
            por_marco = self._filas("tf", desde)
            por_confluencia = self._filas("conf_confirmadas", desde)
            por_conflicto = self._filas("conf_en_conflicto", desde)
            por_estorbo = self._filas("tp_bloqueado", desde)
        except sqlite3.Error:
            # Una base sin `rupturas_tf` no es un error: el informe se enseña
            # como antes, sin cifras, en vez de caerse.
            return {}
        return {
            "ventana_dias": self.ventana_dias,
            "min_n": self.min_n,
            "horizonte_h": round(self.horizonte_h, 1),
            "por_marco": {f"{tf}|{d}": c for (tf, d), c in por_marco.items()},
            "por_confluencia": {f"{int(k)}|{d}": c for (k, d), c in por_confluencia.items()
                                if k is not None},
            "por_conflicto": {f"{int(k)}|{d}": c for (k, d), c in por_conflicto.items()
                              if k is not None},
            "por_estorbo": {f"{int(k)}|{d}": c for (k, d), c in por_estorbo.items()
                            if k is not None},
        }


def celda(instantanea: dict, grupo: str, clave, direccion: str) -> Optional[dict]:
    """Busca una celda sin inventar otra si falta: devuelve None y ya."""
    if not instantanea:
        return None
    return (instantanea.get(grupo) or {}).get(f"{clave}|{direccion}")
