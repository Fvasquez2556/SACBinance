"""
Fase 6: que ningun porcentaje salga a pantalla sin decir lo que es.

El defecto que esto cierra: el numero 3,2 hacia dos trabajos —objetivo NETO
del operador y hito BRUTO de medicion— con la misma etiqueta y escrito a mano
en quince sitios. Medido sobre 502 recorridos completos de produccion, 37
señales (el 15,5 % de las que el tablero daba por meta cumplida) nunca
llegaron al objetivo real.
"""
import unittest
from unittest.mock import patch

from src.config.settings import get_settings
from src.presentacion.contrato import BRUTO, NETO, Porcentaje, contrato_de_lectura
from src.presentacion.oportunidades import _avisos


class ContratoTests(unittest.TestCase):
    def test_a_percentage_never_travels_without_saying_what_it_is(self):
        p = Porcentaje(3.2, NETO, 0.5)
        self.assertEqual(p.etiqueta, "+3.2 % neto")
        self.assertEqual(p.a_bruto().pct, 3.7)
        self.assertEqual(p.a_bruto().etiqueta, "+3.7 % bruto")
        # Convertir dos veces vuelve al mismo sitio.
        self.assertEqual(p.a_bruto().a_neto().pct, p.pct)
        self.assertEqual(p.a_neto(), p)

    def test_the_goal_and_the_milestone_do_not_coincide(self):
        c = contrato_de_lectura()
        self.assertEqual(c["objetivo_operador"]["tipo"], NETO)
        self.assertEqual(c["hito_referencia"]["tipo"], BRUTO)
        self.assertFalse(c["coinciden"])
        # La brecha es exactamente el coste.
        self.assertAlmostEqual(
            c["objetivo_operador_bruto"]["pct"] - c["hito_referencia"]["pct"],
            c["coste_pct"], places=6)

    def test_the_milestone_is_worth_less_than_it_looks(self):
        c = contrato_de_lectura()
        # Tocar +3,2 % de precio deja +2,7 % netos: medio punto por debajo del
        # objetivo, con el mismo numero en la etiqueta.
        self.assertLess(c["hito_referencia_neto"]["pct"], c["objetivo_operador"]["pct"])

    def test_moving_the_goal_moves_every_number(self):
        s = get_settings().model_copy(update={"objetivo_operador_pct": 4.2})
        with patch("src.presentacion.contrato.get_settings", return_value=s):
            c = contrato_de_lectura()
        self.assertEqual(c["objetivo_operador"]["pct"], 4.2)
        self.assertEqual(c["objetivo_operador"]["etiqueta"], "+4.2 % neto")
        self.assertAlmostEqual(c["objetivo_operador_bruto"]["pct"], 4.7, places=6)
        self.assertEqual(c["hito_referencia"]["pct"], 3.2)   # el hito no se mueve

    def test_a_zero_cost_makes_them_actually_coincide(self):
        s = get_settings().model_copy(update={"coste_operacion_pct": 0.0})
        with patch("src.presentacion.contrato.get_settings", return_value=s):
            c = contrato_de_lectura()
        self.assertTrue(c["coinciden"])


