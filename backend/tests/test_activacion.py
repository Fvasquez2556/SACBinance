"""
Pruebas de la fase 7a: el candado, el reparto y la reversion.

Lo que estas pruebas tienen que impedir, por orden de gravedad:

  1. que se active algo sin que el operador lo haya revisado
  2. que se active una politica que pasa sus puertas pero es PEOR que la
     referencia
  3. que un episodio cambie de brazo a mitad
  4. que cambiar el documento o un umbral no mueva la huella
  5. que revertir borre lo que ya paso
"""
import hashlib
import json
import os
import sqlite3
import unittest

import src.activacion.registro as R
from src.activacion.almacen import (
    ACTIVACION_SCHEMA,
    ActivacionRechazada,
    AlmacenActivacion,
)
from src.activacion.registro import (
    BRAZO_REFERENCIA,
    BRAZO_RIVAL,
    FRACCION_RIVAL,
    brazo_de,
    huella,
)
from src.activacion.veredicto import (
    EMPATE_PP,
    elegir_rival,
    estabilidad_temporal,
    puede_activarse,
)


def _estable(*claves):
    """Corte por mitades superado, para las pruebas que no lo estan probando."""
    return {k: {"estable": True, "n": 40, "primera_mitad": 0.5,
                "segunda_mitad": 0.4} for k in claves}


def _db():
    c = sqlite3.connect(":memory:")
    c.executescript(ACTIVACION_SCHEMA)
    c.executescript(
        "CREATE TABLE IF NOT EXISTS episodios (episode_id INTEGER PRIMARY KEY, "
        "symbol TEXT, n_planes INTEGER, ts_apertura INTEGER)")
    return c


def _pol(clave, veredicto="APROBADA", dinero=1.0, pareado=0.5,
         exploracion=False):
    """Una fila de politica como la devuelve el informe de la fase 5."""
    return {
        "politica": clave, "exploracion": exploracion, "veredicto": veredicto,
        "medibles": 60,
        "dinero": {"media": dinero + 0.2, "ic_bajo": dinero, "ic_alto": dinero + 0.4,
                   "n": 60, "pares": 40},
        "pareado_vs_ref": {"media": pareado + 0.1, "ic_bajo": pareado,
                           "ic_alto": pareado + 0.3, "n": 60, "pares": 40},
        "habilidad": {"ic_bajo": 3.0},
    }


def _informe(politicas, medibles_ref=60):
    return {"politicas": politicas,
            "referencia": {"politica": "REF", "medibles": medibles_ref}}


# =============================================================================
#  El candado
# =============================================================================

class TestElCandado(unittest.TestCase):

    def test_the_pinned_document_hash_matches_the_real_file(self):
        """
        La huella incluye el sha256 del documento aprobado. Si el .md cambia y
        la constante no, la promesa de "modificar el documento cambia la
        huella" seria falsa.
        """
        ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
            "audit", "2026-09-22", "plan-evolucion-motores", R.DOCUMENTO)
        if not os.path.exists(ruta):
            self.skipTest("el documento no esta en este arbol")
        real = hashlib.sha256(open(ruta, "rb").read()).hexdigest()
        self.assertEqual(R.DOCUMENTO_SHA256, real,
                         "el documento cambio sin actualizar su huella")

    def test_moving_any_threshold_moves_the_fingerprint(self):
        """Un umbral que se pueda bajar sin dejar rastro no es un umbral."""
        antes = huella()
        original = dict(R.REVERSION)
        try:
            R.REVERSION["daño_puntos_por_operacion"] = 5.0
            self.assertNotEqual(huella(), antes)
        finally:
            R.REVERSION.clear()
            R.REVERSION.update(original)
        self.assertEqual(huella(), antes)

    def test_the_fraction_is_in_the_fingerprint(self):
        antes = huella()
        original = R.FRACCION_RIVAL
        try:
            R.FRACCION_RIVAL = 0.10
            self.assertNotEqual(huella(), antes)
        finally:
            R.FRACCION_RIVAL = original

    def test_the_phase5_fingerprint_is_part_of_this_one(self):
        """
        Un rival elegido bajo otras politicas no es el mismo rival. Si la fase
        5 abre version, esta tambien.
        """
        d = json.loads(R.declaracion_json())
        self.assertIn("fase5_huella", d)
        self.assertIn("fase5_version", d)

    def test_freezing_twice_keeps_the_first_date(self):
        db = _db()
        a = AlmacenActivacion(db)
        p = a.congelar(ahora_ms=1000)
        q = a.congelar(ahora_ms=9999)
        self.assertTrue(p["nuevo"])
        self.assertFalse(q["nuevo"])
        self.assertEqual(q["ts_congelado"], 1000)


