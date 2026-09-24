"""
La cartera de verdad: 10 dolares, una moneda a la vez, reinvirtiendo todo.

Por que esto NO es sumar medias
-------------------------------
Una media por operacion contesta "¿cuanto deja una señal?". No contesta
"¿cuanto acaba teniendo el operador?", y con **una sola posicion a la vez** son
preguntas distintas por dos motivos:

1. **Tomar A significa no tomar B.** Mientras una operacion esta viva, todas
   las demas oportunidades pasan de largo. Con 1.989 planes al dia y una
   posicion, se toma el 0,05 % de lo que el sistema ve. Cual se toma importa
   mas que cuanto deja cada una — y eso es exactamente lo que una media por
   operacion borra.
2. **Reinvertir todo compone, y componer no es sumar.** Dos operaciones de
   +10 % y -10 % no dejan el capital igual: lo dejan en 99 %. El orden tambien
   cambia el resultado final, y una media no tiene orden.

El suelo del exchange
---------------------
Con 10 dolares esto deja de ser teorico. Binance exige un importe minimo por
orden (`MIN_NOTIONAL`, tipicamente 5 USDT en los pares USDT). Si una racha de
perdidas deja el capital por debajo, **no es que se gane menos: es que no se
puede operar**. La simulacion lo marca y se para, porque seguir contando
operaciones imposibles seria inventar un resultado.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from src.experimentos.informe import FILTROS_SQL, RESUELTOS
from src.experimentos.registro import huella

# Importe minimo por orden en los pares USDT de Binance. Es del exchange, no
# una preferencia: por debajo la orden se rechaza.
MIN_NOTIONAL_USDT = 5.0


@dataclass
class Escenario:
    """
    Las restricciones del operador. Son SUYAS; aqui solo se traducen a reglas.

    El caso declarado por Felix el 22-sep-2026: 10 USDT, todo en una moneda,
    reinvirtiendo ganancias y perdidas, hasta que el monto de para mas.
    """
    capital_inicial: float = 10.0
    posiciones_max: int = 1
    fraccion_por_posicion: float = 1.0      # 1.0 = todo el capital disponible
    min_notional: float = MIN_NOTIONAL_USDT
    filtro: Optional[str] = "DECISORIA"
    etiqueta: str = "10 USDT, una moneda a la vez, reinvirtiendo todo"

    def como_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class Operacion:
    plan_id: int
    symbol: str
    abre_ms: int
    cierra_ms: int
    invertido: float
    resultado_pct: float
    desenlace: str
    capital_despues: float


@dataclass
class Resultado:
    escenario: dict
    politica: str
    capital_inicial: float
    capital_final: float
    n_operaciones: int
    n_oportunidades: int
    n_descartadas_por_ocupado: int
    ganadoras: int
    racha_perdedora_max: int
    caida_maxima_pct: float
    parada_por_minimo: bool
    ts_parada: Optional[int] = None
    operaciones: list = field(default_factory=list)

    def como_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__
             if k != "operaciones"}
        d["retorno_pct"] = (round((self.capital_final / self.capital_inicial - 1) * 100, 2)
                            if self.capital_inicial else None)
        d["tasa_acierto_pct"] = (round(100.0 * self.ganadoras / self.n_operaciones, 1)
                                 if self.n_operaciones else None)
        d["ocupacion_pct"] = (round(100.0 * self.n_operaciones / self.n_oportunidades, 2)
                              if self.n_oportunidades else None)
        return d


class Cartera:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.db = conn

    def _oportunidades(self, politica: str, filtro: Optional[str]) -> list[dict]:
        """
        Las operaciones medibles, en orden cronologico estricto.

        El orden es el del mundo: se decide con lo que se sabia entonces. Una
        cartera que elige mirando el desenlace no es una cartera, es un deseo.
        """
        cond = FILTROS_SQL.get(filtro) if filtro else None
        sql = """SELECT e.plan_id, e.symbol, e.ts_creado, e.ms_fill, e.ms_desenlace,
                        e.desenlace, e.resultado_pct, p.horizonte_ms
                 FROM experimento_resultados e
                 JOIN planes p ON p.plan_id = e.plan_id
                 WHERE e.huella = ? AND e.politica = ?
                   AND e.desenlace IN ('OBJETIVO','STOP','VENCIDO')
                   AND e.resultado_pct IS NOT NULL"""
        if cond:
            sql += f" AND ({cond})"
        sql += " ORDER BY e.ts_creado, e.plan_id"
        cur = self.db.execute(sql, (huella(), politica))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def simular(self, politica: str = "REF",
                escenario: Optional[Escenario] = None) -> Resultado:
        esc = escenario or Escenario()
        opor = self._oportunidades(politica, esc.filtro)

        capital = esc.capital_inicial
        pico = capital
        caida_max = 0.0
        libres_ms = 0                 # cuando se libera la posicion
        ops: list[Operacion] = []
        descartadas = 0
        racha = racha_max = 0
        ganadoras = 0
        parada = False
        ts_parada = None

        for o in opor:
            abre = o["ts_creado"] + (o["ms_fill"] or 0)
            if abre < libres_ms:
                descartadas += 1
                continue

            invertido = capital * esc.fraccion_por_posicion
            if invertido < esc.min_notional:
                # No es que se gane menos: es que la orden se rechaza.
                parada, ts_parada = True, abre
                break

            resultado = o["resultado_pct"]
            capital = capital * (1.0 + resultado / 100.0)
            cierra = o["ts_creado"] + (o["ms_desenlace"] or o["horizonte_ms"] or 0)
            libres_ms = cierra

            if resultado > 0:
                ganadoras += 1
                racha = 0
            else:
                racha += 1
                racha_max = max(racha_max, racha)

            pico = max(pico, capital)
            if pico > 0:
                caida_max = max(caida_max, (pico - capital) / pico * 100.0)

            ops.append(Operacion(
                plan_id=o["plan_id"], symbol=o["symbol"], abre_ms=abre,
                cierra_ms=cierra, invertido=round(invertido, 4),
                resultado_pct=resultado, desenlace=o["desenlace"],
                capital_despues=round(capital, 4)))

        return Resultado(
            escenario=esc.como_dict(), politica=politica,
            capital_inicial=esc.capital_inicial,
            capital_final=round(capital, 4),
            n_operaciones=len(ops), n_oportunidades=len(opor),
            n_descartadas_por_ocupado=descartadas, ganadoras=ganadoras,
            racha_perdedora_max=racha_max, caida_maxima_pct=round(caida_max, 2),
            parada_por_minimo=parada, ts_parada=ts_parada, operaciones=ops)

    def comparar(self, politicas=None, escenario: Optional[Escenario] = None) -> dict:
        """
        Todas las politicas bajo el MISMO escenario y el mismo orden temporal.

        Es la unica comparacion que contesta la pregunta del operador, porque
        todas compiten por la misma posicion unica.
        """
        from src.experimentos.registro import POLITICAS
        claves = politicas or [p.clave for p in POLITICAS]
        esc = escenario or Escenario()
        filas = [self.simular(c, esc).como_dict() for c in claves]
        filas.sort(key=lambda f: -(f["capital_final"] or 0))
        return {"escenario": esc.como_dict(), "huella": huella(),
                "resultados": filas,
                "aviso": ("con una sola posicion a la vez, lo que decide no es "
                          "cuanto deja cada señal sino cual se toma: se opera "
                          "una fraccion minima de lo que el sistema ve")}