class AvisosTests(unittest.TestCase):
    """Los hechos que ayudan a elegir entre diecisiete avisos con una posicion."""

    def setUp(self):
        self.contrato = contrato_de_lectura()
        self.alerta = {"entry": 100.0, "take_profit": 106.0, "stop_loss": 97.0,
                       "reward_neto_pct": 5.5}

    def claves(self, **kw):
        alerta = dict(self.alerta, **kw.pop("alerta", {}))
        return {a["clave"] for a in _avisos(
            alerta, kw.get("ident", {}), kw.get("motores", {}),
            self.contrato, kw.get("precio"))}

    def test_a_plan_short_of_the_goal_is_flagged_with_both_numbers(self):
        avisos = _avisos(dict(self.alerta, reward_neto_pct=1.4), {}, {},
                         self.contrato, None)
        corto = [a for a in avisos if a["clave"] == "objetivo_corto"]
        self.assertTrue(corto)
        self.assertIn("+1.40 % neto", corto[0]["texto"])
        self.assertIn("+3.2 % neto", corto[0]["texto"])

    def test_a_repetition_says_so_without_calling_it_worse(self):
        avisos = _avisos(self.alerta, {"es_primera": False, "ordinal": 5}, {},
                         self.contrato, None)
        rep = [a for a in avisos if a["clave"] == "repeticion"][0]
        self.assertIn("n.º 5", rep["texto"])
        # Medido: el ordinal no predice. El aviso no puede insinuar que si.
        self.assertIn("no predice", rep["texto"])

    def test_the_first_of_an_episode_gets_no_warning(self):
        self.assertNotIn("repeticion", self.claves(ident={"es_primera": True, "ordinal": 1}))

    def test_the_one_h_anchor_is_marked_because_it_is_the_only_measured_edge(self):
        avisos = self.claves(motores={"continuacion": {
            "veredicto": "ESPERAR", "ancla_direccion": "RUPTURA_ALCISTA"}})
        self.assertIn("ancla_1h", avisos)

    def test_conflicting_timeframes_are_named_not_averaged(self):
        avisos = _avisos(self.alerta, {}, {"continuacion": {
            "veredicto": "CONFLICTO", "marcos_alcistas": ["5m"],
            "marcos_bajistas": ["1h"]}}, self.contrato, None)
        c = [a for a in avisos if a["clave"] == "conflicto"][0]
        self.assertIn("5m", c["texto"])
        self.assertIn("1h", c["texto"])

    def test_a_price_already_away_from_the_entry_is_said(self):
        avisos = _avisos(self.alerta, {}, {}, self.contrato, precio=101.5)
        d = [a for a in avisos if a["clave"] == "desvio"][0]
        self.assertIn("+1.50 %", d["texto"])
        self.assertNotIn("desvio", self.claves(precio=100.2))

    def test_no_warning_ever_tells_the_operator_what_to_do(self):
        todos = _avisos(dict(self.alerta, reward_neto_pct=1.4, tp_bloqueado=True,
                             resistencia=103.0),
                        {"es_primera": False, "ordinal": 3},
                        {"continuacion": {"veredicto": "CONFLICTO",
                                          "marcos_alcistas": ["5m"],
                                          "marcos_bajistas": ["1h"]}},
                        self.contrato, 101.5)
        self.assertTrue(todos)
        for a in todos:
            self.assertNotIn("no entres", a["texto"].lower())
            self.assertNotIn("evita", a["texto"].lower())




class RehidratadasTests(unittest.TestCase):
    """
    Tras un reinicio las alertas se reconstruyen desde `outcomes`, que no
    guarda identidad de episodio ni recompensa neta. El hueco es correcto —
    mezclar un plan congelado con estructura de hoy es lo que este sistema
    evita— pero tiene que decirse, no quedarse en blanco.
    """

    def test_a_rehydrated_alert_explains_its_missing_identity(self):
        avisos = _avisos({"entry": 100.0, "take_profit": 106.0, "stop_loss": 97.0},
                         {}, {}, contrato_de_lectura(), None)
        claves = {a["clave"] for a in avisos}
        self.assertIn("rehidratada", claves)
        texto = [a for a in avisos if a["clave"] == "rehidratada"][0]["texto"]
        self.assertIn("reinicio", texto)

    def test_an_alert_with_identity_says_nothing_about_it(self):
        avisos = _avisos({"entry": 100.0, "take_profit": 106.0, "stop_loss": 97.0,
                          "reward_neto_pct": 5.5},
                         {"es_primera": True, "ordinal": 1}, {},
                         contrato_de_lectura(), None)
        self.assertNotIn("rehidratada", {a["clave"] for a in avisos})



