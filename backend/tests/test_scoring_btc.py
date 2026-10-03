"""
El regimen de BTC no puede saltarse el techo sin flujo ni el piso por macro.

Hasta el 3-oct-2026 engine.py multiplicaba el score por el regimen de BTC
DESPUES de score_and_tier y recalculaba el tier desde cero. Un 79 sin flujo
confirmado pasaba a 86 (FUERTE), y un 73 con macro NEUTRAL volvia a ser
MODERADA pese al piso de 75. Ver audit/2026-10-03/revision-completa (E1).
"""
import unittest
from types import SimpleNamespace

from src.analysis.scoring import (TIER_EXTRA, TIER_FUERTE, TIER_MODERADA,
                                  TIER_NONE, score_and_tier)
from src.state.symbol_state import Metrics


def _metricas(z_rise, velocity, vol_ratio=2.0, drawdown=0.0):
    m = Metrics()
    m.z_rise = z_rise
    m.velocity = velocity
    m.vol_ratio = vol_ratio
    m.drawdown_from_peak = drawdown
    return m


def _ind(trend_up=True, rsi5=60.0, macd_rising=True):
    return SimpleNamespace(valid=True, trend_up=trend_up, rsi5=rsi5, macd_rising=macd_rising)


SIN_FLUJO = None
CON_FLUJO = SimpleNamespace(trades_30s=20, buy_dominant=True, sell_dominant=False)

# Subida muy fuerte: 48 + 22 + 10 + 6 + 8 + 6 + 5 = 105 -> 100 antes de gates
FUERTE = dict(metrics=_metricas(4.2, 2.0), ind=_ind())
# Subida media: 48 + 4 + 7 + 6 + 8 = 73 (RSI 75 y MACD plano no suman)
MEDIA = dict(metrics=_metricas(2.45, 1.0), ind=_ind(rsi5=75.0, macd_rising=False))


class TestBtcNoSaltaLosFiltros(unittest.TestCase):

    def test_sin_flujo_no_llega_a_fuerte_aunque_btc_suba(self):
        val, tier = score_and_tier("RISING", macro_global="ALCISTA", flow=SIN_FLUJO,
                                   btc_regime="ALCISTA", **FUERTE)
        self.assertEqual(val, 79)
        self.assertEqual(tier, TIER_MODERADA)

    def test_con_flujo_confirmado_si_puede_ser_extra(self):
        val, tier = score_and_tier("RISING", macro_global="ALCISTA", flow=CON_FLUJO,
                                   btc_regime="ALCISTA", **FUERTE)
        self.assertEqual(val, 100)
        self.assertEqual(tier, TIER_EXTRA)

    def test_piso_de_macro_neutral_se_respeta(self):
        val, tier = score_and_tier("RISING", macro_global="NEUTRAL", flow=SIN_FLUJO,
                                   btc_regime="NEUTRAL", **MEDIA)
        self.assertEqual(val, 73)
        self.assertEqual(tier, TIER_NONE)

    def test_btc_alcista_cuenta_antes_del_piso_y_del_techo(self):
        # 73 x 1.10 = 80 -> techo sin flujo 79 -> supera el piso de 75
        val, tier = score_and_tier("RISING", macro_global="NEUTRAL", flow=SIN_FLUJO,
                                   btc_regime="ALCISTA", **MEDIA)
        self.assertEqual(val, 79)
        self.assertEqual(tier, TIER_MODERADA)

    def test_btc_bajista_resta(self):
        # 100 x 0.55 = 55, bajo el piso de 60 con macro ALCISTA
        val, tier = score_and_tier("RISING", macro_global="ALCISTA", flow=CON_FLUJO,
                                   btc_regime="BAJISTA", **FUERTE)
        self.assertEqual(val, 55)
        self.assertEqual(tier, TIER_NONE)

    def test_btc_no_toca_los_fondos(self):
        m = _metricas(0.0, 0.5, vol_ratio=2.0, drawdown=-0.05)
        con_btc = score_and_tier("VALLEY", m, "ALCISTA", stabilize_count=3, flow=CON_FLUJO,
                                 ind=_ind(), btc_regime="ALCISTA")
        sin_btc = score_and_tier("VALLEY", m, "ALCISTA", stabilize_count=3, flow=CON_FLUJO,
                                 ind=_ind(), btc_regime="NEUTRAL")
        self.assertEqual(con_btc, sin_btc)

    def test_ningun_fuerte_sin_flujo_en_toda_la_rejilla(self):
        """El hallazgo del 3-oct, como propiedad: sin flujo confirmado no hay FUERTE ni EXTRA."""
        for macro in ("ALCISTA", "NEUTRAL", "BAJISTA"):
            for btc in ("ALCISTA", "NEUTRAL", "BAJISTA"):
                for z in (2.0, 2.5, 3.0, 4.0, 5.0):
                    for vel in (0.0, 0.5, 1.0, 2.0):
                        val, tier = score_and_tier("RISING", _metricas(z, vel), macro, flow=SIN_FLUJO,
                                                   ind=_ind(), btc_regime=btc)
                        self.assertLessEqual(val, 79, (macro, btc, z, vel))
                        self.assertNotIn(tier, (TIER_FUERTE, TIER_EXTRA), (macro, btc, z, vel))


if __name__ == "__main__":
    unittest.main()


class TestMotorAplicaBtcUnaSolaVez(unittest.TestCase):
    """El camino real: StateEngine.on_closed_candle con BTC alcista y sin flujo."""

    def test_subida_sin_flujo_con_btc_alcista_queda_en_moderada(self):
        import asyncio
        from src.state.engine import StateEngine
        from src.state.symbol_state import Candle

        eng = StateEngine()
        eng._get("BTCUSDT").macro_global = "ALCISTA"
        st = eng._get("XUSDT")
        t0 = 1_790_000_000_000 // 60_000 * 60_000
        velas, p = [], 1.0
        for k in range(120):                      # ruido de +-0,1 % por minuto
            p *= 1.001 if k % 2 == 0 else 0.999
            velas.append(Candle(t=t0 + k * 60_000, o=p, h=p * 1.0004, l=p * 0.9996, c=p, v=1000.0))
        eng.preload_1m("XUSDT", velas)
        st.slopes = {"15m": {"tendencia": "ALCISTA"}}   # no recalcular la macro sin velas de 15m
        st.macro_global = "ALCISTA"
        st.macro_trends["15m"] = "ALCISTA"

        t = velas[-1].t
        for _ in range(3):                        # tres minutos de +0,35 %: subida clara, sin flujo
            t += 60_000
            o, p = p, p * 1.0035
            asyncio.run(eng.on_closed_candle("XUSDT", t, o, p * 1.0002, o * 0.9998, p, 1500.0))

        self.assertEqual(st.fsm_state, "RISING")
        self.assertEqual(st.btc_regime, "ALCISTA")
        # 79 es el techo sin flujo: con el error, 79 x 1.10 daba 86 y FUERTE
        self.assertEqual(st.score, 79)
        self.assertEqual(st.tier, TIER_MODERADA)
