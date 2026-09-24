"""
Los dos motores de la fase 4.

Lo que se comprueba aqui no es que acierten — no predicen nada y no lo
pretenden. Se comprueba que **no puedan** hacer las tres cosas que este plan
prohibe: llamar compra a una tesis, publicar un plan sin disparador, y rellenar
un hueco de datos con una cifra.
"""
import json
import sqlite3
import unittest

from src.motores.almacen import MOTORES_SCHEMA, AlmacenMotores
from src.motores.caida import (
    ABRE,
    AVANZA,
    INVALIDADO,
    BASE_EN_FORMACION,
    CADUCADO,
    CAIDA_ACTIVA,
    DESACELERACION,
    NUEVA_CAIDA,
    RECUPERACION,
    REBOTE_CONFIRMADO,
    SIN_CAIDA,
    EstadoCaida,
    avanzar_caida,
    ruptura_valida,
)
from src.motores.continuacion import (
    EXPANSION_COMPRESION,
    EXTENDIDO,
    PULLBACK_TENDENCIA,
    RUPTURA_RETEST,
    RUPTURA_SOSTENIDA,
    evaluar_continuacion,
)
from src.motores.contrato import (
    CANDIDATO,
    CONFLICTO,
    DATOS_INSUFICIENTES,
    ESPERAR,
    MOTOR_CAIDA,
    ORIGEN_MUESTRA,
    SIN_TESIS,
    Lectura,
    Observacion,
)

_T = 1_790_000_000_000
_PLAN = {"valid": True, "entry": 100.0, "take_profit": 106.0, "stop_loss": 97.0}
_TENDENCIAS = {"5m": "ALCISTA", "15m": "ALCISTA", "1h": "ALCISTA", "4h": "NEUTRAL"}


def obs(**kw) -> Observacion:
    base = dict(symbol="TESTUSDT", ts_ms=_T, precio=100.0, velas_1m=300,
                fsm_state="RISING", display_state="SUBIENDO",
                tendencias=dict(_TENDENCIAS), plan=dict(_PLAN),
                impulso={"fase": "SOSTENIDA", "consumido_pct": 1.0},
                ancla={"direccion": "SIN_RUPTURA", "tendencia": "NEUTRAL"},
                ancla_tf="1h", ancla_edad_min=10.0)
    base.update(kw)
    return Observacion(**base)


def ancla_rota(**kw) -> dict:
    d = {"direccion": "RUPTURA_ALCISTA", "tendencia": "ALCISTA",
         "confirmada": True, "nivel_roto": 98.0, "toques_nivel": 3}
    d.update(kw)
    return d


# =============================================================================
#  El contrato
# =============================================================================

class ContratoTests(unittest.TestCase):
    def test_a_thesis_cannot_be_called_a_buy_without_its_trigger(self):
        with self.assertRaises(ValueError):
            Lectura(motor="continuacion", symbol="X", ts_ms=_T,
                    veredicto=CANDIDATO, disparador=False)

    def test_only_a_candidate_may_carry_a_plan(self):
        with self.assertRaises(ValueError):
            Lectura(motor="continuacion", symbol="X", ts_ms=_T,
                    veredicto=ESPERAR, entrada=100.0, objetivo=106.0, stop=97.0)

    def test_missing_data_has_to_say_what_is_missing(self):
        with self.assertRaises(ValueError):
            Lectura(motor="caida", symbol="X", ts_ms=_T,
                    veredicto=DATOS_INSUFICIENTES)

    def test_a_contradiction_between_timeframes_is_not_averaged(self):
        o = obs(tendencias={"5m": "ALCISTA", "1h": "BAJISTA"})
        self.assertTrue(o.hay_conflicto())
        self.assertEqual(o.marcos_en_conflicto(), (("5m",), ("1h",)))


# =============================================================================
#  Motor A — continuacion
# =============================================================================

