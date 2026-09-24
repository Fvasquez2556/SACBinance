"""
El informe que decide. Aplica las puertas congeladas; no las inventa.

Una revision externa señalo, con razon, que tener las puertas en un diccionario
no significa haberlas verificado: el modulo guardaba medias y conteos, y la
lectura estadistica declarada —poblacion decisoria, comparacion pareada contra
la referencia, intervalos agrupados por par, puerta de habilidad— no existia en
ninguna parte. Esto es esa lectura.

Tres cosas que este modulo hace y que un promedio no hace
---------------------------------------------------------
1. **Compara pareado contra la referencia.** La misma oportunidad bajo las dos
   politicas. Dos medias independientes no contestan "¿es mejor?" cuando las
   dos miran los mismos dias: comparten el mercado, y el mercado es casi toda
   la varianza.
2. **Agrupa el bootstrap por par.** El 84 % de las señales nace con otra del
   mismo par aun viva. Remuestrear operaciones en vez de pares fabrica
   intervalos estrechos que no significan nada.
3. **Devuelve INCONCLUSO.** Con menos de `n_minimo` observaciones no hay
   veredicto, y decirlo es el resultado. Un "no alcanza" honesto vale mas que
   un porcentaje con dos decimales que se evapora la semana siguiente.
"""
from __future__ import annotations

import math
import random
import sqlite3
from typing import Optional

from src.experimentos.registro import (
    POBLACION_DECISORIA,
    POLITICAS,
    POR_CLAVE,
    PUERTAS,
    huella,
)

APROBADA = "APROBADA"
RECHAZADA = "RECHAZADA"
INCONCLUSO = "INCONCLUSO"

# Desenlaces que representan una operacion con resultado medible.
RESUELTOS = ("OBJETIVO", "STOP", "VENCIDO")

# Los subconjuntos del eje D, como SQL sobre `planes` y sus enlaces.
FILTROS_SQL = {
    # El hallazgo de la fase 4: el ancla de 1h con ruptura alcista al crearse.
    # Viene de la lectura del motor que se guardo con esa misma alerta.
    "D1": """EXISTS (SELECT 1 FROM motor_lecturas m
                     WHERE m.alerta_id = p.legacy_alerta_id
                       AND m.motor = 'continuacion'
                       AND json_extract(m.datos, '$.ancla_direccion') = 'RUPTURA_ALCISTA')""",
    "D2": "p.ordinal_episodio = 1",
    "D3": """EXISTS (SELECT 1 FROM alertas_emitidas a
                     WHERE a.id = p.legacy_alerta_id AND a.telegram = 'enviado')""",
}
FILTROS_SQL["DECISORIA"] = f"({FILTROS_SQL['D2']}) AND ({FILTROS_SQL['D3']})"


def base_geometrica(entrada: float, objetivo: float, stop: float) -> Optional[float]:
    """
    P(+A antes que -B) = B/(A+B) bajo deriva cero.

    Es la tasa que sale por pura geometria. Sin restarla, un porcentaje de
    aciertos alto solo dice que el stop es ancho.
    """
    if not (entrada and objetivo and stop) or not (0 < stop < entrada < objetivo):
        return None
    a = (objetivo - entrada) / entrada
    b = (entrada - stop) / entrada
    return b / (a + b) if (a + b) > 0 else None


def _bootstrap_por_par(pares: dict, n: int = 2000, semilla: int = 20260922) -> dict:
    """
    Remuestrea PARES, no operaciones, y devuelve media e intervalo del 95 %.

    `pares` es {symbol: [valores]}. Un par entra entero o no entra: es lo que
    respeta que sus operaciones esten correlacionadas entre si.
    """
    claves = [k for k, v in pares.items() if v]
    if not claves:
        return {"media": None, "ic_bajo": None, "ic_alto": None, "n": 0, "pares": 0}
    todos = [x for k in claves for x in pares[k]]
    media = sum(todos) / len(todos)
    rnd = random.Random(semilla)
    medias = []
    for _ in range(n):
        muestra = []
        for _ in range(len(claves)):
            muestra.extend(pares[claves[rnd.randrange(len(claves))]])
        if muestra:
            medias.append(sum(muestra) / len(muestra))
    medias.sort()
    q = lambda p: medias[int(p * (len(medias) - 1))] if medias else None
    return {"media": round(media, 4), "ic_bajo": round(q(0.025), 4),
            "ic_alto": round(q(0.975), 4), "n": len(todos), "pares": len(claves)}


