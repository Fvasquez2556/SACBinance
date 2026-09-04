"""
Ancla diaria FIJA: open de la vela 1d de Binance (00:00 UTC).

Por que existe este modulo
--------------------------
El "%Cambio 24h" que muestra Binance en su Clasificacion es una ventana
ROLLING: compara el precio de ahora contra el de hace exactamente 24 horas.
Ese denominador se mueve solo, minuto a minuto, asi que el numero cambia
aunque el precio no haga nada. No sirve como referencia estable.

El ancla fija resuelve eso: durante todo el dia UTC el denominador es el
mismo (el open de las 00:00), asi que el % es comparable consigo mismo a lo
largo del dia y entre monedas.

De donde sale el open del dia EN CURSO
--------------------------------------
El buffer 1d solo tiene velas CERRADAS (rest_periodic descarga al cierre),
asi que la vela de hoy no esta ahi. Se deriva del buffer 1h, que con 180
velas cubre ~7.5 dias: se busca la vela cuyo open_time sea exactamente el
inicio del dia UTC. Fallback en cascada a 15m / 5m / 1m.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_DAY_MS = 86_400_000
_TF_FALLBACK = ("1h", "15m", "5m", "1m")


@dataclass
class DailyAnchor:
    valid: bool = False
    open_price: Optional[float] = None       # open 00:00 UTC del dia en curso
    pct_from_open: Optional[float] = None    # % del precio actual vs ese open
    high_day: Optional[float] = None
    low_day: Optional[float] = None
    pos_in_day_range: Optional[float] = None  # 0 = minimo del dia, 1 = maximo
    day_start_ms: int = 0
    source_tf: str = ""
    candles_used: int = 0

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "open_diario": self.open_price,
            "pct_desde_open_diario": self.pct_from_open,
            "high_dia": self.high_day,
            "low_dia": self.low_day,
            "pos_en_rango_diario": self.pos_in_day_range,
            "day_start_ms": self.day_start_ms,
            "anchor_tf": self.source_tf,
        }


def inicio_dia_utc(now_ms: int) -> int:
    """Timestamp ms del ultimo 00:00 UTC."""
    return now_ms - (now_ms % _DAY_MS)


def calcular_ancla(st, price: float, now_ms: int) -> DailyAnchor:
    """
    st: SymbolState (usa candles_tf_live para incluir la vela en formacion)
    price: precio actual (cierre 1m mas reciente)
    """
    res = DailyAnchor()
    if price <= 0:
        return res

    day_start = inicio_dia_utc(now_ms)
    res.day_start_ms = day_start

    for tf in _TF_FALLBACK:
        try:
            candles = st.candles_tf_live(tf)
        except AttributeError:
            candles = list(st.get_candles_tf(tf))
        if not candles:
            continue

        # Velas del dia en curso (open_time >= 00:00 UTC de hoy)
        del_dia = [c for c in candles if c.t >= day_start]
        if not del_dia:
            continue

        primera = del_dia[0]
        # En 1h/15m/5m/1m el primer open_time del dia debe caer exacto en
        # day_start. Si no coincide, el buffer no alcanza hasta las 00:00 y
        # el "open" seria en realidad el de media manana -> se descarta.
        if primera.t != day_start and tf != "1m":
            continue

        res.open_price = primera.o
        res.high_day = max(c.h for c in del_dia)
        res.low_day = min(c.l for c in del_dia)
        res.source_tf = tf
        res.candles_used = len(del_dia)
        break

    if res.open_price is None or res.open_price <= 0:
        return res

    # El precio vivo puede haber superado el rango de las velas cerradas
    res.high_day = max(res.high_day or price, price)
    res.low_day = min(res.low_day or price, price)

    res.pct_from_open = (price - res.open_price) / res.open_price * 100.0
    rng = res.high_day - res.low_day
    res.pos_in_day_range = (price - res.low_day) / rng if rng > 0 else 0.5
    res.valid = True

    # Redondeo de presentacion
    res.pct_from_open = round(res.pct_from_open, 3)
    res.pos_in_day_range = round(res.pos_in_day_range, 3)
    return res
