import unittest

from src.analysis.rupture_tracker import RuptureTracker
from src.analysis.ruptures import (
    RUPTURA_ALCISTA,
    RUPTURA_BAJISTA,
    clasificar,
)


class FakeDb:
    def __init__(self):
        self.rows = {}
        self.next_id = 1

    def get_rupturas_abiertas(self):
        return [dict(row) for row in self.rows.values() if not row.get("closed")]

    def ultima_ruptura_ts(self, symbol, direction):
        timestamps = [row["ts_open"] for row in self.rows.values()
                      if row["symbol"] == symbol and row["direction"] == direction]
        return max(timestamps) if timestamps else None

    def registrar_ruptura(self, row):
        event_id = self.next_id
        self.next_id += 1
        self.rows[event_id] = dict(row, id=event_id)
        return event_id

    def guardar_ruptura(self, event_id, fields):
        self.rows[event_id].update(fields)


class RuptureTrackerTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()
        self.tracker = RuptureTracker(self.db)

    def test_bullish_track_records_raw_and_directional_returns(self):
        event = self.tracker.abrir(
            "UPUSDT", RUPTURA_ALCISTA, 0, 100.0,
            {"display_state": "BREAKOUT_INCIPIENTE"}, "ruptura detectada",
        )
        updates = self.tracker.on_candle("UPUSDT", 15 * 60_000, 104.0, 98.0, 102.0)
        row = self.db.rows[event["id"]]

        self.assertEqual(row["max_up_pct"], 4.0)
        self.assertEqual(row["max_down_pct"], -2.0)
        self.assertEqual(row["mfe_direction_pct"], 4.0)
        self.assertEqual(row["mae_direction_pct"], -2.0)
        self.assertEqual(row["ret_15m_pct"], 2.0)
        self.assertEqual(updates[0]["horizontes"], [5, 15])

    def test_bearish_track_treats_fall_as_favorable(self):
        event = self.tracker.abrir(
            "DOWNUSDT", RUPTURA_BAJISTA, 0, 100.0,
            {"display_state": "CAYENDO"}, "caída activa",
        )
        self.tracker.on_candle("DOWNUSDT", 64 * 60_000, 102.0, 95.0, 96.0)
        row = self.db.rows[event["id"]]

        self.assertEqual(row["max_up_pct"], 2.0)
        self.assertEqual(row["max_down_pct"], -5.0)
        self.assertEqual(row["mfe_direction_pct"], 5.0)
        self.assertEqual(row["mae_direction_pct"], -2.0)
        self.assertEqual(row["ret_60m_pct"], 4.0)

    def test_classifier_keeps_bullish_and_bearish_routes_separate(self):
        bear = clasificar({
            "display_state": "CAYENDO",
            "impulso": {"caida_acelerando": True},
            "sr_levels": {},
        })
        bull = clasificar({
            "display_state": "SUBIENDO",
            "trend_up": True,
            "is_fakeout": False,
            "impulso": {"valid": True, "fase": "ACELERANDO"},
        })

        self.assertEqual(bear.direccion, RUPTURA_BAJISTA)
        self.assertEqual(bull.direccion, RUPTURA_ALCISTA)


if __name__ == "__main__":
    unittest.main()
