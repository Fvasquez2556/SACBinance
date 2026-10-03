"""Casos construidos a mano: se sabe de antemano qué tiene que salir."""
import unittest

from moderadas_sombra import core as K
from moderadas_sombra import resumen as S

R = 100.0
PLANA = (100.0, 100.2, 99.9, 100.0)


def camino(n=720, **cambios):
    """n velas (o, h, l, c) planas; cambios = {minuto: (o, h, l, c)}."""
    v = [PLANA] * n
    for m, vela in cambios.items():
        v[int(m.lstrip("m"))] = vela
    return [list(x) for x in zip(*v)]


def ventana(o, h, l, c, W=720):
    return K.medir(o, h, l, c, R)["ventanas"][str(W)]


def op(o, h, l, c, entrada, meta, stop_tipo, W=720, stop=95.0):
    res = K.simular(o, h, l, c, R, stop)
    return res[str(W)][K.VARIANTES.index((entrada, meta, stop_tipo))]


class MedirTests(unittest.TestCase):
    def test_sube_directo_y_la_escalera(self):
        o, h, l, c = camino(m30=(100.0, 102.8, 100.0, 102.7))
        v = ventana(o, h, l, c)
        self.assertEqual(v["grupo"], "SUBE_DIRECTO")
        self.assertEqual(v["esc"][K.ESCALERA.index(2.67)], 30)
        self.assertIsNone(v["esc"][K.ESCALERA.index(3.0)])
        self.assertEqual(v["max"], 2.8)
        self.assertEqual(v["min"], -0.1)

    def test_baja_y_sube(self):
        o, h, l, c = camino(m10=(100.0, 100.0, 98.9, 99.0), m40=(99.0, 102.7, 99.0, 102.6))
        self.assertEqual(ventana(o, h, l, c)["grupo"], "BAJA_Y_SUBE")
        self.assertEqual(ventana(o, h, l, c)["min_antes"][1], -1.1)

    def test_caida_y_meta_en_la_misma_vela_cuenta_como_baja_primero(self):
        o, h, l, c = camino(m20=(100.0, 102.7, 98.9, 100.0))
        self.assertEqual(ventana(o, h, l, c)["grupo"], "BAJA_Y_SUBE")

    def test_cortas_laterales_y_caidas(self):
        self.assertEqual(ventana(*camino(m5=(100.0, 101.5, 100.0, 100.0)))["grupo"], "SE_QUEDA_CORTA")
        self.assertEqual(ventana(*camino(m5=(100.0, 100.5, 97.5, 98.0)))["grupo"], "CAE")
        self.assertEqual(ventana(*camino())["grupo"], "LATERAL")

    def test_retoques_solo_si_antes_subio_medio_por_ciento(self):
        # Base que no toca R ni arma. Sube +0,6 % y vuelve a R: 1. Otra vez: 2.
        # Una bajada a R sin subida previa de +0,5 % no cuenta.
        base = (100.2, 100.3, 100.1, 100.2)
        v = [base] * 720
        v[3] = (100.2, 100.6, 100.2, 100.5)     # arma
        v[6] = (100.3, 100.3, 99.95, 100.1)     # toca R -> 1
        v[9] = (100.2, 100.7, 100.2, 100.6)     # arma
        v[12] = (100.3, 100.3, 99.9, 100.1)     # toca R -> 2
        v[15] = (100.2, 100.4, 99.9, 100.2)     # toca R sin haber armado -> no cuenta
        o, h, l, c = [list(x) for x in zip(*v)]
        self.assertEqual(ventana(o, h, l, c)["retoques"], 2)
        self.assertEqual(ventana(*camino())["retoques"], 0)

    def test_ventana_corta_solo_ve_su_tramo(self):
        o, h, l, c = camino(m100=(100.0, 103.0, 100.0, 102.9))
        self.assertEqual(ventana(o, h, l, c, 60)["grupo"], "LATERAL")
        self.assertEqual(ventana(o, h, l, c, 180)["grupo"], "SUBE_DIRECTO")

    def test_ventana_incompleta_es_none(self):
        o, h, l, c = camino(n=100)
        self.assertIsNone(K.medir(o, h, l, c, R)["ventanas"]["180"])
        self.assertIsNotNone(K.medir(o, h, l, c, R)["ventanas"]["60"])