class ContinuacionTests(unittest.TestCase):
    def test_without_the_slow_anchor_it_says_so_instead_of_guessing(self):
        l = evaluar_continuacion(obs(ancla={}))
        self.assertEqual(l.veredicto, DATOS_INSUFICIENTES)
        self.assertTrue(any("1h" in f for f in l.faltantes))
        self.assertIsNone(l.entrada)

    def test_a_stale_anchor_is_missing_data_not_a_silent_fallback(self):
        l = evaluar_continuacion(obs(ancla=ancla_rota(), ancla_edad_min=600.0))
        self.assertEqual(l.veredicto, DATOS_INSUFICIENTES)
        self.assertTrue(any("vieja" in f for f in l.faltantes))

    def test_too_few_candles_is_missing_data(self):
        l = evaluar_continuacion(obs(velas_1m=10, ancla=ancla_rota()))
        self.assertEqual(l.veredicto, DATOS_INSUFICIENTES)
        self.assertTrue(any("velas 1m" in f for f in l.faltantes))

    def test_a_sustained_break_on_the_anchor_with_live_impulse_is_a_candidate(self):
        l = evaluar_continuacion(obs(ancla=ancla_rota(), vol_ratio=1.4))
        self.assertEqual(l.veredicto, CANDIDATO)
        self.assertEqual(l.familia, RUPTURA_SOSTENIDA)
        self.assertTrue(l.disparador)
        self.assertEqual((l.entrada, l.objetivo, l.stop), (100.0, 106.0, 97.0))

    def test_an_unconfirmed_break_waits_and_names_what_is_missing(self):
        l = evaluar_continuacion(obs(ancla=ancla_rota(confirmada=False)))
        self.assertEqual(l.veredicto, ESPERAR)
        self.assertEqual(l.familia, RUPTURA_SOSTENIDA)
        self.assertTrue(any("no la da por" in r for r in l.razones))
        self.assertIsNone(l.entrada)

    def test_an_exhausted_move_is_watched_and_never_chased(self):
        l = evaluar_continuacion(obs(ancla=ancla_rota(),
                                     impulso={"fase": "AGOTADA", "consumido_pct": 9.0}))
        self.assertEqual(l.familia, EXTENDIDO)
        self.assertEqual(l.veredicto, ESPERAR)
        self.assertFalse(l.disparador)

    def test_a_move_that_already_ran_too_far_is_extended_too(self):
        l = evaluar_continuacion(obs(ancla=ancla_rota(),
                                     impulso={"fase": "ACELERANDO", "consumido_pct": 12.0}))
        self.assertEqual(l.familia, EXTENDIDO)
        self.assertEqual(l.veredicto, ESPERAR)

    def test_a_flat_coin_is_not_an_extended_move(self):
        """
        `FASE_AGOTADA` se devuelve en cuanto el precio esta bajo la EMA7 en dos
        marcos, o sea casi cualquier moneda parada. En la primera pasada en
        vivo eso etiqueto 320 lecturas como "movimiento extendido" con un
        consumido de 0,74 % de mediana y sin ninguna ruptura detras. Una moneda
        quieta no tiene tesis; no puede tenerla gastada.
        """
        l = evaluar_continuacion(obs(
            ancla={"direccion": "SIN_RUPTURA", "tendencia": "NEUTRAL"},
            impulso={"fase": "AGOTADA", "consumido_pct": 0.74}))
        self.assertEqual(l.veredicto, SIN_TESIS)
        self.assertIsNone(l.familia)

    def test_a_pullback_is_not_swallowed_by_the_exhaustion_check(self):
        """
        Un pullback dentro de una tendencia viva ES, por definicion, precio por
        debajo de su EMA corta — lo mismo que dispara FASE_AGOTADA. Sin la
        excepcion, EXTENDIDO se comia justo la familia que se quiere medir.
        """
        l = evaluar_continuacion(obs(
            ancla={"direccion": "SIN_RUPTURA", "tendencia": "ALCISTA"},
            grind={"detected": True},
            impulso={"fase": "AGOTADA", "consumido_pct": 0.9},
            retroceso={"detectado": True, "confirmado": True,
                       "caida_pct": -2.4, "rebote_pct": 1.4}))
        self.assertEqual(l.familia, PULLBACK_TENDENCIA)
        self.assertEqual(l.veredicto, CANDIDATO)

    def test_a_really_spent_move_is_still_caught(self):
        for imp in ({"fase": "AGOTADA", "consumido_pct": 1.0},
                    {"fase": "SOSTENIDA", "consumido_pct": 12.0}):
            l = evaluar_continuacion(obs(ancla=ancla_rota(), impulso=imp))
            self.assertEqual(l.familia, EXTENDIDO, imp)
            self.assertEqual(l.veredicto, ESPERAR)

    def test_the_retest_needs_the_rebound_confirmed_before_it_is_a_buy(self):
        cerca = obs(ancla=ancla_rota(nivel_roto=99.5), precio=100.0,
                    retroceso={"detectado": True, "confirmado": False})
        l = evaluar_continuacion(cerca)
        self.assertEqual(l.familia, RUPTURA_RETEST)
        self.assertEqual(l.veredicto, ESPERAR)
        l2 = evaluar_continuacion(obs(
            ancla=ancla_rota(nivel_roto=99.5), precio=100.0,
            retroceso={"detectado": True, "confirmado": True}))
        self.assertEqual(l2.veredicto, CANDIDATO)
        self.assertEqual(l2.familia, RUPTURA_RETEST)

    def test_a_pullback_in_a_live_trend_waits_for_the_measured_bounce(self):
        base = dict(ancla={"direccion": "SIN_RUPTURA", "tendencia": "ALCISTA"},
                    grind={"detected": True},
                    retroceso={"detectado": True, "confirmado": False,
                               "caida_pct": -2.4, "rebote_pct": 0.3})
        l = evaluar_continuacion(obs(**base))
        self.assertEqual(l.familia, PULLBACK_TENDENCIA)
        self.assertEqual(l.veredicto, ESPERAR)
        base["retroceso"] = {"detectado": True, "confirmado": True,
                             "caida_pct": 2.4, "rebote_pct": 1.4}
        self.assertEqual(evaluar_continuacion(obs(**base)).veredicto, CANDIDATO)

    def test_compression_says_when_not_where_so_it_never_fires_alone(self):
        l = evaluar_continuacion(obs(
            ancla={"direccion": "SIN_RUPTURA", "tendencia": "NEUTRAL"},
            compresion={"detected": True, "pivot": 101.0}, precio=100.0))
        self.assertEqual(l.familia, EXPANSION_COMPRESION)
        self.assertEqual(l.veredicto, ESPERAR)
        self.assertTrue(any("no hacia donde" in r for r in l.razones))

    def test_a_trigger_with_the_timeframes_contradicting_is_conflict_not_a_buy(self):
        l = evaluar_continuacion(obs(
            ancla=ancla_rota(), vol_ratio=1.4,
            tendencias={"5m": "ALCISTA", "15m": "BAJISTA", "1h": "ALCISTA"}))
        self.assertEqual(l.veredicto, CONFLICTO)
        self.assertIsNone(l.entrada)
        self.assertTrue(any("se contradicen" in r for r in l.razones))

    def test_a_trigger_without_valid_levels_is_not_a_buy(self):
        l = evaluar_continuacion(obs(ancla=ancla_rota(), vol_ratio=1.4,
                                     plan={"valid": False}))
        self.assertEqual(l.veredicto, ESPERAR)
        self.assertTrue(any("niveles validos" in r for r in l.razones))

    def test_nothing_happening_is_reported_as_nothing_happening(self):
        l = evaluar_continuacion(obs(
            ancla={"direccion": "SIN_RUPTURA", "tendencia": "NEUTRAL"}))
        self.assertEqual(l.veredicto, SIN_TESIS)
        self.assertIsNone(l.familia)

    def test_the_same_observation_always_gives_the_same_reading(self):
        o = obs(ancla=ancla_rota(), vol_ratio=1.4)
        a, b = evaluar_continuacion(o), evaluar_continuacion(o)
        self.assertEqual(a.como_fila(), b.como_fila())


