"""La primera alerta del dia y el episodio vigente, tal y como los pide el tablero."""
import unittest
from unittest.mock import patch

from src.config.settings import get_settings
from src.persistence.db import Database

H = 3600_000
HOY = 1_790_000_000_000          # un instante cualquiera
MEDIANOCHE = HOY - 10 * H        # "medianoche" que manda el navegador


def niveles(entry=100.0, sl=97.0, tp=106.0):
    return {'valid': True, 'entry': entry, 'stop_loss': sl, 'take_profit': tp,
            'tf': '5m', 'sl_basis': 'soporte estructural'}


class ReferenciasTests(unittest.TestCase):
    def setUp(self):
        ajustes = get_settings().model_copy(update={'db_path': ':memory:'})
        with patch('src.persistence.db.get_settings', return_value=ajustes):
            self.db = Database()

    def tearDown(self):
        self.db._conn.close()

    def alerta(self, ts, entry=100.0, telegram='no_procede', symbol='TESTUSDT'):
        return self.db.registrar_alerta({
            'ts_ms': ts, 'symbol': symbol, 'signal_id': None, 'entry': entry,
            'take_profit': entry * 1.06, 'stop_loss': entry * 0.97,
            'telegram': telegram, 'senal_n': 1})

    def test_yesterdays_alert_is_not_todays_first(self):
        self.alerta(MEDIANOCHE - 3 * H, entry=90.0)          # ayer
        self.alerta(MEDIANOCHE + 1 * H, entry=100.0)         # la primera de hoy
        self.alerta(MEDIANOCHE + 5 * H, entry=104.0, telegram='enviado')
        ref = self.db.referencias_par('TESTUSDT', MEDIANOCHE)
        self.assertEqual(ref['primera_del_dia']['entry'], 100.0)
        self.assertEqual(ref['primera_del_dia']['ts_ms'], MEDIANOCHE + 1 * H)
        self.assertEqual(ref['alertas_del_dia'], 2)
        self.assertEqual(ref['enviadas_del_dia'], 1)

    def test_a_pair_without_alerts_today_says_so_instead_of_failing(self):
        self.alerta(MEDIANOCHE - 3 * H)
        ref = self.db.referencias_par('TESTUSDT', MEDIANOCHE)
        self.assertIsNone(ref['primera_del_dia'])
        self.assertEqual((ref['alertas_del_dia'], ref['enviadas_del_dia']), (0, 0))
        self.assertIsNone(ref['episodio'])

    def test_the_symbol_is_normalised_and_other_pairs_do_not_leak_in(self):
        self.alerta(MEDIANOCHE + 1 * H, entry=100.0)
        self.alerta(MEDIANOCHE + 2 * H, entry=7.0, symbol='OTROUSDT')
        ref = self.db.referencias_par('testusdt', MEDIANOCHE)
        self.assertEqual(ref['symbol'], 'TESTUSDT')
        self.assertEqual(ref['alertas_del_dia'], 1)
        self.assertEqual(ref['primera_del_dia']['entry'], 100.0)

    def test_the_episode_carries_its_first_plan_so_the_panel_can_show_it(self):
        reg = self.db.registro_episodios()
        a1 = self.alerta(MEDIANOCHE + 1 * H, entry=100.0)
        a2 = self.alerta(MEDIANOCHE + 4 * H, entry=101.0)
        reg.registrar(symbol='TESTUSDT', ts_ms=MEDIANOCHE + 1 * H,
                      tl=niveles(100.0), alerta_id=a1)
        reg.registrar(symbol='TESTUSDT', ts_ms=MEDIANOCHE + 4 * H,
                      tl=niveles(101.0, sl=97.5), alerta_id=a2)
        ref = self.db.referencias_par('TESTUSDT', MEDIANOCHE)
        ep = ref['episodio']
        self.assertEqual(ep['n_planes'], 2)
        self.assertEqual(ep['fase'], 'ABIERTO')
        self.assertEqual(ep['primer_plan']['entry'], 100.0)
        self.assertEqual(ep['primer_plan']['ordinal_episodio'], 1)
        self.assertEqual(ep['primer_plan']['ts_creado'], MEDIANOCHE + 1 * H)


if __name__ == '__main__':
    unittest.main()