class SimularTests(unittest.TestCase):
    def test_entrada_en_R_cobra_la_meta(self):
        o, h, l, c = camino(m30=(100.0, 102.8, 100.0, 102.7))
        self.assertEqual(op(o, h, l, c, 0.0, 2.67, "SISTEMA"), ["TP", 30, 2.17])

    def test_limite_se_llena_y_no_cobra_en_su_vela(self):
        # Toca -1 % y en la MISMA vela llegaría a +2,67 % desde 99: no cuenta; cobra después.
        o, h, l, c = camino(m10=(100.0, 101.8, 98.9, 101.0), m20=(101.0, 101.7, 101.0, 101.6))
        self.assertEqual(op(o, h, l, c, 1.0, 2.67, "SIN_STOP"), ["TP", 10, 2.17])

    def test_limite_que_no_se_llena(self):
        o, h, l, c = camino()
        self.assertEqual(op(o, h, l, c, 0.5, 2.67, "SIN_STOP"), ["NE", None, 0.0])

    def test_meta_y_stop_en_la_misma_vela_es_stop(self):
        o, h, l, c = camino(m15=(100.0, 103.0, 94.0, 100.0))
        self.assertEqual(op(o, h, l, c, 0.0, 2.67, "SISTEMA")[0], "SL")

    def test_salto_bajo_el_stop_sale_en_la_apertura(self):
        o, h, l, c = camino(m15=(93.0, 93.5, 92.0, 93.0))
        cod, mins, neto = op(o, h, l, c, 0.0, 2.67, "SISTEMA")
        self.assertEqual((cod, mins), ("SL", 15))
        self.assertAlmostEqual(neto, -7.5)

    def test_plan_roto_si_la_compra_queda_bajo_el_stop(self):
        o, h, l, c = camino(m10=(100.0, 100.0, 98.9, 99.0))
        self.assertEqual(op(o, h, l, c, 1.0, 2.67, "SISTEMA", stop=99.5), ["PR", None, 0.0])

    def test_sin_stop_cierra_al_final_de_la_ventana(self):
        o, h, l, c = camino(m59=(100.0, 101.0, 100.0, 101.0))
        self.assertEqual(op(o, h, l, c, 0.0, 2.67, "SIN_STOP", W=60), ["TI", 59, 0.5])

    def test_stop_fijo_a_1_8_del_precio_de_compra(self):
        # Compra límite en 99 (R - 1 %): el stop fijo queda en 97,218, no en el del sistema.
        o, h, l, c = camino(m10=(100.0, 100.0, 98.9, 99.0), m30=(99.0, 99.0, 97.1, 97.5))
        self.assertEqual(op(o, h, l, c, 1.0, 2.67, "FIJO_1.8", stop=90.0), ["SL", 20, -2.3])
        self.assertEqual(op(o, h, l, c, 1.0, 2.67, "SISTEMA", stop=90.0)[0], "TI")
        # Sin tocar 97,218 y cobrando la meta desde 99: +2,67 % = 101,64
        o, h, l, c = camino(m10=(100.0, 100.0, 98.9, 99.0), m40=(99.5, 101.7, 99.4, 101.6))
        self.assertEqual(op(o, h, l, c, 1.0, 2.67, "FIJO_1.8"), ["TP", 30, 2.17])

    def test_stop_fijo_con_salto_sale_en_la_apertura(self):
        o, h, l, c = camino(m20=(97.0, 97.5, 96.5, 97.0))       # desde R: stop en 98,2; abre en 97
        cod, mins, neto = op(o, h, l, c, 0.0, 2.67, "FIJO_1.8")
        self.assertEqual((cod, mins), ("SL", 20))
        self.assertAlmostEqual(neto, -3.5)

    def test_ventana_abierta(self):
        o, h, l, c = camino(n=100)
        self.assertEqual(op(o, h, l, c, 0.0, 2.67, "SIN_STOP", W=180), ["AB", None, None])


