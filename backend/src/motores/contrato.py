"""
Vocabulario comun de los dos motores de la fase 4.

Que es un motor aqui
--------------------
Una funcion pura que mira una `Observacion` —todo ya calculado antes de
decidir— y devuelve una `Lectura`: que tesis ve, en que estado esta, por que, y
que le falta para ser una entrada. No emite, no avisa, no puntua de 0 a 100 y
no toca ningun nivel. En esta fase escribe en su propia tabla y nada mas.

Las tres reglas que este modulo hace cumplir
--------------------------------------------
1. **Una tesis no es una compra.** `CANDIDATO` exige `disparador=True`. Ver una
   base bonita, una caida desacelerando o una compresion a punto no basta: hay
   que declarar antes que evento convierte la observacion en entrada, y que ese
   evento haya ocurrido. El constructor lo rechaza si no.
2. **Un plan solo viaja con un candidato.** Una lectura que no es candidata no
   puede llevar entrada, objetivo ni stop. Asi no existe la ruta por la que un
   "podria rebotar" acaba pintado como plan en una pantalla.
3. **Faltar un dato es un resultado.** `DATOS_INSUFICIENTES` es un veredicto de
   primera clase, con la lista de lo que falta. No se rellena con un cero ni se
   degrada a `ESPERAR`, que significa otra cosa: "la tesis existe y aun no ha
   disparado".

`CONFLICTO` es el cuarto: los marcos se contradicen. No se promedia ni se
inventa una confianza intermedia — se dice que se contradicen y quien mira
decide.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

MOTORES_VERSION = "motores-v1"

MOTOR_CONTINUACION = "continuacion"
MOTOR_CAIDA = "caida"

# --- Veredictos ---------------------------------------------------------------
CANDIDATO = "CANDIDATO"
ESPERAR = "ESPERAR"
CONFLICTO = "CONFLICTO"
DATOS_INSUFICIENTES = "DATOS_INSUFICIENTES"
SIN_TESIS = "SIN_TESIS"

VEREDICTOS = (CANDIDATO, ESPERAR, CONFLICTO, DATOS_INSUFICIENTES, SIN_TESIS)

# Por que se guardo esta lectura. Sin `MUESTRA` la poblacion guardada seria
# solo la que ya paso el filtro comprador, y entonces cualquier tasa medida
# sobre ella esta condicionada al filtro que se queria evaluar.
ORIGEN_TRANSICION = "TRANSICION"
ORIGEN_ALERTA = "ALERTA"
ORIGEN_VETO = "VETO"
ORIGEN_MUESTRA = "MUESTRA"

ORIGENES = (ORIGEN_TRANSICION, ORIGEN_ALERTA, ORIGEN_VETO, ORIGEN_MUESTRA)

# Velas de 1m que hacen falta para que cualquiera de los dos motores opine.
MINIMO_VELAS = 60


@dataclass(frozen=True)
class Observacion:
    """
    La foto que ve un motor. Todos los campos vienen ya calculados por el
    engine: el motor no recalcula nada ni mira el reloj del sistema, para que
    la misma observacion produzca siempre la misma lectura.
    """
    symbol: str
    ts_ms: int
    precio: float
    velas_1m: int = 0
    fsm_state: str = ""
    display_state: str = ""
    tendencias: dict = field(default_factory=dict)      # macro_trends por marco
    taxonomia: dict = field(default_factory=dict)
    impulso: dict = field(default_factory=dict)
    retroceso: dict = field(default_factory=dict)
    compresion: dict = field(default_factory=dict)
    grind: dict = field(default_factory=dict)
    ignicion: dict = field(default_factory=dict)
    base_rebote: dict = field(default_factory=dict)
    consolidacion: dict = field(default_factory=dict)
    niveles: dict = field(default_factory=dict)         # sr_levels
    plan: dict = field(default_factory=dict)            # trade_levels congelables
    flujo: dict = field(default_factory=dict)
    # El ancla: la lectura del marco lento. Es el unico marco con ventaja
    # medida frente a su control (1h: +8,46 pp), asi que es el que manda y no
    # se deja caducar en silencio — si esta vieja, falta un dato.
    ancla: dict = field(default_factory=dict)
    ancla_tf: str = "1h"
    ancla_edad_min: Optional[float] = None
    confluencia: dict = field(default_factory=dict)
    pos_en_rango: Optional[float] = None
    atr_pct: Optional[float] = None
    vol_ratio: Optional[float] = None
    rango_1h_pct: Optional[float] = None
    drawdown_pct: Optional[float] = None
    ruptura_nivel: Optional[float] = None               # ultimo techo roto
    ruptura_edad_min: Optional[float] = None
    btc_regime: str = ""

    def faltantes(self) -> tuple:
        """Que impide opinar. Vacio = hay con que."""
        faltan = []
        if self.velas_1m < MINIMO_VELAS:
            faltan.append(f"velas 1m ({self.velas_1m}/{MINIMO_VELAS})")
        if not self.precio or self.precio <= 0:
            faltan.append("precio")
        if not self.tendencias:
            faltan.append("tendencia por marco")
        return tuple(faltan)

    def marcos_en_conflicto(self) -> tuple:
        """
        Marcos que se contradicen ahora mismo. Devuelve (alcistas, bajistas).

        No se resuelve por mayoria: que 15m suba y 1h baje es informacion, y
        taparlo con un voto es justo lo que el plan prohibe.
        """
        alc = tuple(sorted(tf for tf, v in self.tendencias.items() if v == "ALCISTA"))
        baj = tuple(sorted(tf for tf, v in self.tendencias.items() if v == "BAJISTA"))
        return alc, baj

    def hay_conflicto(self) -> bool:
        alc, baj = self.marcos_en_conflicto()
        return bool(alc) and bool(baj)


@dataclass(frozen=True)
class Lectura:
    """Lo que un motor concluye en un instante. Inmutable y serializable."""
    motor: str
    symbol: str
    ts_ms: int
    veredicto: str
    familia: Optional[str] = None
    estado: Optional[str] = None
    estado_desde_ms: Optional[int] = None
    razones: tuple = ()
    faltantes: tuple = ()
    datos: dict = field(default_factory=dict)
    disparador: bool = False
    precio: Optional[float] = None
    entrada: Optional[float] = None
    objetivo: Optional[float] = None
    stop: Optional[float] = None
    version: str = MOTORES_VERSION

    def __post_init__(self):
        if self.veredicto not in VEREDICTOS:
            raise ValueError(f"veredicto desconocido: {self.veredicto}")
        if self.veredicto == CANDIDATO and not self.disparador:
            raise ValueError(
                "un candidato exige que su disparador declarado haya ocurrido")
        if self.veredicto != CANDIDATO and any(
                x is not None for x in (self.entrada, self.objetivo, self.stop)):
            raise ValueError(
                "solo un candidato puede llevar plan; una tesis no es una compra")
        if self.veredicto == DATOS_INSUFICIENTES and not self.faltantes:
            raise ValueError("faltan datos pero no se dice cuales")

    @property
    def es_compra(self) -> bool:
        return self.veredicto == CANDIDATO

    def como_fila(self) -> dict:
        return {
            "motor": self.motor, "symbol": self.symbol, "ts_ms": self.ts_ms,
            "veredicto": self.veredicto, "familia": self.familia,
            "estado": self.estado, "estado_desde_ms": self.estado_desde_ms,
            "razones": list(self.razones), "faltantes": list(self.faltantes),
            "datos": dict(self.datos), "disparador": int(self.disparador),
            "precio": self.precio, "entrada": self.entrada,
            "objetivo": self.objetivo, "stop": self.stop, "version": self.version,
        }

    def clave_cambio(self) -> tuple:
        """Lo que define 'esto ya no es lo mismo que la vez anterior'."""
        return (self.veredicto, self.familia, self.estado, self.disparador)


def sin_datos(motor: str, obs: Observacion, faltan: tuple) -> Lectura:
    return Lectura(motor=motor, symbol=obs.symbol, ts_ms=obs.ts_ms,
                   veredicto=DATOS_INSUFICIENTES, faltantes=faltan,
                   precio=obs.precio or None)
