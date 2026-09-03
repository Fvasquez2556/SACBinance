"""Estadistica adaptativa por moneda (portado de v2 sin cambios)."""
from __future__ import annotations
import math


class EwmaStat:
    __slots__ = ("alpha", "mean", "var", "n")

    def __init__(self, alpha: float) -> None:
        self.alpha = alpha
        self.mean = 0.0
        self.var = 0.0
        self.n = 0

    def update(self, x: float) -> None:
        self.n += 1
        if self.n == 1:
            self.mean = x
            self.var = 0.0
            return
        delta = x - self.mean
        self.mean += self.alpha * delta
        self.var = (1.0 - self.alpha) * (self.var + self.alpha * delta * delta)

    @property
    def std(self) -> float:
        return math.sqrt(max(self.var, 0.0))


class AdaptiveStats:
    __slots__ = ("_ret", "_vol", "_sigma_min", "ready_n")

    def __init__(self, alpha: float, sigma_min: float) -> None:
        self._ret = EwmaStat(alpha)
        self._vol = EwmaStat(alpha)
        self._sigma_min = sigma_min
        self.ready_n = 0

    def update(self, ret_1m: float, volume_1m: float) -> None:
        self._ret.update(ret_1m)
        self._vol.update(volume_1m)
        self.ready_n += 1

    @property
    def sigma(self) -> float:
        return max(self._ret.std, self._sigma_min)

    @property
    def mean_ret(self) -> float:
        return self._ret.mean

    def z(self, cumulative_return: float, window: int) -> float:
        denom = self.sigma * math.sqrt(max(window, 1))
        if denom <= 0.0:
            return 0.0
        return cumulative_return / denom

    def vol_ratio(self, volume_1m: float) -> float:
        m = self._vol.mean
        if m <= 0.0:
            return 1.0
        return volume_1m / m
