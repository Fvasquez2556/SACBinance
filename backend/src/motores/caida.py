"""
Motor B — caida y recuperacion en spot, en sombra.

Dos preguntas distintas, nunca mezcladas:

    1. ¿La caida sigue activa o se esta estabilizando?
    2. ¿Aparecio una recuperacion que justifique evaluar una NUEVA compra?

No hay cortos en el alcance. Una caida detectada no es una operacion: es un
estado del mercado que hay que saber describir para **no** comprar todavia.

El dato que obliga a este diseno
---------------------------------
La intuicion dice que una ruptura bajista significa que la caida sigue. Medido
el 22-sep sobre 20.359 rupturas bajistas maduras, con barreras homogeneas en R
y control pareado, dice lo contrario:

    todas          detector 44,1 %  control 45,8 %   -1,76 pp [-2,72, -0,80]
    marco 1h       detector 32,3 %  control 37,0 %   -4,73 pp
    con volumen >=2x  detector 35,8 %  control 45,0 %   -9,26 pp [-14,2, -4,3]

Es decir: romper a la baja **con volumen** es el caso donde MENOS probable es
que la caida continue. La regla popular («el volumen confirma la ruptura») esta
del reves en estos datos. Por eso este motor no tiene ninguna familia que diga
«va a seguir bajando»: su unico trabajo es seguir el estado y esperar el
disparador declarado de recuperacion.

El disparador declarado
-----------------------
`REBOTE_CONFIRMADO` —el unico estado que puede producir un candidato— exige las
DOS cosas a la vez:

    ruptura valida       el precio rompio el techo de la base, CON volumen
                         suficiente y sin llegar tarde (ver `ruptura_valida`)
    retroceso.confirmado el rebote desde el suelo ya pasa del 1 %

Las dos estan medidas por separado (`base_rebote.py` y `retroceso.py`); ninguna
anticipa el suelo, las dos confirman despues del hecho. Anticipar el suelo es
exactamente lo que este motor tiene prohibido.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.config.settings import get_settings
from src.motores.contrato import (
    CANDIDATO,
    CONFLICTO,
    ESPERAR,
    MOTOR_CAIDA,
    SIN_TESIS,
    Lectura,
    Observacion,
    sin_datos,
)

# --- Estados ------------------------------------------------------------------
SIN_CAIDA = "SIN_CAIDA"
CAIDA_ACTIVA = "CAIDA_ACTIVA"
DESACELERACION = "DESACELERACION"
BASE_EN_FORMACION = "BASE_EN_FORMACION"
RECUPERACION = "RECUPERACION"
REBOTE_CONFIRMADO = "REBOTE_CONFIRMADO"

ESTADOS = (SIN_CAIDA, CAIDA_ACTIVA, DESACELERACION, BASE_EN_FORMACION,
           RECUPERACION, REBOTE_CONFIRMADO)

# Solo desde aqui puede salir una compra.
ESTADOS_COMPRABLES = (REBOTE_CONFIRMADO,)

# --- Motivos de transicion ----------------------------------------------------
ABRE = "ABRE"
AVANZA = "AVANZA"
NUEVA_CAIDA = "NUEVA_CAIDA"
INVALIDADO = "INVALIDADO"
CADUCADO = "CADUCADO"

_FSM_DROPPING = "DROPPING"
_FSM_BOTTOMING = "BOTTOMING"
_FSM_VALLEY = "VALLEY"
_FSM_RISING = "RISING"


def ruptura_valida(base: dict) -> tuple:
    """
    ¿La base se rompio de verdad? Devuelve (si_o_no, lo_que_falta).

    `base_rebote.rompio` NO significa «ruptura valida»: el detector lo pone en
    cuanto el maximo de la vela pasa el techo, **antes** de mirar el volumen y
    antes de mirar si la ruptura es reciente. Puede devolver `rompio=True` con
    `detected=False` y motivo «rompe sin volumen». Tomarlo como disparador era
    confirmar rebotes que el propio detector rechaza.

    Aqui se exigen las tres condiciones por separado, sin heredar el `score`
    del detector: este motor no puntua.
    """
    s = get_settings()
    if not base.get("rompio"):
        return False, "romper el techo de la base"
    vol = base.get("ruptura_vol_ratio")
    if vol is None:
        return False, "el volumen de la ruptura (no se pudo medir)"
    if vol < s.base_ruptura_vol_min:
        return False, (f"volumen en la ruptura ({vol}x, minimo "
                       f"{s.base_ruptura_vol_min}x)")
    dist = base.get("dist_techo_pct")
    if dist is not None and dist > s.base_max_sobre_techo_pct:
        return False, (f"una ruptura reciente (ya {dist}% sobre el techo)")
    return True, ""


@dataclass
class EstadoCaida:
    """
    Lo que el motor recuerda de un simbolo. Serializable a proposito: vive en
    la tabla, no en memoria, asi que reiniciar no reabre una caida ya cerrada
    ni reinicia su reloj — el mismo error que la fase 1 corrigio en episodios.
    """
    symbol: str
    estado: str = SIN_CAIDA
    desde_ms: int = 0
    abierto_ms: int = 0
    suelo: Optional[float] = None          # el minimo visto en esta caida
    pico: Optional[float] = None           # de donde venia
    caida_pct: Optional[float] = None
    base_techo: Optional[float] = None
    base_piso: Optional[float] = None
    n_transiciones: int = 0

    def como_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def desde_dict(cls, d: dict) -> "EstadoCaida":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


def avanzar_caida(est: EstadoCaida, obs: Observacion) -> tuple:
    """
    Funcion pura: (estado_nuevo, lectura, motivo_transicion_o_None).

    No muta `est`. Devuelve un `EstadoCaida` nuevo, para que el mismo par de
    argumentos de siempre el mismo resultado y el replay coincida con el vivo.
    """
    s = get_settings()
    faltan = obs.faltantes()
    if faltan:
        return est, sin_datos(MOTOR_CAIDA, obs, faltan), None

    retro = obs.retroceso or {}
    base = obs.base_rebote or {}
    taxo = obs.taxonomia or {}
    precio = obs.precio

    caducidad_ms = s.motor_caida_caducidad_horas * 3600_000
    nuevo = EstadoCaida(**est.como_dict())
    motivo = None

    # --- Caducidad: 12 h es la ventana del episodio, y este motor usa la misma.
    if (nuevo.estado != SIN_CAIDA and nuevo.abierto_ms
            and obs.ts_ms - nuevo.abierto_ms >= caducidad_ms):
        nuevo = EstadoCaida(symbol=obs.symbol, estado=SIN_CAIDA, desde_ms=obs.ts_ms,
                            n_transiciones=nuevo.n_transiciones + 1)
        motivo = CADUCADO
        return nuevo, _lectura(nuevo, obs, (
            f"caducado: {s.motor_caida_caducidad_horas} h sin resolverse. Un "
            "movimiento que sigue vivo al dia siguiente es otro episodio.",),
            {}), motivo

    cayendo = (taxo.get("estado") == "CAIDA" or obs.fsm_state == _FSM_DROPPING
               or obs.display_state == "CAYENDO")
    # `retroceso.caida_pct` viene CON SIGNO: una caida del 26 % es -26.0. El
    # umbral se declara en magnitud, asi que se compara en valor absoluto.
    # Comparar el valor con signo contra un umbral positivo hacia que el motor
    # no pudiera abrir jamas — lo cazo el replay sobre ocho caidas reales de
    # entre -18 % y -45 %, donde no abrio ni una. Las pruebas no lo vieron
    # porque sus datos de ejemplo repetian el mismo error de signo.
    caida_pct = retro.get("caida_pct")
    suficiente = (caida_pct is not None
                  and abs(caida_pct) >= s.motor_caida_min_caida_pct)

    datos = {
        "fsm": obs.fsm_state, "display": obs.display_state,
        "taxonomia": taxo.get("estado"),
        "caida_pct": caida_pct, "suelo": retro.get("suelo"),
        "rebote_pct": retro.get("rebote_pct"),
        "minutos_desde_suelo": retro.get("minutos_desde_suelo"),
        "base_velas": base.get("base_velas"), "base_techo": base.get("base_techo"),
        "base_piso": base.get("base_piso"), "vol_dryup": base.get("vol_dryup"),
        "rompio": base.get("rompio"),
        "ruptura_vol_ratio": base.get("ruptura_vol_ratio"),
        "drawdown_pct": obs.drawdown_pct,
    }

    # --- Abrir --------------------------------------------------------------
    if nuevo.estado == SIN_CAIDA:
        if cayendo and suficiente:
            nuevo = EstadoCaida(
                symbol=obs.symbol, estado=CAIDA_ACTIVA, desde_ms=obs.ts_ms,
                abierto_ms=obs.ts_ms, suelo=retro.get("suelo") or precio,
                pico=retro.get("pico_previo"), caida_pct=caida_pct,
                n_transiciones=est.n_transiciones + 1)
            return nuevo, _lectura(nuevo, obs, (
                f"caida activa: {abs(caida_pct):.2f} % desde el pico. No se "
                "compra aqui — se sigue.",), datos), ABRE
        return est, Lectura(
            motor=MOTOR_CAIDA, symbol=obs.symbol, ts_ms=obs.ts_ms,
            veredicto=SIN_TESIS, estado=SIN_CAIDA, estado_desde_ms=est.desde_ms or None,
            razones=("no hay caida que seguir",), datos=datos,
            precio=precio), None

    # --- Rebote que falla: pierde el piso de SU base ------------------------
    # No es lo mismo que perder el minimo absoluto. Un rebote confirmado que se
    # cae por debajo del piso de la base ya fallo, aunque todavia le queden dos
    # puntos hasta el suelo de la caida: es la familia "rebote debil que vuelve
    # a perder soporte", y sin esta regla se quedaria marcado como confirmado
    # mientras el precio se lo come.
    piso = nuevo.base_piso or base.get("base_piso")
    if (nuevo.estado == REBOTE_CONFIRMADO and piso and precio and precio < piso):
        nuevo = EstadoCaida(symbol=obs.symbol, estado=SIN_CAIDA, desde_ms=obs.ts_ms,
                            n_transiciones=nuevo.n_transiciones + 1)
        return nuevo, _lectura(nuevo, obs, (
            f"rebote invalidado: perdio el piso de su base ({piso}). El plan "
            "que salio de aqui conserva su resultado; este episodio se cierra.",),
            datos), INVALIDADO

    # --- Nueva caida: pierde el suelo anterior ------------------------------
    if (nuevo.suelo and precio and precio < nuevo.suelo
            and nuevo.estado != CAIDA_ACTIVA):
        nuevo = EstadoCaida(
            symbol=obs.symbol, estado=CAIDA_ACTIVA, desde_ms=obs.ts_ms,
            abierto_ms=nuevo.abierto_ms, suelo=precio, pico=nuevo.pico,
            caida_pct=caida_pct, n_transiciones=nuevo.n_transiciones + 1)
        return nuevo, _lectura(nuevo, obs, (
            "perdio el suelo anterior: vuelve a caida activa. El rebote que "
            "se estaba formando queda invalidado.",), datos), NUEVA_CAIDA

    if nuevo.suelo is None or (precio and precio < nuevo.suelo):
        nuevo.suelo = precio

    # --- Avanzar ------------------------------------------------------------
    destino = nuevo.estado
    razon = None

    if nuevo.estado == CAIDA_ACTIVA:
        if obs.fsm_state in (_FSM_BOTTOMING, _FSM_VALLEY, _FSM_RISING) or not cayendo:
            destino = DESACELERACION
            razon = (f"la caida se frena (1m en {obs.fsm_state}). Frenar no es "
                     "suelo: el suelo solo se sabe despues.")
    elif nuevo.estado == DESACELERACION:
        velas = base.get("base_velas") or 0
        if velas >= s.motor_caida_base_min_velas or obs.fsm_state == _FSM_VALLEY:
            destino = BASE_EN_FORMACION
            razon = (f"base en formacion: {velas} velas de rango estrecho"
                     + (f", volumen secandose a {base.get('vol_dryup')}x"
                        if base.get("vol_dryup") else ""))
    elif nuevo.estado == BASE_EN_FORMACION:
        if retro.get("detectado"):
            destino = RECUPERACION
            razon = (f"recuperacion en curso: {retro.get('rebote_pct')} % desde "
                     "el suelo. Todavia no es una compra.")
    elif nuevo.estado == RECUPERACION:
        rota, _falta = ruptura_valida(base)
        if rota and bool(retro.get("confirmado")):
            destino = REBOTE_CONFIRMADO
            razon = ("rebote confirmado: rompio el techo de la base con volumen "
                     f"{base.get('ruptura_vol_ratio')}x y el rebote desde el "
                     f"suelo ya es de {retro.get('rebote_pct')} %")

    if destino != nuevo.estado:
        nuevo = EstadoCaida(
            symbol=obs.symbol, estado=destino, desde_ms=obs.ts_ms,
            abierto_ms=nuevo.abierto_ms, suelo=nuevo.suelo, pico=nuevo.pico,
            caida_pct=nuevo.caida_pct,
            base_techo=base.get("base_techo") or nuevo.base_techo,
            base_piso=base.get("base_piso") or nuevo.base_piso,
            n_transiciones=nuevo.n_transiciones + 1)
        return (nuevo,
                _lectura(nuevo, obs, (razon,), datos,
                         disparo_ahora=(destino == REBOTE_CONFIRMADO)),
                AVANZA)

    return nuevo, _lectura(nuevo, obs, (), datos), None


def _lectura(est: EstadoCaida, obs: Observacion, razones: tuple,
             datos: dict, disparo_ahora: bool = False) -> Lectura:
    """
    Traduce el estado a veredicto.

    Solo REBOTE_CONFIRMADO puede comprar, y **solo en el minuto en que
    dispara**. Un rebote confirmado hace tres horas no es una compra nueva cada
    minuto: el plan que nacio de aquel disparo sigue su propio reloj, y
    reemitirlo seria contar diez veces el mismo movimiento — justo lo que la
    identidad por episodio existe para evitar. Sin esta distincion el replay
    sobre ocho caidas reales marcaba entre 161 y 340 minutos como candidato por
    par.
    """
    base = obs.base_rebote or {}
    retro = obs.retroceso or {}
    faltan_para_comprar = []
    rota, falta_ruptura = ruptura_valida(base)
    if not rota:
        faltan_para_comprar.append(falta_ruptura)
    if not retro.get("confirmado"):
        faltan_para_comprar.append("rebote de al menos 1 % desde el suelo")

    razones = tuple(r for r in razones if r)
    if est.estado not in ESTADOS_COMPRABLES and faltan_para_comprar:
        razones = razones + (
            "falta el disparador declarado: " + " y ".join(faltan_para_comprar),)

    if est.estado == SIN_CAIDA:
        return Lectura(motor=MOTOR_CAIDA, symbol=obs.symbol, ts_ms=obs.ts_ms,
                       veredicto=SIN_TESIS, estado=est.estado,
                       estado_desde_ms=est.desde_ms or None,
                       razones=razones, datos=datos, precio=obs.precio)

    if est.estado not in ESTADOS_COMPRABLES:
        return Lectura(motor=MOTOR_CAIDA, symbol=obs.symbol, ts_ms=obs.ts_ms,
                       veredicto=ESPERAR, estado=est.estado,
                       estado_desde_ms=est.desde_ms, razones=razones,
                       datos=datos, precio=obs.precio)

    if not disparo_ahora:
        return Lectura(
            motor=MOTOR_CAIDA, symbol=obs.symbol, ts_ms=obs.ts_ms,
            veredicto=ESPERAR, estado=est.estado, estado_desde_ms=est.desde_ms,
            razones=razones + ("el disparador ya ocurrio; el plan que salio de "
                               "ahi sigue su propio reloj",),
            datos=datos, precio=obs.precio)

    # Rebote confirmado en este mismo minuto. Dos cosas pueden impedir que sea
    # candidato.
    if obs.hay_conflicto():
        alc, baj = obs.marcos_en_conflicto()
        return Lectura(
            motor=MOTOR_CAIDA, symbol=obs.symbol, ts_ms=obs.ts_ms,
            veredicto=CONFLICTO, estado=est.estado, estado_desde_ms=est.desde_ms,
            razones=razones + (f"el rebote disparo, pero suben {', '.join(alc)} "
                               f"y bajan {', '.join(baj)}",),
            datos=datos, precio=obs.precio)

    plan = obs.plan or {}
    e, tp, sl = plan.get("entry"), plan.get("take_profit"), plan.get("stop_loss")
    if not (plan.get("valid") and e and tp and sl and 0 < sl < e < tp):
        return Lectura(
            motor=MOTOR_CAIDA, symbol=obs.symbol, ts_ms=obs.ts_ms,
            veredicto=ESPERAR, estado=est.estado, estado_desde_ms=est.desde_ms,
            razones=razones + ("el rebote disparo, pero el plan no tiene "
                               "niveles validos",),
            datos=datos, precio=obs.precio)

    return Lectura(
        motor=MOTOR_CAIDA, symbol=obs.symbol, ts_ms=obs.ts_ms,
        veredicto=CANDIDATO, estado=est.estado, estado_desde_ms=est.desde_ms,
        disparador=True, razones=razones, datos=datos, precio=obs.precio,
        entrada=e, objetivo=tp, stop=sl)
