"""
Las reglas de activacion y reversion de la fase 7, congeladas antes del veredicto.

Por que existe este fichero hoy y no el 17-oct
----------------------------------------------
La fase 7 del plan exige una fraccion "definida antes de ver sus resultados".
El 23-sep ya se vio un resultado parcial del universo entero de la fase 5. Cada
dia que estas reglas siguieran sin escribirse, la eleccion quedaria mas teñida
por lo que uno va viendo pasar — y no habria forma de demostrar lo contrario.

Aqui NO se activa nada. Lo unico que existe es el candado:

  - quien PUEDE ser el rival (la regla, nunca el nombre)
  - en que proporcion se reparte, y por que esa y no otra
  - cuando se puede empezar (cuatro puertas simultaneas)
  - cuando hay que parar, y por que no se para al ir ganando
  - que significa parar: un interruptor, no restaurar una copia

Igual que en la fase 5, la declaracion entera se reduce a una huella de
contenido. Cambiar una linea cambia la huella y abre otra version, en vez de
reescribir el pasado en silencio.

El registro documentado esta en
`audit/2026-09-22/plan-evolucion-motores/fase7/ACTIVACION_CONGELADA.md`.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

REGISTRO_VERSION = "fase7a-v2"

# Huella del documento aprobado. Entra en la huella de contenido: si el .md
# cambia y esta constante no, una prueba lo dice por su nombre.
DOCUMENTO = "fase7/ACTIVACION_CONGELADA.md"
DOCUMENTO_SHA256 = "2859611ffbd70e0df3c87be30b104265142888d845412ed01af56a990af9bf95"

# --- Los brazos ---------------------------------------------------------------
BRAZO_REFERENCIA = "REFERENCIA"
BRAZO_RIVAL = "RIVAL"
BRAZOS = (BRAZO_REFERENCIA, BRAZO_RIVAL)

# =============================================================================
#  La declaracion congelada. NO SE MODIFICA.
# =============================================================================

# --- Quien puede ser el rival: la regla, no el nombre ------------------------
#
# Nombrar al rival hoy seria prejuzgar la fase 5. Lo que se congela es como se
# elige, para que no se pueda reescribir despues a favor de quien vaya ganando.
SELECCION_DEL_RIVAL = (
    "la politica de la fase 5, distinta de REF y no marcada como exploracion, "
    "que (a) pase las tres puertas sobre la poblacion decisoria, (b) bata a la "
    "referencia en la comparacion PAREADA sobre los mismos planes con el "
    "limite inferior por encima de cero, y (c) mantenga esa ventaja pareada en "
    "las DOS MITADES temporales de la poblacion; de las que cumplan las tres, "
    "la de mayor limite inferior del dinero"
)

# El riesgo de coronar a una ganadora por azar. Se miran hasta diez politicas;
# quedarse con el maximo de diez limites inferiores infla por construccion.
# La defensa no es un apaño de umbral: es la misma que este proyecto ya usa
# desde el 22-sep —partir la muestra por la mitad y exigir que aguante—, que
# es lo que tumbo a "la primera señal es la buena" y a la regla C3.
RIESGO_DE_SELECCION = (
    "se examinan varias politicas y quedarse con la mejor infla el resultado; "
    "por eso la ganadora tiene que sostener su ventaja pareada en las dos "
    "mitades temporales, no solo en el agregado"
)
# Las tres formas de que no haya rival. Todas son resultados, no fracasos.
SIN_RIVAL = (
    "ninguna politica pasa las tres puertas",
    "ninguna bate a la referencia en pareado: pasar puertas absolutas no basta",
    "la ganadora no aguanta el corte por mitades",
    "la ganadora es REF: no hay nada que cambiar",
)

# Que pasa si dos quedan dentro del margen de empate. NO se bloquea la
# activacion —dos que baten a la referencia son las dos una mejora, y
# paralizarse ante el exito es tan arbitrario como perseguirlo—, pero el
# desempate NO puede mirar los numeros, porque ahi es donde entra el azar.
# Se deshace por ESTRUCTURA: el orden de ejes que el plan fijo el 22-sep
# (salida, entrada, stop) y, dentro del eje, el cambio mas pequeño.
DESEMPATE = (
    "por el orden de ejes del plan (salida, entrada, stop) y luego por la "
    "menor desviacion respecto a la referencia; nunca por el resultado"
)

# --- La fraccion -------------------------------------------------------------
#
# 25 %. La v1 puso 50 % apoyandose en "~2 planes decisorios al dia", y ese 2
# era EL ATASCO DE LA HAMBRUNA DEL EVALUADOR leido como tasa de llegada. Medido
# con el atasco drenado: 17,6 planes decisorios creados al dia y ~10,5
# medibles. Con eso, el brazo rival llega a n=50 en ~19 dias al 25 %.
#
# Y la fraccion SI acota exposicion —la v1 lo negaba y era un error—: al 25 %,
# una de cada cuatro señales del operador lleva el TP del rival en vez de la
# mitad. El cortacircuitos complementa ese limite, no lo sustituye.
#
# La justificacion completa, con la tabla de las tres fracciones, esta en el
# §3 del documento.
FRACCION_RIVAL = 0.25

ASIGNACION = (
    "por episodio, determinista: los primeros 8 bytes de "
    "sha256('<huella>:<episode_id>'), escalados a [0,1), caen por debajo de "
    "FRACCION_RIVAL -> RIVAL. Se escribe una vez y no se recalcula; si el "
    "episodio ya tiene brazo, ese gana aunque cambie la huella"
)

# --- Las cuatro puertas de entrada a la fase 7b ------------------------------
PUERTAS_ACTIVACION = {
    "fase5_tres_puertas": "pasan sobre la poblacion decisoria",
    "fase5_n_minimo": 50,
    "rival_existe": "por la regla de SELECCION_DEL_RIVAL",
    "revisado_por_el_operador": "explicito, nunca automatico",
    "integridad": ("sin colisiones de asignacion, sin modificaciones "
                   "retroactivas de niveles, ningun plan emitido sin brazo"),
}

# --- Reversion: asimetrica a proposito ---------------------------------------
#
# Parar ante el daño protege el dinero. Parar ante el exito es elegir el
# momento que mas favorece — que es como se fabrico el +0,25 % de la regla C3
# que se evaporo con tres horas mas de datos. El plan lo dice con estas
# palabras: "No detener la prueba en cuanto salga una cifra favorable".
REVERSION = {
    "daño_puntos_por_operacion": 1.0,
    "daño_n_minimo_por_brazo": 15,
    "cortacircuitos_pct_capital": -10.0,
    # Solo si la referencia NO esta igual de hundida: si cae todo el mercado,
    # revertir no recupera nada y acaba el experimento por el motivo
    # equivocado. Con la referencia sana, la perdida si es atribuible al rival.
    "cortacircuitos_exige_referencia_sana": True,
    "integridad": "cualquier fallo revierte de inmediato, sin esperar a n",
    "manual": "el operador, cuando quiera, sin justificar",
    "no_se_para_al_ir_ganando": True,
}

# --- La rampa: por calendario, no por resultados -----------------------------
RAMPA = {
    "revisiones_dias": (30, 60),
    "la_fraccion_no_sube_por_un_resultado_intermedio": True,
}

# Exigencia expresa del plan: no mover dos cosas a la vez.
CONGELADO_DURANTE_7B = (
    "presupuesto de avisos",
    "tamaño de posicion",
    "un plan notificado abierto por simbolo",
)

# La lectura principal no depende de que tomo el operador; la secundaria si, y
# por eso va siempre con la tasa de toma por brazo al lado.
LECTURA = {
    "principal": "todos los planes decisorios emitidos, evaluados en sombra",
    "secundaria": ("las operaciones realmente tomadas, siempre con la tasa de "
                   "toma por brazo"),
    "si_discrepan": "manda la principal",
}


def _declaracion() -> dict:
    """
    Todo lo que cambia un resultado, incluida la version de la fase 5 con la
    que se acopla: un rival elegido bajo otras politicas no es el mismo rival.
    """
    from src.experimentos.registro import REGISTRO_VERSION as FASE5_VERSION
    from src.experimentos.registro import huella as huella_fase5
    return {
        "version": REGISTRO_VERSION,
        "seleccion_del_rival": SELECCION_DEL_RIVAL,
        "sin_rival": list(SIN_RIVAL),
        "fraccion_rival": FRACCION_RIVAL,
        "asignacion": ASIGNACION,
        "puertas_activacion": PUERTAS_ACTIVACION,
        "riesgo_de_seleccion": RIESGO_DE_SELECCION,
        "desempate": DESEMPATE,
        "reversion": REVERSION,
        "rampa": {"revisiones_dias": list(RAMPA["revisiones_dias"]),
                  "la_fraccion_no_sube_por_un_resultado_intermedio": True},
        "congelado_durante_7b": list(CONGELADO_DURANTE_7B),
        "lectura": LECTURA,
        "fase5_version": FASE5_VERSION,
        "fase5_huella": huella_fase5(),
        "documento": DOCUMENTO,
        "documento_sha256": DOCUMENTO_SHA256,
    }


def huella() -> str:
    """Huella de contenido de la declaracion entera. 16 hex, suficiente."""
    crudo = json.dumps(_declaracion(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


def declaracion_json() -> str:
    return json.dumps(_declaracion(), sort_keys=True, ensure_ascii=False)


# --- El reparto ---------------------------------------------------------------

def brazo_de(episode_id, huella_registro: Optional[str] = None) -> str:
    """
    Que brazo le toca a un episodio. Determinista y reproducible.

    Sin generador aleatorio a proposito: este servicio reinicia, y un `random`
    con estado daria otro reparto despues de cada reinicio. Con un hash, el
    mismo episodio da el mismo brazo dentro de la misma version del registro, y
    se puede reproducir años despues desde la huella y el `episode_id`.

    La huella entra en el hash para que una version nueva rebaraje en vez de
    heredar el reparto de la anterior — heredarlo seria llevarse su suerte.

    Se compara contra `FRACCION_RIVAL` en vez de mirar si el hash es par: con
    la paridad, cambiar la fraccion declarada dejaria el reparto en el 50 %
    sin que nada lo delatara, y el documento y el codigo dirian cosas
    distintas. Asi solo hay una fuente.

    Esto NO decide nada por si solo: quien manda es la fila ya escrita en
    `activacion_asignacion`. Ver `AlmacenActivacion.asignar()`.
    """
    h = huella_registro or huella()
    d = hashlib.sha256(f"{h}:{episode_id}".encode("utf-8")).digest()
    u = int.from_bytes(d[:8], "big") / float(1 << 64)   # uniforme en [0,1)
    return BRAZO_RIVAL if u < FRACCION_RIVAL else BRAZO_REFERENCIA
