"""La vara del veredicto y el candado del estudio."""
import json
import unittest
from unittest.mock import patch

import apoyo  # noqa: F401

from sac_ia import informe, registro
from sac_ia.almacen import Almacen


class EstadisticaTests(unittest.TestCase):
    def test_auc(self):
        self.assertEqual(informe.auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]), 1.0)
        self.assertEqual(informe.auc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]), 0.0)
        self.assertEqual(informe.auc([0.5] * 4, [0, 1, 0, 1]), 0.5)
        self.assertIsNone(informe.auc([0.1, 0.2], [1, 1]))
        # 3 de los 4 pares positivo-negativo bien ordenados
        self.assertEqual(informe.auc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]), 0.75)

    def test_bootstrap_por_grupo_contiene_el_punto(self):
        filas = [{"g": i % 10, "p": (i % 7) / 7, "meta_primero": int(i % 3 == 0)}
                 for i in range(200)]
        punto = informe.auc([f["p"] for f in filas], [f["meta_primero"] for f in filas])
        lo, hi = informe.bootstrap_grupos(
            filas, "g", lambda m: informe.auc([f["p"] for f in m], [f["meta_primero"] for f in m]),
            b=300)
        self.assertLessEqual(lo, punto)
        self.assertGreaterEqual(hi, punto)

    def test_un_solo_grupo_no_da_intervalo(self):
        filas = [{"g": 1, "x": 1.0}] * 20
        self.assertEqual(informe.bootstrap_grupos(filas, "g", lambda m: 1.0, b=50), (None, None))


class VeredictoTests(unittest.TestCase):
    def sol(self, **kw):
        base = {"n": 300, "a_tiempo_frac": 0.97, "auc": 0.62, "auc_ic_par": [0.55, 0.69],
                "auc_ic_dia": [0.54, 0.70], "auc_mitades": [0.6, 0.64],
                "media_aceptados_pct": 0.4, "media_todos_pct": 0.1,
                "dif_acept_rech_ic": [0.1, 0.9]}
        return {"brazos": {"SOL": {**base, **kw}}}

    def test_ayuda_solo_si_pasa_todo(self):
        self.assertEqual(informe.veredicto(self.sol(), {"delta_p95_ms": 100})[0], "AYUDA")
        for cambio in ({"n": 200}, {"auc_ic_dia": [0.49, 0.7]}, {"auc_mitades": [0.6, 0.48]},
                       {"media_aceptados_pct": 0.05}, {"a_tiempo_frac": 0.8}):
            self.assertEqual(informe.veredicto(self.sol(**cambio), {})[0], "INCONCLUSO", cambio)

    def test_entorpece(self):
        self.assertEqual(informe.veredicto(self.sol(), {"delta_p95_ms": 2500})[0], "ENTORPECE")
        self.assertEqual(informe.veredicto(self.sol(auc_ic_par=[0.3, 0.45]), {})[0], "ENTORPECE")
        self.assertEqual(informe.veredicto(self.sol(dif_acept_rech_ic=[-1, -0.1]), {})[0],
                         "ENTORPECE")

    def test_antes_de_tiempo_el_informe_esta_cegado(self):
        a = Almacen(":memory:")
        a.fijar_meta("inicio_rodaje_ms", 1)
        a.fijar_meta("inicio_medicion_ms", 1000)
        a.fijar_meta("huella_medicion", registro.huella())
        a.guardar_decision({"caso_id": 1, "brazo": "SOL", "modelo": "gpt-6-sol", "estado": "OK",
                            "accion": "ENTRAR", "p_meta": 0.93, "razon": "secreto",
                            "a_tiempo": 1})
        texto = informe.generar(a, 2000)
        self.assertIn("Cegado", texto)
        for prohibido in ("ENTRAR", "0.93", "secreto", "AUC"):
            self.assertNotIn(prohibido, texto)
        self.assertEqual(a.uno("SELECT COUNT(*) FROM eventos"), 0)
        informe.generar(a, 2000, desvelar=True)
        self.assertEqual(a.uno("SELECT tipo FROM eventos"), "DESVELADO_ANTES_DE_TIEMPO")

    def test_si_la_huella_cambio_no_hay_veredicto(self):
        a = Almacen(":memory:")
        a.fijar_meta("inicio_medicion_ms", 1000)
        a.fijar_meta("huella_medicion", "otra")
        texto = informe.generar(a, 1000 + registro.MEDICION_MS + 1)
        self.assertIn("Sin veredicto", texto)


class InterferenciaTests(unittest.TestCase):
    def test_las_muestras_del_reloj_en_julio_no_cuentan(self):
        a = Almacen(":memory:")
        inicio = 1_790_000_000_000
        a.fijar_meta("inicio_rodaje_ms", inicio)
        for i in range(40):
            a.guardar_salud({"ts_ms": inicio + i * 30_000, "modo": "RODAJE",
                             "edad_vela_ms": 30_000 + (i % 10) * 3_000})
        # el arranque con el reloj en julio: fecha anterior al rodaje y edad negativa
        a.guardar_salud({"ts_ms": inicio - 5_500_000_000, "modo": "RODAJE",
                         "edad_vela_ms": -5_509_371_260})
        # y una edad negativa dentro del rodaje, que tampoco puede existir
        a.guardar_salud({"ts_ms": inicio + 50 * 30_000, "modo": "RODAJE",
                         "edad_vela_ms": -1_000})
        r = informe.interferencia(a)["RODAJE"]
        self.assertEqual((r["muestras"], r["descartadas_imposibles"]), (40, 2))
        self.assertGreater(r["edad_vela_p95_ms"], 50_000)

    def test_una_muestra_real_muy_alta_si_cuenta(self):
        # SAC recien arrancado, todavia cargando velas: es real, no se descarta.
        a = Almacen(":memory:")
        a.fijar_meta("inicio_rodaje_ms", 1000)
        a.guardar_salud({"ts_ms": 2000, "modo": "RODAJE", "edad_vela_ms": 9_961_069})
        self.assertEqual(informe.interferencia(a)["RODAJE"]["descartadas_imposibles"], 0)


class RegistroTests(unittest.TestCase):
    def test_esquema_estricto_valido_para_structured_outputs(self):
        e = registro.ESQUEMA_DECISION
        self.assertFalse(e["additionalProperties"])
        self.assertEqual(set(e["required"]), set(e["properties"]))

    def test_la_huella_cambia_si_cambia_el_prompt_o_la_declaracion(self):
        h = registro.huella()
        with patch.object(registro, "prompt_decision", return_value="otro prompt"):
            self.assertNotEqual(registro.huella(), h)
        with patch.dict(registro.KRONOS, {"trayectorias": 64}):
            self.assertNotEqual(registro.huella(), h)
        self.assertEqual(registro.huella(), h)

    def test_la_declaracion_es_serializable(self):
        json.dumps(registro.declaracion())


if __name__ == "__main__":
    unittest.main()
