"""
Los resultados, por poblacion, con su horizonte y su modelo de coste a la vista.

Por que por poblacion
---------------------
«¿Cuanto acierta el sistema?» no tiene una respuesta: tiene cuatro, y difieren
mucho. Sobre el universo entero son 1.989 planes al dia de 286 pares que se
repiten; sobre lo que llega a Telegram son 54; sobre lo que el usuario toma de
verdad son dos. Dar un solo numero obliga a elegir en silencio cual, y el que
siempre se elegia era el mas grande — el que mejor suena y menos significa.

Aqui la poblacion se elige explicitamente y **siempre viaja al lado del
numero**, junto con el horizonte y el coste supuesto. Un porcentaje sin esas
tres cosas no se puede comparar con otro.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from src.config.settings import get_settings
from src.presentacion.contrato import contrato_de_lectura

POBLACIONES = {
    "TODAS": ("todos los planes con identidad", None),
    "PRIMERA_EPISODIO": ("primera oportunidad de cada episodio",
                         "p.ordinal_episodio = 1"),
    "TELEGRAM": ("avisados por Telegram",
                 "EXISTS (SELECT 1 FROM alertas_emitidas a "
                 "WHERE a.id = p.legacy_alerta_id AND a.telegram = 'enviado')"),
    "DECISORIA": ("avisados por Telegram y primeros de su episodio",
                  "p.ordinal_episodio = 1 AND EXISTS (SELECT 1 FROM alertas_emitidas a "
                  "WHERE a.id = p.legacy_alerta_id AND a.telegram = 'enviado')"),
}


def resultados_por_poblacion(conn: sqlite3.Connection,
                             poblacion: str = "DECISORIA",
                             desde_ms: Optional[int] = None) -> dict:
    """
    Lo medido por el evaluador de la fase 2 sobre la poblacion que se pida.

    Solo ventanas COMPLETAS: una operacion abierta no es un empate ni una
    ganancia, y promediarla es como se fabrico el +0,25 % que se evaporo en
    septiembre. Las abiertas se cuentan aparte, a la vista.

    Y solo ventanas OBSERVADAS. `plan_recorrido` marca completa=1 cuando el
    reloj vence, sin mirar cuantas velas llego a ver, y las que faltan no se
    pierden al azar: una vela ausente borra la barrera que mas se toca, y la
    que mas se toca es la mas cercana — el stop. **Faltar datos fabrica
    objetivos.** Medido el 24-sep, la habilidad aparente cae de +26,67 pp
    (cobertura 0,75-0,90) a +2,49 pp (por encima de 0,99).

    Las mal observadas se cuentan aparte igual que las vencidas, por la misma
    razon: no son fallos, son mediciones que no existen.
    """
    s = get_settings()
    cobertura_min = s.presentacion_cobertura_minima
    etiqueta, cond = POBLACIONES.get(poblacion, POBLACIONES["DECISORIA"])
    where = ["1=1"]
    # Parametros CON NOMBRE, no posicionales: el suelo de cobertura aparece en
    # la clausula SELECT, o sea ANTES que el filtro de fecha en el texto del
    # SQL, y con `?` habria que acordarse de ese orden en cada cambio. Con
    # nombre no se puede equivocar.
    args: dict = {"cob": cobertura_min}
    if cond:
        where.append(f"({cond})")
    if desde_ms:
        where.append("p.ts_creado >= :desde")
        args["desde"] = desde_ms
    w = " AND ".join(where)

    def uno(sql):
        cur = conn.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # `obs` es "suficientemente observada". Va en cada agregado en vez de en el
    # WHERE para que las mal observadas se puedan CONTAR sin entrar en ninguna
    # media — desaparecerlas seria tan engañoso como promediarlas.
    obs = "r.cobertura IS NOT NULL AND r.cobertura >= :cob"
    resumen = uno(f"""
        SELECT COUNT(*) planes,
               SUM(r.completa = 1) completas,
               SUM(r.completa = 0) abiertas,
               SUM(r.completa = 1 AND NOT ({obs})) mal_observadas,
               SUM(r.desenlace = 'OBJETIVO' AND ({obs})) objetivo,
               SUM(r.desenlace = 'STOP' AND ({obs})) stop,
               SUM(r.desenlace = 'VENCIDO' AND ({obs})) vencido,
               ROUND(AVG(CASE WHEN r.completa = 1 AND ({obs})
                              THEN r.resultado_pct END), 4) media_pct,
               COUNT(DISTINCT p.symbol) pares
        FROM planes p JOIN plan_recorrido r ON r.plan_id = p.plan_id
        WHERE {w}""")[0]

    completas = resumen["completas"] or 0
    resueltas = (resumen["objetivo"] or 0) + (resumen["stop"] or 0)
    return {
        "poblacion": poblacion,
        "etiqueta": etiqueta,
        # Las CUATRO cosas sin las que un porcentaje no se puede comparar. La
        # cuarta se añadio el 24-sep: dos tasas medidas con distinto suelo de
        # cobertura no son comparables, y hasta ese dia el suelo era cero sin
        # que nada lo dijera.
        "horizonte_horas": s.signal_expiry_hours,
        "coste_pct": s.coste_operacion_pct,
        "cobertura_minima": cobertura_min,
        "contrato": contrato_de_lectura(),
        "planes": resumen["planes"],
        "pares": resumen["pares"],
        "completas": completas,
        "abiertas": resumen["abiertas"],
        "objetivo": resumen["objetivo"],
        "stop": resumen["stop"],
        "vencido": resumen["vencido"],
        # Ventana cerrada por reloj pero mal observada. No es un fallo ni un
        # acierto: es una medicion que no existe. Se cuenta a la vista en vez
        # de desaparecerse, igual que las vencidas.
        "mal_observadas": resumen["mal_observadas"],
        # La tasa se calcula sobre las que TIENEN desenlace de barrera, no
        # sobre el total: incluir las vencidas en el denominador de "acierto"
        # fue el fallo F14 de la auditoria del 10-sep.
        "acierto_pct": (round(100.0 * (resumen["objetivo"] or 0) / resueltas, 2)
                        if resueltas else None),
        "resueltas": resueltas,
        "media_pct": resumen["media_pct"],
        "nota": ("La tasa de acierto se mide sobre las que tocaron una barrera; "
                 "las vencidas por reloj se cuentan aparte porque no son "
                 "fallos. Las ventanas abiertas no entran en ninguna media. "
                 f"Y solo cuentan las observadas al {100*cobertura_min:.0f} % o "
                 "mas: donde faltan velas se pierde antes el stop que el "
                 "objetivo, asi que la falta de datos infla el acierto."),
    }


def todas_las_poblaciones(conn: sqlite3.Connection,
                          desde_ms: Optional[int] = None) -> dict:
    """
    Las cuatro a la vez. Verlas juntas es el punto: la diferencia entre ellas
    suele ser mayor que cualquier mejora que se discuta.
    """
    return {
        "poblaciones": [resultados_por_poblacion(conn, k, desde_ms)
                        for k in POBLACIONES],
        "aviso": ("Los cuatro numeros miden el mismo sistema sobre poblaciones "
                  "distintas. Compararlos entre si no dice que una regla sea "
                  "mejor: dice que no son la misma pregunta."),
    }
