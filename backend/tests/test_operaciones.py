"""El diario del usuario. Fase 3: solo entra lo que el declara, y no lo reescribe nadie."""
import unittest
from unittest.mock import patch

from src.config.settings import get_settings
from src.operaciones import Diario, ErrorDiario
from src.persistence.db import SCHEMA_VERSION, Database

H = 3600_000
NOW = 1_790_000_000_000


def niveles(entry=100.0, tp=104.87, sl=97.55):
    return {'valid': True, 'entry': entry, 'take_profit': tp, 'stop_loss': sl,
            'tf': '5m', 'sl_basis': 'soporte estructural'}


class DiarioTests(unittest.TestCase):
    def setUp(self):
        ajustes = get_settings().model_copy(update={'db_path': ':memory:'})
        with patch('src.persistence.db.get_settings', return_value=ajustes):
            self.db = Database()
        self.reg = self.db.registro_episodios()
        self.diario = Diario(self.db._conn, coste_pct=0.5)

    def tearDown(self):
        self.db._conn.close()

    def plan(self, ts=NOW, alerta_id=1, tl=None, symbol='TESTUSDT'):
        alerta = self.db.registrar_alerta({
            'ts_ms': ts, 'symbol': symbol, 'entry': (tl or niveles())['entry'],
            'take_profit': (tl or niveles())['take_profit'],
            'stop_loss': (tl or niveles())['stop_loss'], 'telegram': 'enviado'})
        return self.reg.registrar(symbol=symbol, ts_ms=ts, tl=tl or niveles(),
                                  alerta_id=alerta)

    # --- El ejemplo del plan: A ganadora, B perdedora ----------------------

    def test_a_later_signal_does_not_touch_the_trade_you_took(self):
        a = self.plan(ts=NOW, alerta_id=1)
        op = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0,
                               plan_id=a['plan_id'], tipo='DECLARADA')
        # Señal B del mismo par, con otros niveles, que acaba en stop.
        b = self.plan(ts=NOW + 2 * H, alerta_id=2,
                      tl=niveles(entry=103.0, tp=107.0, sl=100.5))
        self.reg.cerrar_por_desenlace(b['plan_id'], NOW + 4 * H, 'SL')
        # A sigue midiendose contra SUS niveles.
        cerrada = self.diario.cerrar(op['operacion_id'], NOW + 5 * H, 104.87, 'TP')
        self.assertEqual(cerrada['resultado_pct'], 4.37)      # 4,87 bruto − 0,5 de coste
        self.assertEqual(cerrada['objetivo'], 104.87)
        self.assertEqual(cerrada['stop'], 97.55)
        # Y la B, que no se tomo, no aparece en el diario.
        self.assertEqual(len(self.diario.listar()), 1)
        self.assertEqual(self.reg.plan(b['plan_id'])['desenlace'], 'SL')

    def test_the_trade_keeps_the_levels_it_copied_when_it_opened(self):
        a = self.plan()
        op = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0,
                               plan_id=a['plan_id'])
        self.db._conn.execute("UPDATE planes SET take_profit = 999 WHERE plan_id = ?",
                              (a['plan_id'],))
        self.assertEqual(self.diario.operacion(op['operacion_id'])['objetivo'], 104.87)

    def test_an_alert_or_a_telegram_send_never_creates_a_trade(self):
        self.plan(ts=NOW, alerta_id=1)
        self.plan(ts=NOW + 13 * H, alerta_id=2)
        self.db._conn.execute(
            """INSERT INTO notificacion_planes
               (alerta_id, symbol, ts_open, ts_activado, entry, take_profit, stop_loss,
                estado, message_id) VALUES (1,'TESTUSDT',?,?,100.0,104.87,97.55,'ABIERTO',42)""",
            (NOW, NOW))
        self.assertEqual(self.diario.listar(), [])
        self.assertEqual(self.diario.resumen()['abiertas'], 0)

    # --- Reentrar es otra operacion ---------------------------------------

    def test_a_loss_and_a_re_entry_are_two_trades_with_a_correct_balance(self):
        primera = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0,
                                    tipo='DECLARADA', cantidad=10)
        self.diario.cerrar(primera['operacion_id'], NOW + H, 97.55, 'SL')
        segunda = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW + 2 * H,
                                    precio_entrada=98.0, tipo='DECLARADA', cantidad=10)
        self.diario.cerrar(segunda['operacion_id'], NOW + 4 * H, 104.0, 'TP')
        ops = self.diario.listar()
        self.assertEqual(len(ops), 2)
        self.assertEqual(self.diario.operacion(primera['operacion_id'])['resultado_pct'], -2.95)
        self.assertEqual(self.diario.operacion(segunda['operacion_id'])['resultado_pct'], 5.6224)
        suma = [f for f in self.diario.resumen()['por_tipo']
                if f['tipo'] == 'DECLARADA' and f['estado'] == 'CERRADA'][0]
        self.assertEqual(suma['n'], 2)
        self.assertEqual(suma['positivas'], 1)
        self.assertAlmostEqual(suma['suma_pct'], 2.6724, places=4)

    # --- Parciales y cantidades -------------------------------------------

    def test_partials_weight_the_exit_price_and_close_when_nothing_is_left(self):
        op = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0,
                               cantidad=10, tipo='DECLARADA')
        self.diario.parcial(op['operacion_id'], NOW + H, 106.0, 5)
        viva = self.diario.operacion(op['operacion_id'])
        self.assertEqual(viva['estado'], 'ABIERTA')
        self.assertEqual(viva['cantidad_abierta'], 5)
        self.diario.parcial(op['operacion_id'], NOW + 2 * H, 102.0, 5)
        cerrada = self.diario.operacion(op['operacion_id'])
        self.assertEqual(cerrada['estado'], 'CERRADA')
        self.assertEqual(cerrada['precio_salida'], 104.0)      # media ponderada
        self.assertEqual(cerrada['resultado_pct'], 3.5)
        self.assertEqual(cerrada['resultado_moneda'], 35.0)    # 10 × 100 × 3,5 %

    def test_a_partial_cannot_exceed_what_is_open_and_needs_a_quantity(self):
        op = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0,
                               cantidad=4)
        with self.assertRaises(ErrorDiario):
            self.diario.parcial(op['operacion_id'], NOW + H, 101.0, 5)
        sin_cantidad = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW,
                                         precio_entrada=100.0)
        with self.assertRaises(ErrorDiario):
            self.diario.parcial(sin_cantidad['operacion_id'], NOW + H, 101.0, 1)

    # --- Reglas que protegen el registro ----------------------------------

    def test_a_closed_trade_cannot_be_closed_again(self):
        op = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0)
        self.diario.cerrar(op['operacion_id'], NOW + H, 103.0)
        with self.assertRaises(ErrorDiario):
            self.diario.cerrar(op['operacion_id'], NOW + 2 * H, 110.0)
        self.assertEqual(self.diario.operacion(op['operacion_id'])['precio_salida'], 103.0)

    def test_a_plan_from_another_pair_is_refused(self):
        a = self.plan(symbol='OTROUSDT')
        with self.assertRaises(ErrorDiario):
            self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0,
                              plan_id=a['plan_id'])
        with self.assertRaises(ErrorDiario):
            self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0,
                              plan_id=99999)
        with self.assertRaises(ErrorDiario):
            self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=0)

    def test_a_cancelled_trade_is_not_a_zero_loss(self):
        op = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0)
        self.diario.cancelar(op['operacion_id'], NOW + H, 'me equivoque de par')
        fila = self.diario.operacion(op['operacion_id'])
        self.assertEqual(fila['estado'], 'CANCELADA')
        self.assertIsNone(fila['resultado_pct'])
        self.assertEqual(self.diario.resumen()['abiertas'], 0)

    def test_simulated_and_declared_are_counted_apart(self):
        s = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0,
                              tipo='SIMULADA')
        d = self.diario.abrir(symbol='OTROUSDT', ts_ms=NOW, precio_entrada=50.0,
                              tipo='DECLARADA', cantidad=2)
        self.diario.cerrar(s['operacion_id'], NOW + H, 110.0)
        self.diario.cerrar(d['operacion_id'], NOW + H, 45.0)
        tipos = {f['tipo']: f for f in self.diario.resumen()['por_tipo']
                 if f['estado'] == 'CERRADA'}
        self.assertEqual(tipos['SIMULADA']['suma_pct'], 9.5)
        self.assertEqual(tipos['DECLARADA']['suma_pct'], -10.5)
        self.assertNotIn('IMPORTADA', tipos)
        moneda = {f['tipo']: f['suma'] for f in self.diario.resumen()['moneda_por_tipo']}
        self.assertEqual(moneda, {'DECLARADA': -10.5})   # la simulada no tiene dinero

    def test_an_open_trade_shows_an_unrealised_number_marked_as_such(self):
        op = self.diario.abrir(symbol='TESTUSDT', ts_ms=NOW, precio_entrada=100.0)
        viva = self.diario.con_precio(self.diario.operacion(op['operacion_id']), 103.0)
        self.assertEqual(viva['no_realizado_pct'], 2.5)
        self.assertIsNone(viva['resultado_pct'])
        cerrada = self.diario.cerrar(op['operacion_id'], NOW + H, 103.0)
        self.assertIsNone(self.diario.con_precio(cerrada, 120.0)['no_realizado_pct'])

    def test_the_migration_creates_the_journal_empty(self):
        self.assertGreaterEqual(SCHEMA_VERSION, 18)
        tablas = {r[0] for r in self.db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'operaciones', 'operacion_eventos'} <= tablas)
        self.assertEqual(self.db.diario_operaciones().listar(), [])


if __name__ == '__main__':
    unittest.main()
