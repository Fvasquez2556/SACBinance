"""
Deteccion de niveles de soporte y resistencia.

Metodo: pivotes locales (swing highs / lows) sobre velas de TF medio.
Un pivote es una vela cuyo extremo supera al de las N velas vecinas a cada
lado. Los pivotes cercanos (dentro de sr_cluster_pct%) se agrupan en un nivel;
un nivel con >= sr_min_touches toques se considera estructural.

Uso:
  - Stop loss mas inteligente (debajo del soporte real, no solo del swing low)
  - Avisar si un breakout choca contra una resistencia cercana
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.config.settings import get_settings


@dataclass
class Nivel:
    precio: float
    toques: int

    def to_dict(self) -> dict:
        return {"precio": self.precio, "toques": self.toques}


@dataclass
class NivelesResult:
    soportes: List[Nivel] = field(default_factory=list)      # ordenados: mas cercano primero
    resistencias: List[Nivel] = field(default_factory=list)  # ordenados: mas cercana primero

    def to_dict(self) -> dict:
        return {
            "soportes": [n.to_dict() for n in self.soportes],
            "resistencias": [n.to_dict() for n in self.resistencias],
        }


def _pivotes(valores: List[float], window: int, es_alto: bool) -> List[float]:
    """Devuelve los valores de los pivotes locales (highs si es_alto, lows si no)."""
    pivs = []
    n = len(valores)
    for i in range(window, n - window):
        v = valores[i]
        vecinos = valores[i - window:i] + valores[i + 1:i + 1 + window]
        if es_alto:
            if all(v >= x for x in vecinos):
                pivs.append(v)
        else:
            if all(v <= x for x in vecinos):
                pivs.append(v)
    return pivs


def _agrupar(pivotes: List[float], cluster_pct: float) -> List[Nivel]:
    """Agrupa pivotes cercanos en niveles. Cada nivel: precio medio + n toques."""
    if not pivotes:
        return []
    ordenados = sorted(pivotes)
    niveles: List[Nivel] = []
    grupo = [ordenados[0]]
    for p in ordenados[1:]:
        base = grupo[0]
        if base > 0 and abs(p - base) / base * 100.0 <= cluster_pct:
            grupo.append(p)
        else:
            niveles.append(Nivel(precio=sum(grupo) / len(grupo), toques=len(grupo)))
            grupo = [p]
    niveles.append(Nivel(precio=sum(grupo) / len(grupo), toques=len(grupo)))
    return niveles


def detectar_niveles(candles: list, price: float) -> NivelesResult:
    """
    candles: buffer de velas de TF medio (1h recomendado) con .h y .l
    price: precio actual — separa soportes (debajo) de resistencias (encima)
    """
    s = get_settings()
    res = NivelesResult()
    if not candles or len(candles) < s.sr_pivot_window * 2 + 5 or price <= 0:
        return res

    highs = [c.h for c in candles]
    lows = [c.l for c in candles]
    w = s.sr_pivot_window

    piv_high = _pivotes(highs, w, es_alto=True)
    piv_low = _pivotes(lows, w, es_alto=False)

    niveles_high = _agrupar(piv_high, s.sr_cluster_pct)
    niveles_low = _agrupar(piv_low, s.sr_cluster_pct)

    # Todos los pivotes pueden actuar como soporte o resistencia segun la
    # posicion del precio actual. Se combinan y se reparten.
    todos = [n for n in niveles_high + niveles_low if n.toques >= s.sr_min_touches]

    soportes = [n for n in todos if n.precio < price]
    resistencias = [n for n in todos if n.precio > price]

    # Soportes: el mas cercano al precio primero (precio mas alto)
    soportes.sort(key=lambda n: n.precio, reverse=True)
    # Resistencias: la mas cercana primero (precio mas bajo)
    resistencias.sort(key=lambda n: n.precio)

    res.soportes = soportes[:s.sr_max_levels]
    res.resistencias = resistencias[:s.sr_max_levels]
    return res
