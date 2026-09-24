"""
La regla que elige al rival, congelada antes de que exista un veredicto.

Por que no basta con el veredicto de la fase 5
----------------------------------------------
Las tres puertas de la fase 5 son ABSOLUTAS: dinero por encima del
deslizamiento y habilidad por encima de la base geometrica. Una politica puede
pasarlas **siendo peor que la referencia** — le basta con ganar algo y acertar
mas de lo que la geometria predice. Activar eso seria un retroceso presentado
como mejora.

El propio plan lo pide en su §8: "Comparacion pareada frente a la politica
vigente, no unicamente frente a una salida inferior". La fase 5 calcula ese
pareado y lo reporta, pero no lo mete en su veredicto. No se toca su registro
congelado —cambiarlo invalidaria la prueba en curso— asi que la condicion se
añade AQUI, como requisito adicional de activacion. Es mas estricto, no menos,
y queda escrito antes de ver quien gana.

En resumen, para ser rival hay que:

  1. pasar las tres puertas de la fase 5 sobre la poblacion decisoria,
  2. batir a la referencia en la comparacion PAREADA sobre los mismos planes, y
  3. sostener esa ventaja en las DOS MITADES temporales de la muestra.

La tercera es la defensa contra coronar a una ganadora por azar: se examinan
hasta diez politicas y quedarse con el maximo de diez estimaciones infla por
construccion. Partir la muestra es lo que ya tumbo aqui a "la primera señal es
la buena" y a la regla C3 del hoyo.

Y una honestidad sobre el origen: estas reglas se fijaron el 23-sep, DESPUES de
haber visto un resultado parcial del universo entero y ANTES de cualquier
veredicto sobre la poblacion decisoria. Es "fijado antes del veredicto", no
"ajeno a todo resultado", y asi hay que describirlo.
"""
from __future__ import annotations

from typing import Optional

from src.experimentos.registro import (
    EJE_ENTRADA,
    EJE_SALIDA,
    EJE_STOP,
    POR_CLAVE,
)

APROBADA = "APROBADA"

# Margen por debajo del cual dos candidatas se consideran empatadas. Es
# arbitrario y se declara como tal: 0,10 puntos sobre un limite inferior que se
# mide en decimas es ruido de estimacion, no una diferencia.
EMPATE_PP = 0.10

# El orden de preferencia para deshacer un empate. NO mira resultados: sale de
# las prioridades del propio plan, escritas el 22-sep antes de que existiera
# ningun dato de la fase 5. Su prioridad 1 es "evaluar +4,2 % netos frente a
# objetivos menores y al TP variable actual" — la salida. Despues la entrada,
# despues el stop.
ORDEN_EJES = (EJE_SALIDA, EJE_ENTRADA, EJE_STOP)


def _desviacion(clave: str) -> float:
    """
    Cuanto se aparta una politica de la referencia, para el segundo desempate.

    Entre dos empatadas del mismo eje se prefiere la que mueve menos: es el
    cambio mas pequeño que consigue la mejora, y el mas facil de revertir.
    """
    p = POR_CLAVE.get(clave)
    if p is None:
        return 99.0
    for campo in ("objetivo_neto_pct", "descuento_pct", "stop_pct"):
        v = getattr(p, campo, None)
        if v is not None:
            return abs(float(v))
    if p.stop_multiplo is not None:
        return abs(float(p.stop_multiplo) - 1.0)
    return 99.0


def estabilidad_temporal(db, politica: str, huella_f5: str,
                         filtro_sql: str) -> dict:
    """
    ¿La ventaja pareada sobre la referencia aguanta al partir la muestra?

    Se miran hasta diez politicas y se corona a la del mayor limite inferior.
    Quedarse con el maximo de diez estimaciones infla por construccion, y con
    n=50 por celda eso no es teorico. La defensa no es un apaño de umbral: es
    la que este proyecto ya usa desde el 22-sep —partir por la mitad y exigir
    que aguante—, la misma que tumbo a "la primera señal es la buena" y a la
    regla C3 del hoyo.

    No toca el codigo congelado de la fase 5: lee su tabla de resultados.
    """
    filas = db.execute(
        f"""SELECT m.ts_creado, m.resultado_pct - r.resultado_pct AS dif
            FROM experimento_resultados m
            JOIN experimento_resultados r
              ON r.plan_id = m.plan_id AND r.huella = m.huella AND r.politica = 'REF'
            JOIN planes p ON p.plan_id = m.plan_id
            LEFT JOIN alertas_emitidas a ON a.id = p.legacy_alerta_id
            WHERE m.huella = ? AND m.politica = ?
              AND m.desenlace IN ('OBJETIVO','STOP')
              AND r.desenlace IN ('OBJETIVO','STOP')
              AND m.resultado_pct IS NOT NULL AND r.resultado_pct IS NOT NULL
              AND ({filtro_sql})
            ORDER BY m.ts_creado""",
        (huella_f5, politica)).fetchall()
    n = len(filas)
    if n < 4:
        return {"estable": False, "n": n,
                "por_que": f"hacen falta al menos 4 pares medibles y hay {n}"}
    corte = n // 2
    primera = [f[1] for f in filas[:corte]]
    segunda = [f[1] for f in filas[corte:]]
    m1 = sum(primera) / len(primera)
    m2 = sum(segunda) / len(segunda)
    estable = m1 > 0 and m2 > 0
    return {"estable": estable, "n": n,
            "primera_mitad": round(m1, 4), "segunda_mitad": round(m2, 4),
            "por_que": ("la ventaja aguanta en las dos mitades"
                        if estable else
                        f"no aguanta el corte: {m1:+.2f} y {m2:+.2f}")}