class Informe:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.db = conn

    def _filas(self, sql: str, args=()) -> list[dict]:
        cur = self.db.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # --- Poblaciones --------------------------------------------------------

    def poblacion(self, filtro: Optional[str] = None) -> list[int]:
        """Los plan_id que entran en una lectura. `None` = todos los medidos."""
        cond = FILTROS_SQL.get(filtro) if filtro else None
        sql = """SELECT DISTINCT e.plan_id FROM experimento_resultados e
                 JOIN planes p ON p.plan_id = e.plan_id
                 WHERE e.huella = ?"""
        if cond:
            sql += f" AND ({cond})"
        return [r["plan_id"] for r in self._filas(sql, (huella(),))]

    def _resultados(self, politica: str, filtro: Optional[str]) -> dict:
        cond = FILTROS_SQL.get(filtro) if filtro else None
        sql = """SELECT e.plan_id, e.symbol, e.desenlace, e.resultado_pct,
                        e.entrada, e.objetivo, e.stop
                 FROM experimento_resultados e
                 JOIN planes p ON p.plan_id = e.plan_id
                 WHERE e.huella = ? AND e.politica = ?"""
        if cond:
            sql += f" AND ({cond})"
        return {f["plan_id"]: f for f in self._filas(sql, (huella(), politica))}

    # --- Las puertas --------------------------------------------------------

    def evaluar_politica(self, politica: str,
                         filtro: Optional[str] = "DECISORIA") -> dict:
        """
        Las tres puertas sobre una politica, en la poblacion que se pida.

        Devuelve el veredicto y TODO lo que hace falta para discutirlo: la n,
        cuantos pares distintos, la tasa de ejecucion y las dos puertas por
        separado. Nunca devuelve solo un numero.
        """
        pol = POR_CLAVE.get(politica)
        mios = self._resultados(politica, filtro)
        ref = self._resultados("REF", filtro)
        minimo = PUERTAS["n_minimo"]
        umbral = PUERTAS["dinero_limite_inferior_pct"]

        elegibles = len(mios)
        llenadas = sum(1 for f in mios.values()
                       if f["desenlace"] not in ("NO_LLENADO", "SIN_DATOS", None))
        medibles = {k: f for k, f in mios.items() if f["desenlace"] in RESUELTOS
                    and f["resultado_pct"] is not None}

        # --- Puerta 1: dinero, en absoluto y pareado contra la referencia ---
        por_par, por_par_dif = {}, {}
        for k, f in medibles.items():
            por_par.setdefault(f["symbol"], []).append(f["resultado_pct"])
            r = ref.get(k)
            if r and r["desenlace"] in RESUELTOS and r["resultado_pct"] is not None:
                por_par_dif.setdefault(f["symbol"], []).append(
                    f["resultado_pct"] - r["resultado_pct"])
        absoluto = _bootstrap_por_par(por_par)
        pareado = _bootstrap_por_par(por_par_dif)

        # --- Puerta 2: habilidad sobre la base geometrica ---
        por_par_hab = {}
        for k, f in medibles.items():
            base = base_geometrica(f["entrada"], f["objetivo"], f["stop"])
            if base is None:
                continue
            acierto = 1.0 if f["desenlace"] == "OBJETIVO" else 0.0
            por_par_hab.setdefault(f["symbol"], []).append((acierto - base) * 100.0)
        habilidad = _bootstrap_por_par(por_par_hab)

        def veredicto(res, umbral_):
            if res["n"] < minimo:
                return INCONCLUSO
            if res["ic_bajo"] is None:
                return INCONCLUSO
            return APROBADA if res["ic_bajo"] > umbral_ else RECHAZADA

        v_dinero = veredicto(absoluto, umbral)
        v_habilidad = veredicto(habilidad, PUERTAS["habilidad_min_puntos"])
        if INCONCLUSO in (v_dinero, v_habilidad):
            final = INCONCLUSO
        elif v_dinero == APROBADA and v_habilidad == APROBADA:
            final = APROBADA
        else:
            final = RECHAZADA

        return {
            "politica": politica,
            "descripcion": pol.descripcion if pol else None,
            "exploracion": bool(pol and pol.exploracion),
            "filtro": filtro or "TODAS",
            "elegibles": elegibles,
            "llenadas": llenadas,
            "tasa_ejecucion": (round(100.0 * llenadas / elegibles, 2)
                               if elegibles else None),
            "medibles": len(medibles),
            "n_minimo": minimo,
            "dinero": {**absoluto, "umbral": umbral, "veredicto": v_dinero},
            "pareado_vs_ref": pareado,
            "habilidad": {**habilidad, "umbral": PUERTAS["habilidad_min_puntos"],
                          "veredicto": v_habilidad},
            "veredicto": final,
            "por_que": self._por_que(final, absoluto, habilidad, minimo),
        }

    @staticmethod
    def _por_que(final, dinero, habilidad, minimo) -> str:
        if final == INCONCLUSO:
            falta = max(0, minimo - min(dinero["n"], habilidad["n"]))
            return (f"sin veredicto: hacen falta {minimo} operaciones medibles y "
                    f"hay {min(dinero['n'], habilidad['n'])}"
                    + (f"; faltan {falta}" if falta else ""))
        if final == APROBADA:
            return (f"gana dinero por encima del deslizamiento "
                    f"({dinero['ic_bajo']:+.2f} % en el peor caso del intervalo) "
                    f"y bate a su base geometrica ({habilidad['ic_bajo']:+.2f} pp)")
        partes = []
        if dinero["ic_bajo"] is not None and dinero["ic_bajo"] <= PUERTAS["dinero_limite_inferior_pct"]:
            partes.append(f"el limite inferior del dinero es {dinero['ic_bajo']:+.2f} %, "
                          f"no supera {PUERTAS['dinero_limite_inferior_pct']}")
        if habilidad["ic_bajo"] is not None and habilidad["ic_bajo"] <= 0:
            partes.append(f"la habilidad no se separa de su base geometrica "
                          f"({habilidad['ic_bajo']:+.2f} pp)")
        return "; ".join(partes) or "no pasa alguna puerta"

    # --- El informe entero --------------------------------------------------

    def completo(self, filtro: Optional[str] = "DECISORIA") -> dict:
        politicas = [self.evaluar_politica(p.clave, filtro)
                     for p in POLITICAS if p.clave != "REF"]
        referencia = self.evaluar_politica("REF", filtro)
        aprobadas = [p["politica"] for p in politicas
                     if p["veredicto"] == APROBADA and not p["exploracion"]]
        return {
            "huella": huella(),
            "poblacion": POBLACION_DECISORIA if filtro == "DECISORIA" else (filtro or "TODAS"),
            "puertas": dict(PUERTAS),
            "referencia": referencia,
            "politicas": politicas,
            "aprobadas": aprobadas,
            "conclusion": (
                "ninguna politica pasa las tres puertas todavia"
                if not aprobadas else
                "pasan las tres puertas: " + ", ".join(aprobadas)),
        }

    def por_subconjunto(self, politica: str = "REF") -> list[dict]:
        """La misma politica leida en cada subconjunto del eje D."""
        return [self.evaluar_politica(politica, f)
                for f in (None, "D1", "D2", "D3", "DECISORIA")]
