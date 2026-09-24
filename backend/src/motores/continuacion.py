"""
Motor A — continuacion alcista, en sombra.

La pregunta: «¿hay una compra de continuacion razonable DESDE ESTE MOMENTO, con
este objetivo, esta invalidacion y este horizonte?»

Por que el ancla es 1h y no 5m
------------------------------
Medido el 22-sep sobre 43.500 rupturas por marco maduras, con barreras
homogeneas en R y un control pareado (entrada al azar en el mismo par, mismo
periodo, misma R):

    marco 5m   detector 48,7 %  control 53,0 %   -4,32 pp [-5,40, -3,24]
    marco 15m  detector 54,6 %  control 55,6 %   -1,04 pp [-2,96, +0,88]
    marco 1h   detector 64,5 %  control 56,0 %   +8,46 pp [+4,23, +12,69]

Y la ventaja de 1h aguanta al partir la muestra: +6,96 pp en la primera mitad,
+9,94 pp en la segunda. El 5m produce 4.398 rupturas alcistas al dia y **resta**.
Asi que el disparador se ancla en 1h y los marcos rapidos entran como contexto,
nunca como motivo. Detalle en `audit/2026-09-22/.../MEDICION_RUPTURAS_EN_R.md`.

Lo que este motor NO hace
-------------------------
No puntua de 0 a 100 — la puntuacion actual no ordena (AUC 0,535 en el tramo
reciente), y anadir otra cifra que no ordena no mejora nada. No pondera la
confluencia entre marcos: medida contra su control, ninguna celda de
confluencia bate al azar (AUC 0,506). Se sigue guardando el dato, pero no pesa.
No emite, no avisa y no toca un solo nivel.
"""
from __future__ import annotations

from src.config.settings import get_settings
from src.motores.contrato import (
    CANDIDATO,
    CONFLICTO,
    ESPERAR,
    MOTOR_CONTINUACION,
    SIN_TESIS,
    Lectura,
    Observacion,
    sin_datos,
)

# --- Familias -----------------------------------------------------------------
EXTENDIDO = "EXTENDIDO"
RUPTURA_SOSTENIDA = "RUPTURA_SOSTENIDA"
RUPTURA_RETEST = "RUPTURA_RETEST"
PULLBACK_TENDENCIA = "PULLBACK_TENDENCIA"
EXPANSION_COMPRESION = "EXPANSION_COMPRESION"

FAMILIAS = (EXTENDIDO, RUPTURA_SOSTENIDA, RUPTURA_RETEST,
            PULLBACK_TENDENCIA, EXPANSION_COMPRESION)

# Orden de resolucion, que la cadena de `_tesis` implementa en ese mismo orden.
# Agotamiento primero, por seguridad: si la subida ya esta gastada no puede
# clasificarse como ruptura sostenida aunque el detector de ruptura dispare.
# Es la misma prioridad que ya usa `taxonomy.PRIORIDAD`.
PRIORIDAD = (EXTENDIDO, RUPTURA_RETEST, RUPTURA_SOSTENIDA,
             PULLBACK_TENDENCIA, EXPANSION_COMPRESION)

_RUPTURA_ALCISTA = "RUPTURA_ALCISTA"
# Las fases reales del medidor de impulso. "DESACELERANDO" no entra:
# frenar no es agotarse, y confundirlos descarta pullbacks validos.
_FASES_GASTADAS = ("AGOTADA",)


def _plan_valido(plan: dict) -> bool:
    if not plan or not plan.get("valid"):
        return False
    e, tp, sl = plan.get("entry"), plan.get("take_profit"), plan.get("stop_loss")
    return bool(e and tp and sl and 0 < sl < e < tp)


