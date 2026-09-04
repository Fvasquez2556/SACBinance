"""
Compresion de volatilidad con conteo de CONTRACCIONES PROGRESIVAS.

Que agrega sobre `consolidation.py`
-----------------------------------
`detectar_consolidacion` mide si el ATR esta comprimido AHORA (una foto).
Esto mide la ESTRUCTURA de como se comprimio: cuenta los retrocesos
sucesivos y verifica que cada uno sea menor que el anterior (18% -> 12% ->
6%, la "regla de la mitad" de Minervini). Un rango lateral plano y una base
que se estrecha progresivamente tienen el mismo ATR bajo, pero solo el
segundo indica que la oferta se esta agotando.

ADVERTENCIA DE DIRECCION — leer antes de usar
---------------------------------------------
La compresion predice CUANDO, no HACIA DONDE. Es el resultado clasico de
Mandelbrot: los cambios grandes siguen a cambios grandes "de cualquier
signo". Los modelos de volatilidad (GARCH y familia) pronostican magnitud,
no direccion; los retornos crudos casi no tienen dependencia serial mientras
que los retornos al cuadrado si.

Por eso este detector devuelve `direccion_sesgo = "INDEFINIDA"` SIEMPRE.
Una moneda comprimida entra a vigilancia, no a compra. La direccion se
decide en el momento de la expansion, con volumen y flujo, no durante la
base. Mezclar las dos cosas es como se compran bases que rompen a la baja.

Las tasas de exito que circulan para VCP (60-70%, 90%) vienen de sitios
comerciales de formacion, no de literatura revisada. No se asumen aca.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from src.config.settings import get_settings


@dataclass
class Contraccion:
    """Un retroceso: desde un maximo pivote hasta el minimo pivote siguiente."""
    idx_alto: int
    idx_bajo: int
    precio_alto: float
    precio_bajo: float
    profundidad_pct: float
    velas: int


@dataclass
class CompressionResult:
    detected: bool = False
    score: int = 0

    n_contracciones: int = 0
    profundidades: List[float] = field(default_factory=list)  # ej [18.2, 11.5, 6.1]
    progresiva: bool = False        # cada contraccion < anterior
    regla_mitad: bool = False       # cada una ~50% de la anterior
    ratio_medio: Optional[float] = None

    atr_pct: Optional[float] = None
    atr_percentil: Optional[int] = None
    vol_dryup: Optional[float] = None      # vol ultima contraccion / primera
    rango_pct: Optional[float] = None      # ancho de la base actual
    duracion_velas: int = 0

    pivot: Optional[float] = None          # techo de la base (nivel de ruptura)
    piso: Optional[float] = None           # suelo de la base (invalidacion)
    dist_pivot_pct: Optional[float] = None # cuanto falta para romper

    direccion_sesgo: str = "INDEFINIDA"    # NUNCA cambia — ver docstring
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "detected": self.detected, "score": self.score,
            "n_contracciones": self.n_contracciones,
            "profundidades": [round(p, 2) for p in self.profundidades],
            "progresiva": self.progresiva, "regla_mitad": self.regla_mitad,
            "ratio_medio": self.ratio_medio, "atr_pct": self.atr_pct,
            "atr_percentil": self.atr_percentil, "vol_dryup": self.vol_dryup,
            "rango_pct": self.rango_pct, "duracion_velas": self.duracion_velas,
            "pivot": self.pivot, "piso": self.piso,
            "dist_pivot_pct": self.dist_pivot_pct,
            "direccion_sesgo": self.direccion_sesgo, "reason": self.reason,
        }


# =============================================================================
#  Pivotes (fractales)
# =============================================================================

def _pivotes(highs: np.ndarray, lows: np.ndarray, k: int) -> Tuple[List[int], List[int]]:
    """
    Maximos y minimos locales: extremo estricto respecto a k velas a cada lado.
    Simple y determinista; no requiere zigzag ni parametros de porcentaje.
    """
    n = highs.size
    altos, bajos = [], []
    for i in range(k, n - k):
        vh = highs[i]
        if vh == highs[i - k:i + k + 1].max() and vh > highs[i - k:i].max() \
           and vh >= highs[i + 1:i + k + 1].max():
            altos.append(i)
        vl = lows[i]
        if vl == lows[i - k:i + k + 1].min() and vl < lows[i - k:i].min() \
           and vl <= lows[i + 1:i + k + 1].min():
            bajos.append(i)
    return altos, bajos


def _contracciones(highs, lows, altos: List[int], bajos: List[int]) -> List[Contraccion]:
    """
    Empareja cada maximo pivote con el minimo pivote siguiente.
    Cada par alto->bajo es un retroceso medible.
    """
    out: List[Contraccion] = []
    for ia in altos:
        siguientes = [ib for ib in bajos if ib > ia]
        if not siguientes:
            continue
        ib = siguientes[0]
        pa, pb = float(highs[ia]), float(lows[ib])
        if pa <= 0:
            continue
        out.append(Contraccion(
            idx_alto=ia, idx_bajo=ib, precio_alto=pa, precio_bajo=pb,
            profundidad_pct=(pa - pb) / pa * 100.0, velas=ib - ia,
        ))
    # Sin solapamiento: cada contraccion arranca despues de que termino la previa
    limpio: List[Contraccion] = []
    for c in out:
        if not limpio or c.idx_alto >= limpio[-1].idx_bajo:
            limpio.append(c)
    return limpio


# =============================================================================
#  Detector
# =============================================================================

def detectar_compresion(candles: list, atr_percentil: Optional[int] = None) -> CompressionResult:
    """
    candles: buffer del TF de trabajo (15m por defecto), con .o .h .l .c .v
    atr_percentil: percentil de ATR ya calculado por detectar_consolidacion.
                   Si viene None se calcula aca.
    """
    s = get_settings()
    res = CompressionResult()

    w = s.compresion_window
    if len(candles) < w:
        res.reason = "datos insuficientes"
        return res

    v = list(candles)[-w:]
    highs = np.array([c.h for c in v], dtype=float)
    lows = np.array([c.l for c in v], dtype=float)
    closes = np.array([c.c for c in v], dtype=float)
    vols = np.array([c.v for c in v], dtype=float)
    precio = float(closes[-1])
    if precio <= 0:
        return res

    # --- ATR% y su percentil dentro de la ventana ---------------------------
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
    )
    if tr.size < s.compresion_atr_period:
        res.reason = "datos insuficientes para ATR"
        return res
    atr_series = np.convolve(tr, np.ones(s.compresion_atr_period) / s.compresion_atr_period,
                             mode="valid")
    atr_pct_series = atr_series / closes[-atr_series.size:] * 100.0
    res.atr_pct = round(float(atr_pct_series[-1]), 3)
    res.atr_percentil = (
        int(atr_percentil) if atr_percentil is not None
        else int((atr_pct_series <= atr_pct_series[-1]).mean() * 100)
    )

    # --- Contracciones progresivas ------------------------------------------
    altos, bajos = _pivotes(highs, lows, s.compresion_pivot_k)
    contras = _contracciones(highs, lows, altos, bajos)
    contras = [c for c in contras if c.profundidad_pct >= s.compresion_min_profundidad_pct]
    contras = contras[-s.compresion_max_contracciones:]

    res.n_contracciones = len(contras)
    res.profundidades = [c.profundidad_pct for c in contras]

    if len(contras) >= 2:
        ratios = [
            contras[i].profundidad_pct / contras[i - 1].profundidad_pct
            for i in range(1, len(contras))
            if contras[i - 1].profundidad_pct > 0
        ]
        if ratios:
            res.ratio_medio = round(float(np.mean(ratios)), 3)
            # Progresiva: cada una menor que la anterior (con tolerancia)
            res.progresiva = all(r <= s.compresion_ratio_max for r in ratios)
            # Regla de la mitad: ratio en una banda alrededor de 0.5
            res.regla_mitad = all(
                s.compresion_half_min <= r <= s.compresion_half_max for r in ratios
            )

    # --- Base actual: techo, piso, ancho ------------------------------------
    inicio_base = contras[0].idx_alto if contras else max(0, w - s.compresion_base_velas)
    res.duracion_velas = w - inicio_base
    res.pivot = float(highs[inicio_base:].max())
    res.piso = float(lows[inicio_base:].min())
    if res.pivot > 0:
        res.rango_pct = round((res.pivot - res.piso) / res.pivot * 100.0, 2)
        res.dist_pivot_pct = round((res.pivot - precio) / precio * 100.0, 2)

    # --- Secado de volumen ---------------------------------------------------
    if len(contras) >= 2:
        v_ini = vols[contras[0].idx_alto:contras[0].idx_bajo + 1]
        v_fin = vols[contras[-1].idx_alto:contras[-1].idx_bajo + 1]
        if v_ini.size and v_fin.size and v_ini.mean() > 0:
            res.vol_dryup = round(float(v_fin.mean() / v_ini.mean()), 3)
    if res.vol_dryup is None:
        mitad = vols[-res.duracion_velas:] if res.duracion_velas else vols
        if mitad.size >= 4:
            m = mitad.size // 2
            prim, ult = mitad[:m].mean(), mitad[m:].mean()
            res.vol_dryup = round(float(ult / prim), 3) if prim > 0 else None

    # --- Filtros duros -------------------------------------------------------
    if res.atr_percentil > s.compresion_atr_percentil_max:
        res.reason = (f"ATR en percentil {res.atr_percentil} — "
                      f"no hay compresion real")
        return res
    if res.n_contracciones < s.compresion_min_contracciones:
        res.reason = (f"solo {res.n_contracciones} contracciones "
                      f"(minimo {s.compresion_min_contracciones})")
        return res
    if not res.progresiva:
        res.reason = (f"contracciones no progresivas "
                      f"{[round(p,1) for p in res.profundidades]} — "
                      f"rango lateral, no base que se estrecha")
        return res
    if res.rango_pct is not None and res.rango_pct > s.compresion_rango_max_pct:
        res.reason = f"base demasiado ancha ({res.rango_pct}%)"
        return res

    # --- Score ---------------------------------------------------------------
    val = 40
    val += min(res.n_contracciones - s.compresion_min_contracciones, 3) * 7
    val += int(max(0, (s.compresion_atr_percentil_max - res.atr_percentil)) * 0.4)
    if res.regla_mitad:
        val += 12
    if res.vol_dryup is not None:
        if res.vol_dryup <= s.compresion_vol_dryup_max:
            val += 14                      # oferta agotandose
        elif res.vol_dryup > 1.3:
            val -= 10                      # volumen creciendo en la base: sospechoso
    # Base estrecha suma
    if res.rango_pct is not None:
        val += int(max(0.0, s.compresion_rango_max_pct - res.rango_pct) * 1.5)
    # Cerca del pivote = ruptura inminente
    if res.dist_pivot_pct is not None and res.dist_pivot_pct <= s.compresion_cerca_pivot_pct:
        val += 10

    res.score = max(0, min(100, val))
    res.detected = res.score >= s.compresion_score_min

    res.reason = (
        f"{res.n_contracciones} contracciones "
        f"{[round(p,1) for p in res.profundidades]}% "
        f"(ratio {res.ratio_medio}) | ATR p{res.atr_percentil} | "
        f"base {res.rango_pct}% | vol {res.vol_dryup}x | "
        f"pivote {res.pivot} a {res.dist_pivot_pct}% | DIRECCION INDEFINIDA"
    )
    return res
