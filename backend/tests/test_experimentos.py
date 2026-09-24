"""
La prueba prospectiva de la fase 5.

Lo que se comprueba aqui no es que una politica gane — eso es lo que la prueba
va a medir durante semanas, y adelantarlo seria el error que este proyecto ya
cometio dos veces. Se comprueba que **el metodo no se pueda romper**: que las
politicas queden congeladas, que solo entre terreno nuevo, que el riesgo se
iguale antes de comparar stops, y que una orden que nunca se llena no se
cuente como una operacion de cero.
"""
import sqlite3
import unittest

from src.episodios import EPISODIOS_SCHEMA, RegistroEpisodios
from src.experimentos.almacen import EXPERIMENTOS_SCHEMA, AlmacenExperimentos
from src.experimentos.informe import APROBADA, INCONCLUSO, RECHAZADA
from src.experimentos.registro import (
    EJE_SALIDA,
    EJE_STOP,
    NO_LLENADO,
    POLITICAS,
    POR_CLAVE,
    PUERTAS,
    barreras_de,
    huella,
)

M = 60_000
INICIO = 1_790_000_000_000
PLAN = {"entry": 100.0, "take_profit": 106.0, "stop_loss": 97.0}


# =============================================================================
#  El candado
# =============================================================================

class CongeladoTests(unittest.TestCase):
    def test_the_fingerprint_is_stable_across_calls(self):
        self.assertEqual(huella(), huella())
        self.assertEqual(len(huella()), 16)

    def test_changing_a_policy_changes_the_fingerprint(self):
        import src.experimentos.registro as R
        antes = huella()
        original = R.POLITICAS
        R.POLITICAS = original[:-1]          # quitar una politica ya es otra cosa
        try:
            self.assertNotEqual(huella(), antes)
        finally:
            R.POLITICAS = original
        self.assertEqual(huella(), antes)

    def test_moving_a_gate_changes_the_fingerprint(self):
        import src.experimentos.registro as R
        antes = huella()
        original = dict(R.PUERTAS)
        R.PUERTAS["dinero_limite_inferior_pct"] = 0.10   # aflojar la puerta
        try:
            self.assertNotEqual(huella(), antes)
        finally:
            R.PUERTAS.clear()
            R.PUERTAS.update(original)
        self.assertEqual(huella(), antes)

    def test_the_pinned_document_hash_matches_the_real_file(self):
        """
        La huella incluye el sha256 del documento aprobado. Si el .md cambia y
        la constante no, la promesa de "modificar el documento cambia la
        huella" seria falsa — y esta prueba lo dice.
        """
        import hashlib
        import os
        import src.experimentos.registro as R
        ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
            "audit", "2026-09-22", "plan-evolucion-motores", R.DOCUMENTO)
        if not os.path.exists(ruta):
            self.skipTest("el documento no esta en este arbol")
        real = hashlib.sha256(open(ruta, "rb").read()).hexdigest()
        self.assertEqual(R.DOCUMENTO_SHA256, real,
                         "el documento cambio sin actualizar su huella")

    def test_the_money_gate_is_the_one_that_was_agreed(self):
        # Si alguien la baja, esta prueba lo dice por su nombre.
        self.assertEqual(PUERTAS["dinero_limite_inferior_pct"], 0.30)
        self.assertEqual(PUERTAS["bootstrap"], "agrupado por par")
        self.assertEqual(PUERTAS["n_minimo"], 50)


# =============================================================================
#  Las barreras de cada politica
# =============================================================================