# =============================================================================
#  El reparto
# =============================================================================

class TestElReparto(unittest.TestCase):

    def test_the_arm_is_deterministic_across_restarts(self):
        """Sin esto, reiniciar rebarajaria y los brazos dejarian de significar."""
        self.assertEqual(brazo_de(12345), brazo_de(12345))
        self.assertEqual(brazo_de(12345), brazo_de(12345, huella()))

    def test_a_different_fingerprint_reshuffles(self):
        """Heredar el reparto de otra version seria llevarse su suerte."""
        distintos = sum(1 for e in range(400)
                        if brazo_de(e, "huella-a") != brazo_de(e, "huella-b"))
        self.assertGreater(distintos, 100, "el reparto no se rebarajo")

    def test_the_split_follows_the_declared_fraction(self):
        """
        La fraccion vive en un sitio. Si alguien la cambia y el reparto sigue
        al 50 %, el documento y el codigo dirian cosas distintas.
        """
        n = 4000
        rivales = sum(1 for e in range(n) if brazo_de(e) == BRAZO_RIVAL)
        self.assertAlmostEqual(rivales / n, FRACCION_RIVAL, delta=0.03)

        original = R.FRACCION_RIVAL
        try:
            R.FRACCION_RIVAL = 0.10
            rivales = sum(1 for e in range(n) if brazo_de(e) == BRAZO_RIVAL)
            self.assertAlmostEqual(rivales / n, 0.10, delta=0.03)
        finally:
            R.FRACCION_RIVAL = original

    def test_an_episode_never_changes_arm(self):
        """
        Si la quinta repeticion de un movimiento cayera en el brazo contrario a
        la primera, los dos brazos estarian midiendo el mismo movimiento.
        """
        db = _db()
        db.execute("INSERT INTO episodios (episode_id, symbol) VALUES (7,'AAAUSDT')")
        a = AlmacenActivacion(db)
        a.congelar()
        primero = a.asignar(7, "AAAUSDT")
        # Se fuerza el brazo contrario en la tabla y se vuelve a pedir: gana la
        # fila, no el recalculo.
        contrario = (BRAZO_REFERENCIA if primero == BRAZO_RIVAL else BRAZO_RIVAL)
        db.execute("UPDATE activacion_asignacion SET brazo=? WHERE episode_id=7",
                   (contrario,))
        db.commit()
        self.assertEqual(a.asignar(7, "AAAUSDT"), contrario)
        self.assertEqual(a.brazo_de_episodio(7), contrario)

    def test_the_imbalance_is_reported_not_corrected(self):
        db = _db()
        a = AlmacenActivacion(db)
        a.congelar()
        for e in range(1, 41):
            db.execute("INSERT INTO episodios (episode_id, symbol) VALUES (?,?)",
                       (e, "AAAUSDT"))
            a.asignar(e, "AAAUSDT")
        r = a.reparto()
        self.assertEqual(r["n"], 40)
        self.assertEqual(sum(r["por_brazo"].values()), 40)
        self.assertIsNotNone(r["fraccion_rival"])


# =============================================================================
#  Quien puede ser el rival
# =============================================================================

