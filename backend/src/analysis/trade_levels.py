"""
Calculo de niveles de trading: entrada, take profit, stop loss.

Filosofia:
  - Stop loss ESTRUCTURAL: debajo del soporte real mas cercano (si se conoce)
    o del swing low reciente (15m), con buffer ATR. Si la estructura queda
    demasiado lejos, se acota a max_risk_pct.
  - Take profit por R:R: TP = entry + riesgo × rr_target. Si hay una
    resistencia entre entry y TP, se avisa (el precio debera atravesarla).
  - Solo se calcula para estados alcistas/acumulacion (largo).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.analysis.ma_slopes import calcular_atr_pct
from src.config.settings import get_settings

_OPERABLE = {"SUBIENDO", "BREAKOUT_INCIPIENTE", "TOCÓ_FONDO", "CONSOLIDANDO"}


@dataclass
class TradeLevels:
    valid: bool = False
    entry: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_reward: Optional[float] = None
    risk_pct: Optional[float] = None
    reward_pct: Optional[float] = None
    atr_pct: Optional[float] = None
    ruido_1m_pct: Optional[float] = None
    nearest_resistance: Optional[float] = None
    tp_blocked_by_resistance: bool = False
    # El nivel que SOSTIENE el stop y el que hay que ROMPER para llegar al TP.
    # Se calculaban y se tiraban: el operador veia un stop sin saber sobre que
    # se apoya, y un TP sin saber que hay en medio.
    soporte: Optional[float] = None
    toques_soporte: Optional[int] = None
    toques_resistencia: Optional[int] = None
    # ¿El TP que ofrece llega siquiera al objetivo del operador? El TP sale de
    # riesgo × rr_target, asi que en pares tranquilos se queda corto: en la
    # muestra del 5-7 sep, el 57% ofrecia menos de +3.2%.
    objetivo_alcanzable: bool = False
    reward_neto_pct: float = 0.0
    sl_basis: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "entry": self.entry,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "risk_reward": self.risk_reward,
            "risk_pct": self.risk_pct,
            "reward_pct": self.reward_pct,
            "atr_pct": self.atr_pct,
            "ruido_1m_pct": self.ruido_1m_pct,
            "objetivo_alcanzable": self.objetivo_alcanzable,
            "reward_neto_pct": self.reward_neto_pct,
            "nearest_resistance": self.nearest_resistance,
            "tp_blocked_by_resistance": self.tp_blocked_by_resistance,
            "soporte": self.soporte,
            "toques_soporte": self.toques_soporte,
            "toques_resistencia": self.toques_resistencia,
            "sl_basis": self.sl_basis,
            "reason": self.reason,
        }


def _round_price(p: float) -> float:
    if p >= 100:
        return round(p, 2)
    if p >= 1:
        return round(p, 4)
    if p >= 0.01:
        return round(p, 6)
    return round(p, 8)


def _ruido_recorrido_pct(candles_1m: list, tramo: int, paso: int,
                         alcista: bool = True) -> Optional[float]:
    """
    Recorrido tipico EN CONTRA del par: mediana del peor tramo adverso dentro
    de ventanas moviles de `tramo` minutos.

    `alcista=True` mide la caida maxima pico->valle (lo que sufre un comprador);
    `alcista=False` mide la subida maxima valle->pico (lo que sufre un vendedor).

    Por que no basta el ATR de 15m: el ATR mide el tamano de la vela, no cuanto
    se aleja el precio en contra mientras aguantas la operacion. Medido sobre
    699 senales del 5 al 7 de septiembre de 2026, el |MAE| mediano fue 1.83%
    mientras el SL mediano era 1.26%: el stop vivia dentro del ruido y saltaba
    antes del objetivo en el 33% de las senales que SI lo alcanzaban.

    Ojo con la rama bajista: esa medicion es de operaciones COMPRADORAS. La
    simetria del calculo no es una medicion de la simetria del mercado.
    """
    if len(candles_1m) < tramo + paso:
        return None
    adversos = []
    for ini in range(0, len(candles_1m) - tramo + 1, paso):
        seg = candles_1m[ini:ini + tramo]
        extremo = 0.0
        peor = 0.0
        for c in seg:
            if alcista:
                if c.h > extremo:
                    extremo = c.h
                if extremo > 0:
                    adverso = (extremo - c.l) / extremo * 100.0
                    if adverso > peor:
                        peor = adverso
            else:
                if extremo <= 0 or c.l < extremo:
                    extremo = c.l
                if extremo > 0:
                    adverso = (c.h - extremo) / extremo * 100.0
                    if adverso > peor:
                        peor = adverso
        adversos.append(peor)
    if not adversos:
        return None
    adversos.sort()
    n = len(adversos)
    return adversos[n // 2] if n % 2 else (adversos[n // 2 - 1] + adversos[n // 2]) / 2.0


def _ruido_pullback_pct(candles_1m: list, tramo: int, paso: int) -> Optional[float]:
    """Retroceso tipico del comprador. Ver `_ruido_recorrido_pct`."""
    return _ruido_recorrido_pct(candles_1m, tramo, paso, alcista=True)


def calcular_niveles(
    price: float,
    candles_15m: list,
    display_state: str,
    niveles_sr=None,
    candles_1m: Optional[list] = None,
) -> TradeLevels:
    """
    price: precio actual (cierre 1m mas reciente)
    candles_15m: buffer de velas 15m (.l, .h, .c)
    display_state: estado visible del par
    niveles_sr: NivelesResult opcional (soportes/resistencias) de levels.py
    candles_1m: buffer de velas 1m, para medir el ruido real del par
    """
    s = get_settings()
    res = TradeLevels()

    if display_state not in _OPERABLE:
        res.reason = "estado no operable (solo contexto)"
        return res
    if price <= 0 or len(candles_15m) < 20:
        res.reason = "datos insuficientes"
        return res

    atr_pct = calcular_atr_pct(candles_15m, s.atr_period)
    if atr_pct is None or atr_pct <= 0:
        res.reason = "ATR no disponible"
        return res
    atr_abs = price * atr_pct / 100.0
    res.atr_pct = round(atr_pct, 3)

    entry = price

    # --- Stop loss: prioriza soporte real, si no swing low 15m ---
    soporte = None
    if niveles_sr is not None and niveles_sr.soportes:
        soporte = niveles_sr.soportes[0].precio  # mas cercano por debajo del precio
        res.soporte = _round_price(soporte)
        res.toques_soporte = niveles_sr.soportes[0].toques

    if soporte is not None:
        stop_loss = soporte - atr_abs * s.sl_buffer_atr
        res.sl_basis = "soporte estructural"
    else:
        recent = list(candles_15m)[-s.swing_lookback_15m:]
        swing_low = min(c.l for c in recent)
        stop_loss = swing_low - atr_abs * s.sl_buffer_atr
        res.sl_basis = "swing low 15m"

    risk = entry - stop_loss

    # Riesgo minimo: el SL tiene que quedar FUERA del ruido del par, no solo
    # despegado del precio. Dos suelos, se toma el mas exigente:
    #   a) multiplo del ATR de 15m
    #   b) el retroceso tipico del par medido en 1m (ver _ruido_pullback_pct)
    min_risk = atr_abs * s.min_risk_atr
    base_min = "ATR"
    if candles_1m:
        ruido = _ruido_pullback_pct(list(candles_1m),
                                    s.sl_ruido_tramo_1m, s.sl_ruido_paso_1m)
        if ruido is not None:
            res.ruido_1m_pct = round(ruido, 2)
            ruido_abs = entry * ruido * s.sl_ruido_mult / 100.0
            if ruido_abs > min_risk:
                min_risk, base_min = ruido_abs, "ruido 1m"
    if risk < min_risk:
        risk = min_risk
        stop_loss = entry - risk
        res.sl_basis = f"riesgo minimo ({base_min})"

    # Riesgo maximo. Antes se acotaba en silencio, y ese recorte volvia a meter
    # el stop dentro del ruido: el par pedia mas margen del permitido y se le
    # daba igual un stop que no aguanta. Si no cabe, no se emite.
    max_risk = entry * s.max_risk_pct / 100.0
    if risk > max_risk:
        res.risk_pct = round(risk / entry * 100.0, 2)
        res.reason = (f"SL fuera del ruido exigiria {res.risk_pct}% de riesgo, "
                      f"por encima del maximo {s.max_risk_pct}% — no se emite")
        return res

    # --- Take profit por R:R objetivo ---
    take_profit = entry + risk * s.rr_target

    # --- Resistencia entre entry y TP ---
    if niveles_sr is not None and niveles_sr.resistencias:
        r = niveles_sr.resistencias[0].precio  # mas cercana por encima
        res.nearest_resistance = _round_price(r)
        res.toques_resistencia = niveles_sr.resistencias[0].toques
        if entry < r < take_profit:
            res.tp_blocked_by_resistance = True

    res.valid = True
    res.entry = _round_price(entry)
    res.stop_loss = _round_price(stop_loss)
    res.take_profit = _round_price(take_profit)
    res.risk_pct = round(risk / entry * 100.0, 2)
    res.reward_pct = round((take_profit - entry) / entry * 100.0, 2)
    res.risk_reward = round(s.rr_target, 2)
    # NETO, no bruto. Cobrar un TP de +2.5% con 0.5% de costes deja +2.0%, y
    # el objetivo del operador son +3.2%. Comparar el bruto con el objetivo
    # hacia pasar por "alcanzable" a señales que no podian serlo.
    res.reward_neto_pct = round(res.reward_pct - s.coste_operacion_pct, 2)
    res.objetivo_alcanzable = res.reward_neto_pct >= s.objetivo_operador_pct

    aviso = " | OJO: resistencia antes del TP" if res.tp_blocked_by_resistance else ""
    res.reason = (
        f"SL: {res.sl_basis} | ATR15m={atr_pct:.2f}% | "
        + (f"ruido1m={res.ruido_1m_pct}% | " if res.ruido_1m_pct is not None else "") +
        f"riesgo={res.risk_pct}% beneficio={res.reward_pct}% "
        f"(neto {res.reward_neto_pct}%) R:R={res.risk_reward}{aviso}"
    )
    return res


# --- Plan direccional por marco temporal --------------------------------------
# `calcular_niveles` es del tablero: siempre comprador, siempre sobre 15m, y con
# la entrada clavada al precio. Esto es para la consulta manual de un par, donde
# la ruptura la marca el marco (ver `tf_rupture.py`) y hay dos diferencias que
# no son cosmeticas:
#
#   1. La entrada es un RANGO, no un precio. Entrar al precio de la señal es
#      justo lo unico que se midio con el intervalo entero por debajo de cero:
#      -0.26%/op, IC 95% [-0.40, -0.11] sobre 1347 señales (9-sep-2026). Comprar
#      mas abajo mejoro ~0.47 puntos, y el mecanismo medido fue ARITMETICO — el
#      objetivo en precio queda mas cerca — no mayor acierto. El rango va del
#      nivel roto (el retest) al precio actual: es estructura del propio marco,
#      no un descuento inventado.
#   2. Admite direccion bajista. Y hay que decirlo cada vez: TODO lo medido en
#      este proyecto es comprador. Un plan vendedor aqui es aritmetica sobre la
#      estructura, sin una sola operacion medida detras.

_DIR_ALCISTA = "RUPTURA_ALCISTA"
_DIR_BAJISTA = "RUPTURA_BAJISTA"

_AVISO_BAJISTA = (
    "Direccion bajista: este proyecto no tiene ninguna medicion de operaciones "
    "vendedoras. Los niveles son aritmetica sobre la estructura, no una ventaja "
    "demostrada."
)


@dataclass
class PlanDireccional:
    valid: bool = False
    direccion: str = ""
    tf: str = ""
    # Rango de entrada. `entrada_ref` es el extremo MALO (entrar a mercado
    # ahora). Riesgo y beneficio se miden ahi para no adornarlos con un relleno
    # mejor que quiza no ocurra.
    entrada_min: Optional[float] = None
    entrada_max: Optional[float] = None
    entrada_ref: Optional[float] = None
    rango_pct: Optional[float] = None
    mejora_max_pct: Optional[float] = None
    rellena_en_retest: bool = False
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_pct: Optional[float] = None
    reward_pct: Optional[float] = None
    reward_neto_pct: Optional[float] = None
    risk_reward: Optional[float] = None
    atr_pct: Optional[float] = None
    ruido_1m_pct: Optional[float] = None
    sl_basis: str = ""
    nivel_estorbo: Optional[float] = None
    # El nivel estructural sobre el que se apoya el stop de ESTE marco.
    nivel_apoyo: Optional[float] = None
    toques_apoyo: Optional[int] = None
    tp_bloqueado: bool = False
    objetivo_alcanzable: bool = False
    advertencia: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "direccion": self.direccion,
            "tf": self.tf,
            "entrada_min": self.entrada_min,
            "entrada_max": self.entrada_max,
            "entrada_ref": self.entrada_ref,
            "rango_pct": self.rango_pct,
            "mejora_max_pct": self.mejora_max_pct,
            "rellena_en_retest": self.rellena_en_retest,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_pct": self.risk_pct,
            "reward_pct": self.reward_pct,
            "reward_neto_pct": self.reward_neto_pct,
            "risk_reward": self.risk_reward,
            "atr_pct": self.atr_pct,
            "ruido_1m_pct": self.ruido_1m_pct,
            "sl_basis": self.sl_basis,
            "nivel_estorbo": self.nivel_estorbo,
            "nivel_apoyo": self.nivel_apoyo,
            "toques_apoyo": self.toques_apoyo,
            "tp_bloqueado": self.tp_bloqueado,
            "objetivo_alcanzable": self.objetivo_alcanzable,
            "advertencia": self.advertencia,
            "reason": self.reason,
        }


def _nivel_estructural(niveles_sr, limite: float, debajo: bool):
    """Primer nivel validado estrictamente por debajo (o por encima) de `limite`."""
    if niveles_sr is None:
        return None
    candidatos = niveles_sr.soportes if debajo else niveles_sr.resistencias
    for n in candidatos or ():
        if (n.precio < limite) if debajo else (n.precio > limite):
            return n
    return None


def calcular_plan_direccional(
    direccion: str,
    price: float,
    candles_tf: list,
    nivel_roto: Optional[float],
    tf: str = "15m",
    niveles_sr=None,
    candles_1m: Optional[list] = None,
) -> PlanDireccional:
    """
    direccion:  RUPTURA_ALCISTA | RUPTURA_BAJISTA (ver `tf_rupture.py`)
    price:      precio actual
    candles_tf: buffer del marco que marco la ruptura (da el ATR y la escala)
    nivel_roto: el nivel que el precio atraveso; ancla el rango y el stop
    niveles_sr: NivelesResult de ese mismo marco
    candles_1m: buffer de 1m para el suelo de ruido del stop

    El ATR sale del MARCO de la ruptura, asi que un plan de 4h nace con un stop
    y un objetivo de 4h. Es lo que se pidio, pero conviene saber lo que implica:
    el seguimiento de este sistema cierra a las 24h y un objetivo de 4h puede
    tardar dias. Un plan de 4h no esta medido por la maquinaria que mide los
    de 1m.
    """
    s = get_settings()
    res = PlanDireccional(direccion=direccion, tf=tf)
    alcista = direccion == _DIR_ALCISTA
    if not alcista:
        res.advertencia = _AVISO_BAJISTA

    if direccion not in (_DIR_ALCISTA, _DIR_BAJISTA):
        res.reason = "sin direccion de ruptura: no hay plan que calcular"
        return res
    if price <= 0 or len(candles_tf) < 20:
        res.reason = "datos insuficientes en este marco"
        return res
    if nivel_roto is None or nivel_roto <= 0:
        res.reason = "sin nivel roto: el rango de entrada no tiene donde anclarse"
        return res

    atr_pct = calcular_atr_pct(candles_tf, s.atr_period)
    if atr_pct is None or atr_pct <= 0:
        res.reason = f"ATR de {tf} no disponible"
        return res
    atr_abs = price * atr_pct / 100.0
    res.atr_pct = round(atr_pct, 3)

    # --- Rango de entrada -----------------------------------------------------
    # Del nivel roto al precio actual, acotado por informe_rango_max_pct: si el
    # precio ya se fue muy lejos del nivel, el rango entero deja de ser una
    # entrada y pasa a ser una apuesta a que vuelva.
    tope = price * (1.0 + s.informe_rango_max_pct / 100.0)
    piso = price * (1.0 - s.informe_rango_max_pct / 100.0)
    if alcista:
        entrada_max = price
        entrada_min = min(price, max(nivel_roto, piso))
    else:
        entrada_min = price
        entrada_max = max(price, min(nivel_roto, tope))
    entrada_ref = price   # el extremo malo en las dos direcciones: fill a mercado

    # --- Stop loss ------------------------------------------------------------
    # Primero la estructura del marco; si no hay nivel mas alla del rango, el
    # propio nivel roto, que es lo que tiene que aguantar para que la ruptura
    # siga siendo ruptura.
    if alcista:
        soporte = _nivel_estructural(niveles_sr, entrada_min, debajo=True)
        base = soporte.precio if soporte is not None else min(nivel_roto, entrada_min)
        res.sl_basis = "soporte estructural" if soporte is not None else "nivel roto (retest)"
        res.nivel_apoyo = _round_price(base)
        res.toques_apoyo = soporte.toques if soporte is not None else None
        stop_loss = base - atr_abs * s.sl_buffer_atr
        risk = entrada_ref - stop_loss
    else:
        resistencia = _nivel_estructural(niveles_sr, entrada_max, debajo=False)
        base = resistencia.precio if resistencia is not None else max(nivel_roto, entrada_max)
        res.nivel_apoyo = _round_price(base)
        res.toques_apoyo = resistencia.toques if resistencia is not None else None
        res.sl_basis = ("resistencia estructural" if resistencia is not None
                        else "nivel roto (retest)")
        stop_loss = base + atr_abs * s.sl_buffer_atr
        risk = stop_loss - entrada_ref

    # Suelo de riesgo: el stop fuera del ruido, igual que en `calcular_niveles`.
    min_risk = atr_abs * s.min_risk_atr
    base_min = "ATR"
    if candles_1m:
        ruido = _ruido_recorrido_pct(list(candles_1m), s.sl_ruido_tramo_1m,
                                     s.sl_ruido_paso_1m, alcista=alcista)
        if ruido is not None:
            res.ruido_1m_pct = round(ruido, 2)
            ruido_abs = entrada_ref * ruido * s.sl_ruido_mult / 100.0
            if ruido_abs > min_risk:
                min_risk, base_min = ruido_abs, "ruido 1m"
    if risk < min_risk:
        risk = min_risk
        stop_loss = entrada_ref - risk if alcista else entrada_ref + risk
        res.sl_basis = f"riesgo minimo ({base_min})"

    # Techo de riesgo: si el stop honesto no cabe, no se emite plan. Recortarlo
    # en silencio es volver a meter el stop dentro del ruido.
    max_risk = entrada_ref * s.max_risk_pct / 100.0
    if risk > max_risk:
        res.risk_pct = round(risk / entrada_ref * 100.0, 2)
        res.reason = (f"el stop fuera del ruido pediria {res.risk_pct}% de riesgo, "
                      f"por encima del maximo {s.max_risk_pct}% — no se emite plan")
        return res

    # El rango no puede acercarse al stop: una entrada pegada al stop nace
    # muerta. Se le deja como minimo un cuarto del riesgo de margen.
    if alcista:
        entrada_min = min(max(entrada_min, stop_loss + risk * 0.25), entrada_max)
    else:
        entrada_max = max(min(entrada_max, stop_loss - risk * 0.25), entrada_min)

    take_profit = (entrada_ref + risk * s.rr_target) if alcista \
        else (entrada_ref - risk * s.rr_target)

    # --- Estorbo en el camino -------------------------------------------------
    estorbo = _nivel_estructural(niveles_sr, entrada_ref, debajo=not alcista)
    if estorbo is not None:
        dentro = (entrada_ref < estorbo.precio < take_profit) if alcista \
            else (take_profit < estorbo.precio < entrada_ref)
        res.nivel_estorbo = _round_price(estorbo.precio)
        res.tp_bloqueado = bool(dentro)

    res.valid = True
    res.entrada_min = _round_price(entrada_min)
    res.entrada_max = _round_price(entrada_max)
    res.entrada_ref = _round_price(entrada_ref)
    res.stop_loss = _round_price(stop_loss)
    res.take_profit = _round_price(take_profit)
    res.risk_pct = round(risk / entrada_ref * 100.0, 2)
    res.reward_pct = round(abs(take_profit - entrada_ref) / entrada_ref * 100.0, 2)
    res.risk_reward = round(s.rr_target, 2)
    res.rango_pct = round((entrada_max - entrada_min) / entrada_ref * 100.0, 2)
    # Cuanto mejora entrar en el extremo bueno del rango en vez de a mercado.
    # Es aritmetica pura: acerca el objetivo en precio. NO sube el acierto —
    # eso se midio: la probabilidad de subir +3.2% es plana en ~27% haya bajado
    # antes 0.5% o 5%.
    mejor = entrada_min if alcista else entrada_max
    res.mejora_max_pct = round(abs(entrada_ref - mejor) / entrada_ref * 100.0, 2)
    res.rellena_en_retest = res.mejora_max_pct > 0.05
    # NETO, no bruto: cobrar el TP deja el bruto menos costes.
    res.reward_neto_pct = round(res.reward_pct - s.coste_operacion_pct, 2)
    res.objetivo_alcanzable = res.reward_neto_pct >= s.objetivo_operador_pct

    aviso = " | OJO: nivel de por medio antes del TP" if res.tp_bloqueado else ""
    res.reason = (
        f"SL: {res.sl_basis} | ATR{tf}={atr_pct:.2f}% | "
        + (f"ruido1m={res.ruido_1m_pct}% | " if res.ruido_1m_pct is not None else "")
        + f"riesgo={res.risk_pct}% beneficio={res.reward_pct}% "
          f"(neto {res.reward_neto_pct}%) R:R={res.risk_reward}{aviso}"
    )
    return res
