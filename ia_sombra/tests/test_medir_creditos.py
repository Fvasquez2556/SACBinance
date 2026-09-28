"""Sin saldo en OpenAI: se reconoce, se avisa, y no se empieza a medir."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import apoyo
from apoyo import ClienteFalso

from sac_ia import informe, llm, registro
from sac_ia.__main__ import cmd_medir
from sac_ia.almacen import Almacen
from sac_ia.presupuesto import Presupuesto

AHORA = 1_790_000_000_000


class SinSaldo(Exception):
    """Como el RateLimitError de OpenAI cuando la cuenta no tiene credito."""
    status_code = 429
    code = "credit_balance_exhausted"
    type = "insufficient_quota"


class CreditosTests(unittest.TestCase):
    def test_sin_saldo_tiene_nombre_propio_y_no_retiene_la_reserva(self):
        a = Almacen(":memory:")
        d = llm.decidir(ClienteFalso(excepcion=SinSaldo("sin saldo")), "SOL", {"x": 1}, 1,
                        AHORA + 120_000, Presupuesto(a, 1, 1), 60, lambda: AHORA)
        self.assertEqual(d["estado"], "SIN_CREDITOS")
        self.assertEqual(a.uno("SELECT estado FROM gasto"), "LIBERADO")

    def test_un_429_normal_sigue_siendo_un_429(self):
        class Ritmo(Exception):
            status_code = 429
            code = "rate_limit_exceeded"
        a = Almacen(":memory:")
        d = llm.decidir(ClienteFalso(excepcion=Ritmo("despacio")), "SOL", {"x": 1}, 1,
                        AHORA + 120_000, Presupuesto(a, 1, 1), 60, lambda: AHORA)
        self.assertEqual(d["estado"], "ERROR_HTTP_429")

    def test_estado_avisa_aunque_el_informe_este_cegado(self):
        a = Almacen(":memory:")
        a.fijar_meta("inicio_medicion_ms", AHORA - 1000)
        a.guardar_decision({"caso_id": 1, "brazo": "SOL", "modelo": "gpt-6-sol",
                            "estado": "SIN_CREDITOS", "solicitado_ms": AHORA - 60_000,
                            "a_tiempo": 0})
        self.assertEqual(len(informe.operativo(a, AHORA)["advertencias"]), 1)
        texto = informe.generar(a, AHORA)
        self.assertIn("ATENCION: OpenAI sin saldo", texto)
        self.assertIn("Cegado", texto)
        # pasado un dia sin fallos, la advertencia desaparece
        self.assertEqual(informe.operativo(a, AHORA + 25 * 3600_000)["advertencias"], [])


class MedirTests(unittest.TestCase):
    def setUp(self):
        # cmd_medir es una orden de consola: deja su conexion abierta hasta que
        # el proceso acaba, y Windows no deja borrar un fichero abierto.
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        raiz = Path(self.tmp.name)
        (raiz / "Kronos" / "model").mkdir(parents=True)
        (raiz / "openai.key").write_text("sk-prueba\n", encoding="utf-8")
        sac = raiz / "sac.db"
        sac.write_bytes(b"")
        self.cfg = apoyo.config.cargar({
            "IA_DB": str(raiz / "ia.db"), "IA_SAC_DB": str(sac),
            "IA_KRONOS_CODIGO": str(raiz / "Kronos"),
            "IA_CLAVE_OPENAI": str(raiz / "openai.key")})
        a = Almacen(self.cfg.ia_db)
        a.fijar_meta("inicio_rodaje_ms", llm.ahora_ms() - registro.RODAJE_MIN_MS - 60_000)
        a.db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def medir(self, resultados):
        with redirect_stdout(io.StringIO()) as salida:
            codigo = cmd_medir(self.cfg, False, prueba=lambda cfg: resultados)
        a = Almacen(self.cfg.ia_db)
        inicio = a.meta("inicio_medicion_ms")
        a.db.close()
        return codigo, salida.getvalue(), inicio

    def test_no_empieza_si_la_consulta_de_prueba_no_sale_bien(self):
        codigo, texto, inicio = self.medir([
            {"brazo": "LUNA", "estado": "OK"},
            {"brazo": "SOL", "estado": "SIN_CREDITOS", "motivo": "credit_balance_exhausted"}])
        self.assertEqual(codigo, 1)
        self.assertIn("SOL devolvio SIN_CREDITOS", texto)
        self.assertIsNone(inicio)

    def test_empieza_si_las_dos_salen_bien(self):
        codigo, texto, inicio = self.medir([{"brazo": "LUNA", "estado": "OK"},
                                            {"brazo": "SOL", "estado": "OK"}])
        self.assertEqual(codigo, 0, texto)
        self.assertIsNotNone(inicio)


if __name__ == "__main__":
    unittest.main()