# =============================================================================
#  Motor B — caida y recuperacion
# =============================================================================

def obs_caida(**kw) -> Observacion:
    base = dict(fsm_state="DROPPING", display_state="CAYENDO",
                taxonomia={"estado": "CAIDA"},
                retroceso={"detectado": False, "confirmado": False,
                           "caida_pct": -4.0, "suelo": 96.0, "pico_previo": 100.0},
                base_rebote={}, precio=96.0)
    base.update(kw)
    return obs(**base)


class CaidaTests(unittest.TestCase):
    def test_a_market_with_no_buy_is_still_followed(self):
        est, lec, motivo = avanzar_caida(EstadoCaida(symbol="TESTUSDT"), obs_caida())
        self.assertEqual(motivo, ABRE)
        self.assertEqual(est.estado, CAIDA_ACTIVA)
        self.assertEqual(lec.veredicto, ESPERAR)
        self.assertIsNone(lec.entrada)
        self.assertTrue(any("No se compra" in r for r in lec.razones))

    def test_the_drop_is_measured_in_magnitude_not_in_sign(self):
        """
        `retroceso.caida_pct` llega con signo: una caida del 26 % es -26.0.
        El motor comparaba el valor con signo contra un umbral positivo, asi
        que no podia abrir jamas. Ocho caidas reales de entre -18 % y -45 %
        pasaron por la maquina sin abrir una sola vez. Las pruebas de antes no
        lo vieron porque sus datos de ejemplo tenian el mismo signo del error.
        """
        for magnitud in (-2.0, -4.0, -18.79, -44.92):
            est, lec, motivo = avanzar_caida(
                EstadoCaida(symbol="TESTUSDT"),
                obs_caida(retroceso={"detectado": True, "caida_pct": magnitud,
                                     "suelo": 96.0, "pico_previo": 100.0}))
            self.assertEqual(motivo, ABRE, f"no abrio con {magnitud} %")
            self.assertEqual(est.estado, CAIDA_ACTIVA)
            self.assertIn(f"{abs(magnitud):.2f} %", lec.razones[0])

    def test_a_shallow_dip_does_not_open_an_episode(self):
        est, lec, motivo = avanzar_caida(
            EstadoCaida(symbol="TESTUSDT"),
            obs_caida(retroceso={"detectado": False, "caida_pct": -0.4}))
        self.assertIsNone(motivo)
        self.assertEqual(est.estado, SIN_CAIDA)
        self.assertEqual(lec.veredicto, SIN_TESIS)

    def test_the_whole_sequence_only_buys_at_the_declared_trigger(self):
        est = EstadoCaida(symbol="TESTUSDT")
        est, _, _ = avanzar_caida(est, obs_caida())
        self.assertEqual(est.estado, CAIDA_ACTIVA)

        est, lec, _ = avanzar_caida(est, obs_caida(fsm_state="BOTTOMING",
                                                   display_state="TOCÓ_FONDO"))
        self.assertEqual(est.estado, DESACELERACION)
        self.assertEqual(lec.veredicto, ESPERAR)

        est, lec, _ = avanzar_caida(est, obs_caida(
            fsm_state="VALLEY", display_state="CONSOLIDANDO",
            base_rebote={"base_velas": 40, "base_techo": 97.5, "base_piso": 96.0,
                         "vol_dryup": 0.55}))
        self.assertEqual(est.estado, BASE_EN_FORMACION)

        est, lec, _ = avanzar_caida(est, obs_caida(
            fsm_state="RISING", display_state="SUBIENDO", precio=96.8,
            retroceso={"detectado": True, "confirmado": False, "caida_pct": -4.0,
                       "suelo": 96.0, "rebote_pct": 0.8},
            base_rebote={"base_velas": 40, "base_techo": 97.5, "rompio": False}))
        self.assertEqual(est.estado, RECUPERACION)
        self.assertEqual(lec.veredicto, ESPERAR)
        self.assertIsNone(lec.entrada)
        self.assertTrue(any("disparador declarado" in r for r in lec.razones))

        est, lec, motivo = avanzar_caida(est, obs_caida(
            fsm_state="RISING", display_state="SUBIENDO", precio=97.8,
            retroceso={"detectado": True, "confirmado": True, "caida_pct": -4.0,
                       "suelo": 96.0, "rebote_pct": 1.9},
            base_rebote={"base_velas": 40, "base_techo": 97.5, "rompio": True,
                         "ruptura_vol_ratio": 3.2, "dist_techo_pct": 0.3}))
        self.assertEqual(motivo, AVANZA)
        self.assertEqual(est.estado, REBOTE_CONFIRMADO)
        self.assertEqual(lec.veredicto, CANDIDATO)
        self.assertTrue(lec.disparador)
        self.assertEqual((lec.entrada, lec.objetivo, lec.stop), (100.0, 106.0, 97.0))

    def test_a_confirmed_rebound_is_a_buy_once_not_every_minute(self):
        """
        El disparador es un instante. Un rebote confirmado hace tres horas no
        es una compra nueva cada minuto: el plan que nacio de ahi sigue su
        propio reloj. Sin esto, el replay sobre caidas reales marcaba entre 161
        y 340 minutos como candidato en un solo par.
        """
        est = EstadoCaida(symbol="TESTUSDT", estado=RECUPERACION, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0)
        disparo = dict(
            precio=97.8,
            retroceso={"detectado": True, "confirmado": True, "caida_pct": -4.0,
                       "suelo": 96.0, "rebote_pct": 1.9},
            base_rebote={"rompio": True, "base_techo": 97.5, "base_piso": 97.0,
                         "ruptura_vol_ratio": 3.2, "dist_techo_pct": 0.3})
        est, lec, motivo = avanzar_caida(est, obs_caida(**disparo))
        self.assertEqual(motivo, AVANZA)
        self.assertEqual(lec.veredicto, CANDIDATO)

        for i in range(1, 4):
            est, lec, motivo = avanzar_caida(
                est, obs_caida(ts_ms=_T + i * 60_000, **disparo))
            self.assertIsNone(motivo)
            self.assertEqual(est.estado, REBOTE_CONFIRMADO)
            self.assertEqual(lec.veredicto, ESPERAR)
            self.assertIsNone(lec.entrada)
            self.assertTrue(any("ya ocurrio" in r for r in lec.razones))

    def test_breaking_the_base_without_the_bounce_is_still_not_a_buy(self):
        est = EstadoCaida(symbol="TESTUSDT", estado=RECUPERACION, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0)
        est2, lec, motivo = avanzar_caida(est, obs_caida(
            precio=97.8, retroceso={"detectado": True, "confirmado": False,
                                    "caida_pct": -4.0, "suelo": 96.0},
            base_rebote={"rompio": True, "base_techo": 97.5}))
        self.assertIsNone(motivo)
        self.assertEqual(est2.estado, RECUPERACION)
        self.assertEqual(lec.veredicto, ESPERAR)

    def test_a_failed_rebound_is_closed_even_if_the_absolute_low_holds(self):
        """
        Perder el piso de la base no es perder el minimo de la caida. Sin esta
        regla, un rebote confirmado seguia marcado como confirmado mientras el
        precio se lo comia, con dos puntos de margen hasta el suelo.
        """
        est = EstadoCaida(symbol="TESTUSDT", estado=REBOTE_CONFIRMADO,
                          desde_ms=_T, abierto_ms=_T, suelo=96.0, base_piso=97.0)
        est2, lec, motivo = avanzar_caida(est, obs_caida(precio=96.8))
        self.assertEqual(motivo, INVALIDADO)
        self.assertEqual(est2.estado, SIN_CAIDA)
        self.assertEqual(lec.veredicto, SIN_TESIS)
        self.assertIsNone(lec.entrada)
        self.assertTrue(any("conserva su resultado" in r for r in lec.razones))

    def test_a_rebound_holding_above_its_base_floor_stays_alive(self):
        est = EstadoCaida(symbol="TESTUSDT", estado=REBOTE_CONFIRMADO,
                          desde_ms=_T, abierto_ms=_T, suelo=96.0, base_piso=97.0)
        est2, _, motivo = avanzar_caida(est, obs_caida(
            precio=97.6,
            retroceso={"detectado": True, "confirmado": True, "caida_pct": -4.0,
                       "suelo": 96.0, "rebote_pct": 1.7},
            base_rebote={"rompio": True, "base_techo": 97.5, "base_piso": 97.0,
                                     "ruptura_vol_ratio": 3.2, "dist_techo_pct": 0.3}))
        self.assertIsNone(motivo)
        self.assertEqual(est2.estado, REBOTE_CONFIRMADO)

    def test_touching_the_ceiling_without_volume_is_not_the_trigger(self):
        """
        `base_rebote.rompio` se pone en cuanto el maximo pasa el techo, ANTES
        de mirar el volumen: el detector puede devolver `rompio=True` con
        `detected=False` y motivo «rompe sin volumen». Tomarlo como disparador
        confirmaba rebotes que el propio detector rechaza.
        """
        est = EstadoCaida(symbol="TESTUSDT", estado=RECUPERACION, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0)
        flojo = dict(precio=97.8,
                     retroceso={"detectado": True, "confirmado": True,
                                "caida_pct": -4.0, "suelo": 96.0, "rebote_pct": 1.9},
                     base_rebote={"rompio": True, "base_techo": 97.5,
                                  "ruptura_vol_ratio": 0.5, "dist_techo_pct": 0.2})
        est2, lec, motivo = avanzar_caida(est, obs_caida(**flojo))
        self.assertIsNone(motivo)
        self.assertEqual(est2.estado, RECUPERACION)
        self.assertEqual(lec.veredicto, ESPERAR)
        self.assertIsNone(lec.entrada)
        self.assertTrue(any("volumen en la ruptura" in r for r in lec.razones))

    def test_a_break_that_already_ran_away_is_not_the_trigger_either(self):
        est = EstadoCaida(symbol="TESTUSDT", estado=RECUPERACION, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0)
        _, lec, motivo = avanzar_caida(est, obs_caida(
            precio=101.0,
            retroceso={"detectado": True, "confirmado": True, "caida_pct": -4.0,
                       "suelo": 96.0, "rebote_pct": 5.2},
            base_rebote={"rompio": True, "base_techo": 97.5,
                         "ruptura_vol_ratio": 3.2, "dist_techo_pct": 4.0}))
        self.assertIsNone(motivo)
        self.assertEqual(lec.veredicto, ESPERAR)
        self.assertTrue(any("reciente" in r for r in lec.razones))

    def test_an_unmeasurable_volume_is_not_taken_as_good(self):
        self.assertEqual(ruptura_valida({"rompio": True})[0], False)
        self.assertIn("no se pudo medir", ruptura_valida({"rompio": True})[1])

    def test_losing_the_floor_invalidates_the_rebound_instead_of_hoping(self):
        est = EstadoCaida(symbol="TESTUSDT", estado=RECUPERACION, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0)
        est2, lec, motivo = avanzar_caida(est, obs_caida(precio=95.0))
        self.assertEqual(motivo, NUEVA_CAIDA)
        self.assertEqual(est2.estado, CAIDA_ACTIVA)
        self.assertEqual(est2.suelo, 95.0)

    def test_twelve_hours_close_the_episode_like_everywhere_else(self):
        est = EstadoCaida(symbol="TESTUSDT", estado=BASE_EN_FORMACION,
                          desde_ms=_T, abierto_ms=_T, suelo=96.0)
        tarde = obs_caida(ts_ms=_T + 13 * 3600_000)
        est2, lec, motivo = avanzar_caida(est, tarde)
        self.assertEqual(motivo, CADUCADO)
        self.assertEqual(est2.estado, SIN_CAIDA)

    def test_a_confirmed_rebound_with_timeframes_fighting_is_conflict(self):
        est = EstadoCaida(symbol="TESTUSDT", estado=RECUPERACION, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0)
        _, lec, _ = avanzar_caida(est, obs_caida(
            precio=97.8, tendencias={"5m": "ALCISTA", "1h": "BAJISTA"},
            retroceso={"detectado": True, "confirmado": True, "caida_pct": -4.0,
                       "suelo": 96.0, "rebote_pct": 1.9},
            base_rebote={"rompio": True, "base_techo": 97.5,
                         "ruptura_vol_ratio": 3.2, "dist_techo_pct": 0.3}))
        self.assertEqual(lec.veredicto, CONFLICTO)
        self.assertIsNone(lec.entrada)

    def test_the_state_survives_a_restart_because_it_lives_in_a_row(self):
        est = EstadoCaida(symbol="TESTUSDT", estado=BASE_EN_FORMACION,
                          desde_ms=_T, abierto_ms=_T, suelo=96.0, caida_pct=-4.0)
        copia = EstadoCaida.desde_dict(json.loads(json.dumps(est.como_dict())))
        self.assertEqual(copia.como_dict(), est.como_dict())

    def test_without_candles_it_reports_missing_data_and_keeps_its_state(self):
        est = EstadoCaida(symbol="TESTUSDT", estado=RECUPERACION, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0)
        est2, lec, motivo = avanzar_caida(est, obs_caida(velas_1m=5))
        self.assertEqual(lec.veredicto, DATOS_INSUFICIENTES)
        self.assertIsNone(motivo)
        self.assertEqual(est2.estado, RECUPERACION)


