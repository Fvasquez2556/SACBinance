"""
Los dos niveles que el plan calculaba y no enseñaba.

El operador veia "SL 0.211382" sin saber sobre que se apoya, y un TP sin saber
si habia algo en medio. Aqui se comprueba que los dos viajan congelados con el
plan y llegan al aviso de Telegram.
"""
import unittest
from types import SimpleNamespace

from src.analysis.tf_rupture import _vol_ratio, leer_tf
from src.analysis.trade_levels import calcular_niveles
from src.notify.telegram import _lineas_niveles, texto_plan_notificado
from src.state.active_alert import AlertManager
from src.state.symbol_state import Candle

_MINUTO = 60_000


def _vela(i, alto, bajo, cierre, vol=1000.0):
    return Candle(t=i * _MINUTO, o=cierre, h=alto, l=bajo, c=cierre, v=vol)


def _rango(n=140, techo=102.0, suelo=100.0, vol=1000.0):
    velas = []
    for i in range(n):
        fase = i % 8
        if fase == 0:
            velas.append(_vela(i, techo, techo - 0.4, techo - 0.3, vol))
        elif fase == 4:
            velas.append(_vela(i, suelo + 0.4, suelo, suelo + 0.3, vol))
        else:
            medio = (techo + suelo) / 2
            velas.append(_vela(i, medio + 0.2, medio - 0.2, medio, vol))
    return velas


class NivelesEnElPlanTests(unittest.TestCase):
    """`calcular_niveles` ya conocia los dos niveles; ahora los publica."""

    def niveles(self):
        velas = _rango()
        from src.analysis.levels import detectar_niveles
        sr = detectar_niveles(velas, 101.0)
        return calcular_niveles(101.0, velas, 'SUBIENDO', niveles_sr=sr,
                                candles_1m=velas), sr

    def test_the_support_that_holds_the_stop_is_published_with_its_touches(self):
        plan, sr = self.niveles()
        if not sr.soportes:
            self.skipTest('el detector no encontro soporte en este zigzag')
        d = plan.to_dict()
        self.assertIsNotNone(d['soporte'])
        self.assertEqual(d['toques_soporte'], sr.soportes[0].toques)
        # El stop queda por debajo del soporte, no encima: lleva el colchon del ATR.
        self.assertLess(d['stop_loss'], d['soporte'])

    def test_the_ceiling_is_published_whether_or_not_it_blocks_the_target(self):
        plan, sr = self.niveles()
        d = plan.to_dict()
        if sr.resistencias:
            self.assertIsNotNone(d['nearest_resistance'])
            self.assertEqual(d['toques_resistencia'], sr.resistencias[0].toques)
        else:
            self.assertIsNone(d['nearest_resistance'])


class AlertaCongelaLosNivelesTests(unittest.TestCase):
    def test_the_alert_freezes_both_levels_with_the_rest_of_the_plan(self):
        manager = AlertManager()
        tl = {'entry': 100.0, 'take_profit': 106.0, 'stop_loss': 97.0,
              'soporte': 97.5, 'sl_basis': 'soporte estructural',
              'nearest_resistance': 104.0, 'tp_blocked_by_resistance': True,
              'toques_soporte': 4, 'toques_resistencia': 3}
        impulso = SimpleNamespace(fase='SOSTENIDA', fuerza=80, consumido_pct=1.0)
        alerta = manager.emitir('TESTUSDT', 1, 1_000_000, {'score': 80}, tl, impulso)
        d = alerta.to_dict()
        self.assertEqual(d['soporte'], 97.5)
        self.assertEqual(d['resistencia'], 104.0)
        self.assertEqual(d['sl_basis'], 'soporte estructural')
        self.assertTrue(d['tp_bloqueado'])
        self.assertEqual((d['toques_soporte'], d['toques_resistencia']), (4, 3))

    def test_a_plan_without_structural_levels_freezes_nothing_invented(self):
        manager = AlertManager()
        tl = {'entry': 100.0, 'take_profit': 106.0, 'stop_loss': 97.0,
              'sl_basis': 'swing low 15m'}
        impulso = SimpleNamespace(fase='SOSTENIDA', fuerza=80, consumido_pct=1.0)
        d = manager.emitir('TESTUSDT', 1, 1_000_000, {'score': 80}, tl, impulso).to_dict()
        self.assertIsNone(d['soporte'])
        self.assertIsNone(d['resistencia'])
        self.assertEqual(d['sl_basis'], 'swing low 15m')
        self.assertFalse(d['tp_bloqueado'])


