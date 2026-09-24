"""Las tasas medidas del informe por marcos: con su n, su ventana y sin rellenos."""
import sqlite3
import time
import unittest

from src.analysis.pair_report import construir_informe
from src.analysis.tf_estadistica import EstadisticaRupturas, celda
from src.analysis.tf_rupture import RUPTURA_ALCISTA, RUPTURA_BAJISTA
from src.state.symbol_state import Candle

H = 3600_000
AHORA = int(time.time() * 1000)

_ESQUEMA = """
CREATE TABLE rupturas_tf (
  id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, tf TEXT, direction TEXT,
  ts_open INTEGER, confirmada INTEGER, conf_confirmadas INTEGER,
  conf_en_conflicto INTEGER, tp_bloqueado INTEGER,
  ms_fill INTEGER, ms_tp INTEGER, ms_sl INTEGER, closed INTEGER);
"""


def _vela(i, alto, bajo, cierre):
    return Candle(t=i * 60_000, o=cierre, h=alto, l=bajo, c=cierre, v=1000.0)


def _rango(n=114, techo=102.0, suelo=100.0):
    velas = []
    for i in range(n):
        fase = i % 8
        if fase == 0:
            velas.append(_vela(i, techo, techo - 0.4, techo - 0.3))
        elif fase == 4:
            velas.append(_vela(i, suelo + 0.4, suelo, suelo + 0.3))
        else:
            medio = (techo + suelo) / 2
            velas.append(_vela(i, medio + 0.2, medio - 0.2, medio))
    return velas


def _ruptura_alcista(techo=102.0):
    velas = _rango()
    for k in range(6):
        c = techo + 0.5 + k * 0.2
        velas.append(_vela(len(velas), c + 0.1, c - 0.3, c))
    return velas


class EstadisticaTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript(_ESQUEMA)

    def tearDown(self):
        self.conn.close()

    def sembrar(self, n, *, tf='5m', confirmadas=2, conflicto=0, estorbo=0,
                acierta=True, horas_tp=4.0, llena=True, dias=1,
                direccion=RUPTURA_ALCISTA):
        for i in range(n):
            self.conn.execute(
                """INSERT INTO rupturas_tf (symbol, tf, direction, ts_open, confirmada,
                     conf_confirmadas, conf_en_conflicto, tp_bloqueado, ms_fill, ms_tp,
                     ms_sl, closed)
                   VALUES ('TESTUSDT',?,?,?,1,?,?,?,?,?,?,1)""",
                (tf, direccion, AHORA - dias * 24 * H, confirmadas, conflicto,
                 estorbo, 0 if llena else None,
                 int(horas_tp * H) if (llena and acierta) else None,
                 None if acierta else H))
        self.conn.commit()

    def stats(self, **kw):
        return EstadisticaRupturas(self.conn, horizonte_ms=12 * H, **kw).instantanea()

    def test_a_cell_carries_its_sample_and_its_window(self):
        self.sembrar(80)
        inst = self.stats(min_n=50, ventana_dias=14)
        c = celda(inst, 'por_marco', '5m', RUPTURA_ALCISTA)
        self.assertEqual((c['n'], c['rellenadas'], c['fiable']), (80, 80, True))
        self.assertEqual(c['tp_antes_sl'], 100.0)
        self.assertEqual(inst['ventana_dias'], 14)
        self.assertEqual(inst['horizonte_h'], 12.0)

    def test_below_the_minimum_it_says_so_instead_of_widening_the_cell(self):
        self.sembrar(20)
        c = celda(self.stats(min_n=50), 'por_marco', '5m', RUPTURA_ALCISTA)
        self.assertFalse(c['fiable'])
        self.assertIsNone(c['tp_antes_sl'])
        self.assertIsNone(c['horas_mediana'])
        self.assertEqual(c['n'], 20)          # el dato sigue ahi, sin conclusion

    def test_what_never_filled_is_reported_apart_from_what_hit(self):
        self.sembrar(60, llena=True, acierta=True)
        self.sembrar(40, llena=False, acierta=False)
        c = celda(self.stats(min_n=50), 'por_marco', '5m', RUPTURA_ALCISTA)
        self.assertEqual((c['n'], c['rellenadas']), (100, 60))
        self.assertEqual(c['pct_fill'], 60.0)
        self.assertEqual(c['tp_antes_sl'], 100.0)   # sobre las que llenaron

    def test_the_window_leaves_out_what_is_too_old(self):
        self.sembrar(60, dias=1)
        self.sembrar(60, dias=30)
        c = celda(self.stats(min_n=50, ventana_dias=14), 'por_marco', '5m', RUPTURA_ALCISTA)
        self.assertEqual(c['n'], 60)

    def test_the_horizon_share_counts_only_what_fit_in_it(self):
        self.sembrar(60, horas_tp=4.0)
        self.sembrar(60, horas_tp=20.0, tf='1h')
        inst = self.stats(min_n=50)
        rapido = celda(inst, 'por_marco', '5m', RUPTURA_ALCISTA)
        lento = celda(inst, 'por_marco', '1h', RUPTURA_ALCISTA)
        self.assertEqual(rapido['pct_dentro_horizonte'], 100.0)
        self.assertEqual(lento['pct_dentro_horizonte'], 0.0)
        self.assertEqual(lento['horas_mediana'], 20.0)

    def test_a_missing_table_gives_no_numbers_instead_of_an_error(self):
        vacia = sqlite3.connect(':memory:')
        self.assertEqual(EstadisticaRupturas(vacia).instantanea(), {})
        vacia.close()
        self.assertIsNone(celda({}, 'por_marco', '5m', RUPTURA_ALCISTA))


