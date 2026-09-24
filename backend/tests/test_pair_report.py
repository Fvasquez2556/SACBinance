import unittest

from src.analysis.pair_report import construir_informe, normalizar_symbol
from src.analysis.tf_rupture import (
    RUPTURA_ALCISTA,
    RUPTURA_BAJISTA,
    SIN_DATOS,
    SIN_RUPTURA,
    leer_tf,
)
from src.analysis.trade_levels import calcular_plan_direccional
from src.state.symbol_state import Candle

_MINUTO = 60_000


def _vela(i, alto, bajo, cierre):
    return Candle(t=i * _MINUTO, o=cierre, h=alto, l=bajo, c=cierre, v=1000.0)


def _rango(n=114, techo=102.0, suelo=100.0):
    """Zigzag limpio entre `suelo` y `techo`: deja pivotes repetidos en ambos."""
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


def _ruptura_bajista(suelo=100.0):
    velas = _rango()
    for k in range(6):
        c = suelo - 0.5 - k * 0.2
        velas.append(_vela(len(velas), c + 0.3, c - 0.1, c))
    return velas


class NormalizarSymbolTests(unittest.TestCase):
    def test_completa_el_par_cuando_solo_se_escribe_la_moneda(self):
        self.assertEqual(normalizar_symbol("btc"), "BTCUSDT")
        self.assertEqual(normalizar_symbol(" eth/usdt "), "ETHUSDT")
        self.assertEqual(normalizar_symbol("SOLUSDT"), "SOLUSDT")

    def test_rechaza_lo_que_no_tiene_forma_de_par(self):
        for entrada in ("", "   ", "b", "BTC USDT", "../etc/passwd", "DROP TABLE"):
            self.assertIsNone(normalizar_symbol(entrada), entrada)


class LeerTFTests(unittest.TestCase):
    def test_cierre_sobre_un_techo_tocado_es_ruptura_alcista(self):
        velas = _ruptura_alcista()
        lectura = leer_tf("15m", velas, velas[-1].c)
        self.assertEqual(lectura.direccion, RUPTURA_ALCISTA)
        self.assertTrue(lectura.confirmada)
        self.assertAlmostEqual(lectura.nivel_roto, 102.0, places=6)
        self.assertGreaterEqual(lectura.toques_nivel, 2)
        self.assertEqual(lectura.velas_desde_ruptura, 6)

    def test_cierre_bajo_un_suelo_tocado_es_ruptura_bajista(self):
        velas = _ruptura_bajista()
        lectura = leer_tf("1h", velas, velas[-1].c)
        self.assertEqual(lectura.direccion, RUPTURA_BAJISTA)
        self.assertAlmostEqual(lectura.nivel_roto, 100.0, places=6)

    def test_el_rango_intacto_no_es_ruptura(self):
        velas = _rango(n=120)
        lectura = leer_tf("15m", velas, velas[-1].c)
        self.assertEqual(lectura.direccion, SIN_RUPTURA)
        self.assertIsNone(lectura.nivel_roto)

    def test_una_sola_vela_pasada_no_se_da_por_confirmada(self):
        velas = _ruptura_alcista()[:-5]   # deja un unico cierre sobre el techo
        lectura = leer_tf("15m", velas, velas[-1].c)
        self.assertEqual(lectura.direccion, RUPTURA_ALCISTA)
        self.assertFalse(lectura.confirmada)
        self.assertIn("sin confirmar", lectura.razon)

    def test_sin_historia_el_marco_no_opina(self):
        lectura = leer_tf("4h", _rango(n=10), 101.0)
        self.assertEqual(lectura.direccion, SIN_DATOS)
        self.assertFalse(lectura.confirmada)