class AvisoDeTelegramTests(unittest.TestCase):
    def test_the_message_says_what_holds_the_stop(self):
        lineas = _lineas_niveles(
            {'soporte': 97.5, 'toques_soporte': 4, 'sl_basis': 'soporte estructural'},
            entry=100.0, tp=106.0)
        self.assertIn('soporte que sostiene el SL', lineas[0])
        self.assertIn('97.5', lineas[0])
        self.assertIn('-2.50%', lineas[0])
        self.assertIn('4 toques', lineas[0])

    def test_a_ceiling_in_the_way_is_named_as_what_has_to_break(self):
        lineas = _lineas_niveles({'resistencia': 104.0, 'tp_bloqueado': True,
                                  'toques_resistencia': 3}, entry=100.0, tp=106.0)
        self.assertIn('techo que debe romper', lineas[0])
        self.assertIn('esta entre la entrada y el TP', lineas[0])
        self.assertIn('+4.00%', lineas[0])

    def test_a_ceiling_above_the_target_is_reported_without_alarm(self):
        lineas = _lineas_niveles({'resistencia': 110.0, 'tp_bloqueado': False},
                                 entry=100.0, tp=106.0)
        self.assertIn('por encima del TP', lineas[0])
        self.assertNotIn('debe romper', lineas[0])

    def test_without_levels_the_message_does_not_invent_lines(self):
        self.assertEqual(_lineas_niveles({}, entry=100.0, tp=106.0), [])
        self.assertEqual(_lineas_niveles({'resistencia': None}, 100.0, 106.0), [])

    def test_the_whole_notice_carries_the_two_levels(self):
        plan = {'symbol': 'TESTUSDT', 'alerta_id': 7, 'ts_open': 1_700_000_000_000,
                'entry': 100.0, 'take_profit': 106.0, 'stop_loss': 97.0,
                'last_price': 101.0, 'estado': 'ABIERTO', 'mfe': 1.0, 'mae': -0.5,
                'contexto': {'coste_pct': 0.5, 'soporte': 97.5, 'toques_soporte': 4,
                             'sl_basis': 'soporte estructural', 'resistencia': 104.0,
                             'tp_bloqueado': True, 'toques_resistencia': 3}}
        texto = texto_plan_notificado(plan)
        self.assertIn('soporte que sostiene el SL', texto)
        self.assertIn('techo que debe romper', texto)


class VolumenDeLaRupturaTests(unittest.TestCase):
    """Sin IndSnap del marco el volumen se perdia: 74 % de las filas sin dato."""

    def test_the_ratio_is_computed_from_the_candles_when_no_snapshot_exists(self):
        velas = _rango(vol=1000.0)
        velas[-1] = _vela(len(velas) - 1, 103.0, 102.0, 102.8, vol=3000.0)
        self.assertEqual(_vol_ratio(velas), 3.0)
        lectura = leer_tf('5m', velas, 102.8, ind=None)
        self.assertEqual(lectura.vol_ratio, 3.0)

    def test_without_enough_history_it_says_nothing_instead_of_guessing(self):
        self.assertIsNone(_vol_ratio(_rango(n=10)))
        self.assertIsNone(_vol_ratio([]))

    def test_a_flat_book_of_zero_volume_does_not_divide_by_zero(self):
        self.assertIsNone(_vol_ratio(_rango(vol=0.0)))


if __name__ == '__main__':
    unittest.main()
