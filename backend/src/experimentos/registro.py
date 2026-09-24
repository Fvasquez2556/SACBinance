"""
Las politicas congeladas de la fase 5, y el candado que impide moverlas.

Por que un candado y no una constante
-------------------------------------
Una prueba prospectiva solo vale si sus definiciones se escribieron ANTES de
ver los resultados. Nada impide, seis dias despues, "afinar" un umbral porque
el numero quedo feo — y ese cambio no deja rastro en un fichero de constantes.

Aqui la declaracion entera se reduce a una huella de contenido. Cada resultado
se guarda con esa huella. Si alguien cambia una politica, la huella cambia y
los resultados viejos quedan marcados como de otra version en vez de mezclarse
en silencio con los nuevos. No se puede reescribir el pasado sin que se note.

El registro documentado esta en
`audit/2026-09-22/plan-evolucion-motores/fase5/REGISTRO_CONGELADO.md`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

REGISTRO_VERSION = "fase5-v3"

# La version del METODO, no solo de las barreras. Dos mediciones con las mismas
# constantes pero distinta regla de fill o de cobertura NO son comparables, y
# sin esto compartirian identificacion. Lo levanto una revision externa: la
# huella cubria los numeros y dejaba fuera el procedimiento.
METODO_VERSION = "metodo-v2"

# Reglas del metodo que cambian el resultado y por tanto entran en la huella.
REGLA_FILL = (
    "la vela del fill aplica su STOP (se lleno bajando, asi que el minimo vino "
    "despues) pero NO concede el objetivo (su maximo pudo ser anterior al fill); "
    "solo cuentan velas cuyo minuto entero cae en la ventana"
)
REGLA_COBERTURA = (
    "un plan solo es medible con cobertura >= 0,90 de las velas esperadas; "
    "por debajo se marca SIN_DATOS, no entra en ninguna media y se puede volver "
    "a medir cuando las velas se recuperen"
)
COBERTURA_MINIMA = 0.90

POBLACION_DECISORIA = "avisado por Telegram Y primera oportunidad de su episodio"

# Huella del documento aprobado. Si el .md cambia, esta constante deja de
# coincidir y una prueba lo dice; y como entra en la huella, los resultados
# viejos quedan identificados en vez de mezclarse.
DOCUMENTO = "fase5/REGISTRO_CONGELADO.md"
DOCUMENTO_SHA256 = "af285a769f2d1f1ccfcd97e5c497d5a52a0fdd35cc553ac3dfb511b0da752900"

# --- Ejes ---------------------------------------------------------------------
EJE_REFERENCIA = "REFERENCIA"
EJE_SALIDA = "SALIDA"
EJE_ENTRADA = "ENTRADA"
EJE_STOP = "STOP"

# --- Desenlaces propios de esta fase ------------------------------------------
NO_LLENADO = "NO_LLENADO"   # la entrada diferida nunca se lleno: no hubo operacion
# La ventana vencio pero no se observo lo suficiente para medirla. NO es una
# perdida ni un empate: es una medicion que no existe, y se puede repetir
# cuando las velas se recuperen.
SIN_DATOS = "SIN_DATOS"


@dataclass(frozen=True)
class Politica:
    """
    Una regla completa de entrada, salida e invalidacion.

    Los tres campos opcionales dicen que se APARTA de la referencia; lo que no
    se declara se hereda del plan. Asi cada politica mueve una sola cosa y la
    comparacion sigue siendo pareada.
    """
    clave: str
    eje: str
    descripcion: str
    # Salida: objetivo neto fijo, en porcentaje sobre la entrada efectiva.
    objetivo_neto_pct: Optional[float] = None
    # Entrada: descuento sobre la entrada del plan, en porcentaje.
    descuento_pct: Optional[float] = None
    # Stop: fijo en porcentaje, o multiplicador sobre el del plan.
    stop_pct: Optional[float] = None
    stop_multiplo: Optional[float] = None
    # Solo informativo: no compite, se explora.
    exploracion: bool = False

    def como_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# =============================================================================
#  La declaracion congelada. NO SE MODIFICA.
#
#  Cambiar cualquier linea de aqui cambia la huella y abre otra version. Eso
#  es intencionado: es la diferencia entre una prueba prospectiva y una
#  busqueda.
# =============================================================================

POLITICAS = (
    Politica("REF", EJE_REFERENCIA,
             "la politica vigente: entrada, TP y SL que el plan congelo"),

    # --- Eje A: la salida ---
    Politica("A1", EJE_SALIDA, "objetivo fijo +2,7 % neto", objetivo_neto_pct=2.7),
    Politica("A2", EJE_SALIDA, "objetivo fijo +3,2 % neto", objetivo_neto_pct=3.2),
    Politica("A3", EJE_SALIDA, "objetivo fijo +4,2 % neto — el rival principal",
             objetivo_neto_pct=4.2),
    Politica("A4", EJE_SALIDA, "objetivo fijo +4,7 % neto", objetivo_neto_pct=4.7),
    Politica("A5", EJE_SALIDA, "objetivo fijo +5,2 % neto — exploracion registrada",
             objetivo_neto_pct=5.2, exploracion=True),

    # --- Eje B: la entrada diferida ---
    # El objetivo es el MISMO PRECIO que el de la referencia, no el mismo
    # porcentaje. Es lo que hace un operador de verdad —el TP es un nivel
    # estructural, no una distancia— y es la variante que midio el estudio del
    # 10-sep, que es el unico respaldo previo que tiene este eje. La primera
    # version del documento decia "en porcentaje" y el codigo hacia esto otro:
    # la discrepancia la encontro una revision externa y se resolvio a favor
    # del precio absoluto, con la correccion anotada en el documento.
    Politica("B1", EJE_ENTRADA, "comprar 0,5 % por debajo; mismo precio objetivo",
             descuento_pct=0.5),
    Politica("B2", EJE_ENTRADA, "comprar 1,5 % por debajo; mismo precio objetivo",
             descuento_pct=1.5),

    # --- Eje C: el stop, con el riesgo monetario igualado ---
    Politica("C1", EJE_STOP, "stop fijo -2,0 %", stop_pct=2.0),
    Politica("C2", EJE_STOP, "stop fijo -3,0 %", stop_pct=3.0),
    Politica("C3", EJE_STOP, "stop del plan x 1,5", stop_multiplo=1.5),
)

POR_CLAVE = {p.clave: p for p in POLITICAS}

# Las puertas, tambien congeladas. Viven aqui para que el informe no pueda
# usar un umbral distinto del declarado sin que la huella lo delate.
PUERTAS = {
    "dinero_limite_inferior_pct": 0.30,
    "habilidad_min_puntos": 0.0,
    "terreno_nuevo": "solo planes creados despues de la congelacion",
    "n_minimo": 50,
    "bootstrap": "agrupado por par",
    "ic": 95,
}

# Los subconjuntos del eje D. No son politicas: son etiquetas de lectura, y por
# eso no consumen evaluacion propia.
FILTROS = {
    "D1": "ancla de 1h con ruptura alcista al crear el plan",
    "D2": "primera oportunidad de su episodio",
    "D3": "avisado por Telegram",
}


def _declaracion() -> dict:
    """
    Todo lo que cambia un resultado. No solo las barreras: tambien el metodo.

    Una revision externa señalo que la huella anterior cubria los numeros y
    dejaba fuera el procedimiento, de modo que se podia cambiar la regla de
    fill sin que nada lo delatara. Aqui entran las dos reglas que deciden si
    una operacion existe y si es medible, la version del evaluador, la
    poblacion que decide y la huella del documento aprobado.
    """
    from src.evaluacion.recorrido import EVALUADOR_VERSION
    return {
        "version": REGISTRO_VERSION,
        "metodo": METODO_VERSION,
        "evaluador": EVALUADOR_VERSION,
        "regla_fill": REGLA_FILL,
        "regla_cobertura": REGLA_COBERTURA,
        "cobertura_minima": COBERTURA_MINIMA,
        "poblacion_decisoria": POBLACION_DECISORIA,
        "documento": DOCUMENTO,
        "documento_sha256": DOCUMENTO_SHA256,
        "politicas": [p.como_dict() for p in POLITICAS],
        "puertas": PUERTAS,
        "filtros": FILTROS,
    }


def huella() -> str:
    """Huella de contenido de la declaracion entera. 16 hex, suficiente."""
    crudo = json.dumps(_declaracion(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


def declaracion_json() -> str:
    return json.dumps(_declaracion(), sort_keys=True, ensure_ascii=False)


# --- Traduccion de una politica a barreras concretas -------------------------

@dataclass(frozen=True)
class Barreras:
    """Lo que la politica pide para un plan concreto, ya en precios."""
    entrada: float
    objetivo: float
    stop: float
    # Cuanto hay que esperar a que el precio baje para entrar. None = a mercado.
    entrada_limite: Optional[float] = None
    # Escala de la posicion para que el riesgo monetario sea el de la
    # referencia. Un stop el doble de ancho lleva media posicion.
    tamano_relativo: float = 1.0
    notas: tuple = field(default_factory=tuple)

    def valida(self) -> bool:
        return (all(isinstance(x, (int, float))
                    for x in (self.entrada, self.objetivo, self.stop))
                and 0 < self.stop < self.entrada < self.objetivo)


def barreras_de(politica: Politica, plan: dict, coste_pct: float) -> Optional[Barreras]:
    """
    Convierte una politica en barreras para un plan.

    `plan` necesita entry, take_profit, stop_loss. Devuelve None si el plan no
    da para medir esta politica — que es un resultado, no un fallo.
    """
    entry = plan.get("entry")
    tp = plan.get("take_profit")
    sl = plan.get("stop_loss")
    if not (entry and tp and sl) or not (0 < sl < entry < tp):
        return None

    riesgo_ref = (entry - sl) / entry          # la unidad de riesgo de la referencia
    entrada = float(entry)
    limite = None
    notas = []

    # --- Entrada diferida ---
    if politica.descuento_pct:
        entrada = entry * (1.0 - politica.descuento_pct / 100.0)
        limite = entrada
        notas.append(f"entra {politica.descuento_pct} % por debajo del plan")

    # --- Stop ---
    if politica.stop_pct is not None:
        stop = entrada * (1.0 - politica.stop_pct / 100.0)
    elif politica.stop_multiplo is not None:
        stop = entrada * (1.0 - riesgo_ref * politica.stop_multiplo)
    else:
        # Hereda el riesgo de la referencia, medido sobre la entrada efectiva.
        stop = entrada * (1.0 - riesgo_ref)

    # --- Salida ---
    if politica.objetivo_neto_pct is not None:
        # El objetivo se declara NETO; la barrera de precio es bruta.
        objetivo = entrada * (1.0 + (politica.objetivo_neto_pct + coste_pct) / 100.0)
    elif politica.descuento_pct:
        # Entrada diferida con el objetivo de la referencia: mismo precio de
        # salida, no el mismo porcentaje. Comprar mas abajo y ademas mover el
        # objetivo mas abajo seria cambiar dos cosas a la vez.
        objetivo = float(tp)
    else:
        objetivo = float(tp)

    riesgo_nuevo = (entrada - stop) / entrada
    tamano = (riesgo_ref / riesgo_nuevo) if riesgo_nuevo > 0 else 0.0
    if politica.eje == EJE_STOP:
        notas.append(f"posicion x{tamano:.2f} para igualar el riesgo monetario")

    b = Barreras(entrada=entrada, objetivo=objetivo, stop=stop,
                 entrada_limite=limite, tamano_relativo=tamano,
                 notas=tuple(notas))
    return b if b.valida() else None
