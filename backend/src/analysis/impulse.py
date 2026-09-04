"""
Fuerza del impulso: no cuanto subio, sino si SIGUE subiendo.

El problema que resuelve
------------------------
El score del sistema mide magnitud: z_rise, velocidad, volumen, flujo. Todos
responden "¿esta subiendo mucho?". Ninguno responde "¿el impulso gana o pierde
fuerza?", que es una derivada, no un nivel.

Por eso una moneda podia entrar como FUERTE justo cuando el movimiento se
estaba apagando: los cuerpos de vela encogiendose, el volumen secandose y el
precio haciendo maximos cada vez mas planos siguen dando un z_rise alto,
porque el z mira el retorno acumulado, no su tendencia.

Como se mide
------------
Sobre cada TF (1m, 3m derivado, 5m) se parte la ventana en dos mitades y se
comparan:

    aceleracion    ROC de la mitad reciente / ROC de la mitad previa
    cuerpo_ratio   tamaño medio del cuerpo reciente / previo
    vol_ratio      volumen medio reciente / previo

Un impulso sano tiene los tres >= 1. Cuando los cuerpos encogen y el volumen
se seca mientras el precio aun sube, el movimiento se esta agotando: es
distribucion, no continuacion.

Las cuatro fases
----------------
    ACELERANDO      gana fuerza: cuerpos y volumen creciendo
    SOSTENIDA       mantiene el ritmo sin acelerar
    DESACELERANDO   pierde fuerza de forma medible
    AGOTADA         techo: perdio la EMA rapida, o climax de volumen con
                    maximos planos, o RSI girando desde sobrecompra

El 3m no viene de Binance: se agrega desde las velas 1m del propio buffer.
Es exacto (3 velas de 1m alineadas = 1 de 3m) y no cuesta otro stream.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from src.config.settings import get_settings
from src.utils.fastmath import ema as _ema

FASE_ACELERANDO = "ACELERANDO"
FASE_SOSTENIDA = "SOSTENIDA"
FASE_DESACELERANDO = "DESACELERANDO"
FASE_AGOTADA = "AGOTADA"
FASE_SIN_DATOS = "SIN_DATOS"

# Fases que dejan pasar una alerta nueva (modo equilibrado)
FASES_OK = (FASE_ACELERANDO, FASE_SOSTENIDA)

_ORDEN = {
    FASE_ACELERANDO: 3, FASE_SOSTENIDA: 2,
    FASE_DESACELERANDO: 1, FASE_AGOTADA: 0, FASE_SIN_DATOS: -1,
}


@dataclass
class TFImpulse:
    """Medida de impulso sobre un timeframe concreto."""
    tf: str
    valid: bool = False
    roc_reciente: float = 0.0     # % de la mitad reciente
    roc_previo: float = 0.0
    aceleracion: Optional[float] = None
    cuerpo_ratio: Optional[float] = None
    vol_ratio: Optional[float] = None
    verdes_reciente: float = 0.0
    sobre_ema: bool = False
    maximos_planos: bool = False

    def to_dict(self) -> dict:
        return {
            "tf": self.tf, "valid": self.valid,
            "roc_reciente": round(self.roc_reciente, 3),
            "roc_previo": round(self.roc_previo, 3),
            "aceleracion": round(self.aceleracion, 2) if self.aceleracion is not None else None,
            "cuerpo_ratio": round(self.cuerpo_ratio, 2) if self.cuerpo_ratio is not None else None,
            "vol_ratio": round(self.vol_ratio, 2) if self.vol_ratio is not None else None,
            "verdes": round(self.verdes_reciente, 2),
            "sobre_ema": self.sobre_ema,
            "maximos_planos": self.maximos_planos,
        }


@dataclass
class ImpulseResult:
    valid: bool = False
    fuerza: int = 0                       # 0-100
    fase: str = FASE_SIN_DATOS
    aceleracion: Optional[float] = None   # media ponderada entre TFs
    cuerpo_ratio: Optional[float] = None
    vol_ratio: Optional[float] = None
    consumido_pct: Optional[float] = None  # % ya recorrido desde el minimo
    caida_acelerando: bool = False          # cuchillo cayendo (para fondos)
    por_tf: dict = field(default_factory=dict)
    reason: str = ""

    @property
    def permite_alerta(self) -> bool:
        return self.fase in FASES_OK

    def to_dict(self) -> dict:
        return {
            "valid": self.valid, "fuerza": self.fuerza, "fase": self.fase,
            "aceleracion": round(self.aceleracion, 2) if self.aceleracion is not None else None,
            "cuerpo_ratio": round(self.cuerpo_ratio, 2) if self.cuerpo_ratio is not None else None,
            "vol_ratio": round(self.vol_ratio, 2) if self.vol_ratio is not None else None,
            "consumido_pct": self.consumido_pct,
            "caida_acelerando": self.caida_acelerando,
            "por_tf": {k: v.to_dict() for k, v in self.por_tf.items()},
            "reason": self.reason,
        }


def agregar(candles_1m: list, factor: int) -> list:
    """
    Agrega velas 1m en velas de `factor` minutos, alineadas al reloj (una vela
    de 3m empieza en un minuto multiplo de 3). Sin alinear, los cuerpos y
    volumenes saldrian repartidos de forma arbitraria y la comparacion entre
    mitades no significaria nada.

    Devuelve objetos con los mismos atributos que Candle (.t .o .h .l .c .v).
    """
    if not candles_1m:
        return []
    paso_ms = factor * 60_000
    out: List[_Agg] = []
    for c in candles_1m:
        inicio = c.t - (c.t % paso_ms)
        if out and out[-1].t == inicio:
            a = out[-1]
            a.h = max(a.h, c.h)
            a.l = min(a.l, c.l)
            a.c = c.c
            a.v += c.v
        else:
            out.append(_Agg(t=inicio, o=c.o, h=c.h, l=c.l, c=c.c, v=c.v))
    return out


@dataclass
class _Agg:
    t: int
    o: float
    h: float
    l: float
    c: float
    v: float


def _medir_tf(tf: str, candles: list, ventana: int) -> TFImpulse:
    """Compara la mitad reciente de la ventana contra la previa."""
    res = TFImpulse(tf=tf)
    if len(candles) < ventana + 8:
        return res

    v = list(candles)[-ventana:]
    mitad = ventana // 2
    prev, rec = v[:mitad], v[mitad:]

    closes = np.array([c.c for c in v], dtype=float)
    if np.any(closes <= 0):
        return res

    def _roc(seg):
        base = seg[0].o
        return (seg[-1].c - base) / base * 100.0 if base > 0 else 0.0

    def _cuerpo(seg):
        return float(np.mean([abs(c.c - c.o) / c.o for c in seg if c.o > 0])) * 100.0

    def _vol(seg):
        return float(np.mean([c.v for c in seg]))

    res.roc_previo = _roc(prev)
    res.roc_reciente = _roc(rec)
    cp, cr = _cuerpo(prev), _cuerpo(rec)
    vp, vr = _vol(prev), _vol(rec)

    # Aceleracion solo tiene sentido si la mitad previa subia. Si venia plana o
    # bajando, un ROC reciente positivo ya es aceleracion por definicion.
    if res.roc_previo > 0.01:
        res.aceleracion = res.roc_reciente / res.roc_previo
    elif res.roc_reciente > 0:
        res.aceleracion = 2.0
    else:
        res.aceleracion = 0.0

    res.cuerpo_ratio = (cr / cp) if cp > 0 else None
    res.vol_ratio = (vr / vp) if vp > 0 else None
    res.verdes_reciente = float(np.mean([1.0 if c.c > c.o else 0.0 for c in rec]))

    # Precio sobre la EMA rapida: perderla es la señal mas limpia de que el
    # tramo se acabo.
    closes_full = np.array([c.c for c in candles], dtype=float)
    ema7 = _ema(closes_full, 7)
    res.sobre_ema = bool(closes_full[-1] >= ema7[-1])

    # Maximos planos: el ultimo tercio no supera el maximo del tramo anterior
    highs = np.array([c.h for c in v], dtype=float)
    t = max(2, ventana // 3)
    res.maximos_planos = bool(highs[-t:].max() <= highs[:-t].max())

    res.valid = True
    return res


def medir_impulso(candles_1m: list, ind=None) -> ImpulseResult:
    """
    candles_1m: buffer de velas 1m cerradas (el 3m y el 5m se derivan de el).
    ind: IndSnap de 1m, opcional (RSI/MACD refuerzan la deteccion de techo).
    """
    s = get_settings()
    res = ImpulseResult()

    if len(candles_1m) < s.impulso_min_velas:
        res.reason = "datos insuficientes"
        return res

    series = {
        "1m": (list(candles_1m), s.impulso_ventana_1m),
        "3m": (agregar(candles_1m, 3), s.impulso_ventana_3m),
        "5m": (agregar(candles_1m, 5), s.impulso_ventana_5m),
    }
    pesos = {"1m": s.impulso_peso_1m, "3m": s.impulso_peso_3m, "5m": s.impulso_peso_5m}

    validos = {}
    for tf, (velas, ventana) in series.items():
        m = _medir_tf(tf, velas, ventana)
        res.por_tf[tf] = m
        if m.valid:
            validos[tf] = m

    if not validos:
        res.reason = "ningun timeframe evaluable"
        return res

    # --- Medias ponderadas entre TFs ---
    def _pond(attr):
        num = den = 0.0
        for tf, m in validos.items():
            val = getattr(m, attr)
            if val is not None:
                num += val * pesos[tf]
                den += pesos[tf]
        return num / den if den > 0 else None

    res.aceleracion = _pond("aceleracion")
    res.cuerpo_ratio = _pond("cuerpo_ratio")
    res.vol_ratio = _pond("vol_ratio")

    # --- Recorrido consumido desde el minimo reciente ---
    v = list(candles_1m)[-s.impulso_lookback_consumido:]
    minimo = min(c.l for c in v)
    precio = candles_1m[-1].c
    if minimo > 0:
        res.consumido_pct = round((precio - minimo) / minimo * 100.0, 2)

    # --- Caida acelerando (cuchillo) ---
    # Es el espejo de la aceleracion alcista, y el unico criterio de impulso
    # que tiene sentido en un fondo: no "¿se apaga la subida?" sino "¿la
    # caida todavia va a mas?". Se mide sobre los TFs lentos, que es donde
    # una caida sostenida se distingue de una mecha de un minuto.
    bajistas = [m for m in validos.values() if m.tf in ("3m", "5m")]
    if bajistas:
        res.caida_acelerando = all(
            m.roc_reciente < 0 and m.roc_reciente < m.roc_previo for m in bajistas
        )

    # --- Fase ---
    res.fase, motivos = _clasificar_fase(res, validos, ind, s)
    res.fuerza = _puntuar(res, validos, s)
    res.valid = True
    res.reason = " | ".join(motivos) if motivos else res.fase.lower()
    return res


def _clasificar_fase(res: ImpulseResult, validos: dict, ind, s) -> tuple:
    motivos: List[str] = []

    acel = res.aceleracion if res.aceleracion is not None else 1.0
    cuerpo = res.cuerpo_ratio if res.cuerpo_ratio is not None else 1.0
    vol = res.vol_ratio if res.vol_ratio is not None else 1.0

    # --- AGOTADA: señales de techo ---
    perdio_ema = sum(1 for m in validos.values() if not m.sobre_ema)
    planos = sum(1 for m in validos.values() if m.maximos_planos)

    if perdio_ema >= 2:
        motivos.append(f"precio bajo la EMA7 en {perdio_ema} TFs")
        return FASE_AGOTADA, motivos
    if planos >= 2 and cuerpo < 1.0:
        motivos.append(f"maximos planos en {planos} TFs con cuerpos encogiendo")
        return FASE_AGOTADA, motivos
    if ind is not None and getattr(ind, "valid", False):
        if ind.rsi5 >= s.impulso_rsi_techo and not ind.macd_rising:
            motivos.append(f"RSI {ind.rsi5:.0f} girando con MACD cayendo")
            return FASE_AGOTADA, motivos
    if res.consumido_pct is not None and res.consumido_pct >= s.impulso_consumido_agotado:
        motivos.append(f"{res.consumido_pct}% ya recorrido desde el minimo")
        return FASE_AGOTADA, motivos

    # --- DESACELERANDO: pierde fuerza de forma medible ---
    # Se exigen DOS de las tres señales: una sola es ruido de una vela.
    flojas = 0
    if acel < s.impulso_acel_min:
        flojas += 1
        motivos.append(f"aceleracion {acel:.2f}")
    if cuerpo < s.impulso_cuerpo_min:
        flojas += 1
        motivos.append(f"cuerpos {cuerpo:.2f}x")
    if vol < s.impulso_vol_min:
        flojas += 1
        motivos.append(f"volumen {vol:.2f}x")
    if flojas >= 2:
        return FASE_DESACELERANDO, motivos

    # --- ACELERANDO ---
    if acel >= s.impulso_acel_fuerte and cuerpo >= 1.0 and vol >= 1.0:
        return FASE_ACELERANDO, [f"acel {acel:.2f} cuerpos {cuerpo:.2f}x vol {vol:.2f}x"]

    return FASE_SOSTENIDA, motivos


def _puntuar(res: ImpulseResult, validos: dict, s) -> int:
    """Fuerza 0-100. Es una lectura continua; la decision la toma la fase."""
    base = {FASE_ACELERANDO: 75, FASE_SOSTENIDA: 55,
            FASE_DESACELERANDO: 30, FASE_AGOTADA: 10}.get(res.fase, 0)

    acel = res.aceleracion if res.aceleracion is not None else 1.0
    cuerpo = res.cuerpo_ratio if res.cuerpo_ratio is not None else 1.0
    vol = res.vol_ratio if res.vol_ratio is not None else 1.0

    base += int(max(-12, min(12, (acel - 1.0) * 12)))
    base += int(max(-8, min(8, (cuerpo - 1.0) * 10)))
    base += int(max(-6, min(6, (vol - 1.0) * 6)))

    verdes = float(np.mean([m.verdes_reciente for m in validos.values()])) if validos else 0.0
    base += int((verdes - 0.5) * 10)

    # Cuanto mas recorrido lleva, menos margen queda
    if res.consumido_pct is not None:
        if res.consumido_pct > s.impulso_consumido_penaliza:
            base -= int(min(15, (res.consumido_pct - s.impulso_consumido_penaliza) * 2))

    return max(0, min(100, base))


def fase_peor_que(a: str, b: str) -> bool:
    """True si la fase `a` es peor que `b` (para detectar degradacion)."""
    return _ORDEN.get(a, -1) < _ORDEN.get(b, -1)