def _tesis(obs: Observacion) -> tuple:
    """
    Devuelve (familia, condiciones_cumplidas, disparo, razones, datos).

    `condiciones` son los hechos que hacen que la tesis exista; `disparo` es el
    evento declarado que la convierte en entrada. Separarlos es el punto: sin
    esa separacion, ver el patron y comprarlo son la misma cosa.
    """
    s = get_settings()
    ancla = obs.ancla or {}
    taxo = obs.taxonomia or {}
    imp = obs.impulso or {}
    retro = obs.retroceso or {}
    comp = obs.compresion or {}
    grind = obs.grind or {}

    fase = imp.get("fase") or ""
    consumido = imp.get("consumido_pct")
    ancla_alcista = ancla.get("direccion") == _RUPTURA_ALCISTA
    ancla_tendencia = ancla.get("tendencia") or "NEUTRAL"

    datos = {
        "ancla_tf": obs.ancla_tf,
        "ancla_direccion": ancla.get("direccion"),
        "ancla_confirmada": ancla.get("confirmada"),
        "ancla_nivel": ancla.get("nivel_roto"),
        "ancla_toques": ancla.get("toques_nivel"),
        "ancla_tendencia": ancla_tendencia,
        "ancla_edad_min": obs.ancla_edad_min,
        "fase_impulso": fase,
        "consumido_pct": consumido,
        "taxonomia": taxo.get("estado"),
        "vol_ratio": obs.vol_ratio,
        "pos_en_rango": obs.pos_en_rango,
        "conf_confirmadas": (obs.confluencia or {}).get("confirmadas"),
    }

    # --- EXTENDIDO: se observa, no se persigue ---------------------------
    #
    # Dos condiciones que la primera version no tenia, y que la medicion en
    # vivo obligo a poner:
    #
    # 1. **Tiene que haber una tesis que este gastada.** `FASE_AGOTADA` se
    #    devuelve en cuanto el precio esta bajo la EMA7 en dos marcos, que es
    #    casi cualquier moneda parada. En la primera pasada eso etiqueto 320
    #    lecturas como "movimiento extendido" con `consumido_pct` de 0,74 % de
    #    mediana y 238 de ellas sin ninguna ruptura en 1h: no eran movimientos
    #    extendidos, eran monedas quietas.
    # 2. **Un retroceso no es agotamiento.** Un pullback dentro de una
    #    tendencia viva ES, por definicion, precio por debajo de su EMA corta.
    #    Sin esta excepcion, `EXTENDIDO` se tragaba justo la familia que el
    #    plan quiere medir.
    hay_tesis_alcista = ancla_alcista or ancla_tendencia == "ALCISTA"
    en_retroceso = bool(retro.get("detectado"))
    gastado = hay_tesis_alcista and (
        taxo.get("estado") == "AGOTAMIENTO"
        or (consumido is not None and consumido >= s.alerta_consumido_max)
        or (fase in _FASES_GASTADAS and not en_retroceso))
    if gastado:
        motivo = (f"impulso {fase}" if fase in _FASES_GASTADAS
                  else (f"consumido {consumido}% del recorrido"
                        if consumido is not None and consumido >= s.alerta_consumido_max
                        else "taxonomia dice agotamiento"))
        return (EXTENDIDO, True, False,
                (f"movimiento extendido: {motivo}",
                 "se observa y se descarta; perseguirlo es la entrada tardia "
                 "que este sistema intenta dejar de hacer"),
                datos)

    # --- RUPTURA_RETEST: rompio, volvio al nivel y lo respeto -------------
    nivel = ancla.get("nivel_roto")
    if ancla_alcista and nivel and obs.precio:
        dist = (obs.precio / nivel - 1.0) * 100.0
        datos["dist_nivel_pct"] = round(dist, 3)
        volvio = 0 <= dist <= s.motores_retest_banda_pct
        if volvio:
            disparo = bool(retro.get("confirmado")) and obs.precio >= nivel
            razones = [f"el precio volvio al nivel roto de {obs.ancla_tf} "
                       f"({nivel}) y esta a {dist:+.2f} %"]
            if disparo:
                razones.append("cerro por encima del nivel con el rebote ya "
                               "confirmado desde el suelo")
            else:
                razones.append("falta el disparador: cierre sobre el nivel con "
                               "rebote confirmado (>= 1 % desde el suelo)")
            return (RUPTURA_RETEST, True, disparo, tuple(razones), datos)

    # --- RUPTURA_SOSTENIDA: el ancla rompio y el movimiento sigue vivo ----
    if ancla_alcista:
        vol = obs.vol_ratio
        vol_ok = vol is None or vol >= s.motores_vol_minimo
        disparo = (bool(ancla.get("confirmada"))
                   and fase in ("ACELERANDO", "SOSTENIDA")
                   and vol_ok
                   and obs.display_state in ("SUBIENDO", "BREAKOUT_INCIPIENTE"))
        razones = [f"ruptura alcista en {obs.ancla_tf} sobre {nivel}"
                   f" ({ancla.get('toques_nivel')} toques)"]
        if not ancla.get("confirmada"):
            razones.append("falta el disparador: el marco aun no la da por "
                           "confirmada")
        elif fase not in ("ACELERANDO", "SOSTENIDA"):
            razones.append(f"falta el disparador: el impulso esta {fase or 'sin medir'}")
        elif not vol_ok:
            razones.append(f"falta el disparador: volumen {vol}x, por debajo de "
                           f"{s.motores_vol_minimo}x")
        elif obs.display_state not in ("SUBIENDO", "BREAKOUT_INCIPIENTE"):
            razones.append(f"falta el disparador: el 1m esta en {obs.display_state}")
        else:
            razones.append("confirmada, impulso vivo y volumen suficiente")
        return (RUPTURA_SOSTENIDA, True, disparo, tuple(razones), datos)

    # --- PULLBACK_TENDENCIA: tendencia viva + retroceso medido -----------
    if ancla_tendencia == "ALCISTA" and grind.get("detected"):
        detectado = bool(retro.get("detectado"))
        datos["caida_pct"] = retro.get("caida_pct")
        datos["rebote_pct"] = retro.get("rebote_pct")
        if detectado:
            # `confirmado` = ya rebotó >= 1 % del suelo. Es la version medida:
            # 24,4 % de acierto cobrable frente a 19,5 % sin esperar.
            disparo = bool(retro.get("confirmado"))
            razones = [f"tendencia alcista viva en {obs.ancla_tf} y retroceso de "
                       f"{retro.get('caida_pct')} % desde el pico"]
            razones.append("el rebote desde el suelo ya esta confirmado"
                           if disparo else
                           "falta el disparador: el rebote desde el suelo aun "
                           "no llega al 1 %")
            return (PULLBACK_TENDENCIA, True, disparo, tuple(razones), datos)

    # --- EXPANSION_COMPRESION --------------------------------------------
    if comp.get("detected") or taxo.get("estado") in ("COMPRIMIDA", "BASE_POST_CAIDA"):
        pivot = comp.get("pivot") or taxo.get("pivot")
        datos["pivot"] = pivot
        rompio = bool(pivot and obs.precio and obs.precio > pivot)
        vol = obs.vol_ratio
        disparo = rompio and (vol is None or vol >= s.motores_vol_minimo)
        razones = [f"compresion vigente con pivote en {pivot}"]
        razones.append("el precio rompio el pivote con volumen"
                       if disparo else
                       "falta el disparador: la compresion dice CUANDO habra "
                       "movimiento, no hacia donde; se espera la expansion")
        return (EXPANSION_COMPRESION, True, disparo, tuple(razones), datos)

    return (None, False, False, ("sin tesis de continuacion en este momento",), datos)