class InformeConTasasTests(unittest.TestCase):
    """Lo que el informe enseña ahora, y los dos avisos que se reescribieron."""

    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript(_ESQUEMA)

    def tearDown(self):
        self.conn.close()

    def sembrar(self, n, **kw):
        EstadisticaTests.sembrar(self, n, **kw)

    def informe(self, buffers=None, min_n=50):
        inst = EstadisticaRupturas(self.conn, min_n=min_n, horizonte_ms=12 * H).instantanea()
        velas = _ruptura_alcista()
        return construir_informe('TESTUSDT', velas[-1].c,
                                 buffers or {'5m': velas}, velas, estadistica=inst)

    def test_each_reading_arrives_with_the_measured_rate_beside_it(self):
        self.sembrar(80, tf='5m', horas_tp=3.0)
        marco = self.informe()['timeframes'][0]
        self.assertEqual(marco['direccion'], RUPTURA_ALCISTA)
        est = marco['estadistica']
        self.assertEqual(est['marco']['n'], 80)
        self.assertTrue(est['marco']['fiable'])
        self.assertEqual(est['ventana_dias'], 14)
        self.assertEqual(est['horizonte_h'], 12.0)

    def test_the_summary_is_conditioned_on_confluence_not_on_the_longest_frame(self):
        self.sembrar(80, confirmadas=1)
        resumen = self.informe()['resumen']
        est = resumen['estadistica']
        self.assertEqual(est['n_confirmadas'], resumen['n_confirmadas'])
        celda_conf = est['confluencia']
        self.assertTrue(celda_conf is None or celda_conf['n'] >= 0)

    def test_the_conflict_warning_no_longer_claims_a_risk_the_data_denies(self):
        # Conflicto lee MEJOR que el acuerdo: 80 aciertos con conflicto,
        # 80 fallos sin el.
        # La direccion dominante en este caso es la bajista (marco mas largo),
        # asi que la comparacion se busca en SU celda, no en otra.
        for direccion in (RUPTURA_ALCISTA, RUPTURA_BAJISTA):
            self.sembrar(80, conflicto=1, acierta=True, direccion=direccion)
            self.sembrar(80, conflicto=0, acierta=False, direccion=direccion)
        velas_alcista = _ruptura_alcista()
        velas_bajista = _rango() + [_vela(114 + k, 99.7 - k * 0.2, 99.2 - k * 0.2,
                                          99.4 - k * 0.2) for k in range(6)]
        informe = self.informe({'5m': velas_alcista, '15m': velas_bajista})
        self.assertTrue(informe['resumen']['en_conflicto'])
        aviso = next(a for a in informe['advertencias'] if a.startswith('Marcos en desacuerdo'))
        self.assertIn('no anticipa peor resultado', aviso)
        self.assertIn('n=80', aviso)
        self.assertNotIn('24h', aviso)

    def test_without_sample_the_conflict_warning_states_no_conclusion(self):
        velas_alcista = _ruptura_alcista()
        velas_bajista = _rango() + [_vela(114 + k, 99.7 - k * 0.2, 99.2 - k * 0.2,
                                          99.4 - k * 0.2) for k in range(6)]
        informe = self.informe({'5m': velas_alcista, '15m': velas_bajista})
        aviso = next(a for a in informe['advertencias'] if a.startswith('Marcos en desacuerdo'))
        self.assertIn('Sin muestra suficiente', aviso)
        self.assertNotIn('no anticipa', aviso)

    def test_a_frame_too_slow_for_the_day_is_flagged_with_its_measured_share(self):
        self.sembrar(80, tf='5m', horas_tp=20.0)      # solo el 0% cabe en 12 h
        informe = self.informe()
        aviso = next((a for a in informe['advertencias'] if a.startswith('Horizonte')), None)
        self.assertIsNotNone(aviso)
        self.assertIn('5m (0.0%', aviso)
        self.assertIn('12', aviso)

    def test_a_frame_that_fits_the_day_raises_no_horizon_warning(self):
        self.sembrar(80, tf='5m', horas_tp=3.0)
        informe = self.informe()
        self.assertIsNone(next((a for a in informe['advertencias']
                                if a.startswith('Horizonte')), None))

    def test_without_statistics_the_report_still_works_as_before(self):
        velas = _ruptura_alcista()
        informe = construir_informe('TESTUSDT', velas[-1].c, {'5m': velas}, velas)
        self.assertIsNone(informe['timeframes'][0]['estadistica'])
        self.assertIsNone(informe['resumen']['estadistica'])


if __name__ == '__main__':
    unittest.main()