class PrevioTests(unittest.TestCase):
    def series(self, ultimas15):
        T = [i * K.MIN for i in range(60)]
        O, H, L, C, V = [], [], [], [], []
        for k, (o, h, l, c) in enumerate(ultimas15):
            for m in range(15):
                O.append(o if m == 0 else c)
                C.append(c)
                H.append(h if m == 7 else max(o, c) if m == 0 else c)
                L.append(l if m == 8 else min(o, c) if m == 0 else c)
                V.append(10.0)
        return T, O, H, L, C, V

    def test_martillo_y_envolvente(self):
        T, O, H, L, C, V = self.series([(100, 100, 100, 100), (100, 100, 100, 100),
                                        (101, 101.2, 99.5, 100), (100, 100.6, 97, 100.5)])
        idx = {t: i for i, t in enumerate(T)}
        f = K.features(T, O, H, L, C, V, 60 * K.MIN + 5, idx.get)
        self.assertIn("MARTILLO", f["patrones"])
        self.assertEqual(f["vol5_vs_55"], 1.0)

    def test_sin_60_velas_no_hay_rasgos(self):
        T, O, H, L, C, V = self.series([(100, 100, 100, 100)] * 4)
        idx = {t: i for i, t in enumerate(T)}
        self.assertIsNone(K.features(T, O, H, L, C, V, 30 * K.MIN, idx.get))

    def test_control_determinista_y_en_su_franja(self):
        ts = 1_790_000_000_000
        a, b = K.inicio_control(7, ts), K.inicio_control(7, ts)
        self.assertEqual(a, b)
        self.assertTrue(ts - 36 * 3600_000 - K.MIN <= a <= ts - 12 * 3600_000)


class PatronesTests(unittest.TestCase):
    def test_los_empates_no_fabrican_un_quintil_bueno(self):
        # Una variable que vale siempre lo mismo no puede ordenar nada.
        rs = []
        for i in range(200):
            v = [PLANA] * 720
            if i % 2:
                v[5] = (100.0, 103.0, 100.0, 102.9)
            o, h, l, c = [list(x) for x in zip(*v)]
            rs.append({"ts": i, "feat": {"patrones": ["NINGUNO"]}, "alerta": {"score": 75},
                       "eval": K.evaluar(o, h, l, c, R, 95.0)})
        q = S.patrones(rs, 720)["senal"]["score"]["quintiles"]
        self.assertTrue(all(abs(t["tasa_pct"] - 50) <= 10 for t in q), q)


class RepeticionesTests(unittest.TestCase):
    def test_primera_del_movimiento_y_una_por_ventana(self):
        h = 3_600_000
        rs = [{"id": i, "symbol": "X", "tier": "MODERADA", "ts": t} for i, t in
              enumerate([0, 30 * 60_000, 2 * h, 14 * h + 1, 14 * h + 2 * 60_000])]
        S.marcar_repeticiones(rs)
        self.assertEqual([r["primera"] for r in rs], [True, False, False, True, False])
        self.assertEqual([r["una_por"][60] for r in rs], [True, False, True, True, False])
        self.assertEqual([r["una_por"][720] for r in rs], [True, False, False, True, False])

    def test_neto_por_senal_cuenta_las_que_no_entran_como_cero(self):
        base = {"symbol": "X", "tier": "MODERADA", "ts": 0, "primera": True}
        o, h, l, c = camino(m30=(100.0, 102.8, 100.0, 102.7))
        con = dict(base, id=1, eval=K.evaluar(o, h, l, c, R, 95.0))
        sin = dict(base, id=2, eval=K.evaluar(*camino(), R, 95.0))
        r = S.operaciones([con, sin], 720, (0.5, 2.67, "SIN_STOP"))
        self.assertEqual((r["entradas"], r["n"]), (0, 2))
        r = S.operaciones([con, sin], 720, (0.0, 2.67, "SIN_STOP"))
        self.assertEqual(r["entradas"], 2)
        self.assertAlmostEqual(r["neto_por_senal"], (2.17 + (-0.5)) / 2)


if __name__ == "__main__":
    unittest.main()