class TestLaEleccionDelRival(unittest.TestCase):

    def test_a_policy_that_passes_its_gates_but_loses_to_the_reference_is_not_a_rival(self):
        """
        El fallo que esta regla existe para impedir. Las puertas de la fase 5
        son absolutas: una politica puede ganar algo y acertar mas que su
        geometria siendo PEOR que lo que ya hay. Activarla seria un retroceso
        presentado como mejora.
        """
        sel = elegir_rival(_informe([_pol("A3", dinero=0.9, pareado=-0.4)]))
        self.assertIsNone(sel["rival"])
        self.assertIn("comparacion pareada", sel["por_que"])

    def test_no_policy_passing_means_no_rival(self):
        sel = elegir_rival(_informe([_pol("A3", veredicto="RECHAZADA")]))
        self.assertIsNone(sel["rival"])
        self.assertIn("ninguna", sel["por_que"])

    def test_an_inconclusive_report_yields_no_rival(self):
        sel = elegir_rival(_informe([_pol("A1", veredicto="INCONCLUSO"),
                                     _pol("A3", veredicto="INCONCLUSO")]))
        self.assertIsNone(sel["rival"])

    def test_exploration_policies_never_win(self):
        """A5 esta declarada como exploracion; no compite aunque gane."""
        sel = elegir_rival(_informe([
            _pol("A5", dinero=9.0, pareado=9.0, exploracion=True),
            _pol("A3", dinero=1.0, pareado=0.5)]))
        self.assertEqual(sel["rival"], "A3")

    def test_the_highest_lower_bound_wins(self):
        sel = elegir_rival(_informe([_pol("A1", dinero=0.5, pareado=0.2),
                                     _pol("A3", dinero=1.4, pareado=0.9)]))
        self.assertEqual(sel["rival"], "A3")

    def test_a_tie_is_broken_by_structure_not_by_result(self):
        """
        Dos dentro del margen de empate: decide el orden de ejes del plan
        (salida antes que stop), no quien tenga la decima mas alta.
        """
        sel = elegir_rival(_informe([
            _pol("C1", dinero=1.00, pareado=0.5),
            _pol("A2", dinero=1.00 - EMPATE_PP / 2, pareado=0.5)]))
        self.assertEqual(sel["rival"], "A2")
        self.assertIn("empatan", sel["por_que"])

    def test_a_tie_within_the_same_axis_prefers_the_smallest_change(self):
        sel = elegir_rival(_informe([
            _pol("A4", dinero=1.00, pareado=0.5),
            _pol("A1", dinero=1.00 - EMPATE_PP / 2, pareado=0.5)]))
        self.assertEqual(sel["rival"], "A1")

    def test_ready_only_when_a_rival_exists(self):
        self.assertFalse(puede_activarse(
            _informe([_pol("A3", veredicto="INCONCLUSO")]),
            estabilidad=_estable("A3"))["listo"])
        p = puede_activarse(_informe([_pol("A3")]), estabilidad=_estable("A3"))
        self.assertTrue(p["listo"])
        self.assertEqual(p["rival"], "A3")

    def test_without_the_split_half_check_nothing_is_ready(self):
        """
        Una eleccion sin el corte cumple dos de las tres condiciones. Dejarla
        pasar como lista seria saltarse justo la que protege del azar.
        """
        p = puede_activarse(_informe([_pol("A3")]))
        self.assertTrue(p["provisional"])
        self.assertFalse(p["listo"])
        self.assertIsNone(p["rival"])

    def test_a_winner_that_does_not_survive_the_split_is_not_a_rival(self):
        """
        La defensa contra coronar una ganadora por azar. Se miran hasta diez
        politicas; el maximo de diez estimaciones esta inflado por
        construccion. Partir la muestra es lo que ya tumbo aqui a la regla C3.
        """
        inestable = {"A3": {"estable": False, "n": 40, "primera_mitad": 1.2,
                            "segunda_mitad": -0.9,
                            "por_que": "no aguanta el corte"}}
        sel = elegir_rival(_informe([_pol("A3")]), estabilidad=inestable)
        self.assertIsNone(sel["rival"])
        self.assertIn("corte por mitades", sel["por_que"])

    def test_the_stable_one_wins_over_the_unstable_higher_one(self):
        est = {"A3": {"estable": False}, "A1": {"estable": True}}
        sel = elegir_rival(_informe([_pol("A3", dinero=2.0, pareado=1.5),
                                     _pol("A1", dinero=0.6, pareado=0.3)]),
                           estabilidad=est)
        self.assertEqual(sel["rival"], "A1")


# =============================================================================
#  Activar y revertir
# =============================================================================

