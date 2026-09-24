"""Evaluador comun de recorridos. Fase 2: mide en sombra, no sustituye a nadie."""
import json
import random
import sqlite3
import unittest
from unittest.mock import patch

from src.config.settings import get_settings
from src.episodios import EPISODIOS_SCHEMA, RegistroEpisodios
from src.evaluacion import (
    EVALUACION_SCHEMA,
    AlmacenRecorridos,
    Estado,
    Plan,
    Vela,
    avanzar,
    cerrar_por_reloj,
    cobertura,
    evaluar,
    resultado_politica,
)
from src.evaluacion.adaptadores import SeguimientoStreaming, replay
from src.persistence.db import SCHEMA_VERSION, Database

M = 60_000
INICIO = 1_700_000_000_000


def plan(entrada=100.0, objetivo=106.0, stop=97.0, horas=12):
    return Plan(entrada=entrada, objetivo=objetivo, stop=stop,
                inicio_ms=INICIO, horizonte_ms=horas * 3600_000)


def velas(*filas, desde=0):
    """(o, h, l, c) por minuto, empezando en INICIO + desde."""
    return [Vela(INICIO + (desde + i) * M, *f) for i, f in enumerate(filas)]


class ReglaTests(unittest.TestCase):
    def test_a_candle_outside_the_window_never_counts(self):
        p = plan(horas=1)
        antes = Vela(INICIO - M, 100, 110, 90, 100)
        despues = Vela(INICIO + 60 * M, 100, 110, 90, 100)
        # La ultima vela del horizonte es la que cierra justo en el limite.
        dentro = Vela(INICIO + 59 * M, 100, 101, 99, 100)
        e = evaluar(p, [antes, dentro, despues])
        self.assertEqual(e.n_velas, 1)
        self.assertIsNone(e.desenlace)

    def test_the_same_candle_twice_changes_nothing(self):
        p = plan()
        v = velas((100, 103, 99, 102))
        una = evaluar(p, v)
        dos = evaluar(p, v + v + v)
        self.assertEqual(una.como_dict(), dos.como_dict())

    def test_a_stop_and_a_target_in_one_minute_is_a_stop_and_is_flagged(self):
        p = plan()
        e = evaluar(p, velas((100, 107, 96, 100)))
        self.assertEqual(e.desenlace, 'STOP')
        self.assertTrue(e.ambiguo)
        self.assertIsNotNone(e.ms_objetivo)   # el recorrido sí lo registra

    def test_a_rise_after_the_stop_does_not_rewrite_the_outcome(self):
        p = plan()
        e = evaluar(p, velas((100, 101, 96, 97), (97, 112, 97, 111)))
        self.assertEqual(e.desenlace, 'STOP')
        self.assertEqual(e.ms_desenlace, 0)
        self.assertAlmostEqual(e.mfe_pct, 12.0, places=6)   # el camino sigue vivo
        self.assertEqual(resultado_politica(p, e, coste_pct=0.5), -3.5)

    def test_a_gap_below_the_stop_fills_at_the_open_not_at_the_level(self):
        p = plan()
        e = evaluar(p, velas((94, 95, 93, 94)))
        self.assertEqual(e.desenlace, 'STOP')
        self.assertTrue(e.salto)
        self.assertEqual(e.precio_stop, 94)
        self.assertEqual(resultado_politica(p, e), -6.0)

    def test_an_open_window_has_no_outcome_and_no_result(self):
        p = plan()
        e = evaluar(p, velas((100, 101, 99, 100)), ahora_ms=INICIO + 3600_000)
        self.assertIsNone(e.desenlace)
        self.assertIsNone(resultado_politica(p, e))

    def test_the_clock_expires_it_even_if_no_candle_arrives(self):
        p = plan(horas=1)
        e = evaluar(p, velas((100, 101, 99, 100.5)), ahora_ms=INICIO + 3600_000)
        self.assertEqual(e.desenlace, 'VENCIDO')
        self.assertEqual(resultado_politica(p, e, coste_pct=0.5), 0.0)

    def test_coverage_says_how_much_of_the_window_was_actually_seen(self):
        p = plan(horas=1)
        e = evaluar(p, velas(*[(100, 101, 99, 100)] * 30))
        self.assertEqual(cobertura(p, e, INICIO + 3600_000), 0.5)
        self.assertEqual(cobertura(p, Estado(), INICIO + 3600_000), 0.0)

    def test_milestones_and_horizons_are_recorded_apart_from_the_outcome(self):
        p = plan(objetivo=110.0)
        e = evaluar(p, velas((100, 103.5, 100, 103), (103, 104.5, 102, 104)))
        self.assertEqual(e.hitos['3.2'], 0)
        self.assertEqual(e.hitos['4.2'], M)
        self.assertNotIn('5', e.hitos)
        self.assertEqual(e.horizontes['15']['n'], 2)
        self.assertAlmostEqual(e.horizontes['15']['mfe'], 4.5, places=6)
        self.assertIsNone(e.desenlace)