# =============================================================================
#  Almacen
# =============================================================================

class AlmacenTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(MOTORES_SCHEMA)
        self.alm = AlmacenMotores(self.conn)

    def test_a_reading_round_trips_with_its_reasons_and_data(self):
        l = evaluar_continuacion(obs(ancla=ancla_rota(), vol_ratio=1.4))
        rid = self.alm.guardar(l, ORIGEN_MUESTRA, alerta_id=7)
        fila = self.conn.execute(
            "SELECT veredicto, familia, origen, alerta_id, razones, datos, entrada "
            "FROM motor_lecturas WHERE id = ?", (rid,)).fetchone()
        self.assertEqual(fila[0], CANDIDATO)
        self.assertEqual(fila[1], RUPTURA_SOSTENIDA)
        self.assertEqual(fila[2], ORIGEN_MUESTRA)
        self.assertEqual(fila[3], 7)
        self.assertTrue(json.loads(fila[4]))
        self.assertEqual(json.loads(fila[5])["ancla_tf"], "1h")
        self.assertEqual(fila[6], 100.0)

    def test_the_fall_state_is_reloaded_as_it_was_saved(self):
        est = EstadoCaida(symbol="AUSDT", estado=RECUPERACION, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0, caida_pct=-4.0)
        self.alm.guardar_estado_caida(est, _T)
        est.estado = REBOTE_CONFIRMADO
        self.alm.guardar_estado_caida(est, _T + 60_000)
        vivos = self.alm.cargar_estados_caida()
        self.assertEqual(len(vivos), 1)
        self.assertEqual(vivos["AUSDT"].estado, REBOTE_CONFIRMADO)
        self.assertEqual(vivos["AUSDT"].suelo, 96.0)

    def test_the_summary_counts_by_origin_so_the_sample_is_visible(self):
        l = evaluar_continuacion(obs(ancla=ancla_rota(confirmada=False)))
        self.alm.guardar(l, ORIGEN_MUESTRA)
        self.alm.guardar(l, "ALERTA")
        self.alm.transicion("AUSDT", MOTOR_CAIDA, CAIDA_ACTIVA, DESACELERACION,
                            AVANZA, _T, 96.0, {})
        r = self.alm.resumen(0)
        origenes = {f["origen"] for f in r["por_motor_veredicto"]}
        self.assertEqual(origenes, {ORIGEN_MUESTRA, "ALERTA"})
        self.assertEqual(r["transiciones"][0]["hasta"], DESACELERACION)




