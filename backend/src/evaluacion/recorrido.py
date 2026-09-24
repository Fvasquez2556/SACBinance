"""
Un solo evaluador de recorridos, puro y serializable.

Fase 2 del plan de evolucion. Hoy hay cuatro seguimientos distintos —señales,
outcomes, rupturas y rupturas por marco— que miden lo mismo con reglas
ligeramente distintas, y por eso no se pueden comparar entre si. Este modulo es
la regla unica: una funcion sin estado global, sin reloj propio y sin acceso a
la base, que recibe una vela y devuelve el estado nuevo.

Dos cosas que este modulo mantiene SEPARADAS a proposito
--------------------------------------------------------
1. **El desenlace de la politica**: que le habria pasado a la operacion. Se
   congela en el primer toque de objetivo o de stop y ya no cambia. Si el
   precio sube un 8 % despues del stop, el desenlace sigue siendo el stop.
2. **El recorrido**: por donde paso el precio, con sus horizontes. Sigue
   registrandose despues del desenlace, porque la pregunta «que habria pasado
   con otro objetivo» necesita el camino entero.

Mezclarlas es como se fabrica una victoria que nadie pudo cobrar.

Reglas que vienen de errores medidos
------------------------------------
- **La vela cuenta solo si su minuto entero cae en la ventana** (F02 de la
  auditoria del 10-sep: habia recorridos de 117,9 h en ventanas de 24 h).
- **Idempotencia por marca de tiempo** (F11: 97 tiempos negativos por contar
  velas anteriores a la emision).
- **Barreras simultaneas**: si una misma vela toca objetivo y stop, gana el
  **stop** y la fila queda marcada `ambiguo`. Dentro de un minuto no se sabe el
  orden, y una duda no puede convertirse en una ganancia.
- **Salto de precio**: si la vela abre ya por debajo del stop, el stop se
  ejecuta en la apertura, no en el nivel. El hueco es peor que el nivel, y
  fingir lo contrario es regalarse dinero que no existe.
- **Cobertura**: el estado sabe cuantas velas vio frente a cuantas deberia
  haber. Sin cobertura no hay medicion, hay una suposicion.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

EVALUADOR_VERSION = "recorrido-v1"

MINUTO_MS = 60_000

# Los siete horizontes del plan, en minutos. Son fotos del recorrido, no
# politicas: ninguno cierra la operacion.
HORIZONTES_MIN = (15, 30, 60, 120, 240, 360, 480)

# Hitos fijos sobre la entrada, en porcentaje bruto. El 3,2 y el 4,2 netos del
# estudio salen de aqui sumandoles el coste; se guardan brutos para no atar la
# medicion a un modelo de coste concreto.
HITOS_PCT = (1.0, 2.0, 3.2, 3.7, 4.2, 4.7, 5.0, 8.0)


@dataclass(frozen=True)
class Vela:
    """Vela cerrada de 1 minuto. `t` es la apertura."""
    t: int
    o: float
    h: float
    l: float
    c: float


@dataclass(frozen=True)
class Plan:
    """Lo que define la medicion. Inmutable: una revision es otro plan."""
    entrada: float
    objetivo: float
    stop: float
    inicio_ms: int
    horizonte_ms: int = 12 * 3600_000
    hitos_pct: tuple = HITOS_PCT
    horizontes_min: tuple = HORIZONTES_MIN

    @property
    def fin_ms(self) -> int:
        return self.inicio_ms + self.horizonte_ms

    def valido(self) -> bool:
        return (all(isinstance(x, (int, float)) for x in (self.entrada, self.objetivo, self.stop))
                and 0 < self.stop < self.entrada < self.objetivo)


@dataclass
class Estado:
    """
    Acumulador serializable. Se guarda y se recupera tal cual, asi que un
    reinicio no reinicia la medicion ni la duplica.
    """
    n_velas: int = 0
    ms_primera: Optional[int] = None
    ms_ultima: Optional[int] = None
    t_ultima: Optional[int] = None          # marca absoluta, para idempotencia
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    ms_mfe: Optional[int] = None
    ms_mae: Optional[int] = None
    ms_objetivo: Optional[int] = None
    ms_stop: Optional[int] = None
    precio_stop: Optional[float] = None     # el hueco cuenta como lo que fue
    ambiguo: bool = False
    salto: bool = False
    desenlace: Optional[str] = None         # OBJETIVO | STOP | VENCIDO
    ms_desenlace: Optional[int] = None
    cierre_pct: Optional[float] = None
    hitos: dict = field(default_factory=dict)        # '3.2' -> ms
    horizontes: dict = field(default_factory=dict)   # '60'  -> {ret,mfe,mae,n}

    def como_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def desde_dict(cls, d: dict) -> "Estado":
        campos = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**campos)


def _pct(plan: Plan, precio: float) -> float:
    return (precio / plan.entrada - 1.0) * 100.0


def cuenta(plan: Plan, vela: Vela) -> bool:
    """La vela cuenta solo si su minuto entero cae dentro de la ventana."""
    return vela.t >= plan.inicio_ms and vela.t + MINUTO_MS <= plan.fin_ms


def avanzar(plan: Plan, estado: Estado, vela: Vela) -> Estado:
    """
    Aplica una vela. Funcion pura: mismo estado y misma vela, mismo resultado.

    Repetir una vela ya vista —un reintento, una reconexion, un replay que
    solapa— no cambia nada. Es lo que permite que el mismo codigo sirva para
    streaming y para replay sin que uno mienta respecto del otro.
    """
    if not cuenta(plan, vela):
        return estado
    if estado.t_ultima is not None and vela.t <= estado.t_ultima:
        return estado

    e = replace(estado)
    dt = vela.t - plan.inicio_ms
    e.n_velas += 1
    e.t_ultima = vela.t
    e.ms_ultima = dt
    if e.ms_primera is None:
        e.ms_primera = dt
        e.mfe_pct = _pct(plan, vela.h)
        e.mae_pct = _pct(plan, vela.l)
        e.ms_mfe = e.ms_mae = dt
    else:
        if _pct(plan, vela.h) > e.mfe_pct:
            e.mfe_pct, e.ms_mfe = _pct(plan, vela.h), dt
        if _pct(plan, vela.l) < e.mae_pct:
            e.mae_pct, e.ms_mae = _pct(plan, vela.l), dt
    e.cierre_pct = _pct(plan, vela.c)

    e.hitos = dict(e.hitos)
    for pct in plan.hitos_pct:
        clave = f"{pct:g}"
        if clave not in e.hitos and vela.h >= plan.entrada * (1 + pct / 100.0):
            e.hitos[clave] = dt

    toca_stop = vela.l <= plan.stop
    toca_objetivo = vela.h >= plan.objetivo
    if e.ms_stop is None and toca_stop:
        e.ms_stop = dt
        # Un hueco por debajo del stop se ejecuta en la apertura: peor precio.
        if vela.o <= plan.stop:
            e.precio_stop, e.salto = vela.o, True
        else:
            e.precio_stop = plan.stop
    if e.ms_objetivo is None and toca_objetivo:
        e.ms_objetivo = dt
    if toca_stop and toca_objetivo and e.desenlace is None:
        e.ambiguo = True

    if e.desenlace is None:
        if toca_stop:                      # la duda se resuelve contra la operacion
            e.desenlace, e.ms_desenlace = "STOP", dt
        elif toca_objetivo:
            e.desenlace, e.ms_desenlace = "OBJETIVO", dt

    e.horizontes = dict(e.horizontes)
    for minutos in plan.horizontes_min:
        if dt < minutos * MINUTO_MS:
            clave = str(minutos)
            h = e.horizontes.get(clave) or {"ret": None, "mfe": None, "mae": None, "n": 0}
            h = {
                "ret": e.cierre_pct,
                "mfe": e.mfe_pct if h["mfe"] is None else max(h["mfe"], e.mfe_pct),
                "mae": e.mae_pct if h["mae"] is None else min(h["mae"], e.mae_pct),
                "n": h["n"] + 1,
            }
            e.horizontes[clave] = h
    return e


def cerrar_por_reloj(plan: Plan, estado: Estado, ahora_ms: int) -> Estado:
    """
    Vencer es un desenlace mas, y lo decide el reloj, no la llegada de una vela.

    Sin esto, un par que sale del universo deja su seguimiento colgado: la
    duracion mas larga observada asi fue de 117,9 h sobre una ventana de 24.
    """
    if estado.desenlace is not None or ahora_ms < plan.fin_ms:
        return estado
    return replace(estado, desenlace="VENCIDO",
                   ms_desenlace=estado.ms_ultima if estado.ms_ultima is not None
                   else plan.horizonte_ms)


def cobertura(plan: Plan, estado: Estado, ahora_ms: int) -> float:
    """Velas vistas frente a las que la ventana deberia haber producido."""
    fin = min(ahora_ms, plan.fin_ms)
    esperadas = max(0, (fin - plan.inicio_ms) // MINUTO_MS)
    if esperadas <= 0:
        return 0.0
    return round(min(1.0, estado.n_velas / esperadas), 4)


def completa(plan: Plan, ahora_ms: int) -> bool:
    return ahora_ms >= plan.fin_ms


def resultado_politica(plan: Plan, estado: Estado, coste_pct: float = 0.0) -> Optional[float]:
    """
    Lo que la operacion habria dejado, en porcentaje neto.

    Devuelve None mientras no haya desenlace: una ventana abierta no es un
    empate ni una ganancia, es una medicion que todavia no existe.
    """
    if estado.desenlace is None:
        return None
    if estado.desenlace == "OBJETIVO":
        return round(_pct(plan, plan.objetivo) - coste_pct, 4)
    if estado.desenlace == "STOP":
        precio = estado.precio_stop if estado.precio_stop is not None else plan.stop
        return round(_pct(plan, precio) - coste_pct, 4)
    return round((estado.cierre_pct or 0.0) - coste_pct, 4)


def evaluar(plan: Plan, velas, ahora_ms: Optional[int] = None,
            estado: Optional[Estado] = None) -> Estado:
    """Aplica una secuencia ordenada de velas. Es el adaptador de replay."""
    e = estado or Estado()
    for vela in velas:
        e = avanzar(plan, e, vela)
    if ahora_ms is not None:
        e = cerrar_por_reloj(plan, e, ahora_ms)
    return e