class PlanDireccionalTests(unittest.TestCase):
    def test_el_rango_va_del_nivel_roto_al_precio_y_el_riesgo_se_mide_a_mercado(self):
        velas = _ruptura_alcista()
        precio = velas[-1].c
        lectura = leer_tf("15m", velas, precio)
        plan = calcular_plan_direccional(
            RUPTURA_ALCISTA, precio, velas, lectura.nivel_roto,
            tf="15m", niveles_sr=lectura.niveles,
        )
        self.assertTrue(plan.valid, plan.reason)
        self.assertAlmostEqual(plan.entrada_max, precio, places=6)
        self.assertLess(plan.entrada_min, plan.entrada_max)
        self.assertGreaterEqual(plan.entrada_min, lectura.nivel_roto - 1e-9)
        # El riesgo se mide en el extremo malo: entrar a mercado, no en el retest.
        self.assertAlmostEqual(plan.entrada_ref, precio, places=6)
        self.assertLess(plan.stop_loss, plan.entrada_min)
        self.assertGreater(plan.take_profit, plan.entrada_max)
        self.assertAlmostEqual(plan.reward_pct, plan.risk_pct * plan.risk_reward, places=1)
        self.assertGreater(plan.mejora_max_pct, 0)

    def test_el_plan_bajista_invierte_los_niveles_y_avisa_de_que_no_esta_medido(self):
        velas = _ruptura_bajista()
        precio = velas[-1].c
        lectura = leer_tf("15m", velas, precio)
        plan = calcular_plan_direccional(
            RUPTURA_BAJISTA, precio, velas, lectura.nivel_roto,
            tf="15m", niveles_sr=lectura.niveles,
        )
        self.assertTrue(plan.valid, plan.reason)
        self.assertGreater(plan.stop_loss, plan.entrada_max)
        self.assertLess(plan.take_profit, plan.entrada_min)
        self.assertIn("vendedoras", plan.advertencia)

    def test_el_beneficio_publicado_descuenta_costes(self):
        velas = _ruptura_alcista()
        lectura = leer_tf("15m", velas, velas[-1].c)
        plan = calcular_plan_direccional(
            RUPTURA_ALCISTA, velas[-1].c, velas, lectura.nivel_roto,
            tf="15m", niveles_sr=lectura.niveles,
        )
        self.assertLess(plan.reward_neto_pct, plan.reward_pct)

    def test_sin_nivel_roto_no_hay_plan(self):
        velas = _rango(n=120)
        plan = calcular_plan_direccional(RUPTURA_ALCISTA, velas[-1].c, velas, None)
        self.assertFalse(plan.valid)
        self.assertIn("nivel roto", plan.reason)


class InformeTests(unittest.TestCase):
    def test_el_informe_cubre_los_cuatro_marcos_y_lleva_sus_advertencias(self):
        velas = _ruptura_alcista()
        buffers = {tf: velas for tf in ("5m", "15m", "1h", "4h")}
        informe = construir_informe("TESTUSDT", velas[-1].c, buffers, velas)
        self.assertEqual([m["tf"] for m in informe["timeframes"]],
                         ["5m", "15m", "1h", "4h"])
        self.assertEqual(informe["resumen"]["direccion_dominante"], RUPTURA_ALCISTA)
        self.assertEqual(informe["resumen"]["tf_dominante"], "4h")
        self.assertTrue(all(m["plan"]["valid"] for m in informe["timeframes"]))
        self.assertTrue(informe["advertencias"])

    def test_marcos_en_desacuerdo_se_marcan_en_vez_de_promediarse(self):
        buffers = {
            "5m": _ruptura_alcista(), "15m": _ruptura_alcista(),
            "1h": _ruptura_bajista(), "4h": _ruptura_bajista(),
        }
        informe = construir_informe("TESTUSDT", 101.0, buffers, buffers["5m"])
        self.assertTrue(informe["resumen"]["en_conflicto"])
        self.assertEqual(informe["resumen"]["n_alcistas"], 2)
        self.assertEqual(informe["resumen"]["n_bajistas"], 2)
        self.assertTrue(any("desacuerdo" in a for a in informe["advertencias"]))

    def test_un_marco_sin_historia_no_hunde_el_informe(self):
        buffers = {"5m": _ruptura_alcista(), "15m": _ruptura_alcista(),
                   "1h": _rango(n=120), "4h": []}
        informe = construir_informe("TESTUSDT", 103.5, buffers, buffers["5m"])
        marcos = {m["tf"]: m for m in informe["timeframes"]}
        self.assertEqual(marcos["4h"]["direccion"], SIN_DATOS)
        self.assertIsNone(marcos["4h"]["plan"])
        self.assertTrue(any("4h" in a for a in informe["advertencias"]))


if __name__ == "__main__":
    unittest.main()