class TestActivarYRevertir(unittest.TestCase):

    def setUp(self):
        self.db = _db()
        self.a = AlmacenActivacion(self.db)
        self.a.congelar()

    def test_it_starts_switched_off_with_no_rival(self):
        est = self.a.estado()
        self.assertFalse(est["activo"])
        self.assertIsNone(est["rival"])

    def test_it_refuses_to_activate_without_the_operator(self):
        """La puerta 3 del registro. Sin esto acabaria llamandose sin ella."""
        puede = puede_activarse(_informe([_pol("A3")]), estabilidad=_estable("A3"))
        with self.assertRaises(ActivacionRechazada) as cm:
            self.a.activar("A3", aprobado_por="", puede=puede)
        self.assertIn("revision del operador", str(cm.exception))
        self.assertFalse(self.a.estado()["activo"])

    def test_it_refuses_to_activate_before_phase5_says_so(self):
        puede = puede_activarse(_informe([_pol("A3", veredicto="INCONCLUSO")]),
                                estabilidad=_estable("A3"))
        with self.assertRaises(ActivacionRechazada):
            self.a.activar("A3", aprobado_por="felix", puede=puede)
        self.assertFalse(self.a.estado()["activo"])

    def test_it_refuses_a_rival_the_frozen_rule_did_not_choose(self):
        """No se puede activar la favorita saltandose la regla."""
        puede = puede_activarse(
            _informe([_pol("A1", dinero=0.4, pareado=0.2),
                      _pol("A3", dinero=1.4, pareado=0.9)]),
            estabilidad=_estable("A1", "A3"))
        with self.assertRaises(ActivacionRechazada) as cm:
            self.a.activar("A1", aprobado_por="felix", puede=puede)
        self.assertIn("regla congelada", str(cm.exception))

    def test_a_clean_activation_records_who_approved_it(self):
        puede = puede_activarse(_informe([_pol("A3")]), estabilidad=_estable("A3"))
        est = self.a.activar("A3", aprobado_por="felix", puede=puede,
                             ahora_ms=5000)
        self.assertTrue(est["activo"])
        self.assertEqual(est["rival"], "A3")
        self.assertEqual(est["aprobado_por"], "felix")
        tipos = [r[0] for r in self.db.execute(
            "SELECT tipo FROM activacion_eventos ORDER BY id")]
        self.assertIn("ACTIVADO", tipos)

    def test_reverting_switches_off_and_keeps_the_assignment(self):
        """
        Revertir es apagar, no restaurar. Los episodios ya repartidos conservan
        su brazo: un plan que salio con el TP del rival muere con el TP del
        rival y se sigue evaluando contra el.
        """
        self.db.execute("INSERT INTO episodios (episode_id, symbol) VALUES (3,'AAAUSDT')")
        brazo = self.a.asignar(3, "AAAUSDT")
        puede = puede_activarse(_informe([_pol("A3")]), estabilidad=_estable("A3"))
        self.a.activar("A3", aprobado_por="felix", puede=puede)
        est = self.a.revertir("prueba")
        self.assertFalse(est["activo"])
        self.assertEqual(est["motivo_reversion"], "prueba")
        self.assertEqual(self.a.brazo_de_episodio(3), brazo)
        self.assertEqual(self.a.reparto()["n"], 1)


# =============================================================================
#  Integridad y disparadores
# =============================================================================

class TestIntegridad(unittest.TestCase):

    def setUp(self):
        self.db = _db()
        self.a = AlmacenActivacion(self.db)
        self.a.congelar()

    def test_a_clean_store_has_no_problems(self):
        self.assertEqual(self.a.verificar_integridad(), [])

    def test_a_hand_written_assignment_is_caught(self):
        """
        El reparto tiene que reproducirse desde su huella. Si alguien escribe
        un brazo a mano, la puerta de integridad lo dice.
        """
        self.db.execute("INSERT INTO episodios (episode_id, symbol) VALUES (9,'AAAUSDT')")
        brazo = self.a.asignar(9, "AAAUSDT")
        contrario = (BRAZO_REFERENCIA if brazo == BRAZO_RIVAL else BRAZO_RIVAL)
        self.db.execute("UPDATE activacion_asignacion SET brazo=? WHERE episode_id=9",
                        (contrario,))
        self.db.commit()
        problemas = self.a.verificar_integridad()
        self.assertTrue(any("no se reproducen" in p for p in problemas))

    def test_an_assignment_without_episode_is_caught(self):
        self.db.execute(
            """INSERT INTO activacion_asignacion
                   (episode_id, huella, brazo, symbol, ts_asignado)
               VALUES (404, ?, ?, 'AAAUSDT', 1)""",
            (huella(), brazo_de(404)))
        self.db.commit()
        self.assertTrue(any("sin episodio" in p
                            for p in self.a.verificar_integridad()))

    def test_activation_is_refused_when_integrity_fails(self):
        self.db.execute(
            """INSERT INTO activacion_asignacion
                   (episode_id, huella, brazo, symbol, ts_asignado)
               VALUES (404, ?, 'INVENTADO', 'AAAUSDT', 1)""", (huella(),))
        self.db.commit()
        puede = puede_activarse(_informe([_pol("A3")]), estabilidad=_estable("A3"))
        with self.assertRaises(ActivacionRechazada) as cm:
            self.a.activar("A3", aprobado_por="felix", puede=puede)
        self.assertIn("integridad", str(cm.exception))


