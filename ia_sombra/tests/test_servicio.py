"""
El servicio de punta a punta contra una base de SAC real, con Kronos y OpenAI de mentira.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import apoyo
from apoyo import M, T0, ClienteFalso, MotorFalso

from sac_ia import registro
from sac_ia.almacen import Almacen
from sac_ia.fuente import FuenteSAC
from sac_ia.servicio import Servicio

ACTIVADO = T0 + 30_000


class Reloj:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class ServicioTests(unittest.TestCase):
    def setUp(self):
        self.sac = apoyo.BaseSAC()
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = apoyo.cfg(self.sac, Path(self.tmp.name))
        self.a = Almacen(self.cfg.ia_db)
        self.reloj = Reloj(T0 - 60_000)
        self.cliente = ClienteFalso()
        self.motor = MotorFalso()
        self.s = Servicio(self.cfg, FuenteSAC(self.sac.ruta), self.a, cliente=self.cliente,
                          motor=self.motor, velas_kronos=apoyo.velas_kronos_sinteticas,
                          reloj=self.reloj)
        self.s.iniciar()

    def tearDown(self):
        self.s.fuente.cerrar()
        self.a.db.close()
        self.sac.cerrar()
        self.tmp.cleanup()

    def aviso(self, enviado_en=ACTIVADO + 5_000, **kw):
        i = self.sac.alerta(**kw)
        self.reloj.t = T0 + 1_000
        self.s.descubrir(self.reloj.t)
        self.s.revisar(self.reloj.t)
        self.sac.notificar(i)
        self.sac.telegram(i, "enviado")
        self.reloj.t = enviado_en
        self.s.revisar(self.reloj.t)
        return i

    def medir(self):
        self.a.fijar_meta("inicio_medicion_ms", T0 - 1)
        self.a.fijar_meta("huella_medicion", registro.huella())

    def test_los_avisos_anteriores_al_arranque_no_se_procesan(self):
        viejo = self.sac.alerta(telegram="enviado")
        cfg = apoyo.cfg(self.sac, Path(self.tmp.name) / "b")
        s = Servicio(cfg, FuenteSAC(self.sac.ruta), Almacen(cfg.ia_db), reloj=self.reloj)
        s.iniciar()
        self.assertEqual(int(s.a.meta("cursor_alerta")), viejo)
        self.assertEqual(s.descubrir(T0), 0)
        s.fuente.cerrar()
        s.a.db.close()

    def test_rodaje_registra_caso_y_contexto_sin_gastar(self):
        i = self.aviso()
        caso = self.a.caso(i)
        self.assertEqual((caso["modo"], caso["as_of_ms"], caso["tardio"]), ("RODAJE", ACTIVADO, 0))
        self.assertAlmostEqual(caso["meta_precio"], 100 * (1 + registro.META_BRUTA_PCT / 100))
        self.assertEqual(self.a.uno("SELECT COUNT(*) FROM contextos"), 1)
        self.assertEqual(self.a.uno("SELECT COUNT(*) FROM decisiones"), 0)
        self.assertEqual(self.cliente.llamadas, [])
        self.assertEqual(self.motor.peticiones, [])

    def test_medicion_kronos_alimenta_a_luna_y_sol(self):
        self.medir()
        i = self.aviso()
        k = self.a.filas("SELECT * FROM kronos WHERE caso_id = ?", (i,))[0]
        self.assertEqual(k["estado"], "OK")
        self.assertEqual(k["p_meta"], 0.75)            # 3 de cada 4 trayectorias falsas suben
        self.assertTrue(Path(k["artefacto"]).is_file())
        dec = {d["brazo"]: d for d in self.a.filas("SELECT * FROM decisiones")}
        self.assertEqual(set(dec), {"LUNA", "SOL"})
        self.assertTrue(all(d["estado"] == "OK" and d["a_tiempo"] for d in dec.values()))
        modelos = sorted(c["model"] for c in self.cliente.llamadas)
        self.assertEqual(modelos, ["gpt-6-luna", "gpt-6-sol"])
        import json
        entrada = json.loads(self.cliente.llamadas[0]["input"][0]["content"])
        self.assertTrue(entrada["kronos"]["disponible"])
        self.assertEqual(entrada["kronos"]["p_meta_antes_que_stop"], 0.75)
        # Kronos no puede llevarse el plazo entero: deja margen a los LLM
        self.assertLessEqual(self.motor.peticiones[0][1], 120 - 30)

    def test_dos_avisos_juntos_se_simulan_uno_a_uno_con_su_plazo(self):
        self.medir()
        a = self.sac.alerta(symbol="POLUSDT")
        b = self.sac.alerta(symbol="DOGEUSDT")
        self.reloj.t = T0 + 1_000
        self.s.descubrir(self.reloj.t)
        for i, s in ((a, "POLUSDT"), (b, "DOGEUSDT")):
            self.sac.notificar(i, symbol=s)
            self.sac.telegram(i, "enviado")
        self.reloj.t = ACTIVADO + 5_000
        self.s.revisar(self.reloj.t)
        self.assertEqual([p[0][0]["caso_id"] for p in self.motor.peticiones], [a, b])
        self.assertEqual(self.a.uno("SELECT COUNT(*) FROM decisiones WHERE estado = 'OK'"), 4)

    def test_si_kronos_falla_sol_se_entera_y_decide_igual(self):
        self.motor.error = TimeoutError("lento")
        self.medir()
        i = self.aviso()
        self.assertEqual(self.a.filas("SELECT estado FROM kronos WHERE caso_id = ?", (i,))[0]
                         ["estado"], "FALLO")
        import json
        entrada = json.loads(self.cliente.llamadas[0]["input"][0]["content"])
        self.assertFalse(entrada["kronos"]["disponible"])
        self.assertIn("TimeoutError", entrada["kronos"]["motivo"])

    def test_aviso_visto_tarde_no_se_paga(self):
        self.medir()
        i = self.aviso(enviado_en=ACTIVADO + registro.PLAZO_DECISION_MS + 1)
        self.assertEqual(self.a.caso(i)["tardio"], 1)
        self.assertEqual(self.cliente.llamadas, [])
        self.assertEqual({d["estado"] for d in self.a.filas("SELECT estado FROM decisiones")},
                         {"NO_EJECUTADA"})

    def test_enviado_sin_plan_legible_se_reintenta(self):
        i = self.sac.alerta(telegram="enviado")
        self.reloj.t = ACTIVADO
        self.s.descubrir(self.reloj.t)
        self.s.revisar(self.reloj.t)
        self.assertIsNone(self.a.caso(i))
        self.assertEqual(len(self.a.pendientes()), 1)
        self.sac.notificar(i)
        self.s.revisar(self.reloj.t + 5_000)
        self.assertIsNotNone(self.a.caso(i))
        self.assertEqual(self.a.pendientes(), [])

    def test_no_procede_se_descarta(self):
        i = self.sac.alerta()
        self.s.descubrir(T0)
        self.sac.telegram(i, "no_procede")
        self.s.revisar(T0 + 5_000)
        self.assertEqual(self.a.pendientes(), [])
        self.assertIsNone(self.a.caso(i))

    def test_la_evidencia_no_se_reescribe(self):
        i = self.aviso()
        for sql in ("UPDATE casos SET entrada = 1", "DELETE FROM contextos"):
            with self.assertRaises(sqlite3.IntegrityError, msg=sql):
                self.a.db.execute(sql)
        self.assertEqual(self.a.caso(i)["entrada"], 100.0)

    def test_etiqueta_con_el_evaluador_de_sac(self):
        i = self.aviso()
        inicio = ((ACTIVADO // M) + 1) * M              # primer minuto entero tras el aviso
        n = registro.HORIZONTE_MS // M
        filas = [(100, 100.5, 99.5, 100, 1)] * n
        filas[30] = (100, 104.0, 99.9, 103.9, 1)        # toca la meta (103,7) en el minuto 30
        self.sac.velas("POLUSDT", "1m", inicio, filas)
        self.assertEqual(self.s.etiquetar(ACTIVADO + registro.HORIZONTE_MS), 0)   # aun no
        self.s.etiquetar(ACTIVADO + registro.HORIZONTE_MS + registro.ESPERA_ETIQUETA_MS)
        e = self.a.filas("SELECT * FROM etiquetas WHERE caso_id = ?", (i,))[0]
        self.assertEqual((e["meta_primero"], e["desenlace_meta"], e["final"]), (1, "OBJETIVO", 1))
        self.assertAlmostEqual(e["resultado_meta_pct"], registro.OBJETIVO_OPERADOR_PCT, places=3)
        self.assertGreaterEqual(e["cobertura"], registro.COBERTURA_MINIMA)
        self.assertEqual(e["desenlace_tp"], "VENCIDO")      # el TP (110) nunca se toco

    def test_kronos_se_carga_antes_del_aviso_y_solo_en_medicion(self):
        self.s.paso()
        self.assertFalse(self.motor.arrancado)             # rodaje: no se carga nada
        self.medir()
        self.s.paso()
        self.assertTrue(self.motor.arrancado)

    def test_si_kronos_no_carga_no_se_reintenta_en_cada_vuelta(self):
        intentos = []

        def arrancar_roto():
            intentos.append(1)
            raise RuntimeError("sin torch")
        self.motor.arrancar = arrancar_roto
        self.medir()
        for _ in range(5):
            self.s.paso()
        self.assertEqual(len(intentos), 1)
        self.assertEqual(self.a.uno("SELECT COUNT(*) FROM eventos WHERE tipo = 'KRONOS_NO_CARGA'"), 1)

    def test_la_salud_se_muestrea_con_intervalo_irregular(self):
        instantes = []
        for i in range(40):
            self.reloj.t = T0 + i * 7_000
            self.s.paso()
        instantes = [f["ts_ms"] for f in self.a.filas("SELECT ts_ms FROM salud ORDER BY ts_ms")]
        huecos = {b - a for a, b in zip(instantes, instantes[1:])}
        self.assertGreater(len(instantes), 3)
        self.assertGreater(len(huecos), 1)                 # no siempre el mismo intervalo

    def test_con_poca_cobertura_la_etiqueta_espera_y_no_es_final(self):
        i = self.aviso()
        inicio = ((ACTIVADO // M) + 1) * M
        self.sac.velas("POLUSDT", "1m", inicio, [(100, 100.5, 99.5, 100, 1)] * 300)
        self.s.etiquetar(ACTIVADO + registro.HORIZONTE_MS + registro.ESPERA_ETIQUETA_MS)
        e = self.a.filas("SELECT final, cobertura FROM etiquetas WHERE caso_id = ?", (i,))[0]
        self.assertEqual(e["final"], 0)
        self.assertLess(e["cobertura"], 0.5)


if __name__ == "__main__":
    unittest.main()
