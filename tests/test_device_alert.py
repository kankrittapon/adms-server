"""Scanner offline alert: one alert after 30 min offline, one recovery."""

import unittest
from datetime import datetime, timedelta, timezone

from app.device_alert import decide, is_online

NOW = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)


class TestIsOnline(unittest.TestCase):
    def test_connected_and_fresh(self):
        self.assertTrue(is_online({"updated_at": NOW.isoformat(), "device_connected": True}, NOW))

    def test_stale_health_file_means_collector_down(self):
        old = (NOW - timedelta(minutes=10)).isoformat()
        self.assertFalse(is_online({"updated_at": old, "device_connected": True}, NOW))

    def test_missing_or_disconnected(self):
        self.assertFalse(is_online(None, NOW))
        self.assertFalse(is_online({"updated_at": NOW.isoformat(), "device_connected": False}, NOW))


class TestDecide(unittest.TestCase):
    def test_first_offline_run_only_records(self):
        state, msg = decide({}, False, NOW)
        self.assertEqual(state["offline_since"], NOW.isoformat())
        self.assertIsNone(msg)

    def test_alert_once_after_30_minutes(self):
        state = {"offline_since": (NOW - timedelta(minutes=31)).isoformat(), "alerted": False}
        new, msg = decide(state, False, NOW)
        self.assertTrue(new["alerted"])
        self.assertIn("ขาดการเชื่อมต่อ", msg)
        _, again = decide(new, False, NOW + timedelta(minutes=5))
        self.assertIsNone(again)

    def test_not_before_30_minutes(self):
        state = {"offline_since": (NOW - timedelta(minutes=10)).isoformat(), "alerted": False}
        self.assertIsNone(decide(state, False, NOW)[1])

    def test_recovery_message_only_after_an_alert(self):
        alerted = {"offline_since": (NOW - timedelta(hours=3)).isoformat(), "alerted": True}
        new, msg = decide(alerted, True, NOW)
        self.assertEqual(new, {})
        self.assertIn("กลับมาเชื่อมต่อ", msg)
        quiet = {"offline_since": (NOW - timedelta(minutes=5)).isoformat(), "alerted": False}
        self.assertIsNone(decide(quiet, True, NOW)[1])
