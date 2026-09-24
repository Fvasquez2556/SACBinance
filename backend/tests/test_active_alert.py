"""Regresiones del ciclo de vida de alertas con meta fija y TP corto."""
from __future__ import annotations

import unittest

from src.state.active_alert import (
    ESTADO_CUMPLIDA,
    ESTADO_EXTENDIENDO,
    ESTADO_VIVA,
    MOTIVO_META,
    MOTIVO_SL,
    MOTIVO_TP_CORTO_SIN_EXTENSION,
    AlertManager,
    AlertaActiva,
)


class ActiveAlertResetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = AlertManager()
        self.now = 1_000_000

    def alert(self, take_profit: float = 102.0) -> AlertaActiva:
        alert = AlertaActiva(
            symbol="TESTUSDT",
            signal_id=1,
            ts_emision=self.now,
            entry=100.0,
            take_profit=take_profit,
            stop_loss=98.0,
            score_emision=80,
            tier_emision="FUERTE",
            estado_emision="SUBIENDO",
            macro_emision="ALCISTA",
            fase_emision="SOSTENIDA",
            fuerza_emision=80,
            consumido_emision=1.0,
            precio_actual=100.0,
        )
        self.manager._activas[alert.symbol] = alert
        return alert

    def update(self, now: int, high: float, low: float, close: float):
        return self.manager.actualizar(
            "TESTUSDT", now, high, low, close, impulso=None,
            display_state="SUBIENDO",
        )

    def test_meta_resets_even_when_the_planned_tp_is_short(self) -> None:
        alert = self.alert(take_profit=102.0)

        changed = self.update(self.now + 60_000, high=103.2, low=100.0, close=103.0)

        self.assertIs(changed, alert)
        self.assertFalse(alert.accionable)
        self.assertEqual(alert.motivo_cierre, MOTIVO_META)
        self.assertEqual(alert.estado, ESTADO_CUMPLIDA)

    def test_short_tp_waits_for_extension_before_resetting(self) -> None:
        alert = self.alert(take_profit=102.0)

        changed = self.update(self.now + 60_000, high=102.0, low=100.0, close=101.9)

        self.assertIs(changed, alert)
        self.assertTrue(alert.accionable)
        self.assertEqual(alert.estado, ESTADO_EXTENDIENDO)
        self.assertFalse(alert.tp_corto_superado)

    def test_short_tp_without_extension_resets_after_configured_wait(self) -> None:
        alert = self.alert(take_profit=102.0)
        self.update(self.now + 60_000, high=102.0, low=100.0, close=101.9)

        changed = self.update(self.now + 4 * 3600_000 + 60_000, high=101.9, low=100.0, close=101.0)

        self.assertIs(changed, alert)
        self.assertFalse(alert.accionable)
        self.assertEqual(alert.motivo_cierre, MOTIVO_TP_CORTO_SIN_EXTENSION)

    def test_short_tp_that_is_exceeded_stays_active_toward_meta(self) -> None:
        alert = self.alert(take_profit=102.0)

        changed = self.update(self.now + 60_000, high=102.1, low=100.0, close=102.05)

        self.assertIs(changed, alert)
        self.assertTrue(alert.accionable)
        self.assertTrue(alert.tp_corto_superado)
        self.assertEqual(alert.estado, ESTADO_VIVA)

    def test_stop_wins_when_a_single_bar_crosses_stop_and_meta(self) -> None:
        alert = self.alert(take_profit=104.0)

        changed = self.update(self.now + 60_000, high=104.0, low=97.5, close=103.0)

        self.assertIs(changed, alert)
        self.assertFalse(alert.accionable)
        self.assertEqual(alert.motivo_cierre, MOTIVO_SL)


if __name__ == "__main__":
    unittest.main()