def evaluar_continuacion(obs: Observacion) -> Lectura:
    """Funcion pura: la misma observacion da siempre la misma lectura."""
    faltan = obs.faltantes()
    if not obs.ancla or (obs.ancla.get("direccion") in (None, "SIN_DATOS")):
        faltan = faltan + (f"lectura de {obs.ancla_tf}",)
    elif (obs.ancla_edad_min is not None
            and obs.ancla_edad_min > get_settings().motores_ancla_max_edad_min):
        faltan = faltan + (f"lectura de {obs.ancla_tf} vieja "
                           f"({obs.ancla_edad_min:.0f} min)",)
    if faltan:
        return sin_datos(MOTOR_CONTINUACION, obs, faltan)

    familia, hay_tesis, disparo, razones, datos = _tesis(obs)

    if not hay_tesis:
        return Lectura(motor=MOTOR_CONTINUACION, symbol=obs.symbol, ts_ms=obs.ts_ms,
                       veredicto=SIN_TESIS, razones=razones, datos=datos,
                       precio=obs.precio)

    alc, baj = obs.marcos_en_conflicto()
    datos["marcos_alcistas"] = list(alc)
    datos["marcos_bajistas"] = list(baj)

    if disparo and obs.hay_conflicto():
        return Lectura(
            motor=MOTOR_CONTINUACION, symbol=obs.symbol, ts_ms=obs.ts_ms,
            veredicto=CONFLICTO, familia=familia, razones=razones + (
                f"disparo, pero los marcos se contradicen: suben {', '.join(alc)} "
                f"y bajan {', '.join(baj)}. No se promedia — se dice.",),
            datos=datos, precio=obs.precio)

    if disparo and not _plan_valido(obs.plan):
        return Lectura(
            motor=MOTOR_CONTINUACION, symbol=obs.symbol, ts_ms=obs.ts_ms,
            veredicto=ESPERAR, familia=familia,
            razones=razones + ("disparo, pero el plan no tiene niveles validos: "
                               "sin invalidacion no hay entrada",),
            datos=datos, precio=obs.precio)

    if disparo:
        plan = obs.plan
        return Lectura(
            motor=MOTOR_CONTINUACION, symbol=obs.symbol, ts_ms=obs.ts_ms,
            veredicto=CANDIDATO, familia=familia, disparador=True,
            razones=razones, datos=datos, precio=obs.precio,
            entrada=plan.get("entry"), objetivo=plan.get("take_profit"),
            stop=plan.get("stop_loss"))

    return Lectura(motor=MOTOR_CONTINUACION, symbol=obs.symbol, ts_ms=obs.ts_ms,
                   veredicto=ESPERAR, familia=familia, razones=razones,
                   datos=datos, precio=obs.precio)