class SueloDeLaCaidaTests(unittest.TestCase):
    """
    Mientras la caida sigue activa el suelo baja sin que haya transicion. Si
    ese suelo no se conserva, el motor pierde la referencia contra la que
    invalida un rebote y se queda mirando un minimo que ya no existe.
    """

    def test_the_floor_keeps_dropping_while_the_fall_is_active(self):
        est = EstadoCaida(symbol="TESTUSDT", estado=CAIDA_ACTIVA, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0)
        est2, _, motivo = avanzar_caida(est, obs_caida(precio=94.0))
        self.assertIsNone(motivo)
        self.assertEqual(est2.estado, CAIDA_ACTIVA)
        self.assertEqual(est2.suelo, 94.0)

    def test_the_floor_does_not_rise_when_the_price_bounces(self):
        est = EstadoCaida(symbol="TESTUSDT", estado=CAIDA_ACTIVA, desde_ms=_T,
                          abierto_ms=_T, suelo=94.0)
        est2, _, _ = avanzar_caida(est, obs_caida(precio=95.5))
        self.assertEqual(est2.suelo, 94.0)


# =============================================================================
#  El servicio: deduplicacion, muestra y aislamiento
# =============================================================================

class _Metrics:
    def __init__(self, price=100.0, vol_ratio=1.4):
        self.price = price
        self.vol_ratio = vol_ratio
        self.drawdown_from_peak = -0.01


