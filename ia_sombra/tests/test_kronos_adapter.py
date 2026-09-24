"""El proceso hijo de Kronos se puede matar, y las velas de Binance se leen bien."""
import io
import json
import time
import unittest
from unittest.mock import patch

import apoyo  # noqa: F401

from sac_ia import kronos_adapter


def fabrica_falsa(ajustes):
    return {"cargado": ajustes["modelo"]}


def simulador_falso(predictor, velas, pasos, n, semilla, temperatura, top_p):
    return [[(1.0, 1.0, 1.0, 1.0)] * pasos for _ in range(n)]


def simulador_lento(predictor, velas, pasos, n, semilla, temperatura, top_p):
    time.sleep(30)
    return []


def fabrica_rota(ajustes):
    raise ImportError("sin torch")


AJUSTES = {"codigo": ".", "hilos": 1, "modelo": "m", "tokenizador": "t",
           "revision_modelo": "", "revision_tokenizador": "", "max_contexto": 512}


class MotorTests(unittest.TestCase):
    def test_simula_en_un_proceso_hijo(self):
        motor = kronos_adapter.MotorKronos(AJUSTES, fabrica_falsa, simulador_falso)
        try:
            r = motor.simular([{"caso_id": 7, "velas": [], "semilla": 1}], timeout_s=60)
            self.assertEqual(len(r["trayectorias"][7]), kronos_adapter.registro.KRONOS["trayectorias"])
        finally:
            motor.parar()

    def test_si_pasa_del_plazo_se_mata_y_se_relanza_al_siguiente(self):
        motor = kronos_adapter.MotorKronos(AJUSTES, fabrica_falsa, simulador_lento)
        with self.assertRaises(TimeoutError):
            motor.simular([{"caso_id": 1, "velas": [], "semilla": 1}], timeout_s=2)
        self.assertIsNone(motor.proc)
        motor.simulador = simulador_falso
        r = motor.simular([{"caso_id": 2, "velas": [], "semilla": 1}], timeout_s=60)
        self.assertIn(2, r["trayectorias"])
        motor.parar()

    def test_si_no_carga_lo_dice(self):
        motor = kronos_adapter.MotorKronos(AJUSTES, fabrica_rota, simulador_falso)
        with self.assertRaises(RuntimeError) as ctx:
            motor.simular([], timeout_s=5)
        self.assertIn("sin torch", str(ctx.exception))


class VelasBinanceTests(unittest.TestCase):
    def test_solo_velas_cerradas_con_volumen_base_e_importe(self):
        paso = 900_000
        as_of = 100 * paso + 30_000
        crudas = [[t * paso, "1", "2", "0.5", "1.5", "10", t * paso + paso - 1, "15", 3, "0", "0",
                   "0"] for t in range(90, 101)]           # la de 100 sigue abierta
        respuesta = io.BytesIO(json.dumps(crudas).encode())
        with patch("urllib.request.urlopen", return_value=respuesta) as abrir:
            velas = kronos_adapter.velas_binance("https://x", "POLUSDT", as_of, 5, tf="15m")
        url = abrir.call_args[0][0]
        self.assertIn("interval=15m", url)
        self.assertIn(f"endTime={as_of - 1}", url)
        self.assertEqual([v["t"] for v in velas], [t * paso for t in range(95, 100)])
        self.assertEqual((velas[0]["volumen"], velas[0]["importe"]), (10.0, 15.0))


if __name__ == "__main__":
    unittest.main()
