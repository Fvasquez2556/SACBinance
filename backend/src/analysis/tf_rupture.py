"""
Lectura de ruptura POR MARCO TEMPORAL.

`ruptures.py` clasifica la ruptura del par entero a partir del estado visible,
que sale de la FSM de 1m: es la lectura de un solo marco. Aqui se repite la
pregunta en cada TF por separado —5m, 15m, 1h, 4h— contra la estructura de ESE
marco, para poder ver si lo que pasa en 1m va a favor o en contra de lo que
hacen los marcos largos.

Que es una ruptura aqui, en concreto:
  el ultimo cierre del marco queda al otro lado de un nivel que ya estaba
  validado ANTES (>= sr_min_touches toques), y la tendencia del marco no va en
  contra.

Lo que NO es: una prediccion. Esta lectura no tiene medicion propia todavia —
no ha pasado por las tres puertas de `criterios_sabado` — asi que describe lo
que ya ocurrio en el grafico y nada mas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.analysis.levels import NivelesResult, detectar_niveles
from src.analysis.ma_slopes import analizar_tf, calcular_atr_pct
from src.config.settings import get_settings

RUPTURA_ALCISTA = "RUPTURA_ALCISTA"
RUPTURA_BAJISTA = "RUPTURA_BAJISTA"
SIN_RUPTURA = "SIN_RUPTURA"
SIN_DATOS = "SIN_DATOS"

_ETIQUETAS = {
    RUPTURA_ALCISTA: "Ruptura alcista",
    RUPTURA_BAJISTA: "Ruptura bajista",
    SIN_RUPTURA: "Sin ruptura",
    SIN_DATOS: "Sin datos suficientes",
}

# Minimo para que `detectar_niveles` pueda encontrar pivotes: la ventana del
# pivote a cada lado mas margen. Se recalcula con los ajustes vigentes.
def _min_velas_niveles(s) -> int:
    return s.sr_pivot_window * 2 + 5


@dataclass
class LecturaTF:
    """Lo que se ve en un marco. Todos los campos son observaciones."""
    tf: str
    direccion: str = SIN_DATOS
    etiqueta: str = ""
    razon: str = ""
    confirmada: bool = False
    nivel_roto: Optional[float] = None
    toques_nivel: Optional[int] = None
    velas_desde_ruptura: Optional[int] = None
    distancia_nivel_pct: Optional[float] = None
    tendencia: str = "NEUTRAL"
    slope_ma7: Optional[float] = None
    slope_ma25: Optional[float] = None
    slope_ma99: Optional[float] = None
    atr_pct: Optional[float] = None
    vol_ratio: Optional[float] = None
    rsi14: Optional[float] = None
    macd_rising: Optional[bool] = None
    trend_up: Optional[bool] = None
    n_velas: int = 0
    niveles: Optional[NivelesResult] = None

    def to_dict(self) -> dict:
        return {
            "tf": self.tf,
            "direccion": self.direccion,
            "etiqueta": self.etiqueta or _ETIQUETAS.get(self.direccion, ""),
            "razon": self.razon,
            "confirmada": self.confirmada,
            "nivel_roto": self.nivel_roto,
            "toques_nivel": self.toques_nivel,
            "velas_desde_ruptura": self.velas_desde_ruptura,
            "distancia_nivel_pct": self.distancia_nivel_pct,
            "tendencia": self.tendencia,
            "slope_ma7": self.slope_ma7,
            "slope_ma25": self.slope_ma25,
            "slope_ma99": self.slope_ma99,
            "atr_pct": self.atr_pct,
            "vol_ratio": self.vol_ratio,
            "rsi14": self.rsi14,
            "macd_rising": self.macd_rising,
            "trend_up": self.trend_up,
            "n_velas": self.n_velas,
            "niveles": self.niveles.to_dict() if self.niveles is not None else None,
        }


def _cierres_mas_alla(cerradas: list, nivel: float, alcista: bool,
                      maximo: int) -> int:
    """Cuantas velas seguidas, contando desde la ultima, cerraron pasado el nivel."""
    n = 0
    for c in reversed(cerradas[-maximo:] if maximo > 0 else cerradas):
        if (c.c > nivel) if alcista else (c.c < nivel):
            n += 1
        else:
            break
    return n


def _vol_ratio(candles: list, ventana: int = 20) -> Optional[float]:
    """Volumen de la ultima vela frente a la media de las `ventana` previas."""
    if len(candles) < ventana + 1:
        return None
    previas = [c.v for c in candles[-(ventana + 1):-1]]
    media = sum(previas) / len(previas)
    if media <= 0:
        return None
    return round(candles[-1].v / media, 2)


def leer_tf(tf: str, candles: list, price: float, ind: Optional[object] = None) -> LecturaTF:
    """
    candles: buffer del marco `tf`, velas CERRADAS y en orden.
    price:   precio actual (cierre 1m mas reciente), solo para las distancias.
    ind:     IndSnap ya calculado de ese TF, si lo hay (evita recalcularlo).

    La vela en formacion se deja fuera a proposito: una ruptura se decide con
    un cierre, y una vela viva puede estar pasada del nivel a mitad de camino y
    volver antes de cerrar.
    """
    s = get_settings()
    res = LecturaTF(tf=tf, n_velas=len(candles))

    lookback = max(1, s.informe_ruptura_lookback)
    minimo = _min_velas_niveles(s) + lookback
    if len(candles) < minimo:
        res.direccion = SIN_DATOS
        res.etiqueta = _ETIQUETAS[SIN_DATOS]
        res.razon = (f"hacen falta {minimo} velas de {tf} para buscar niveles; "
                     f"hay {len(candles)}")
        return res

    # Indicadores y pendientes del marco. `analizar_tf` pide 103 velas para la
    # MA99: con menos devuelve valid=False y la tendencia se queda en NEUTRAL,
    # que es lo correcto — no se inventa direccion sin la media larga.
    tf_info = analizar_tf(candles)
    res.tendencia = tf_info.get("tendencia", "NEUTRAL")
    if tf_info.get("valid"):
        res.slope_ma7 = tf_info.get("slope_ma7")
        res.slope_ma25 = tf_info.get("slope_ma25")
        res.slope_ma99 = tf_info.get("slope_ma99")
    res.atr_pct = calcular_atr_pct(candles, s.atr_period)
    if ind is not None and getattr(ind, "valid", False):
        res.rsi14 = round(ind.rsi14, 1)
        res.macd_rising = bool(ind.macd_rising)
        res.trend_up = bool(ind.trend_up)
        res.vol_ratio = round(ind.vol_ratio, 2)
    else:
        # Sin IndSnap del marco —solo los TFs en vivo lo tienen— el volumen se
        # perdia: 14.496 de 19.565 rupturas guardadas no lo traen, y sin el no
        # se puede responder si el volumen en la ruptura sirve de algo. El
        # cociente es el mismo que calcula el indicador: ultima vela contra la
        # media de las 20 previas.
        res.vol_ratio = _vol_ratio(candles)

    # Niveles vigentes AHORA, para pintar soporte y resistencia en pantalla.
    res.niveles = detectar_niveles(candles, price if price > 0 else candles[-1].c)

    # --- La estructura ANTES de la ruptura -----------------------------------
    # El nivel se busca sobre la ventana que termina `lookback` velas atras, no
    # sobre la vela actual. Con el precio de ahora, un nivel que acaba de
    # romperse hacia arriba queda POR DEBAJO del precio y `detectar_niveles` lo
    # reparte como soporte: la ruptura se volveria invisible justo en el
    # momento en que ocurre.
    base = candles[:-lookback]
    referencia = base[-1].c
    previos = detectar_niveles(base, referencia)
    ultimo = candles[-1]

    techo = previos.resistencias[0] if previos.resistencias else None
    suelo = previos.soportes[0] if previos.soportes else None

    alcista = techo is not None and ultimo.c > techo.precio
    bajista = suelo is not None and ultimo.c < suelo.precio

    if alcista and bajista:
        # El precio salio por los dos lados dentro de la ventana: eso no es una
        # ruptura, es un latigazo. Se queda con el lado del ultimo cierre
        # respecto a la referencia y se dice que no esta confirmada.
        alcista = ultimo.c > referencia
        bajista = not alcista

    if not alcista and not bajista:
        res.direccion = SIN_RUPTURA
        res.etiqueta = _ETIQUETAS[SIN_RUPTURA]
        if techo is None and suelo is None:
            res.razon = "sin niveles validados en este marco"
        else:
            partes = []
            if techo is not None:
                partes.append(f"techo {techo.precio:.8g} intacto")
            if suelo is not None:
                partes.append(f"suelo {suelo.precio:.8g} intacto")
            res.razon = " y ".join(partes)
        return res

    nivel = techo if alcista else suelo
    res.direccion = RUPTURA_ALCISTA if alcista else RUPTURA_BAJISTA
    res.etiqueta = _ETIQUETAS[res.direccion]
    res.nivel_roto = nivel.precio
    res.toques_nivel = nivel.toques
    res.velas_desde_ruptura = _cierres_mas_alla(candles, nivel.precio, alcista, lookback)
    if nivel.precio > 0 and price > 0:
        res.distancia_nivel_pct = round((price - nivel.precio) / nivel.precio * 100.0, 2)

    # Confirmada = varios cierres del lado nuevo Y la tendencia del marco no en
    # contra. Con un solo cierre no se distingue una ruptura de una mecha larga.
    suficientes = res.velas_desde_ruptura >= max(1, s.informe_ruptura_confirm_velas)
    en_contra = (res.tendencia == "BAJISTA") if alcista else (res.tendencia == "ALCISTA")
    res.confirmada = bool(suficientes and not en_contra)

    lado = "encima" if alcista else "debajo"
    res.razon = (
        f"cierre de {tf} {lado} de {nivel.precio:.8g} ({nivel.toques} toques), "
        f"{res.velas_desde_ruptura} vela(s) sostenida(s); tendencia {res.tendencia.lower()}"
    )
    if not suficientes:
        res.razon += " — sin confirmar: falta sostenerla"
    elif en_contra:
        res.razon += " — sin confirmar: va contra la tendencia del marco"
    return res


def resumir(lecturas: List[LecturaTF]) -> dict:
    """
    Confluencia entre marcos: cuantos apuntan a cada lado y cual manda.

    "Manda" es literal: el marco mas largo con ruptura confirmada. No hay
    medicion que diga que el marco largo gane, pero cuando 4h y 5m se
    contradicen hay que enseñar los dos y decir que se contradicen, no
    promediarlos y publicar un numero limpio que oculta el desacuerdo.
    """
    orden = {"1m": 0, "5m": 1, "15m": 2, "1h": 3, "4h": 4, "1d": 5}
    alcistas = [l for l in lecturas if l.direccion == RUPTURA_ALCISTA]
    bajistas = [l for l in lecturas if l.direccion == RUPTURA_BAJISTA]
    confirmadas = [l for l in lecturas if l.confirmada]
    confirmadas.sort(key=lambda l: orden.get(l.tf, 0), reverse=True)

    dominante = confirmadas[0].direccion if confirmadas else SIN_RUPTURA
    tf_dominante = confirmadas[0].tf if confirmadas else None
    en_conflicto = bool(alcistas and bajistas)

    if en_conflicto:
        lectura = ("Los marcos se contradicen: "
                   f"{', '.join(l.tf for l in alcistas)} al alza y "
                   f"{', '.join(l.tf for l in bajistas)} a la baja.")
    elif dominante == SIN_RUPTURA:
        lectura = "Ningun marco tiene una ruptura confirmada ahora mismo."
    else:
        etiqueta = _ETIQUETAS[dominante].lower()
        lectura = (f"{etiqueta.capitalize()} confirmada en {tf_dominante}"
                   + (f" y en {', '.join(l.tf for l in confirmadas[1:])}"
                      if len(confirmadas) > 1 else "") + ".")

    return {
        "direccion_dominante": dominante,
        "tf_dominante": tf_dominante,
        "n_alcistas": len(alcistas),
        "n_bajistas": len(bajistas),
        "n_confirmadas": len(confirmadas),
        "en_conflicto": en_conflicto,
        "lectura": lectura,
    }
