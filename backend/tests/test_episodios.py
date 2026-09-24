"""Identidad por episodio y por plan. Fase 1: no cambia ninguna emision."""
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.config.settings import get_settings
from src.episodios import EPISODIOS_SCHEMA, RegistroEpisodios
from src.persistence.db import SCHEMA_VERSION, Database
from src.state.engine import StateEngine

H = 3600_000
NOW = 1_700_000_000_000


def niveles(entry=100.0, sl=97.0, tp=106.0, tf='5m'):
    return {'valid': True, 'entry': entry, 'stop_loss': sl, 'take_profit': tp,
            'risk_pct': 3.0, 'reward_pct': 6.0, 'reward_neto_pct': 5.5,
            'tf': tf, 'sl_basis': 'soporte estructural'}


class RegistroTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript(EPISODIOS_SCHEMA)
        self.reg = RegistroEpisodios(self.conn)

    def tearDown(self):
        self.conn.close()

    def alta(self, ts=NOW, alerta_id=1, signal_id=7, tl=None, symbol='TESTUSDT'):
        return self.reg.registrar(symbol=symbol, ts_ms=ts, tl=tl or niveles(),
                                  snap={'display_state': 'SUBIENDO', 'score': 86,
                                        'tier': 'FUERTE', 'velas': [1, 2, 3]},
                                  alerta_id=alerta_id, signal_id=signal_id)

    def test_two_alerts_inside_the_window_share_the_episode_and_keep_their_order(self):
        a = self.alta(ts=NOW, alerta_id=1)
        b = self.alta(ts=NOW + 6 * H, alerta_id=2, tl=niveles(entry=101, sl=97.5))
        self.assertEqual(a['episode_id'], b['episode_id'])
        self.assertEqual((a['ordinal'], b['ordinal']), (1, 2))
        self.assertTrue(a['episodio_nuevo'])
        self.assertFalse(b['episodio_nuevo'])

    def test_silence_beyond_the_window_opens_another_episode_linked_to_the_first(self):
        a = self.alta(ts=NOW, alerta_id=1)
        b = self.alta(ts=NOW + 12 * H, alerta_id=2)
        self.assertNotEqual(a['episode_id'], b['episode_id'])
        self.assertEqual(b['motivo_cierre'], 'SILENCIO')
        previo = self.reg.filas('SELECT * FROM episodios WHERE episode_id = ?',
                                (a['episode_id'],))[0]
        nuevo = self.reg.filas('SELECT * FROM episodios WHERE episode_id = ?',
                               (b['episode_id'],))[0]
        self.assertEqual(previo['fase'], 'CERRADO')
        self.assertEqual(nuevo['episodio_padre'], a['episode_id'])
        self.assertEqual(b['ordinal'], 1)

    def test_a_different_structural_anchor_is_a_different_thesis(self):
        a = self.alta(ts=NOW, alerta_id=1, tl=niveles(sl=97.0))
        b = self.alta(ts=NOW + H, alerta_id=2, tl=niveles(sl=92.0))
        self.assertNotEqual(a['episode_id'], b['episode_id'])
        self.assertEqual(b['motivo_cierre'], 'ANCLA')

    def test_an_anchor_that_barely_breathes_stays_in_the_same_episode(self):
        a = self.alta(ts=NOW, alerta_id=1, tl=niveles(sl=97.0))
        b = self.alta(ts=NOW + H, alerta_id=2, tl=niveles(sl=98.0))  # +1,03%
        self.assertEqual(a['episode_id'], b['episode_id'])

    def test_registering_the_same_alert_twice_neither_duplicates_nor_advances(self):
        a = self.alta(ts=NOW, alerta_id=1)
        otra = RegistroEpisodios(self.conn)          # como tras un reinicio
        b = otra.registrar(symbol='TESTUSDT', ts_ms=NOW, tl=niveles(), alerta_id=1)
        self.assertEqual(a['plan_id'], b['plan_id'])
        self.assertTrue(b['repetido'])
        self.assertEqual(len(self.reg.filas('SELECT * FROM planes')), 1)
        episodio = self.reg.vigente('TESTUSDT')
        self.assertEqual(episodio['n_planes'], 1)
        self.assertEqual(episodio['primer_plan_id'], a['plan_id'])

    def test_an_alert_without_signal_id_still_gets_its_own_plan(self):
        ident = self.alta(alerta_id=9, signal_id=None)
        plan = self.reg.plan(ident['plan_id'])
        self.assertIsNone(plan['legacy_signal_id'])
        self.assertEqual(plan['legacy_alerta_id'], 9)
        self.assertEqual(plan['r_multiplo'], 2.0)
        self.assertEqual(plan['escenario'], 'SUBIENDO')

    def test_incoherent_levels_are_not_registered_as_a_plan(self):
        self.assertIsNone(self.alta(tl=niveles(entry=100, sl=101, tp=106)))
        self.assertIsNone(self.alta(tl=niveles(entry=100, sl=97, tp=99)))
        self.assertIsNone(self.alta(tl={'valid': True, 'entry': None}))
        self.assertEqual(self.reg.filas('SELECT * FROM planes'), [])

    def test_a_stop_closes_the_episode_and_the_next_plan_opens_another(self):
        a = self.alta(ts=NOW, alerta_id=1)
        self.reg.cerrar_por_desenlace(a['plan_id'], NOW + 2 * H, 'SL')
        b = self.alta(ts=NOW + 3 * H, alerta_id=2)
        self.assertNotEqual(a['episode_id'], b['episode_id'])
        plan = self.reg.plan(a['plan_id'])
        self.assertEqual(plan['desenlace'], 'SL')
        cerrado = self.reg.filas('SELECT * FROM episodios WHERE episode_id = ?',
                                 (a['episode_id'],))[0]
        self.assertEqual(cerrado['motivo_cierre'], 'DESENLACE:SL')

    def test_a_later_rise_does_not_rewrite_the_stop(self):
        a = self.alta(ts=NOW, alerta_id=1)
        self.reg.cerrar_por_desenlace(a['plan_id'], NOW + 2 * H, 'SL')
        self.reg.cerrar_por_desenlace(a['plan_id'], NOW + 5 * H, 'TP')
        self.assertEqual(self.reg.plan(a['plan_id'])['desenlace'], 'SL')

    def test_the_clock_closes_what_nobody_touched_again(self):
        self.alta(ts=NOW, alerta_id=1)
        self.assertEqual(self.reg.barrer(NOW + 6 * H), 0)
        self.assertEqual(self.reg.barrer(NOW + 12 * H), 1)
        self.assertIsNone(self.reg.vigente('TESTUSDT'))
        self.assertEqual(self.reg.barrer(NOW + 24 * H), 0)

    def test_the_summary_counts_firsts_and_plans_without_signal(self):
        self.alta(ts=NOW, alerta_id=1, signal_id=None)
        self.alta(ts=NOW + H, alerta_id=2, signal_id=5)
        resumen = self.reg.resumen()
        self.assertEqual(resumen['planes']['n'], 2)
        self.assertEqual(resumen['planes']['sin_signal'], 1)
        self.assertEqual(resumen['planes']['primeros'], 1)
        self.assertEqual(resumen['silencio_h'], 12.0)