class EquivalenciaTests(unittest.TestCase):
    """Replay y streaming no pueden divergir: comparten la funcion."""

    def secuencia(self, n=240, semilla=7):
        rng = random.Random(semilla)
        precio, filas = 100.0, []
        for _ in range(n):
            o = precio
            c = max(1.0, o * (1 + rng.gauss(0, 0.004)))
            h = max(o, c) * (1 + abs(rng.gauss(0, 0.002)))
            l = min(o, c) * (1 - abs(rng.gauss(0, 0.002)))
            filas.append((o, h, l, c))
            precio = c
        return velas(*filas)

    def test_streaming_and_replay_agree_candle_by_candle(self):
        p = plan()
        v = self.secuencia()
        s = SeguimientoStreaming(p)
        for vela in v:
            s.on_vela(vela)
        self.assertEqual(s.estado.como_dict(), replay(p, v).como_dict())

    def test_a_restart_in_the_middle_does_not_change_the_result(self):
        p = plan()
        v = self.secuencia()
        s = SeguimientoStreaming(p)
        for vela in v[:97]:
            s.on_vela(vela)
        guardado = json.loads(json.dumps(s.como_dict()))     # como iria a la DB
        reanudado = SeguimientoStreaming.desde_dict(p, guardado)
        for vela in v[97:]:
            reanudado.on_vela(vela)
        self.assertEqual(reanudado.estado.como_dict(), replay(p, v).como_dict())

    def test_repeated_and_overlapping_deliveries_do_not_double_count(self):
        p = plan()
        v = self.secuencia()
        desordenado = v[:50] + v[30:80] + v[60:]
        self.assertEqual(replay(p, desordenado).como_dict(), replay(p, v).como_dict())


class AlmacenTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript(EPISODIOS_SCHEMA)
        self.conn.executescript(EVALUACION_SCHEMA)
        self.conn.executescript("""CREATE TABLE klines (symbol TEXT, tf TEXT,
            open_time INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
            PRIMARY KEY (symbol, tf, open_time));
            CREATE TABLE notificacion_planes (alerta_id INTEGER PRIMARY KEY,
            symbol TEXT, estado TEXT);""")
        self.reg = RegistroEpisodios(self.conn)
        self.almacen = AlmacenRecorridos(self.conn, coste_pct=0.5)

    def tearDown(self):
        self.conn.close()

    def sembrar(self, filas, desde=0):
        self.conn.executemany(
            "INSERT OR REPLACE INTO klines VALUES (?,?,?,?,?,?,?,?)",
            [('TESTUSDT', '1m', INICIO + (desde + i) * M, *f, 1)
             for i, f in enumerate(filas)])

    def alta(self, alerta_id=1, ts=INICIO):
        return self.reg.registrar(
            symbol='TESTUSDT', ts_ms=ts,
            tl={'entry': 100.0, 'take_profit': 106.0, 'stop_loss': 97.0,
                'tf': '5m', 'sl_basis': 'soporte estructural'},
            alerta_id=alerta_id, horizonte_ms=3600_000)

    def test_a_plan_is_evaluated_from_the_stored_candles(self):
        ident = self.alta()
        self.sembrar([(100, 101, 99, 100), (100, 107, 100, 106)])
        self.almacen.evaluar_pendientes(INICIO + 3600_000)
        fila = self.almacen.recorrido(ident['plan_id'])
        self.assertEqual(fila['desenlace'], 'OBJETIVO')
        self.assertEqual(fila['resultado_pct'], 5.5)
        self.assertEqual(fila['n_velas'], 2)
        self.assertEqual(fila['completa'], 1)

    def test_a_second_pass_resumes_instead_of_starting_over(self):
        ident = self.alta()
        self.sembrar([(100, 101, 99, 100)])
        self.almacen.evaluar_pendientes(INICIO + 10 * M)
        self.sembrar([(100, 102, 99, 101)], desde=1)
        self.almacen.evaluar_pendientes(INICIO + 20 * M)
        fila = self.almacen.recorrido(ident['plan_id'])
        self.assertEqual(fila['n_velas'], 2)
        self.assertIsNone(fila['desenlace'])
        # Y una pasada sin velas nuevas no altera nada.
        antes = dict(fila)
        self.almacen.evaluar_pendientes(INICIO + 21 * M)
        despues = self.almacen.recorrido(ident['plan_id'])
        self.assertEqual(antes['n_velas'], despues['n_velas'])
        self.assertEqual(antes['mfe_pct'], despues['mfe_pct'])

    def test_a_finished_plan_is_not_evaluated_again(self):
        self.alta()
        self.sembrar([(100, 101, 99, 100)])
        self.almacen.evaluar_pendientes(INICIO + 3600_000)
        self.assertEqual(self.almacen.evaluar_pendientes(INICIO + 2 * 3600_000)['evaluados'], 0)

    def test_horizons_are_stored_apart_from_the_outcome(self):
        ident = self.alta()
        self.sembrar([(100, 103, 99, 102)] + [(102, 108, 102, 107)] * 2, desde=0)
        self.almacen.evaluar_pendientes(INICIO + 3600_000)
        filas = self.almacen.filas(
            "SELECT horizonte_min, mfe_pct, n_velas FROM plan_horizontes WHERE plan_id = ?",
            (ident['plan_id'],))
        self.assertEqual({f['horizonte_min'] for f in filas}, {15, 30, 60, 120, 240, 360, 480})
        self.assertTrue(all(f['n_velas'] == 3 for f in filas))

    def test_no_plan_starves_when_there_are_more_than_one_pass_allows(self):
        # Con 192 planes vivos y 60 por pasada, ordenar por fecha del plan
        # dejaba a los mas nuevos sin evaluar hasta 12 h despues.
        self.almacen.max_por_pasada = 2
        for i in (1, 2, 3):
            self.alta(alerta_id=i, ts=INICIO + i * M)
        self.sembrar([(100, 101, 99, 100)] * 5)
        self.almacen.evaluar_pendientes(INICIO + 10 * M)
        self.almacen.evaluar_pendientes(INICIO + 11 * M)
        evaluados = self.almacen.filas("SELECT plan_id FROM plan_recorrido")
        self.assertEqual(len(evaluados), 3)

    def test_the_shadow_comparison_reports_agreement_and_differences(self):
        ident = self.alta()
        self.conn.execute("INSERT INTO notificacion_planes VALUES (1,'TESTUSDT','TP')")
        self.sembrar([(100, 107, 100, 106)])
        self.almacen.evaluar_pendientes(INICIO + 3600_000)
        comp = self.almacen.comparar_con_notificaciones()
        self.assertEqual((comp['total'], comp['coinciden']), (1, 1))
        self.assertEqual(comp['discrepancias'], [])
        self.conn.execute("UPDATE notificacion_planes SET estado='SL' WHERE alerta_id=1")
        self.assertEqual(self.almacen.comparar_con_notificaciones()['coinciden'], 0)
        self.assertEqual(ident['ordinal'], 1)