def _candidatas(informe: dict) -> list[dict]:
    """Las que pasan las tres puertas Y baten a la referencia en pareado."""
    fuera = []
    for p in informe.get("politicas", []):
        if p.get("exploracion") or p.get("politica") == "REF":
            continue
        if p.get("veredicto") != APROBADA:
            continue
        pareado = p.get("pareado_vs_ref") or {}
        ic = pareado.get("ic_bajo")
        if ic is None or ic <= 0:
            # Pasa sus puertas absolutas pero no se demuestra mejor que lo que
            # ya hay. No es candidata.
            continue
        fuera.append(p)
    return fuera


def elegir_rival(informe: dict, estabilidad: Optional[dict] = None) -> dict:
    """
    Aplica la regla congelada al informe de la fase 5.

    `estabilidad` es {politica: resultado de estabilidad_temporal}. Si se
    omite, la comprobacion del corte por mitades NO se hace y el resultado
    lleva `provisional: True` — porque una eleccion sin ese corte no cumple la
    regla congelada entera y no debe poder presentarse como si la cumpliera.

    Devuelve siempre un dict con `rival` (clave o None) y `por_que` en
    castellano llano. No hay excepciones: "no hay rival" es un resultado.
    """
    prov = estabilidad is None
    cands = _candidatas(informe)
    if estabilidad is not None:
        caidas = [p["politica"] for p in cands
                  if not (estabilidad.get(p["politica"]) or {}).get("estable")]
        cands = [p for p in cands if p["politica"] not in caidas]
        if caidas and not cands:
            return {"rival": None, "candidatas": [], "provisional": False,
                    "por_que": ("baten a la referencia en el agregado ("
                                + ", ".join(caidas)
                                + ") pero ninguna aguanta el corte por mitades")}
    if not cands:
        aprobadas = [p["politica"] for p in informe.get("politicas", [])
                     if p.get("veredicto") == APROBADA and not p.get("exploracion")]
        if aprobadas:
            return {"rival": None, "candidatas": [], "provisional": prov,
                    "por_que": ("pasan sus puertas absolutas ("
                                + ", ".join(aprobadas) +
                                ") pero ninguna se demuestra mejor que la "
                                "referencia en la comparacion pareada")}
        return {"rival": None, "candidatas": [], "provisional": prov,
                "por_que": "ninguna politica pasa las tres puertas"}

    def limite(p):
        return p["dinero"]["ic_bajo"]

    cands.sort(key=lambda p: -limite(p))
    mejor = cands[0]
    empatadas = [p for p in cands if limite(p) >= limite(mejor) - EMPATE_PP]

    if len(empatadas) == 1:
        return {"rival": mejor["politica"], "provisional": prov,
                "candidatas": [p["politica"] for p in cands],
                "por_que": (f"mayor limite inferior del dinero "
                            f"({limite(mejor):+.2f} %) y bate a la referencia "
                            f"en pareado ({mejor['pareado_vs_ref']['ic_bajo']:+.2f} pp)")}

    # Empate: se deshace por estructura, nunca por resultado.
    def orden(p):
        pol = POR_CLAVE.get(p["politica"])
        eje = pol.eje if pol else ""
        i = ORDEN_EJES.index(eje) if eje in ORDEN_EJES else len(ORDEN_EJES)
        return (i, _desviacion(p["politica"]), p["politica"])

    empatadas.sort(key=orden)
    ganadora = empatadas[0]
    claves = ", ".join(p["politica"] for p in empatadas)
    return {
        "rival": ganadora["politica"],
        "provisional": prov,
        "candidatas": [p["politica"] for p in cands],
        "por_que": (f"empatan dentro de {EMPATE_PP} pp ({claves}); se deshace "
                    f"por el orden de ejes del plan (salida, entrada, stop) y "
                    f"luego por el cambio mas pequeño: {ganadora['politica']}"),
    }


def puede_activarse(informe: dict, n_minimo: int = 50,
                    estabilidad: Optional[dict] = None) -> dict:
    """
    Las puertas 1 y 2 de la fase 7a. Las otras dos —revision del operador e
    integridad— no se pueden comprobar desde aqui y se exigen aparte.

    La n no se vuelve a comprobar: una politica con menos de `n_minimo`
    medibles sale INCONCLUSO de la fase 5 y nunca llega a candidata. Se
    reporta igualmente porque "cuanto falta" es la pregunta que se hace todos
    los dias mientras la prueba corre.
    """
    ref = informe.get("referencia") or {}
    n = int(ref.get("medibles") or 0)
    sel = elegir_rival(informe, estabilidad)
    # Una eleccion sin el corte por mitades NO autoriza: cumple dos de las tres
    # condiciones congeladas y presentarla como lista seria saltarse la
    # tercera, que es justo la que protege del azar.
    listo = sel["rival"] is not None and not sel.get("provisional")
    return {
        "listo": listo,
        "rival": sel["rival"] if listo else None,
        "candidatas": sel["candidatas"],
        "provisional": bool(sel.get("provisional")),
        "medibles_referencia": n,
        "faltan": max(0, n_minimo - n),
        "por_que": (sel["por_que"] if not sel.get("provisional")
                    else sel["por_que"] + "; falta el corte por mitades"),
    }


def rival_declarado(informe: dict) -> Optional[str]:
    return elegir_rival(informe)["rival"]
