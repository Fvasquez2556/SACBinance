"""Flujo agresor desde aggTrade (portado de v2 sin cambios)."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Deque, Tuple

_WINDOWS = (5, 15, 30, 90)
_MAX_MS = 90_000


@dataclass
class FlowSnapshot:
    buy_ratio_5s: float = 0.5
    buy_ratio_15s: float = 0.5
    buy_ratio_30s: float = 0.5
    buy_ratio_90s: float = 0.5
    net_30s: float = 0.0
    net_90s: float = 0.0
    trades_30s: int = 0
    quote_vol_30s: float = 0.0

    @property
    def buy_dominant(self) -> bool:
        return self.buy_ratio_30s >= 0.58 and self.buy_ratio_90s >= 0.54

    @property
    def sell_dominant(self) -> bool:
        return self.buy_ratio_30s <= 0.42 and self.buy_ratio_90s <= 0.46


class FlowState:
    __slots__ = ("_tape",)

    def __init__(self) -> None:
        self._tape: Deque[Tuple[int, float, float]] = deque()

    def add_trade(self, t_ms: int, price: float, qty: float, is_buyer_maker: bool) -> None:
        quote = price * qty
        if is_buyer_maker:
            self._tape.append((t_ms, 0.0, quote))
        else:
            self._tape.append((t_ms, quote, 0.0))
        cutoff = t_ms - _MAX_MS
        tape = self._tape
        while tape and tape[0][0] < cutoff:
            tape.popleft()

    def snapshot(self, now_ms: int) -> FlowSnapshot:
        if not self._tape:
            return FlowSnapshot()
        acc = {w: [0.0, 0.0, 0] for w in _WINDOWS}
        for t, b, s in reversed(self._tape):
            age = now_ms - t
            for w in _WINDOWS:
                if age <= w * 1000:
                    a = acc[w]
                    a[0] += b
                    a[1] += s
                    a[2] += 1
            if age > _MAX_MS:
                break

        def ratio(w: int) -> float:
            b, s, _ = acc[w]
            tot = b + s
            return b / tot if tot > 0 else 0.5

        b30, s30, n30 = acc[30]
        b90, s90, _ = acc[90]
        return FlowSnapshot(
            buy_ratio_5s=ratio(5),
            buy_ratio_15s=ratio(15),
            buy_ratio_30s=ratio(30),
            buy_ratio_90s=ratio(90),
            net_30s=b30 - s30,
            net_90s=b90 - s90,
            trades_30s=n30,
            quote_vol_30s=b30 + s30,
        )