class BaseDeDatosTests(unittest.TestCase):
    def setUp(self):
        settings = get_settings().model_copy(update={'db_path': ':memory:'})
        with patch('src.persistence.db.get_settings', return_value=settings):
            self.db = Database()

    def tearDown(self):
        self.db._conn.close()

    def test_the_migration_creates_the_tables_and_the_two_columns(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 16)  # la v16 trajo estas tablas
        tablas = {r[0] for r in self.db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn('episodios', tablas)
        self.assertIn('planes', tablas)
        cols = {r[1] for r in self.db._conn.execute(
            'PRAGMA table_info(alertas_emitidas)')}
        self.assertTrue({'episode_id', 'plan_id'} <= cols)

    def test_an_alert_ends_up_pointing_at_its_episode_and_its_plan(self):
        alerta_id = self.db.registrar_alerta(
            {'ts_ms': NOW, 'symbol': 'TESTUSDT', 'signal_id': None,
             'entry': 100.0, 'take_profit': 106.0, 'stop_loss': 97.0})
        reg = self.db.registro_episodios()
        ident = reg.registrar(symbol='TESTUSDT', ts_ms=NOW, tl=niveles(),
                              alerta_id=alerta_id, signal_id=None)
        self.db.anotar_identidad_alerta(alerta_id, ident['episode_id'],
                                        ident['plan_id'])
        fila = self.db.get_alertas_emitidas(limit=1)[0]
        self.assertEqual(fila['episode_id'], ident['episode_id'])
        self.assertEqual(fila['plan_id'], ident['plan_id'])

    def test_a_notified_outcome_closes_the_episode_without_asking_the_engine(self):
        alerta_id = self.db.registrar_alerta(
            {'ts_ms': NOW, 'symbol': 'TESTUSDT', 'entry': 100.0,
             'take_profit': 106.0, 'stop_loss': 97.0})
        reg = self.db.registro_episodios()
        ident = reg.registrar(symbol='TESTUSDT', ts_ms=NOW, tl=niveles(),
                              alerta_id=alerta_id)
        self.db._conn.execute(
            """INSERT INTO notificacion_planes
               (alerta_id, symbol, ts_open, ts_activado, entry, take_profit,
                stop_loss, estado) VALUES (?,?,?,?,?,?,?,'SL')""",
            (alerta_id, 'TESTUSDT', NOW, NOW, 100.0, 106.0, 97.0))
        self.assertEqual(reg.sincronizar_desenlaces(NOW + 2 * H), 1)
        self.assertEqual(reg.plan(ident['plan_id'])['desenlace'], 'SL')
        self.assertIsNone(reg.vigente('TESTUSDT'))
        # Un segundo barrido no reabre ni reescribe: el desenlace ya esta puesto.
        self.assertEqual(reg.sincronizar_desenlaces(NOW + 3 * H), 0)
        self.assertEqual(reg.plan(ident['plan_id'])['ts_desenlace'], NOW + 2 * H)


class MotorEnSombraTests(unittest.TestCase):
    """La identidad no puede cambiar —ni romper— lo que el operador recibe."""

    def engine(self, registro):
        engine = StateEngine.__new__(StateEngine)
        engine._episodios = registro
        engine._db = Mock()
        return engine

    def test_a_failure_registering_identity_never_reaches_the_alert(self):
        roto = SimpleNamespace(registrar=Mock(side_effect=RuntimeError('fallo')))
        engine = self.engine(roto)
        engine._registrar_identidad('TESTUSDT', {}, niveles(), 1, NOW, 5)
        engine._db.anotar_identidad_alerta.assert_not_called()

    def test_the_switch_off_leaves_the_registry_untouched(self):
        registro = SimpleNamespace(registrar=Mock())
        engine = self.engine(registro)
        apagado = get_settings().model_copy(
            update={'episodio_registro_enabled': False})
        with patch('src.state.engine.get_settings', return_value=apagado):
            engine._registrar_identidad('TESTUSDT', {}, niveles(), 1, NOW, 5)
        registro.registrar.assert_not_called()

    def test_an_alert_without_id_is_not_given_an_episode(self):
        registro = SimpleNamespace(registrar=Mock())
        engine = self.engine(registro)
        engine._registrar_identidad('TESTUSDT', {}, niveles(), None, NOW, None)
        registro.registrar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