class EsquemaTests(unittest.TestCase):
    def test_the_migration_adds_the_tables_without_touching_the_rest(self):
        ajustes = get_settings().model_copy(update={'db_path': ':memory:'})
        with patch('src.persistence.db.get_settings', return_value=ajustes):
            db = Database()
        self.assertGreaterEqual(SCHEMA_VERSION, 17)  # la v17 trajo estas tablas
        tablas = {r[0] for r in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'plan_recorrido', 'plan_horizontes'} <= tablas)
        self.assertIsInstance(db.almacen_recorridos(), AlmacenRecorridos)
        db._conn.close()




class CosteCongeladoTests(AlmacenTests):
    """
    El coste que se descuenta tiene que ser el que el PLAN congelo.

    `planes.coste_pct` se guarda con el plan justamente para esto, pero el
    evaluador descontaba `self.coste_pct`, que viene de la configuracion de
    hoy. Cambiar el ajuste reescribia el resultado neto de toda ventana
    todavia abierta: el mismo plan, medido con un coste que no existia cuando
    se creo. Un plan es inmutable o no lo es.
    """

    def alta_con_coste(self, coste, alerta_id=1):
        return self.reg.registrar(
            symbol='TESTUSDT', ts_ms=INICIO,
            tl={'entry': 100.0, 'take_profit': 105.0, 'stop_loss': 97.0,
                'tf': '5m'},
            alerta_id=alerta_id, horizonte_ms=3600_000, coste_pct=coste)

    def test_the_result_uses_the_cost_the_plan_froze(self):
        ident = self.alta_con_coste(0.5)
        self.sembrar([(100, 101, 99, 100), (100, 106, 100, 105)])
        self.almacen.evaluar_pendientes(INICIO + 3600_000)
        self.assertEqual(
            self.almacen.recorrido(ident['plan_id'])['resultado_pct'], 4.5)

    def test_changing_the_global_cost_does_not_rewrite_an_open_plan(self):
        ident = self.alta_con_coste(0.5)
        self.sembrar([(100, 101, 99, 100)])
        self.almacen.evaluar_pendientes(INICIO + 10 * M)      # ventana abierta

        # Cambia la configuracion y se reanuda: el plan sigue siendo el mismo.
        caro = AlmacenRecorridos(self.conn, coste_pct=0.8)
        self.sembrar([(100, 106, 100, 105)], desde=1)
        caro.evaluar_pendientes(INICIO + 3600_000)

        fila = caro.recorrido(ident['plan_id'])
        self.assertEqual(fila['desenlace'], 'OBJETIVO')
        self.assertEqual(fila['resultado_pct'], 4.5)   # no 4.2

    def test_a_plan_without_its_own_cost_falls_back_to_the_global_one(self):
        # Los planes anteriores a este campo no lo traen. Caen al coste global,
        # y eso se ve porque la fila no tiene el valor, no porque se elija en
        # silencio.
        ident = self.alta_con_coste(None)
        self.sembrar([(100, 101, 99, 100), (100, 106, 100, 105)])
        self.almacen.evaluar_pendientes(INICIO + 3600_000)
        self.assertEqual(
            self.almacen.recorrido(ident['plan_id'])['resultado_pct'], 4.5)
        self.assertIsNone(self.conn.execute(
            'SELECT coste_pct FROM planes WHERE plan_id = ?',
            (ident['plan_id'],)).fetchone()[0])

if __name__ == '__main__':
    unittest.main()