class _EstadoFalso:
    """Lo minimo que el servicio lee de un SymbolState."""

    def __init__(self, symbol="TESTUSDT", **kw):
        self.symbol = symbol
        self.candles = [None] * 300
        self.metrics = _Metrics()
        self.fsm_state = "RISING"
        self.display_state = "SUBIENDO"
        self.macro_trends = dict(_TENDENCIAS)
        self.taxonomia = {}
        self.impulso = {"fase": "SOSTENIDA", "consumido_pct": 1.0}
        self.retroceso = {}
        self.compresion = {}
        self.grind = {}
        self.ignition = {}
        self.base_rebote = {}
        self.consolidation_info = {}
        self.sr_levels = {}
        self.trade_levels = dict(_PLAN)
        self.flow_snap = None
        self.pos_en_rango = 0.5
        self.ind = None
        self.rango_1h_pct = 1.2
        self.btc_regime = "ALCISTA"
        self.__dict__.update(kw)


class ServicioTests(unittest.TestCase):
    def setUp(self):
        from src.motores.servicio import ServicioMotores
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(MOTORES_SCHEMA)
        self.srv = ServicioMotores(AlmacenMotores(self.conn))
        self.st = _EstadoFalso()
        self.srv._ancla["TESTUSDT"] = (ancla_rota(), _T)

    def _filas(self):
        return self.conn.execute(
            "SELECT motor, veredicto, origen FROM motor_lecturas").fetchall()

    def test_the_same_verdict_minute_after_minute_is_not_written_twice(self):
        self.srv.procesar("TESTUSDT", self.st, _T)
        n1 = len(self._filas())
        for i in range(1, 6):
            self.srv.procesar("TESTUSDT", self.st, _T + i * 60_000)
        self.assertEqual(len(self._filas()), n1)

    def test_a_sample_is_written_even_when_nothing_changed(self):
        self.srv.procesar("TESTUSDT", self.st, _T)
        antes = len(self._filas())
        self.srv.procesar("TESTUSDT", self.st, _T + 60_000, origen=ORIGEN_MUESTRA)
        filas = self._filas()
        self.assertEqual(len(filas), antes + 2)   # los dos motores
        self.assertTrue(all(f[2] == ORIGEN_MUESTRA for f in filas[antes:]))

    def test_a_candidate_is_written_even_inside_the_cooldown(self):
        # Primero un veredicto que no dispara, luego el que si.
        self.srv._ancla["TESTUSDT"] = (ancla_rota(confirmada=False), _T)
        self.srv.procesar("TESTUSDT", self.st, _T)
        antes = len(self._filas())
        self.srv._ancla["TESTUSDT"] = (ancla_rota(), _T + 60_000)
        self.srv.procesar("TESTUSDT", self.st, _T + 60_000)
        nuevas = self._filas()[antes:]
        self.assertTrue(any(f[1] == CANDIDATO for f in nuevas))

    def test_the_sample_rotates_so_no_pair_is_left_out_forever(self):
        estados = {f"S{i}USDT": _EstadoFalso(symbol=f"S{i}USDT") for i in range(30)}
        from src.config.settings import get_settings
        s = get_settings()
        vistos = set()
        t = _T
        for _ in range(5):
            self.srv.muestrear(estados, t)
            t += (s.motores_muestra_cada_min + 1) * 60_000
            vistos |= {f[0] for f in self.conn.execute(
                "SELECT DISTINCT symbol FROM motor_lecturas WHERE origen = ?",
                (ORIGEN_MUESTRA,))}
        self.assertGreaterEqual(len(vistos), min(30, 5 * s.motores_muestra_por_pasada))

    def test_a_broken_store_never_reaches_the_caller(self):
        class Roto(AlmacenMotores):
            def guardar(self, *a, **k):
                raise RuntimeError("disco lleno")

            def transicion(self, *a, **k):
                raise RuntimeError("disco lleno")

        from src.motores.servicio import ServicioMotores
        srv = ServicioMotores(Roto(self.conn))
        srv._ancla["TESTUSDT"] = (ancla_rota(), _T)
        veredictos = srv.procesar("TESTUSDT", self.st, _T)
        self.assertEqual(veredictos[MOTOR_CAIDA].veredicto, SIN_TESIS)

    def test_the_switch_turns_both_engines_off(self):
        from src.config.settings import get_settings
        s = get_settings()
        s.motores_enabled = False
        try:
            self.assertIsNone(self.srv.procesar("TESTUSDT", self.st, _T))
            self.assertEqual(self._filas(), [])
        finally:
            s.motores_enabled = True

    def test_a_saturated_pass_still_records_the_alert_with_its_identity(self):
        """
        El tope descartaba tambien las filas con identidad, y ese enlace no se
        recupera: la fila del minuto siguiente es otra observacion, sin la
        alerta detras. Medido en produccion tras el despliegue, 36 de 100
        alertas se quedaron sin lectura vinculada por esta via.
        """
        from src.config.settings import get_settings
        s = get_settings()
        previo = s.motores_max_filas_por_pasada
        s.motores_max_filas_por_pasada = 2
        try:
            saturador = _EstadoFalso(symbol="SATURAUSDT")
            self.srv._ancla["SATURAUSDT"] = (ancla_rota(), _T)
            self.srv.procesar("SATURAUSDT", saturador, _T)     # llena el tope

            self.srv.procesar("TESTUSDT", self.st, _T, origen="ALERTA",
                              alerta_id=777, plan_id=42, episode_id=9)
            filas = self.conn.execute(
                "SELECT motor, origen, alerta_id, plan_id, episode_id "
                "FROM motor_lecturas WHERE alerta_id = 777").fetchall()
            self.assertEqual(len(filas), 2, "faltan lecturas de la alerta 777")
            for f in filas:
                self.assertEqual((f[1], f[2], f[3], f[4]), ("ALERTA", 777, 42, 9))
        finally:
            s.motores_max_filas_por_pasada = previo

    def test_a_saturated_pass_still_records_the_universe_sample(self):
        """
        La muestra es la poblacion de referencia de toda la fase. Perder filas
        suyas en silencio la sesga justo en los minutos con mas movimiento,
        que es cuando el tope salta.
        """
        from src.config.settings import get_settings
        s = get_settings()
        previo = s.motores_max_filas_por_pasada
        s.motores_max_filas_por_pasada = 1
        try:
            self.srv.procesar("SATURAUSDT", _EstadoFalso(symbol="SATURAUSDT"), _T)
            self.srv.procesar("TESTUSDT", self.st, _T, origen=ORIGEN_MUESTRA)
            n = self.conn.execute(
                "SELECT COUNT(*) FROM motor_lecturas WHERE origen = ? AND symbol = ?",
                (ORIGEN_MUESTRA, "TESTUSDT")).fetchone()[0]
            self.assertEqual(n, 2)
        finally:
            s.motores_max_filas_por_pasada = previo

    def test_the_per_pass_cap_delays_rows_but_never_drops_them_silently(self):
        from src.config.settings import get_settings
        s = get_settings()
        previo = s.motores_max_filas_por_pasada
        s.motores_max_filas_por_pasada = 2
        try:
            estados = {f"S{i}USDT": _EstadoFalso(symbol=f"S{i}USDT")
                       for i in range(4)}
            for k in estados:
                self.srv._ancla[k] = (ancla_rota(), _T)
            for k, st in estados.items():
                self.srv.procesar(k, st, _T)
            self.assertEqual(len(self._filas()), 2)      # el tope corta
            # Minuto siguiente: los que se quedaron fuera siguen sin marcar,
            # asi que se escriben ahora en vez de perderse.
            for k, st in estados.items():
                self.srv.procesar(k, st, _T + 60_000)
            self.assertEqual(len(self._filas()), 4)
        finally:
            s.motores_max_filas_por_pasada = previo



