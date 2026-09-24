"""La base de SAC se lee y no se puede tocar."""
import sqlite3
import unittest

import apoyo
from apoyo import M, T0

from sac_ia.fuente import FuenteSAC, IncompatibilidadFuente


class FuenteTests(unittest.TestCase):
    def setUp(self):
        self.sac = apoyo.BaseSAC()
        self.f = FuenteSAC(self.sac.ruta)

    def tearDown(self):
        self.f.cerrar()
        self.sac.cerrar()

    def test_no_se_puede_escribir_en_la_base_de_sac(self):
        self.sac.alerta()
        for sql in ("UPDATE alertas_emitidas SET telegram = 'x'",
                    "DELETE FROM alertas_emitidas",
                    "CREATE TABLE intrusa (x)"):
            with self.assertRaises(sqlite3.OperationalError, msg=sql):
                self.f.conn.execute(sql)
        self.assertEqual(self.sac.conn.execute(
            "SELECT telegram FROM alertas_emitidas").fetchone()[0], "pendiente")

    def test_el_esquema_real_de_sac_tiene_lo_que_la_ia_lee(self):
        info = self.f.comprobar_esquema()
        self.assertTrue(info["planes"])
        self.assertIsNotNone(info["schema_version"])

    def test_una_columna_que_falta_es_incompatibilidad_y_no_se_migra(self):
        self.sac.conn.execute("ALTER TABLE notificacion_planes RENAME COLUMN contexto TO ctx")
        self.sac.conn.commit()
        with self.assertRaises(IncompatibilidadFuente):
            self.f.comprobar_esquema()

    def test_ve_lo_que_sac_escribe_despues_de_abrir(self):
        self.assertEqual(self.f.ultimo_id(), 0)
        i = self.sac.alerta()
        self.assertEqual(self.f.ultimo_id(), i)
        self.sac.telegram(i, "enviado")
        self.assertEqual(self.f.estado_telegram([i]), {i: "enviado"})

    def test_la_vela_en_curso_nunca_entra(self):
        self.sac.velas("POLUSDT", "15m", T0 - 3 * 15 * M, [(1, 2, 0.5, 1.5, 10)] * 4)
        # a T0 + 30 s la vela que abrio en T0 sigue abierta
        cerradas = self.f.velas_cerradas("POLUSDT", "15m", T0 + 30_000, 10)
        self.assertEqual([v[0] for v in cerradas], [T0 - 3 * 15 * M, T0 - 2 * 15 * M, T0 - 15 * M])

    def test_aviso_sin_plan_notificado_es_none(self):
        i = self.sac.alerta(telegram="enviado")
        self.assertIsNone(self.f.aviso(i))
        self.sac.notificar(i)
        aviso = self.f.aviso(i)
        self.assertEqual(aviso["notificacion"]["ts_activado"], T0 + 30_000)

    def test_edad_de_la_ultima_vela(self):
        self.sac.velas("BTCUSDT", "1m", T0, [(1, 1, 1, 1, 1)] * 3)
        self.assertEqual(self.f.edad_ultima_vela_ms(T0 + 3 * M + 5_000), 5_000)


if __name__ == "__main__":
    unittest.main()
