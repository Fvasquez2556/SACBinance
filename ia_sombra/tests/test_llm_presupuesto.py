"""Luna y Sol: todo lo que puede salir mal tiene nombre, y el gasto tiene tope."""
import json
import unittest
from types import SimpleNamespace

import apoyo
from apoyo import ClienteFalso, respuesta

from sac_ia import llm, registro
from sac_ia.almacen import Almacen
from sac_ia.presupuesto import Presupuesto, coste_usd

AHORA = 1_790_000_000_000
PLAZO = AHORA + 120_000
CTX = {"par": "POLUSDT", "plan": {"entrada": 1.0}}


class Timeout(Exception):
    pass


Timeout.__name__ = "APITimeoutError"


class Http(Exception):
    def __init__(self, codigo):
        super().__init__(f"http {codigo}")
        self.status_code = codigo


class LlmTests(unittest.TestCase):
    def setUp(self):
        self.a = Almacen(":memory:")
        self.p = Presupuesto(self.a, 1.0, 5.0)

    def decidir(self, cliente, brazo="SOL", reloj=lambda: AHORA, plazo=PLAZO):
        return llm.decidir(cliente, brazo, CTX, 42, plazo, self.p, 60, reloj)

    def gasto(self):
        return self.a.filas("SELECT estado, reservado_micro, consumido_micro FROM gasto")

    def test_respuesta_valida(self):
        cliente = ClienteFalso()
        d = self.decidir(cliente)
        self.assertEqual((d["estado"], d["accion"], d["p_meta"], d["a_tiempo"]),
                         ("OK", "ENTRAR", 0.62, 1))
        pedido = cliente.llamadas[0]
        self.assertEqual(pedido["model"], "gpt-6-sol")
        self.assertTrue(pedido["text"]["format"]["strict"])
        self.assertEqual(pedido["reasoning"], {"effort": "low"})
        self.assertFalse(pedido["store"])
        self.assertEqual(json.loads(pedido["input"][0]["content"]), CTX)
        self.assertAlmostEqual(d["coste_usd"], coste_usd("gpt-6-sol", 1000, 0, 300))
        self.assertEqual(self.gasto()[0]["estado"], "LIQUIDADO")

    def test_la_respuesta_que_llega_despues_del_plazo_no_cuenta(self):
        tiempos = iter([AHORA, PLAZO + 1])
        d = self.decidir(ClienteFalso(), reloj=lambda: next(tiempos))
        self.assertEqual((d["estado"], d["a_tiempo"]), ("OK", 0))

    def test_incompleta_rechazo_e_invalida_no_son_decisiones(self):
        casos = {
            "INCOMPLETA": respuesta(status="incomplete", incompleta="max_output_tokens"),
            "RECHAZO_MODELO": respuesta(rechazo="no puedo"),
            "INVALIDA": respuesta(texto="{no es json"),
        }
        for estado, r in casos.items():
            d = self.decidir(ClienteFalso([r]))
            self.assertEqual(d["estado"], estado)
            self.assertIsNone(d.get("accion"))

    def test_validacion_local_de_cada_campo(self):
        base = {"accion": "ENTRAR", "p_meta": 0.5, "confianza": "ALTA", "codigos": [], "razon": ""}
        self.assertIsNone(llm.validar(base))
        for cambio in ({"p_meta": 1.5}, {"p_meta": float("nan")}, {"p_meta": True},
                       {"accion": "COMPRAR"}, {"codigos": ["INVENTADO"]}, {"extra": 1}):
            self.assertIsNotNone(llm.validar({**base, **cambio}), cambio)

    def test_timeout_deja_la_reserva_incierta_y_un_400_la_libera(self):
        d = self.decidir(ClienteFalso(excepcion=Timeout("lento")))
        self.assertEqual(d["estado"], "TIMEOUT")
        self.assertEqual(self.gasto()[0]["estado"], "INCIERTO")
        d = self.decidir(ClienteFalso(excepcion=Http(400)))
        self.assertEqual(d["estado"], "ERROR_HTTP_400")
        self.assertEqual(self.gasto()[1]["estado"], "LIBERADO")

    def test_sin_clave_o_sin_tiempo_no_se_llama(self):
        self.assertEqual(self.decidir(None)["estado"], "NO_EJECUTADA")
        cliente = ClienteFalso()
        d = self.decidir(cliente, plazo=AHORA + 3_000)
        self.assertEqual(d["estado"], "NO_EJECUTADA")
        self.assertEqual(cliente.llamadas, [])
        self.assertEqual(self.gasto(), [])

    def test_sin_presupuesto_no_se_llama(self):
        self.p = Presupuesto(self.a, 0.0001, 5.0)
        cliente = ClienteFalso()
        self.assertEqual(self.decidir(cliente)["estado"], "SIN_PRESUPUESTO")
        self.assertEqual(cliente.llamadas, [])


class PresupuestoTests(unittest.TestCase):
    def test_tope_diario_y_total(self):
        a = Almacen(":memory:")
        p = Presupuesto(a, tope_diario_usd=0.10, tope_total_usd=0.15)
        self.assertTrue(p.reservar("a", 1, "SOL", "gpt-6-sol", 0.06, AHORA))
        self.assertFalse(p.reservar("b", 1, "SOL", "gpt-6-sol", 0.06, AHORA))   # dia
        p.liquidar("a", 0.01)                                                   # se gasto menos
        self.assertTrue(p.reservar("b", 1, "SOL", "gpt-6-sol", 0.06, AHORA))
        otro_dia = AHORA + 86_400_000
        self.assertFalse(p.reservar("c", 1, "SOL", "gpt-6-sol", 0.09, otro_dia))  # total
        self.assertTrue(p.reservar("c", 1, "SOL", "gpt-6-sol", 0.07, otro_dia))

    def test_lo_incierto_sigue_contando(self):
        a = Almacen(":memory:")
        p = Presupuesto(a, 0.10, 1.0)
        p.reservar("a", 1, "SOL", "gpt-6-sol", 0.08, AHORA)
        p.incierto("a")
        self.assertFalse(p.reservar("b", 1, "SOL", "gpt-6-sol", 0.05, AHORA))

    def test_modelo_sin_tarifa_no_se_llama(self):
        p = Presupuesto(Almacen(":memory:"), 10, 10)
        self.assertFalse(p.reservar("a", 1, "X", "gpt-desconocido", 0.01, AHORA))

    def test_tarifas_para_cada_brazo(self):
        for cfg in registro.BRAZOS_LLM.values():
            self.assertIn(cfg["modelo"], registro.TARIFAS)


if __name__ == "__main__":
    unittest.main()