# =============================================================================
#  El detector real conectado al motor
# =============================================================================

class DetectorRealTests(unittest.TestCase):
    """
    Las pruebas de arriba le dan al motor diccionarios escritos a mano, y por
    eso no vieron que `base_rebote.rompio` significa otra cosa de la que yo
    creia. Aqui las velas pasan por `detectar_base_rebote` de verdad.
    """

    @staticmethod
    def _velas(vol_ruptura):
        """
        Caida -> capitulacion -> base estrecha con volumen seco -> ruptura.

        La vela de capitulacion no es adorno: sin ella, la ventana mas larga
        que cabe en `base_rango_max_pct` se comia parte de la caida y el techo
        de la base quedaba a mitad del desplome, donde el precio no llega. Con
        un salto de 5 % en una vela, cualquier ventana que la incluya se pasa
        de rango y la base queda donde tiene que quedar.
        """
        from src.state.symbol_state import Candle
        v, t, precio = [], 0, 100.0
        # 120 velas de historial: el detector exige 180 en total
        # (`base_lookback_velas`) y con menos dice "datos insuficientes", que
        # hacia que estas pruebas se saltaran en silencio.
        for _ in range(120):
            v.append(Candle(t=t, o=precio, h=precio * 1.001, l=precio * 0.999,
                            c=precio, v=1000.0)); t += 60_000
        for _ in range(20):
            nuevo_p = precio * 0.997
            v.append(Candle(t=t, o=precio, h=precio, l=nuevo_p * 0.999,
                            c=nuevo_p, v=1500.0)); precio = nuevo_p; t += 60_000
        capitulacion = precio * 0.95
        v.append(Candle(t=t, o=precio, h=precio, l=capitulacion * 0.999,
                        c=capitulacion, v=3000.0)); t += 60_000
        precio = capitulacion
        techo = precio * 1.004
        for _ in range(45):
            v.append(Candle(t=t, o=precio, h=techo * 0.999, l=precio * 0.998,
                            c=precio, v=200.0)); t += 60_000
        v.append(Candle(t=t, o=precio, h=techo * 1.002, l=precio,
                        c=techo * 1.001, v=vol_ruptura))
        return v

    def test_the_detector_says_broke_while_rejecting_it_for_volume(self):
        from src.analysis.base_rebote import detectar_base_rebote
        flojo = detectar_base_rebote(self._velas(vol_ruptura=100.0)).to_dict()
        if not flojo.get("base_techo"):
            self.skipTest("el detector no formo base con estas velas")
        # Esta es la trampa: dice que rompio, y aun asi se rechaza.
        self.assertTrue(flojo["rompio"])
        self.assertFalse(flojo["detected"])
        self.assertIn("sin volumen", flojo["reason"])
        self.assertEqual(ruptura_valida(flojo)[0], False)

    def test_the_engine_does_not_confirm_a_rebound_the_detector_rejected(self):
        from src.analysis.base_rebote import detectar_base_rebote
        flojo = detectar_base_rebote(self._velas(vol_ruptura=100.0)).to_dict()
        if not flojo.get("rompio"):
            self.skipTest("el detector no formo base con estas velas")
        est = EstadoCaida(symbol="TESTUSDT", estado=RECUPERACION, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0)
        _, lec, motivo = avanzar_caida(est, obs_caida(
            precio=97.8,
            retroceso={"detectado": True, "confirmado": True, "caida_pct": -4.0,
                       "suelo": 96.0, "rebote_pct": 1.9},
            base_rebote=flojo))
        self.assertIsNone(motivo)
        self.assertEqual(lec.veredicto, ESPERAR)
        self.assertIsNone(lec.entrada)

    def test_the_engine_does_confirm_when_the_detector_accepts_it(self):
        from src.analysis.base_rebote import detectar_base_rebote
        fuerte = detectar_base_rebote(self._velas(vol_ruptura=3000.0)).to_dict()
        if not ruptura_valida(fuerte)[0]:
            self.skipTest(f"el detector rechazo la ruptura: {fuerte.get('reason')}")
        est = EstadoCaida(symbol="TESTUSDT", estado=RECUPERACION, desde_ms=_T,
                          abierto_ms=_T, suelo=96.0)
        _, lec, motivo = avanzar_caida(est, obs_caida(
            precio=97.8,
            retroceso={"detectado": True, "confirmado": True, "caida_pct": -4.0,
                       "suelo": 96.0, "rebote_pct": 1.9},
            base_rebote=fuerte))
        self.assertEqual(motivo, AVANZA)
        self.assertEqual(lec.veredicto, CANDIDATO)

if __name__ == "__main__":
    unittest.main()