class TestDisparadoresDeReversion(unittest.TestCase):

    def setUp(self):
        self.db = _db()
        self.a = AlmacenActivacion(self.db)
        self.a.congelar()

    def test_harm_reverts(self):
        v = self.a.evaluar_reversion({
            BRAZO_REFERENCIA: {"n": 20, "media_pct": 0.5},
            BRAZO_RIVAL: {"n": 20, "media_pct": -0.8}})
        self.assertTrue(v["revertir"])
        self.assertEqual(v["motivo"], "DAÑO")

    def test_harm_below_the_minimum_n_does_not_revert(self):
        """Tres malas seguidas no son una tendencia."""
        v = self.a.evaluar_reversion({
            BRAZO_REFERENCIA: {"n": 3, "media_pct": 0.5},
            BRAZO_RIVAL: {"n": 3, "media_pct": -9.0}})
        self.assertFalse(v["revertir"])

    def test_the_circuit_breaker_does_not_wait_for_n(self):
        """El dinero de verdad no espera a tener muestra."""
        v = self.a.evaluar_reversion(
            {BRAZO_REFERENCIA: {"n": 2, "media_pct": 0.1},
             BRAZO_RIVAL: {"n": 2, "media_pct": -5.0}},
            capital_pct_rival=-12.0)
        self.assertTrue(v["revertir"])
        self.assertEqual(v["motivo"], "CORTACIRCUITOS")

    def test_winning_never_triggers_a_stop(self):
        """
        La asimetria, probada. Parar al ir ganando es elegir el momento que
        mas favorece — asi se fabrico el +0,25 % de C3 que se evaporo.
        """
        v = self.a.evaluar_reversion({
            BRAZO_REFERENCIA: {"n": 40, "media_pct": 0.1},
            BRAZO_RIVAL: {"n": 40, "media_pct": 9.9}})
        self.assertFalse(v["revertir"])

    def test_a_small_disadvantage_does_not_revert(self):
        v = self.a.evaluar_reversion({
            BRAZO_REFERENCIA: {"n": 40, "media_pct": 0.5},
            BRAZO_RIVAL: {"n": 40, "media_pct": 0.0}})
        self.assertFalse(v["revertir"])


class TestLaReversionSeAplicaSola(unittest.TestCase):
    """
    El fallo que una revision externa encontro: `evaluar_reversion()` devolvia
    una decision y NADIE la llamaba. Un cortacircuitos que nadie acciona no es
    una proteccion, es una funcion.
    """

    def setUp(self):
        self.db = _db()
        self.db.executescript("""
        CREATE TABLE planes (plan_id INTEGER PRIMARY KEY, episode_id INTEGER,
                             legacy_alerta_id INTEGER, ordinal_episodio INTEGER,
                             ts_creado INTEGER);
        CREATE TABLE alertas_emitidas (id INTEGER PRIMARY KEY, telegram TEXT);
        CREATE TABLE experimento_resultados (
            plan_id INTEGER, politica TEXT, huella TEXT, desenlace TEXT,
            resultado_pct REAL, ts_creado INTEGER);
        """)
        self.a = AlmacenActivacion(self.db)
        self.a.congelar()

    def _plan(self, pid, ref_pct, riv_pct):
        """
        Un plan decisorio con su resultado bajo las dos politicas.

        El brazo NO se fuerza: lo decide el hash, como en produccion. Forzarlo
        rompia la comprobacion de integridad —y con razon, porque una
        asignacion escrita a mano no se reproduce desde su huella—, asi que el
        primer intento de este fixture hacia saltar la reversion por INTEGRIDAD
        y el motivo real quedaba tapado.
        """
        eid = pid
        self.db.execute("INSERT INTO episodios (episode_id, symbol) VALUES (?,?)",
                        (eid, f"S{pid}USDT"))
        self.db.execute(
            "INSERT INTO planes VALUES (?,?,?,1,?)", (pid, eid, pid, pid))
        self.db.execute("INSERT INTO alertas_emitidas VALUES (?, 'enviado')", (pid,))
        for pol, pct in (("REF", ref_pct), ("A3", riv_pct)):
            self.db.execute(
                "INSERT INTO experimento_resultados VALUES (?,?,?,'STOP',?,?)",
                (pid, pol, "h5", pct, pid))
        self.db.commit()
        return self.a.asignar(eid, f"S{pid}USDT")

    def _activar(self):
        puede = puede_activarse(_informe([_pol("A3")]), estabilidad=_estable("A3"))
        self.a.activar("A3", aprobado_por="felix", puede=puede)

    def test_with_activation_off_there_is_nothing_to_watch(self):
        v = self.a.vigilar(huella_f5="h5")
        self.assertFalse(v["vigilado"])
        self.assertFalse(v["revertir"])

    def test_the_loop_actually_reverts_on_harm(self):
        """De extremo a extremo: datos -> vigilar -> revertido, sin mano."""
        self._activar()
        # Las dos protecciones interactuan: con 16 operaciones, una perdida por
        # encima del 0,65 % por operacion ya hunde el capital compuesto por
        # debajo del -10 % y salta ANTES el cortacircuitos. Asi que el escenario
        # del daño es una referencia que gana mientras el rival pierde poco:
        # -1,05 puntos de diferencia por operacion, con el rival en -7 % de
        # capital. En produccion eso significa que el dinero se protege mas
        # rapido que la estadistica, que es el orden correcto.
        i = 1
        while min(self.a.resultados_por_brazo("h5", "A3")[b]["n"]
                  for b in (BRAZO_REFERENCIA, BRAZO_RIVAL)) < 16:
            self._plan(i, ref_pct=0.60, riv_pct=-0.45)
            i += 1
            assert i < 200
        v = self.a.vigilar(huella_f5="h5")
        self.assertTrue(v["vigilado"])
        self.assertTrue(v["revertir"])
        self.assertEqual(v["motivo"], "DAÑO")
        self.assertGreater(v["por_brazo"][BRAZO_RIVAL]["capital_pct"], -10.0,
                           "el escenario debia disparar daño, no cortacircuitos")
        self.assertFalse(self.a.estado()["activo"])
        self.assertIn("DAÑO", self.a.estado()["motivo_reversion"])

    def test_it_does_not_revert_when_both_arms_are_fine(self):
        self._activar()
        for i in range(1, 41):
            self._plan(i, ref_pct=0.5, riv_pct=0.6)
        v = self.a.vigilar(huella_f5="h5")
        self.assertFalse(v["revertir"])
        self.assertTrue(self.a.estado()["activo"])