class TelegramIdentidadTests(unittest.TestCase):
    """
    El mensaje decia «Plan #4871» — un id de base de datos — y no distinguia si
    afectaba a una operacion tomada o solo describia otra oportunidad. Ambas
    cosas existian en la base desde las fases 1 y 3.
    """

    def test_the_first_opportunity_of_an_episode_says_so(self):
        from src.notify.telegram import _linea_identidad
        linea = _linea_identidad({"episode_id": 42, "ordinal_episodio": 1,
                                  "trigger_tf": "1h"}, 4871)
        self.assertIn("episodio 42", linea)
        self.assertIn("primera oportunidad", linea)
        self.assertIn("disparado en 1h", linea)

    def test_a_repetition_is_numbered_not_disguised(self):
        from src.notify.telegram import _linea_identidad
        linea = _linea_identidad({"episode_id": 42, "ordinal_episodio": 5}, 4872)
        self.assertIn("n.º 5", linea)
        self.assertNotIn("primera", linea)

    def test_without_identity_it_falls_back_to_the_plan_number_alone(self):
        from src.notify.telegram import _linea_identidad
        self.assertEqual(_linea_identidad({}, 4873), "Plan #4873")

    def test_an_update_says_whether_it_touches_your_open_trade(self):
        from src.notify.telegram import _linea_alcance
        self.assertIn("tu operación abierta", _linea_alcance({"operacion_abierta": True}))
        self.assertIn("Solo describe una oportunidad", _linea_alcance({}))

    def test_the_whole_message_carries_the_identity(self):
        from src.notify.telegram import texto_plan_notificado
        plan = {"symbol": "TESTUSDT", "alerta_id": 7, "ts_open": 1_700_000_000_000,
                "entry": 100.0, "take_profit": 106.0, "stop_loss": 97.0,
                "last_price": 101.0, "estado": "ABIERTO", "mfe": 1.0, "mae": -0.5,
                "contexto": {"coste_pct": 0.5, "episode_id": 42,
                             "ordinal_episodio": 1, "trigger_tf": "1h",
                             "operacion_abierta": True}}
        texto = texto_plan_notificado(plan)
        self.assertIn("episodio 42", texto)
        self.assertIn("primera oportunidad", texto)
        self.assertIn("tu operación abierta", texto)



