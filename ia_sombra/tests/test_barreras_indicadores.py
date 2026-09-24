"""Las piezas puras: indicadores sobre velas cerradas y el conteo de trayectorias."""
import unittest

import apoyo  # noqa: F401

from sac_ia import barreras, indicadores
from sac_ia.kronos_adapter import futuras, serie_util

META, STOP = 103.7, 95.0


class BarrerasTests(unittest.TestCase):
    def test_quien_toca_primero(self):
        self.assertEqual(barreras.clasificar([(100, 101, 99, 100), (100, 104, 99, 103)], META, STOP),
                         barreras.META)
        self.assertEqual(barreras.clasificar([(100, 101, 94, 95)], META, STOP), barreras.STOP)
        self.assertEqual(barreras.clasificar([(100, 101, 99, 100)] * 5, META, STOP),
                         barreras.NINGUNA)

    def test_meta_y_stop_en_la_misma_vela_no_es_acierto(self):
        self.assertEqual(barreras.clasificar([(100, 104, 94, 100)], META, STOP), barreras.AMBIGUA)

    def test_un_cierre_por_encima_del_maximo_cuenta_como_precio_tocado(self):
        # Kronos da high 103 pero cierra en 104: el camino paso por 104 y toca la meta.
        self.assertEqual(barreras.clasificar([(100, 103, 99, 104)], META, STOP), barreras.META)
        # low por encima de la apertura: el minimo real es la apertura, no el low.
        self.assertEqual(barreras.clasificar([(94.5, 101, 96, 100)], META, STOP), barreras.STOP)

    def test_solo_los_precios_no_finitos_o_no_positivos_invalidan(self):
        self.assertEqual(barreras.clasificar([(100, float("nan"), 99, 100)], META, STOP),
                         barreras.INVALIDA)
        self.assertEqual(barreras.clasificar([(100, 101, 0, 100)], META, STOP), barreras.INVALIDA)

    def test_resumen_cuenta_las_velas_ensanchadas(self):
        r = barreras.resumir([[(100, 101, 99, 100), (100, 100.5, 99, 101)]], 100, META, STOP, 0.25)
        self.assertEqual(r["velas_ensanchadas"], 1)
        self.assertEqual(r["n_validas"], 1)

    def test_resumen_cuenta_por_separado_y_se_abstiene_si_hay_demasiadas_invalidas(self):
        buena_meta = [(100, 104, 99, 103)]
        buena_stop = [(100, 101, 94, 95)]
        mala = [(100, float("inf"), 99, 100)]
        r = barreras.resumir([buena_meta] * 3 + [buena_stop], 100, META, STOP, 0.25)
        self.assertEqual(r["p_meta_antes_que_stop"], 0.75)
        self.assertFalse(r["abstiene"])
        r = barreras.resumir([buena_meta, mala, mala, buena_stop], 100, META, STOP, 0.25)
        self.assertTrue(r["abstiene"])
        self.assertIsNone(r["p_meta_antes_que_stop"])

    def test_la_vela_que_empezo_antes_del_aviso_se_descarta(self):
        t = list(range(49))
        self.assertEqual(futuras(t, primera_apertura_ms=1000, as_of_ms=1500, pasos_futuros=48),
                         list(range(1, 49)))
        self.assertEqual(futuras(t, primera_apertura_ms=1500, as_of_ms=1500, pasos_futuros=48),
                         list(range(0, 48)))

    def test_serie_con_hueco_no_sirve(self):
        paso = 3_600_000
        velas = [{"t": i * paso, "o": 1, "h": 1, "l": 1, "c": 1} for i in range(10)]
        self.assertIsNone(serie_util(velas, 10, paso))
        del velas[4]
        self.assertIn("huecos", serie_util(velas + [velas[-1]], 10, paso))
        self.assertIn("solo", serie_util(velas[:5], 10, paso))


class IndicadoresTests(unittest.TestCase):
    def velas(self, cierres):
        return [(i, c, c + 0.5, c - 0.5, c, 10.0) for i, c in enumerate(cierres)]

    def test_rsi_de_una_serie_que_solo_sube_es_100(self):
        self.assertEqual(indicadores.rsi([float(i) for i in range(1, 40)]), 100.0)

    def test_rsi_simetrico_ronda_50(self):
        cierres = [100 + (1 if i % 2 else -1) for i in range(60)]
        self.assertAlmostEqual(indicadores.rsi(cierres), 50, delta=5)

    def test_rsi_sin_suficientes_velas_es_none_no_cero(self):
        self.assertIsNone(indicadores.rsi([1.0] * 10))

    def test_atr_pct_y_posicion(self):
        v = self.velas([100.0] * 30)
        self.assertAlmostEqual(indicadores.atr_pct(v), 1.0, places=6)
        # ultimas 50: cierres 10..59, rango [9,5; 59,5], ultimo cierre 59
        self.assertEqual(indicadores.posicion_en_rango(self.velas(list(range(1, 60))), 50), 0.99)

    def test_resumen_descarta_velas_imposibles_y_dice_si_hay_huecos(self):
        v = self.velas([100.0 + i * 0.1 for i in range(120)])
        v[10] = (10, 100, 99, 101, 100, 1)       # high < low
        r = indicadores.resumen_marco(v, 1)
        self.assertEqual(r["n_velas"], 119)
        self.assertTrue(r["continuas"])           # el hueco esta fuera de las ultimas 50
        self.assertIsNotNone(r["rsi14"])


if __name__ == "__main__":
    unittest.main()