class TestElCortacircuitosMiraLaReferencia(unittest.TestCase):
    """
    La declaracion condiciona el cortacircuitos a que la referencia NO este
    igual de hundida; el codigo no lo hacia. Si cae todo el mercado, revertir
    no recupera nada y acaba el experimento por el motivo equivocado.
    """

    def setUp(self):
        self.a = AlmacenActivacion(_db())
        self.a.congelar()

    def test_it_fires_when_only_the_rival_is_sinking(self):
        v = self.a.evaluar_reversion(
            {BRAZO_REFERENCIA: {"n": 2, "media_pct": 0.1},
             BRAZO_RIVAL: {"n": 2, "media_pct": -5.0}},
            capital_pct_rival=-12.0, capital_pct_ref=-1.0)
        self.assertTrue(v["revertir"])
        self.assertEqual(v["motivo"], "CORTACIRCUITOS")

    def test_it_does_not_fire_when_the_whole_market_is_down(self):
        v = self.a.evaluar_reversion(
            {BRAZO_REFERENCIA: {"n": 2, "media_pct": -5.0},
             BRAZO_RIVAL: {"n": 2, "media_pct": -5.2}},
            capital_pct_rival=-12.0, capital_pct_ref=-14.0)
        self.assertFalse(v["revertir"])


# =============================================================================
#  Lo que esta fase promete NO hacer
# =============================================================================

class TestNoTocaNada(unittest.TestCase):

    def test_the_declaration_says_the_fraction_does_not_ramp_on_good_news(self):
        self.assertTrue(R.RAMPA["la_fraccion_no_sube_por_un_resultado_intermedio"])
        self.assertTrue(R.REVERSION["no_se_para_al_ir_ganando"])

    def test_alert_budget_and_position_size_are_frozen_during_7b(self):
        congelado = " ".join(R.CONGELADO_DURANTE_7B)
        self.assertIn("avisos", congelado)
        self.assertIn("posicion", congelado)

    def test_nothing_is_bound_yet(self):
        """Al terminar la fase 7a no hay rival: nombrarlo seria prejuzgar."""
        d = json.loads(R.declaracion_json())
        self.assertNotIn("rival", d)
        self.assertIn("seleccion_del_rival", d)


if __name__ == "__main__":
    unittest.main()
