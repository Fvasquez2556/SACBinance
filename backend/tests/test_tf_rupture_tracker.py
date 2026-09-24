import unittest

from src.analysis.tf_rupture import RUPTURA_ALCISTA, RUPTURA_BAJISTA
from src.analysis.tf_rupture_tracker import TFRuptureShadow
from src.state.symbol_state import Candle, Metrics
from tests.test_pair_report import _rango, _ruptura_alcista, _ruptura_bajista

_MIN = 60_000


class FakeDb:
    def __init__(self):
        self.rows = {}
        self.next_id = 1

    def get_rupturas_tf_abiertas(self):
        return [dict(r) for r in self.rows.values() if not r.get("closed")]

    def ultima_ruptura_tf_ts(self, symbol, tf, direction):
        ts = [r["ts_open"] for r in self.rows.values()
              if r["symbol"] == symbol and r["tf"] == tf and r["direction"] == direction]
        return max(ts) if ts else None

    def registrar_ruptura_tf(self, row):
        event_id = self.next_id
        self.next_id += 1
        self.rows[event_id] = dict(row, id=event_id)
        return event_id

    def guardar_ruptura_tf(self, event_id, campos):
        self.rows[event_id].update(campos)


class FakeState:
    """Lo minimo que el tracker le pide a un SymbolState."""

    def __init__(self, buffers, price, candles_1m=None):
        self._buffers = buffers
        self.metrics = Metrics()
        self.metrics.price = price
        self.candles = candles_1m or []
        self.ind_htf = {}

    def get_candles_tf(self, tf):
        return self._buffers.get(tf, [])


def _velas_1m(n=200, precio=103.5):
    return [Candle(t=i * _MIN, o=precio, h=precio * 1.002, l=precio * 0.998,
                   c=precio, v=100.0) for i in range(n)]


def _estado(direccion="alcista", price=None):
    velas = _ruptura_alcista() if direccion == "alcista" else _ruptura_bajista()
    precio = price if price is not None else velas[-1].c
    buffers = {tf: velas for tf in ("5m", "15m", "1h", "4h")}
    return FakeState(buffers, precio, _velas_1m(precio=precio))


class ArmadoTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.shadow = TFRuptureShadow(self.db)

    def test_sin_armar_no_registra_lo_que_ya_estaba_en_curso(self):
        st = _estado("alcista")
        self.assertIsNone(self.shadow.evaluar("TESTUSDT", st, "15m", 10 * _MIN))
        self.assertEqual(self.db.rows, {})

    def test_armar_siembra_la_direccion_sin_abrir_filas(self):
        st = _estado("alcista")
        self.shadow.armar({"TESTUSDT": st})
        self.assertEqual(self.db.rows, {})
        # Ya sembrada esa direccion: repetirla no es un cambio, no abre nada.
        self.assertIsNone(self.shadow.evaluar("TESTUSDT", st, "15m", 10 * _MIN))
        self.assertEqual(self.db.rows, {})

    def test_solo_el_cambio_de_direccion_abre_una_fila(self):
        plano = FakeState({tf: _rango(n=120) for tf in ("5m", "15m", "1h", "4h")},
                          101.0, _velas_1m(precio=101.0))
        self.shadow.armar({"TESTUSDT": plano})
        row = self.shadow.evaluar("TESTUSDT", _estado("alcista"), "15m", 10 * _MIN)
        self.assertIsNotNone(row)
        self.assertEqual(row["direction"], RUPTURA_ALCISTA)
        self.assertEqual(row["tf"], "15m")
        self.assertEqual(len(self.db.rows), 1)

    def test_el_cooldown_del_marco_evita_la_misma_ruptura_repetida(self):
        plano = FakeState({tf: _rango(n=120) for tf in ("5m", "15m", "1h", "4h")},
                          101.0, _velas_1m(precio=101.0))
        self.shadow.armar({"TESTUSDT": plano})
        self.assertIsNotNone(self.shadow.evaluar("TESTUSDT", _estado("alcista"), "15m", 0))
        # Vuelve a plano y de nuevo al alza dentro de las 6 velas de 15m.
        self.shadow.evaluar("TESTUSDT", plano, "15m", 10 * _MIN)
        self.assertIsNone(self.shadow.evaluar("TESTUSDT", _estado("alcista"), "15m", 20 * _MIN))
        self.assertEqual(len(self.db.rows), 1)
        # Pasado el cooldown (6 velas de 15m = 90 min) si vuelve a registrarse.
        self.shadow.evaluar("TESTUSDT", plano, "15m", 100 * _MIN)
        self.assertIsNotNone(self.shadow.evaluar("TESTUSDT", _estado("alcista"), "15m", 120 * _MIN))
        self.assertEqual(len(self.db.rows), 2)

    def test_la_confluencia_del_momento_queda_congelada_en_la_fila(self):
        plano = FakeState({tf: _rango(n=120) for tf in ("5m", "15m", "1h", "4h")},
                          101.0, _velas_1m(precio=101.0))
        self.shadow.armar({"TESTUSDT": plano})
        mixto = FakeState(
            {"5m": _ruptura_alcista(), "15m": _ruptura_alcista(),
             "1h": _ruptura_bajista(), "4h": _ruptura_bajista()},
            103.5, _velas_1m(),
        )
        row = self.shadow.evaluar("TESTUSDT", mixto, "15m", 10 * _MIN)
        self.assertEqual(row["conf_alcistas"], 2)
        self.assertEqual(row["conf_bajistas"], 2)
        self.assertEqual(row["conf_en_conflicto"], 1)


class MedicionTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.shadow = TFRuptureShadow(self.db)
        plano = FakeState({tf: _rango(n=120) for tf in ("5m", "15m", "1h", "4h")},
                          101.0, _velas_1m(precio=101.0))
        self.shadow.armar({"TESTUSDT": plano})

    def _abrir(self, direccion="alcista"):
        row = self.shadow.evaluar("TESTUSDT", _estado(direccion), "15m", 0)
        self.assertIsNotNone(row, "la fila de sombra no se abrio")
        return row

    def test_mide_recorrido_favorable_y_adverso_en_la_direccion(self):
        row = self._abrir()
        entry = row["price_open"]
        self.shadow.on_candle("TESTUSDT", 15 * _MIN, entry * 1.02, entry * 0.99, entry * 1.01)
        guardada = self.db.rows[row["id"]]
        self.assertAlmostEqual(guardada["mfe_direction_pct"], 2.0, places=1)
        self.assertAlmostEqual(guardada["mae_direction_pct"], -1.0, places=1)
        self.assertAlmostEqual(guardada["ret_5m_pct"], 1.0, places=1)

    def test_en_bajista_caer_cuenta_como_favorable(self):
        row = self._abrir("bajista")
        entry = row["price_open"]
        self.shadow.on_candle("TESTUSDT", 15 * _MIN, entry * 1.01, entry * 0.98, entry * 0.99)
        guardada = self.db.rows[row["id"]]
        self.assertAlmostEqual(guardada["mfe_direction_pct"], 2.0, places=1)
        self.assertAlmostEqual(guardada["mae_direction_pct"], -1.0, places=1)
        self.assertAlmostEqual(guardada["ret_5m_pct"], 1.0, places=1)

    def test_registra_el_primer_toque_de_cada_barrera_y_no_lo_pisa(self):
        row = self._abrir()
        sl, tp = row["stop_loss"], row["take_profit"]
        self.shadow.on_candle("TESTUSDT", 5 * _MIN, tp * 0.99, sl * 0.99, sl)
        self.shadow.on_candle("TESTUSDT", 20 * _MIN, tp * 1.01, sl * 0.98, tp)
        guardada = self.db.rows[row["id"]]
        self.assertEqual(guardada["ms_sl"], 5 * _MIN)
        self.assertEqual(guardada["ms_tp"], 20 * _MIN)

    def test_el_relleno_del_retest_se_mide_aparte_de_la_entrada_a_mercado(self):
        row = self._abrir()
        borde = row["entrada_min"]
        self.assertLess(borde, row["price_open"], "el rango deberia tener retest")
        self.shadow.on_candle("TESTUSDT", 5 * _MIN, borde * 1.001, borde * 0.999, borde)
        self.shadow.on_candle("TESTUSDT", 30 * _MIN, borde * 1.03, borde, borde * 1.02)
        guardada = self.db.rows[row["id"]]
        self.assertEqual(guardada["ms_fill"], 5 * _MIN)
        self.assertAlmostEqual(guardada["precio_fill"], borde, places=6)
        # Desde el relleno el recorrido favorable es mayor que desde el precio
        # de deteccion: esa diferencia es justo lo que hay que medir.
        self.assertGreater(guardada["mfe_fill_pct"], guardada["mfe_direction_pct"])

    def test_sin_relleno_la_entrada_del_retest_queda_vacia_no_en_cero(self):
        row = self._abrir()
        entry = row["price_open"]
        self.shadow.on_candle("TESTUSDT", 5 * _MIN, entry * 1.01, entry, entry * 1.005)
        guardada = self.db.rows[row["id"]]
        self.assertIsNone(guardada.get("ms_fill"))
        self.assertIsNone(guardada.get("precio_fill"))

    def test_la_ventana_se_cierra_a_las_24h(self):
        row = self._abrir()
        entry = row["price_open"]
        self.shadow.on_candle("TESTUSDT", 24 * 60 * _MIN, entry, entry, entry)
        self.assertEqual(self.db.rows[row["id"]]["closed"], 1)
        self.assertEqual(self.shadow.symbols(), set())

    def test_una_vela_repetida_no_cuenta_dos_veces(self):
        row = self._abrir()
        entry = row["price_open"]
        self.shadow.on_candle("TESTUSDT", 15 * _MIN, entry, entry, entry)
        self.shadow.on_candle("TESTUSDT", 15 * _MIN, entry, entry, entry)
        self.assertEqual(self.db.rows[row["id"]]["n_velas"], 1)

    def test_recupera_las_filas_abiertas_tras_un_reinicio(self):
        row = self._abrir()
        otra = TFRuptureShadow(self.db)
        self.assertEqual(otra.cargar(), 1)
        self.assertEqual(otra.symbols(), {"TESTUSDT"})
        entry = row["price_open"]
        otra.on_candle("TESTUSDT", 15 * _MIN, entry * 1.02, entry, entry)
        self.assertAlmostEqual(self.db.rows[row["id"]]["mfe_direction_pct"], 2.0, places=1)


if __name__ == "__main__":
    unittest.main()