class BarrerasTests(unittest.TestCase):
    def test_a_net_target_becomes_a_gross_price_barrier(self):
        b = barreras_de(POR_CLAVE["A3"], PLAN, coste_pct=0.5)
        # +4,2 % neto con 0,5 de coste = +4,7 % bruto
        self.assertAlmostEqual(b.objetivo, 104.7, places=6)
        self.assertEqual(b.entrada, 100.0)
        self.assertAlmostEqual(b.stop, 97.0, places=6)

    def test_every_exit_policy_keeps_the_entry_and_the_stop_of_the_plan(self):
        ref = barreras_de(POR_CLAVE["REF"], PLAN, 0.5)
        for p in (p for p in POLITICAS if p.eje == EJE_SALIDA):
            b = barreras_de(p, PLAN, 0.5)
            self.assertEqual(b.entrada, ref.entrada, p.clave)
            self.assertAlmostEqual(b.stop, ref.stop, places=6, msg=p.clave)

    def test_a_deferred_entry_keeps_the_risk_percentage_not_the_stop_price(self):
        b = barreras_de(POR_CLAVE["B2"], PLAN, 0.5)
        self.assertAlmostEqual(b.entrada, 98.5, places=6)
        self.assertEqual(b.entrada_limite, b.entrada)
        # El plan arriesgaba el 3 %; desde 98,5 el 3 % son 95,545.
        self.assertAlmostEqual((b.entrada - b.stop) / b.entrada * 100, 3.0, places=4)
        # Y el objetivo es el MISMO PRECIO, no el mismo porcentaje: comprar mas
        # abajo y ademas mover el objetivo seria cambiar dos cosas a la vez.
        self.assertEqual(b.objetivo, PLAN["take_profit"])

    def test_a_wider_stop_carries_a_smaller_position(self):
        """
        Sin esto, el eje del stop premia al que mas arriesga: un stop el doble
        de ancho acierta mas veces porque compra mas billetes, no porque elija
        mejor.
        """
        ancho = barreras_de(POR_CLAVE["C3"], PLAN, 0.5)     # stop del plan x1,5
        estrecho = barreras_de(POR_CLAVE["C1"], PLAN, 0.5)  # stop fijo -2 %
        self.assertLess(ancho.tamano_relativo, 1.0)
        self.assertGreater(estrecho.tamano_relativo, 1.0)
        for b in (ancho, estrecho):
            riesgo = (b.entrada - b.stop) / b.entrada
            self.assertAlmostEqual(riesgo * b.tamano_relativo, 0.03, places=6)

    def test_a_plan_without_usable_levels_is_not_measured(self):
        for malo in ({"entry": 100.0, "take_profit": 99.0, "stop_loss": 97.0},
                     {"entry": 100.0, "take_profit": 106.0, "stop_loss": 101.0},
                     {"entry": None, "take_profit": 106.0, "stop_loss": 97.0},
                     {}):
            self.assertIsNone(barreras_de(POR_CLAVE["REF"], malo, 0.5), malo)


# =============================================================================
#  La medicion
# =============================================================================

class MedicionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(EPISODIOS_SCHEMA)
        self.conn.executescript(EXPERIMENTOS_SCHEMA)
        self.conn.executescript("""CREATE TABLE klines (symbol TEXT, tf TEXT,
            open_time INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
            PRIMARY KEY (symbol, tf, open_time));""")
        self.reg = RegistroEpisodios(self.conn)
        self.alm = AlmacenExperimentos(self.conn, coste_pct=0.5, max_por_pasada=50)

    def tearDown(self):
        self.conn.close()

    def sembrar(self, filas, desde=0, rellenar=True):
        """
        Siembra velas y, por defecto, RELLENA el resto de la ventana.

        El registro congelado exige cobertura >= 90 % para que un plan sea
        medible. Sembrar dos velas de una ventana de sesenta deja cobertura
        del 3 % y el resultado correcto es SIN_DATOS, no una medicion. El
        relleno es plano al ultimo cierre: no mueve ningun desenlace, solo
        acredita que se estuvo mirando.
        """
        self.conn.executemany(
            "INSERT OR REPLACE INTO klines VALUES (?,?,?,?,?,?,?,?)",
            [("TESTUSDT", "1m", INICIO + (desde + i) * M, *f, 1)
             for i, f in enumerate(filas)])
        if not rellenar:
            return
        cierre = filas[-1][3]
        n = desde + len(filas)
        self.conn.executemany(
            "INSERT OR IGNORE INTO klines VALUES (?,?,?,?,?,?,?,?)",
            [("TESTUSDT", "1m", INICIO + i * M, cierre, cierre, cierre, cierre, 1)
             for i in range(n, 60)])

    def alta(self, ts=INICIO, alerta_id=1):
        return self.reg.registrar(
            symbol="TESTUSDT", ts_ms=ts,
            tl=dict(PLAN, tf="5m", sl_basis="soporte estructural"),
            alerta_id=alerta_id, horizonte_ms=3600_000, coste_pct=0.5)

    def resultados(self, plan_id):
        cur = self.conn.execute(
            "SELECT politica, desenlace, resultado_pct, resultado_r, ms_fill, "
            "tamano FROM experimento_resultados WHERE plan_id = ?", (plan_id,))
        return {r[0]: dict(zip(("desenlace", "pct", "r", "ms_fill", "tamano"), r[1:]))
                for r in cur.fetchall()}

    # --- Terreno nuevo ---

    def test_plans_created_before_the_freeze_are_never_measured(self):
        viejo = self.alta(ts=INICIO - 3600_000, alerta_id=1)
        self.alm.congelar(INICIO)
        nuevo = self.alta(ts=INICIO, alerta_id=2)
        self.sembrar([(100, 101, 99, 100)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        self.assertEqual(self.resultados(viejo["plan_id"]), {})
        self.assertTrue(self.resultados(nuevo["plan_id"]))

    def test_without_freezing_nothing_is_measured_at_all(self):
        self.alta()
        self.sembrar([(100, 101, 99, 100)])
        res = self.alm.evaluar_pendientes(INICIO + 3600_000)
        self.assertTrue(res.get("sin_congelar"))
        self.assertEqual(res["evaluados"], 0)

    def test_freezing_twice_keeps_the_first_date(self):
        a = self.alm.congelar(INICIO)
        b = self.alm.congelar(INICIO + 99_999)
        self.assertTrue(a["nuevo"])
        self.assertFalse(b["nuevo"])
        self.assertEqual(b["ts_congelado"], INICIO)

    # --- Las salidas ---

    def test_a_shorter_target_cashes_where_a_longer_one_does_not(self):
        self.alm.congelar(INICIO)
        ident = self.alta()
        # Sube a +3,9 % y se da la vuelta hasta el stop.
        self.sembrar([(100, 103.9, 99.9, 103.5), (103.5, 103.6, 96.5, 96.8)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        r = self.resultados(ident["plan_id"])
        self.assertEqual(r["A1"]["desenlace"], "OBJETIVO")   # +3,2 bruto
        self.assertEqual(r["A2"]["desenlace"], "OBJETIVO")   # +3,7 bruto
        self.assertEqual(r["A3"]["desenlace"], "STOP")       # +4,7 bruto, no llega
        self.assertEqual(r["REF"]["desenlace"], "STOP")      # +6,0 bruto
        self.assertAlmostEqual(r["A1"]["pct"], 2.7, places=4)   # neto
        self.assertAlmostEqual(r["A2"]["pct"], 3.2, places=4)

    # --- La entrada diferida ---

    def test_an_order_that_never_fills_is_not_an_operation_of_zero(self):
        self.alm.congelar(INICIO)
        ident = self.alta()
        self.sembrar([(100, 106.5, 99.9, 106.2)])   # nunca baja a 98,5
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        r = self.resultados(ident["plan_id"])
        self.assertEqual(r["B2"]["desenlace"], NO_LLENADO)
        self.assertIsNone(r["B2"]["pct"])
        self.assertIsNone(r["B2"]["ms_fill"])
        # La referencia si opero, y gano.
        self.assertEqual(r["REF"]["desenlace"], "OBJETIVO")

    def test_the_fill_candle_does_not_grant_the_target(self):
        """
        El maximo de la vela del fill pudo ocurrir ANTES de que la orden se
        llenara. Conceder el objetivo ahi es regalarse una operacion.
        """
        self.alm.congelar(INICIO)
        ident = self.alta()
        # Una sola vela que baja a 98,4 (llena B2) y ademas toca 106,5.
        self.sembrar([(100, 106.5, 98.4, 99.0)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        r = self.resultados(ident["plan_id"])
        self.assertIsNotNone(r["B2"]["ms_fill"])
        self.assertNotEqual(r["B2"]["desenlace"], "OBJETIVO")

    def test_a_filled_order_is_measured_from_its_own_entry(self):
        self.alm.congelar(INICIO)
        ident = self.alta()
        self.sembrar([(100, 100.1, 98.4, 98.6), (98.6, 106.5, 98.5, 106.2)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        r = self.resultados(ident["plan_id"])
        self.assertEqual(r["B2"]["desenlace"], "OBJETIVO")
        # Se mide desde SU entrada (98,5), no desde la del plan (100).
        esperado = (PLAN["take_profit"] / 98.5 - 1) * 100 - 0.5
        self.assertAlmostEqual(r["B2"]["pct"], round(esperado, 4), places=3)
        self.assertGreater(r["B2"]["pct"], r["REF"]["pct"])

    # --- El stop, con el riesgo igualado ---

    def test_the_wider_stop_does_not_win_just_by_risking_more(self):
        self.alm.congelar(INICIO)
        ident = self.alta()
        # Cae a -4 % (saca al stop del plan, no al ancho) y luego sube al TP.
        self.sembrar([(100, 100.2, 96.0, 96.2), (96.2, 106.5, 96.1, 106.2)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        r = self.resultados(ident["plan_id"])
        self.assertEqual(r["REF"]["desenlace"], "STOP")
        self.assertEqual(r["C3"]["desenlace"], "OBJETIVO")   # stop mas ancho aguanta
        # Pero cobra con posicion reducida: su resultado NO es el bruto.
        self.assertLess(r["C3"]["tamano"], 1.0)
        bruto = (106.0 / 100.0 - 1) * 100 - 0.5
        self.assertAlmostEqual(r["C3"]["pct"], round(bruto * r["C3"]["tamano"], 4),
                               places=3)
        self.assertLess(r["C3"]["pct"], bruto)

    # --- Reanudar ---

    def test_an_open_window_produces_no_row_at_all(self):
        """
        Mas fuerte que "la fila existe sin resultado": no existe. Asi no hay
        forma de que una ventana abierta entre en una media por descuido, que
        es como se evaporo el +0,25 % de la regla C3 en septiembre.
        """
        self.alm.congelar(INICIO)
        ident = self.alta()
        self.sembrar([(100, 101, 99, 100)])
        self.alm.evaluar_pendientes(INICIO + 10 * M)
        self.assertEqual(self.resultados(ident["plan_id"]), {})

        self.sembrar([(100, 106.5, 100, 106.2)], desde=1, rellenar=False)
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        self.assertEqual(self.resultados(ident["plan_id"])["REF"]["desenlace"],
                         "OBJETIVO")

    def test_a_closed_plan_is_never_measured_twice(self):
        self.alm.congelar(INICIO)
        ident = self.alta()
        self.sembrar([(100, 106.5, 99, 106.2)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        primera = self.conn.execute(
            "SELECT COUNT(*), MIN(ts_evaluado) FROM experimento_resultados").fetchone()
        res = self.alm.evaluar_pendientes(INICIO + 7200_000)
        segunda = self.conn.execute(
            "SELECT COUNT(*), MIN(ts_evaluado) FROM experimento_resultados").fetchone()
        self.assertEqual(res["evaluados"], 0)
        self.assertEqual(primera, segunda)

    def test_the_summary_only_reports_what_resolved(self):
        self.alm.congelar(INICIO)
        self.alta(alerta_id=1)
        self.sembrar([(100, 101, 99, 100)])
        self.alm.evaluar_pendientes(INICIO + 10 * M)
        res = self.alm.resumen()
        self.assertEqual(res["por_politica"], [])
        self.assertEqual(res["huella"], huella())
        self.assertEqual(res["pendientes_de_medir"], 1)

    def test_every_row_carries_the_fingerprint_it_was_measured_under(self):
        self.alm.congelar(INICIO)
        ident = self.alta()
        self.sembrar([(100, 106.5, 99, 106.2)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        huellas = {r[0] for r in self.conn.execute(
            "SELECT DISTINCT huella FROM experimento_resultados")}
        self.assertEqual(huellas, {huella()})


# =============================================================================
#  Los cinco casos que reprodujo la revision externa
# =============================================================================

class RevisionExternaTests(MedicionTests):
    """
    Cada uno de estos fallaba antes. El primero es el peor: el motor convertia
    una operacion parada en una ganancia del 7 %.
    """

    def test_the_fill_candle_keeps_its_stop(self):
        """
        F5-R1. La vela llena a 98,5 bajando y sigue hasta 95 — por debajo del
        stop de B2 (95,545). El minimo es POSTERIOR al fill, asi que la
        operacion se paro. Antes se descartaba la vela entera y la subida de
        la siguiente se anotaba como OBJETIVO +7,11 %.
        """
        self.alm.congelar(INICIO)
        ident = self.alta()
        self.sembrar([(100, 100.2, 95.0, 96.0), (96.0, 107.0, 96.0, 106.8)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        r = self.resultados(ident["plan_id"])
        self.assertEqual(r["B2"]["desenlace"], "STOP")
        self.assertLess(r["B2"]["pct"], 0)
        self.assertAlmostEqual(r["B2"]["pct"], -3.5, places=2)

    def test_a_fill_after_the_window_is_not_a_purchase(self):
        """
        F5-R2. La unica vela que baja al limite EMPIEZA justo al vencer el
        plazo. Llenarse ahi es comprar despues de que el plan caduco.
        """
        self.alm.congelar(INICIO)
        ident = self.alta()
        self.sembrar([(100, 100.5, 99.5, 100)] * 60)
        self.sembrar([(100, 100.5, 98.0, 98.2)], desde=60, rellenar=False)
        self.alm.evaluar_pendientes(INICIO + 3600_000 + 2 * M)
        r = self.resultados(ident["plan_id"])
        self.assertEqual(r["B2"]["desenlace"], NO_LLENADO)
        self.assertIsNone(r["B2"]["ms_fill"])

    def test_a_matured_window_without_candles_is_not_a_loss(self):
        """
        F5-R3. Vencer por reloj no es haber observado. Sin velas el evaluador
        daba VENCIDO y -0,5 % neto, y esa perdida inventada entraba en la media
        como una operacion resuelta.
        """
        self.alm.congelar(INICIO)
        ident = self.alta()
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        r = self.resultados(ident["plan_id"])
        self.assertEqual(r["REF"]["desenlace"], "SIN_DATOS")
        self.assertIsNone(r["REF"]["pct"])

    def test_a_plan_without_data_is_measured_again_when_the_candles_arrive(self):
        """
        F5-R3 (segunda mitad). Tener una fila excluia el plan para siempre, asi
        que un retraso en recuperar velas fijaba el resultado falso.
        """
        self.alm.congelar(INICIO)
        ident = self.alta()
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        self.assertEqual(self.resultados(ident["plan_id"])["REF"]["desenlace"],
                         "SIN_DATOS")
        self.sembrar([(100, 106.5, 99, 106.2)])
        res = self.alm.evaluar_pendientes(INICIO + 3600_000)
        self.assertEqual(res["evaluados"], 1)
        self.assertEqual(self.resultados(ident["plan_id"])["REF"]["desenlace"],
                         "OBJETIVO")

    def test_the_report_never_hides_the_orders_that_never_filled(self):
        """
        F5-R4. El filtro iba ANTES de agrupar, asi que la columna de no
        llenadas salia siempre a cero y una politica que nunca se llenara
        desaparecia del informe.
        """
        self.alm.congelar(INICIO)
        self.alta()
        self.sembrar([(100, 106.5, 99.9, 106.2)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        por = {f["politica"]: f for f in self.alm.resumen()["por_politica"]}
        self.assertIn("B2", por, "la politica que no se lleno desaparecio")
        self.assertEqual(por["B2"]["no_llenado"], 1)
        self.assertEqual(por["B2"]["resueltas"], 0)
        self.assertEqual(por["B2"]["elegibles"], 1)   # el denominador se conserva
        self.assertIsNone(por["B2"]["media_pct"])
        self.assertEqual(por["REF"]["objetivo"], 1)

    def test_the_fingerprint_covers_the_method_not_only_the_numbers(self):
        """
        F5-R6. Se podia cambiar la regla de fill o la de cobertura sin que la
        huella se moviera, y dos mediciones con semanticas distintas
        compartian identificacion.
        """
        import src.experimentos.registro as R
        antes = huella()
        for campo, nuevo in (("REGLA_FILL", "otra cosa"),
                             ("COBERTURA_MINIMA", 0.10),
                             ("METODO_VERSION", "metodo-v9"),
                             ("DOCUMENTO_SHA256", "0" * 64),
                             ("POBLACION_DECISORIA", "todas")):
            original = getattr(R, campo)
            setattr(R, campo, nuevo)
            try:
                self.assertNotEqual(huella(), antes, campo)
            finally:
                setattr(R, campo, original)
        self.assertEqual(huella(), antes)




# =============================================================================
#  El informe que decide, y la cartera
# =============================================================================

class InformeTests(MedicionTests):
    def setUp(self):
        super().setUp()
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS alertas_emitidas (id INTEGER PRIMARY KEY,
                telegram TEXT);
            CREATE TABLE IF NOT EXISTS motor_lecturas (id INTEGER PRIMARY KEY
                AUTOINCREMENT, alerta_id INTEGER, motor TEXT, datos TEXT);""")
        from src.experimentos.informe import Informe
        self.inf = Informe(self.conn)

    def test_the_geometric_baseline_is_what_pure_chance_gives(self):
        from src.experimentos.informe import base_geometrica
        # +6 % de premio contra 3 % de riesgo: el azar acierta 1 de cada 3.
        self.assertAlmostEqual(base_geometrica(100, 106, 97), 1 / 3, places=4)
        # Simetrico: mitad y mitad.
        self.assertAlmostEqual(base_geometrica(100, 103, 97), 0.5, places=4)
        # Un stop el doble de ancho "acierta" mucho mas sin elegir mejor.
        self.assertGreater(base_geometrica(100, 106, 94), base_geometrica(100, 106, 97))
        self.assertIsNone(base_geometrica(100, 99, 97))

    def test_below_the_minimum_sample_the_verdict_is_inconclusive(self):
        """
        Con pocos datos el resultado es «no alcanza», y eso ES el resultado.
        Devolver un porcentaje ahi es como se fabrican los hallazgos que se
        evaporan la semana siguiente.
        """
        self.alm.congelar(INICIO)
        ident = self.alta()
        self.sembrar([(100, 106.5, 99, 106.2)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        v = self.inf.evaluar_politica("A3", filtro=None)
        self.assertEqual(v["veredicto"], INCONCLUSO)
        self.assertIn("hacen falta", v["por_que"])
        self.assertEqual(v["medibles"], 1)

    def test_the_report_never_averages_orders_that_did_not_fill(self):
        self.alm.congelar(INICIO)
        self.alta()
        self.sembrar([(100, 106.5, 99.9, 106.2)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        v = self.inf.evaluar_politica("B2", filtro=None)
        self.assertEqual(v["elegibles"], 1)
        self.assertEqual(v["llenadas"], 0)
        self.assertEqual(v["medibles"], 0)
        self.assertEqual(v["tasa_ejecucion"], 0.0)
        self.assertIsNone(v["dinero"]["media"])

    def test_the_decisive_population_is_telegram_and_first_of_episode(self):
        from src.experimentos.informe import FILTROS_SQL
        self.assertIn("ordinal_episodio = 1", FILTROS_SQL["DECISORIA"])
        self.assertIn("telegram", FILTROS_SQL["DECISORIA"])
        self.alm.congelar(INICIO)
        ident = self.alta(alerta_id=7)
        self.sembrar([(100, 106.5, 99, 106.2)])
        self.alm.evaluar_pendientes(INICIO + 3600_000)
        # Sin fila en alertas_emitidas, no es poblacion decisoria.
        self.assertEqual(self.inf.poblacion("DECISORIA"), [])
        self.conn.execute("INSERT INTO alertas_emitidas VALUES (7, 'enviado')")
        self.assertEqual(self.inf.poblacion("DECISORIA"), [ident["plan_id"]])

    def test_the_bootstrap_resamples_pairs_not_operations(self):
        """
        Veinte operaciones de UN par no son veinte observaciones
        independientes. Remuestreando pares, el intervalo lo refleja.
        """
        from src.experimentos.informe import _bootstrap_por_par
        un_par = {"AUSDT": [1.0] * 20}
        veinte = {f"S{i}USDT": [1.0] for i in range(20)}
        a, b = _bootstrap_por_par(un_par), _bootstrap_por_par(veinte)
        self.assertEqual((a["n"], a["pares"]), (20, 1))
        self.assertEqual((b["n"], b["pares"]), (20, 20))


class CarteraTests(MedicionTests):
    def _oportunidad(self, plan_id, symbol, ts, resultado, desenlace="OBJETIVO"):
        # El plan se da de alta por el registro real, no a mano: asi la prueba
        # usa el mismo camino que produccion y no inventa filas a medias.
        ident = self.reg.registrar(
            symbol=symbol, ts_ms=ts, tl=dict(PLAN, tf="5m"),
            alerta_id=plan_id, horizonte_ms=3600_000, coste_pct=0.5)
        plan_id = ident["plan_id"]
        self.conn.execute(
            """INSERT INTO experimento_resultados
               (plan_id, politica, huella, symbol, ts_creado, entrada, objetivo,
                stop, tamano, ms_fill, desenlace, ms_desenlace, resultado_pct,
                ts_evaluado)
               VALUES (?,?,?,?,?,?,?,?,1.0,NULL,?,?,?,?)""",
            (plan_id, "REF", huella(), symbol, ts, 100.0, 106.0, 97.0,
             desenlace, 600_000, resultado, ts))

    def test_ten_dollars_all_in_compounds_and_does_not_add_up(self):
        """
        +10 % y -10 % no dejan el capital igual: lo dejan en 99 %. Una media
        por operacion diria cero.
        """
        from src.experimentos.cartera import Cartera, Escenario
        self.alm.congelar(INICIO)
        self._oportunidad(1, "AUSDT", INICIO, 10.0)
        self._oportunidad(2, "BUSDT", INICIO + 3600_000, -10.0, "STOP")
        r = Cartera(self.conn).simular("REF", Escenario(filtro=None))
        self.assertEqual(r.n_operaciones, 2)
        self.assertAlmostEqual(r.capital_final, 9.9, places=4)

    def test_one_position_at_a_time_lets_opportunities_pass(self):
        """
        Tomar A significa no tomar B. Con una posicion, la mayoria de lo que el
        sistema ve pasa de largo — y eso una media por operacion lo borra.
        """
        from src.experimentos.cartera import Cartera, Escenario
        self.alm.congelar(INICIO)
        self._oportunidad(1, "AUSDT", INICIO, 5.0)
        self._oportunidad(2, "BUSDT", INICIO + 60_000, 50.0)    # se la pierde
        self._oportunidad(3, "CUSDT", INICIO + 1_200_000, 5.0)  # ya libre
        r = Cartera(self.conn).simular("REF", Escenario(filtro=None))
        self.assertEqual(r.n_operaciones, 2)
        self.assertEqual(r.n_descartadas_por_ocupado, 1)
        self.assertAlmostEqual(r.capital_final, 10 * 1.05 * 1.05, places=4)

    def test_dropping_below_the_exchange_minimum_stops_the_simulation(self):
        """
        Con 10 dolares esto no es teorico: por debajo del minimo de Binance la
        orden se rechaza. Seguir contando operaciones ahi seria inventarlas.
        """
        from src.experimentos.cartera import Cartera, Escenario
        self.alm.congelar(INICIO)
        for i in range(30):
            self._oportunidad(i + 1, f"S{i}USDT", INICIO + i * 3600_000, -20.0, "STOP")
        r = Cartera(self.conn).simular("REF", Escenario(filtro=None))
        self.assertTrue(r.parada_por_minimo)
        self.assertLess(r.n_operaciones, 30)
        self.assertGreater(r.racha_perdedora_max, 0)
        # La ultima operacion SI era legal (invirtio >= 5) y perdio; lo que ya
        # no se puede es abrir la siguiente. Por eso el capital final queda por
        # debajo del minimo y no encima.
        self.assertLess(r.capital_final, 5.0)
        self.assertIsNotNone(r.ts_parada)

    def test_the_drawdown_is_measured_from_the_peak(self):
        from src.experimentos.cartera import Cartera, Escenario
        self.alm.congelar(INICIO)
        self._oportunidad(1, "AUSDT", INICIO, 50.0)
        self._oportunidad(2, "BUSDT", INICIO + 3600_000, -20.0, "STOP")
        r = Cartera(self.conn).simular("REF", Escenario(filtro=None))
        self.assertAlmostEqual(r.caida_maxima_pct, 20.0, places=1)
        d = r.como_dict()
        self.assertAlmostEqual(d["retorno_pct"], 20.0, places=1)
        self.assertEqual(d["tasa_acierto_pct"], 50.0)



class HambrunaTests(MedicionTests):
    """(ver el docstring de abajo)"""

    def alta_sym(self, symbol, ts, alerta_id):
        return self.reg.registrar(
            symbol=symbol, ts_ms=ts, tl=dict(PLAN, tf="5m"),
            alerta_id=alerta_id, horizonte_ms=3600_000, coste_pct=0.5)

    def velas_sym(self, symbol, n):
        self.conn.executemany(
            "INSERT OR REPLACE INTO klines VALUES (?,?,?,?,?,?,?,?)",
            [(symbol, "1m", INICIO + i * M, 100, 106.5, 99, 106.2, 1)
             for i in range(n)])

    """
    El turno tiene que ser por ULTIMO INTENTO, no por fecha del plan.

    Un plan sin cobertura queda SIN_DATOS y vuelve a la cola. Ordenando por
    `ts_creado`, esos planes —los mas viejos— se reelegian en cada pasada y se
    comian el presupuesto entero: en produccion, tres planes bloquearon la cola
    12 horas mientras 828 esperaban. Es la misma hambruna que la fase 2 ya tuvo
    que corregir en su evaluador.
    """

    def test_a_retried_plan_goes_to_the_back_of_the_queue(self):
        self.alm.congelar(INICIO)
        self.alm.max_por_pasada = 1
        # Cada plan en SU par, para que la cobertura sea de verdad distinta:
        # compartiendo velas los tres estarian cubiertos y la prueba no
        # probaria nada.
        sin_datos = self.alta_sym("POBREUSDT", INICIO, 1)
        self.velas_sym("POBREUSDT", 5)          # 5 de 60: cobertura 0,08
        buenos = [self.alta_sym(f"BUENO{i}USDT", INICIO + i * M, i + 1)
                  for i in (1, 2)]
        for i in (1, 2):
            self.velas_sym(f"BUENO{i}USDT", 62)

        ahora = INICIO + 3600_000 + 5 * M
        for paso in range(4):
            self.alm.evaluar_pendientes(ahora + paso * 1000)

        medidos = {r[0] for r in self.conn.execute(
            "SELECT DISTINCT plan_id FROM experimento_resultados")}
        self.assertIn(sin_datos["plan_id"], medidos)
        self.assertEqual(
            self.conn.execute(
                "SELECT desenlace FROM experimento_resultados WHERE plan_id = ? "
                "LIMIT 1", (sin_datos["plan_id"],)).fetchone()[0], "SIN_DATOS")
        for b in buenos:
            self.assertIn(b["plan_id"], medidos,
                          "un plan medible se quedo detras del SIN_DATOS")

    def test_the_starved_plans_are_the_ones_that_advance(self):
        """Con el turno por intento, cada pasada toca un plan distinto."""
        self.alm.congelar(INICIO)
        self.alm.max_por_pasada = 1
        planes = []
        for i in range(1, 4):
            planes.append(self.alta_sym(f"P{i}USDT", INICIO + i * M, i))
            self.velas_sym(f"P{i}USDT", 62)
        ahora = INICIO + 3600_000 + 10 * M
        for paso in range(3):
            self.alm.evaluar_pendientes(ahora + paso * 1000)
        vistos = {r[0] for r in self.conn.execute(
            "SELECT DISTINCT plan_id FROM experimento_resultados")}
        self.assertEqual(len(vistos), 3, "la cola no avanzo")


if __name__ == "__main__":
    unittest.main()
