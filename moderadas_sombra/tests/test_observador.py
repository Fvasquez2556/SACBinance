"""El observador contra una base de prueba con el esquema de producción, con el reloj a mano."""
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from moderadas_sombra import core as K
from moderadas_sombra import informe
from moderadas_sombra import observador as OB
from moderadas_sombra import resumen as S

MIN = K.MIN
T0 = 1_790_000_040_000 // MIN * MIN          # una frontera de minuto
REPO = Path(__file__).resolve().parents[2]


def fuente_de_prueba(ruta, dias=3):
    db = sqlite3.connect(ruta)
    db.execute("CREATE TABLE klines (symbol TEXT, tf TEXT, open_time INTEGER, o REAL, h REAL, l REAL, c REAL, "
               "v REAL, PRIMARY KEY(symbol, tf, open_time))")
    db.execute("CREATE TABLE alertas_emitidas (id INTEGER PRIMARY KEY, ts_ms INTEGER, symbol TEXT, entry REAL, "
               "stop_loss REAL, tier TEXT, score INTEGER, display_state TEXT, senal_n INTEGER, tp_pct REAL, "
               "sl_pct REAL, telegram TEXT, episode_id INTEGER)")
    rng = random.Random(3)
    p = 100.0
    filas = []
    for k in range(-dias * 1440, 1440):
        o = p
        p *= 1 + rng.gauss(0, 0.001)
        filas.append(("XUSDT", "1m", T0 + k * MIN, o, max(o, p) * 1.0005, min(o, p) * 0.9995, p, 500.0))
    db.executemany("INSERT INTO klines VALUES (?,?,?,?,?,?,?,?)", filas)
    db.commit()
    return db


def alerta(db, aid, ts, tier="MODERADA", entry=100.0, stop=98.2):
    db.execute("INSERT INTO alertas_emitidas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (aid, ts, "XUSDT", entry, stop, tier, 75, "SUBIENDO", 1, 3.6, 1.8, "no_procede", None))
    db.commit()


class ObservadorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.fuente = Path(self.tmp.name) / "sac.db"
        self.sombra = Path(self.tmp.name) / "sombra.db"
        self.src = fuente_de_prueba(self.fuente)

    def tearDown(self):
        self.src.close()
        self.tmp.cleanup()

    def fila(self, aid):
        with sqlite3.connect(self.sombra) as db:
            db.row_factory = sqlite3.Row
            return db.execute("SELECT * FROM senales WHERE alerta_id=?", (aid,)).fetchone()

    def test_ciclo_completo_de_una_senal(self):
        alerta(self.src, 1, T0 - 5 * MIN)                      # anterior a la instalación
        OB.ciclo(self.fuente, self.sombra, stamp=T0)          # primer ciclo: solo fija la cola
        self.assertIsNone(self.fila(1))
        ts = T0 + 30 * MIN + 17_000
        alerta(self.src, 2, ts)
        alerta(self.src, 3, ts + 1000, tier="VIGILANCIA")      # otro nivel: no se mide
        r = OB.ciclo(self.fuente, self.sombra, stamp=ts + 95_000)
        self.assertEqual((r["vistas"], r["registradas"], r["errores"]), (2, 1, 0))
        f = self.fila(2)
        self.assertEqual((f["origen"], f["estado"], f["tier"]), ("PROSPECTIVO", "ABIERTO", "MODERADA"))
        self.assertIsNotNone(f["feat_json"])
        self.assertIsNone(self.fila(3))
        inicio = f["start_ms"]
        OB.ciclo(self.fuente, self.sombra, stamp=inicio + 62 * MIN)
        f = self.fila(2)
        ev = OB.descomprimir(f["eval_z"])
        self.assertEqual(f["estado"], "ABIERTO")
        self.assertIsNotNone(ev["ventanas"]["60"])
        self.assertIsNone(ev["ventanas"]["180"])
        self.assertEqual(f["next_check_ms"], inicio + 182 * MIN)
        self.assertIsNotNone(f["ctrl_z"])                      # su ventana ya había pasado
        OB.ciclo(self.fuente, self.sombra, stamp=inicio + 722 * MIN)
        f = self.fila(2)
        self.assertEqual(f["estado"], "COMPLETO")
        self.assertIsNotNone(OB.descomprimir(f["eval_z"])["ventanas"]["720"])

    def test_la_fuente_no_se_puede_tocar(self):
        fuente = OB.Fuente(self.fuente)
        for sql in ("DELETE FROM alertas_emitidas", "UPDATE klines SET o=1", "CREATE TABLE x(y)"):
            with self.assertRaises(sqlite3.DatabaseError):
                fuente.db.execute(sql)
        fuente.close()

    def test_misma_base_o_reglas_distintas_se_rechazan(self):
        with self.assertRaises(ValueError):
            OB.ciclo(self.fuente, self.fuente, stamp=T0)
        OB.ciclo(self.fuente, self.sombra, stamp=T0)
        with sqlite3.connect(self.sombra) as db:
            db.execute("UPDATE metadata SET value='otra' WHERE key='config'")
        with self.assertRaises(ValueError):
            OB.Almacen(self.sombra, T0)

    def test_informe_con_referencia(self):
        rng = random.Random(5)
        hist = []
        for i in range(400):
            p, o, h, l, c = 100.0, [], [], [], []
            for _ in range(K.SPAN):
                q = p * (1 + rng.gauss(0, 0.002))
                o.append(p), h.append(max(p, q) * 1.001), l.append(min(p, q) * 0.999), c.append(q)
                p = q
            hist.append({"id": i, "ts": T0 - (400 - i) * 13 * 3600_000, "symbol": f"S{i % 40}",
                         "tier": K.NIVELES[i % 2], "telegram": "no_procede", "R": 100.0, "stop": 98.2,
                         "estado": "COMPLETO", "o0_pct": 0.0, "alerta": {"score": 75, "senal_n": 1, "tp_pct": 3.6,
                                                                        "sl_pct": 1.8, "display_state": "SUBIENDO"},
                         "feat": None, "eval": K.evaluar(o, h, l, c, 100.0, 98.2), "ctrl": None})
        ref, completos = S.referencia(hist, "x")
        principal, _ = S.elegir_principal(ref, completos)
        ref["principal"] = {k: principal[k] for k in ("ventana_min", "variante", "nombre", "neto_por_senal",
                                                      "mitades", "positiva_en_ambas", "cumple_reglas",
                                                      "ic95_por_moneda")}
        ruta_ref = Path(self.tmp.name) / "referencia.json"
        import json
        ruta_ref.write_text(json.dumps(ref), encoding="utf-8")
        OB.ciclo(self.fuente, self.sombra, stamp=T0)
        texto = informe.generar(self.sombra, ruta_ref, ahora_ms=T0 + MIN)
        self.assertIn("MODERADA", texto)
        self.assertIn("todavía ninguna", texto)


if __name__ == "__main__":
    unittest.main()