class ResultadosTests(unittest.TestCase):
    """
    «¿Cuánto acierta el sistema?» no tiene una respuesta: tiene cuatro, y la
    que siempre se elegía en silencio era la más grande.
    """

    def setUp(self):
        import sqlite3
        from src.episodios import EPISODIOS_SCHEMA
        from src.evaluacion import EVALUACION_SCHEMA
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(EPISODIOS_SCHEMA)
        self.conn.executescript(EVALUACION_SCHEMA)
        self.conn.executescript(
            "CREATE TABLE alertas_emitidas (id INTEGER PRIMARY KEY, telegram TEXT);")

    def tearDown(self):
        self.conn.close()

    def plan(self, pid, ordinal, avisado, desenlace, resultado, completa=1, cobertura=1.0):
        self.conn.execute(
            """INSERT INTO planes (plan_id, episode_id, ordinal_episodio, symbol,
                                   direccion, motor, ts_creado, entry, take_profit,
                                   stop_loss, horizonte_ms, regla_version,
                                   legacy_alerta_id)
               VALUES (?,?,?,?,'ALCISTA','continuacion',?,100.0,106.0,97.0,
                       43200000,'episodio-v1',?)""",
            (pid, pid, ordinal, f"S{pid}USDT", 1_790_000_000_000, pid))
        self.conn.execute("INSERT INTO alertas_emitidas VALUES (?,?)",
                          (pid, "enviado" if avisado else "no_procede"))
        self.conn.execute(
            """INSERT INTO plan_recorrido (plan_id, symbol, evaluador, inicio_ms,
                   horizonte_ms, entrada, objetivo, stop, completa, desenlace,
                   resultado_pct, cobertura, ts_evaluado)
               VALUES (?,?,'recorrido-v1',?,43200000,100.0,106.0,97.0,?,?,?,?,?)""",
            (pid, f"S{pid}USDT", 1_790_000_000_000, completa, desenlace,
             resultado, cobertura, 1_790_000_000_000))

    def test_a_badly_observed_window_is_not_a_hit(self):
        """
        El sesgo que esto cierra: `plan_recorrido` marca completa=1 cuando el
        reloj vence, sin mirar cuantas velas vio. Y las que faltan no se
        pierden al azar — se pierde antes la barrera mas cercana, que es el
        stop. Faltar datos FABRICA objetivos, y hasta el 24-sep entraban todas.
        """
        from src.presentacion.resultados import resultados_por_poblacion
        self.plan(1, 1, True, "OBJETIVO", 5.5, cobertura=1.0)
        self.plan(2, 1, True, "OBJETIVO", 5.5, cobertura=0.62)
        r = resultados_por_poblacion(self.conn, "TODAS")
        self.assertEqual(r["objetivo"], 1, "la mal observada conto como acierto")
        self.assertEqual(r["mal_observadas"], 1)
        self.assertEqual(r["resueltas"], 1)

    def test_a_badly_observed_window_is_counted_not_hidden(self):
        """Desaparecerla seria tan engañoso como promediarla."""
        from src.presentacion.resultados import resultados_por_poblacion
        self.plan(1, 1, True, "STOP", -3.5, cobertura=0.40)
        r = resultados_por_poblacion(self.conn, "TODAS")
        self.assertEqual(r["planes"], 1)
        self.assertEqual(r["mal_observadas"], 1)
        self.assertIsNone(r["acierto_pct"])
        self.assertIsNone(r["media_pct"], "no puede entrar en ninguna media")

    def test_the_coverage_floor_travels_with_the_number(self):
        """
        Dos tasas medidas con distinto suelo no son comparables. Es la misma
        razon por la que el horizonte y el coste viajan al lado desde la fase 6.
        """
        from src.presentacion.resultados import resultados_por_poblacion
        self.plan(1, 1, True, "OBJETIVO", 5.5)
        r = resultados_por_poblacion(self.conn, "TODAS")
        self.assertIn("cobertura_minima", r)
        self.assertGreater(r["cobertura_minima"], 0.0)
        self.assertIn("observadas al 99 %", r["nota"],
                      "el suelo tiene que decirse, no solo aplicarse")

    def test_the_four_populations_are_different_questions(self):
        from src.presentacion.resultados import todas_las_poblaciones
        self.plan(1, 1, True, "OBJETIVO", 5.5)     # decisoria
        self.plan(2, 3, True, "STOP", -3.5)        # telegram, repeticion
        self.plan(3, 1, False, "STOP", -3.5)       # primera, sin avisar
        self.plan(4, 7, False, "STOP", -3.5)       # ni lo uno ni lo otro
        r = {p["poblacion"]: p for p in todas_las_poblaciones(self.conn)["poblaciones"]}
        self.assertEqual(r["TODAS"]["planes"], 4)
        self.assertEqual(r["TELEGRAM"]["planes"], 2)
        self.assertEqual(r["PRIMERA_EPISODIO"]["planes"], 2)
        self.assertEqual(r["DECISORIA"]["planes"], 1)
        # Y el acierto cambia radicalmente segun cual mires.
        self.assertEqual(r["TODAS"]["acierto_pct"], 25.0)
        self.assertEqual(r["DECISORIA"]["acierto_pct"], 100.0)

    def test_expired_windows_are_not_counted_as_failures(self):
        """
        F14 de la auditoria del 10-sep: incluir las vencidas en el denominador
        del acierto contaba 207 cierres positivos como fallos.
        """
        from src.presentacion.resultados import resultados_por_poblacion
        self.plan(1, 1, True, "OBJETIVO", 5.5)
        self.plan(2, 1, True, "VENCIDO", 0.8)
        r = resultados_por_poblacion(self.conn, "TELEGRAM")
        self.assertEqual(r["resueltas"], 1)        # la vencida no entra
        self.assertEqual(r["acierto_pct"], 100.0)
        self.assertEqual(r["vencido"], 1)          # pero se ve

    def test_open_windows_never_enter_a_mean(self):
        from src.presentacion.resultados import resultados_por_poblacion
        self.plan(1, 1, True, "OBJETIVO", 5.5)
        self.plan(2, 1, True, None, None, completa=0)
        r = resultados_por_poblacion(self.conn, "TELEGRAM")
        self.assertEqual(r["abiertas"], 1)
        self.assertEqual(r["media_pct"], 5.5)      # solo la cerrada

    def test_every_number_travels_with_its_horizon_and_cost(self):
        from src.presentacion.resultados import resultados_por_poblacion
        r = resultados_por_poblacion(self.conn, "TODAS")
        self.assertIn("horizonte_horas", r)
        self.assertIn("coste_pct", r)
        self.assertIn("etiqueta", r)
        self.assertIn("contrato", r)

if __name__ == "__main__":
    unittest.main()
