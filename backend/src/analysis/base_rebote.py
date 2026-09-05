"""
Base corta post-caida y su ruptura: "flush -> base -> reclaim".

Por que no lo cubre `compression.py`
------------------------------------
`detectar_compresion` busca contracciones progresivas sobre 96 velas de 15m,
o sea 24 horas. Es el patron de acumulacion de dias. Una base de una hora no
mueve el percentil del ATR en esa ventana: en CHIPUSDT el 5-sep, con una base
de 56 minutos perfectamente formada, seguia diciendo "ATR en percentil 56, no
hay compresion real".

Este modulo mira lo mismo pero en la escala en la que ocurre: velas de 1m,
ventana de horas, no de dias.

El patron, medido sobre CHIPUSDT (5-sep-2026)
---------------------------------------------
    caida    23:30-00:05  32 min   -2.93%   vol 1m medio  6.606
    base     00:05-01:05  56 min   rango 3.01%   vol 1m medio 4.021 (61%)
    ruptura  01:11        techo 0.05811 roto con vol 15.661 = 3.9x la base
    resultado                      +2.89% sobre el techo

Las tres piezas tienen que estar. Una base sin caida previa es lateral
aburrido; una ruptura sin secado de volumen es ruido; y una caida sin base
es simplemente una caida.

Que NO hace
-----------
No predice la direccion de la ruptura: dispara CUANDO el precio ya rompio el
techo de la base al alza y con volumen. Es confirmacion temprana, no
anticipacion. Anticipar la direccion de una compresion es justo lo que la
literatura de volatilidad dice que no se puede hacer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from src.config.settings import get_settings


@dataclass
class BaseRebote:
    detected: bool = False
    score: int = 0

    # --- La caida previa ---
    caida_pct: Optional[float] = None       # % desde el pico hasta el suelo
    caida_velas: int = 0

    # --- La base ---
    base_velas: int = 0
    base_rango_pct: Optional[float] = None
    base_techo: Optional[float] = None
    base_piso: Optional[float] = None
    vol_dryup: Optional[float] = None       # vol base / vol caida

    # --- La ruptura ---
    rompio: bool = False
    ruptura_vol_ratio: Optional[float] = None   # vol de la vela / media base
    dist_techo_pct: Optional[float] = None      # cuanto pasa del techo
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "detected": self.detected, "score": self.score,
            "caida_pct": self.caida_pct, "caida_velas": self.caida_velas,
            "base_velas": self.base_velas, "base_rango_pct": self.base_rango_pct,
            "base_techo": self.base_techo, "base_piso": self.base_piso,
            "vol_dryup": self.vol_dryup, "rompio": self.rompio,
            "ruptura_vol_ratio": self.ruptura_vol_ratio,
            "dist_techo_pct": self.dist_techo_pct, "reason": self.reason,
        }


def detectar_base_rebote(candles_1m: list) -> BaseRebote:
    """
    candles_1m: buffer de velas 1m cerradas. La ultima es la que se evalua
    como posible ruptura.
    """
    s = get_settings()
    res = BaseRebote()

    minimo = s.base_lookback_velas
    if len(candles_1m) < minimo:
        res.reason = "datos insuficientes"
        return res

    v = list(candles_1m)[-minimo:]
    highs = np.array([c.h for c in v], dtype=float)
    lows = np.array([c.l for c in v], dtype=float)
    vols = np.array([c.v for c in v], dtype=float)
    precio = float(v[-1].c)
    if precio <= 0:
        return res

    # --- 1. La base: la ventana MAS LARGA que termina ahora y cabe en el
    # rango maximo. Se prueba de larga a corta y se toma la primera que
    # cumple, porque una base larga es mas significativa que una corta.
    base_ini = None
    for largo in range(s.base_max_velas, s.base_min_velas - 1, -1):
        if largo >= len(v):
            continue
        seg_hi = highs[-largo:-1].max() if largo > 1 else highs[-1]
        seg_lo = lows[-largo:-1].min() if largo > 1 else lows[-1]
        if seg_lo <= 0:
            continue
        if (seg_hi - seg_lo) / seg_lo * 100.0 <= s.base_rango_max_pct:
            base_ini = len(v) - largo
            res.base_velas = largo - 1     # sin contar la vela de ruptura
            res.base_techo = float(seg_hi)
            res.base_piso = float(seg_lo)
            res.base_rango_pct = round((seg_hi - seg_lo) / seg_lo * 100.0, 2)
            break

    if base_ini is None:
        res.reason = f"sin base: nada encaja en {s.base_rango_max_pct}% de rango"
        return res

    # --- 2. La caida previa: del pico anterior a la base hasta el piso ---
    if base_ini < s.base_caida_min_velas:
        res.reason = "no hay historial suficiente antes de la base"
        return res
    pre_hi = float(highs[:base_ini].max())
    if pre_hi <= 0:
        return res
    res.caida_pct = round((res.base_piso - pre_hi) / pre_hi * 100.0, 2)
    res.caida_velas = base_ini

    if res.caida_pct > -s.base_caida_min_pct:
        res.reason = (f"caida previa {res.caida_pct}% insuficiente "
                      f"(minimo {-s.base_caida_min_pct}%)")
        return res

    # --- 3. Secado de volumen: la base debe respirar menos que la caida ---
    vol_caida = float(vols[:base_ini].mean()) if base_ini else 0.0
    vol_base = float(vols[base_ini:-1].mean()) if res.base_velas else 0.0
    if vol_caida > 0:
        res.vol_dryup = round(vol_base / vol_caida, 2)
        if res.vol_dryup > s.base_vol_dryup_max:
            res.reason = (f"el volumen no seco en la base "
                          f"({res.vol_dryup}x, maximo {s.base_vol_dryup_max})")
            return res

    # --- 4. La ruptura: la ultima vela pasa el techo, y con volumen ---
    ultima = v[-1]
    res.rompio = ultima.h > res.base_techo
    if vol_base > 0:
        res.ruptura_vol_ratio = round(float(ultima.v) / vol_base, 2)
    res.dist_techo_pct = round((precio - res.base_techo) / res.base_techo * 100.0, 2)

    if not res.rompio:
        res.reason = (f"base formada ({res.base_velas} velas, {res.base_rango_pct}%) "
                      f"pero aun no rompe el techo {res.base_techo}")
        return res
    if (res.ruptura_vol_ratio is not None
            and res.ruptura_vol_ratio < s.base_ruptura_vol_min):
        res.reason = (f"rompe sin volumen ({res.ruptura_vol_ratio}x, "
                      f"minimo {s.base_ruptura_vol_min}x)")
        return res
    # Ya muy por encima del techo = la ruptura ocurrio hace rato
    if res.dist_techo_pct > s.base_max_sobre_techo_pct:
        res.reason = (f"ya {res.dist_techo_pct}% sobre el techo — "
                      f"la ruptura no es reciente")
        return res

    # --- Score ---
    val = 50
    val += int(min(abs(res.caida_pct) - s.base_caida_min_pct, 4) * 4)   # caida mas honda, mejor
    val += int(min(res.base_velas / 10.0, 4) * 3)                       # base mas larga, mejor
    if res.vol_dryup is not None:
        val += int(max(0.0, (s.base_vol_dryup_max - res.vol_dryup)) * 20)
    if res.ruptura_vol_ratio is not None:
        val += int(min(res.ruptura_vol_ratio - s.base_ruptura_vol_min, 4) * 4)
    # Base estrecha suma; cuanto mas cerca del techo se dispare, mejor
    val += int(max(0.0, s.base_rango_max_pct - (res.base_rango_pct or 0)) * 2)
    val -= int(max(0.0, res.dist_techo_pct) * 3)

    res.score = max(0, min(100, val))
    res.detected = res.score >= s.base_score_min
    res.reason = (
        f"caida {res.caida_pct}% | base {res.base_velas} velas rango "
        f"{res.base_rango_pct}% | vol seco a {res.vol_dryup}x | "
        f"rompe {res.base_techo} con vol {res.ruptura_vol_ratio}x | "
        f"{res.dist_techo_pct}% sobre el techo"
    )
    return res
