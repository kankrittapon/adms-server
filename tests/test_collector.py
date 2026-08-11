import unittest
import os
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.config import Config
from app.collector import CollectorStateEngine, State
from app.db import determine_status

class TestCollectorStateEngine(unittest.TestCase):
    def test_config_from_env(self):
        with patch.dict(os.environ, {
            "ZK_DEVICE_IP": "192.168.1.201",
            "ZK_DEVICE_PORT": "4370",
            "INITIAL_BACKOFF_SECONDS": "2.0",
            "MAX_BACKOFF_SECONDS": "60.0"
        }):
            cfg = Config.from_env()
            self.assertEqual(cfg.device_ip, "192.168.1.201")
            self.assertEqual(cfg.device_port, 4370)
            self.assertEqual(cfg.initial_backoff, 2.0)
            self.assertEqual(cfg.max_backoff, 60.0)

    def test_determine_status(self):
        dt_ontime = datetime(2026, 8, 11, 8, 15, 0)
        self.assertEqual(determine_status(dt_ontime, "08:00", "08:30"), "ON_TIME")

        dt_late = datetime(2026, 8, 11, 9, 0, 0)
        self.assertEqual(determine_status(dt_late, "08:00", "08:30"), "LATE")

    def test_backoff_calculation(self):
        cfg = Config.from_env()
        engine = CollectorStateEngine(cfg)

        engine.reconnect_attempt = 0
        delay0 = engine.compute_backoff_delay()
        self.assertTrue(1.5 <= delay0 <= 2.5)

        engine.reconnect_attempt = 5
        delay5 = engine.compute_backoff_delay()
        self.assertTrue(48.0 <= delay5 <= 60.0 * 1.2)

    def test_state_transitions(self):
        cfg = Config.from_env()
        engine = CollectorStateEngine(cfg)
        self.assertEqual(engine.state, State.STARTING)

        engine.transition_to(State.CONNECTING)
        self.assertEqual(engine.state, State.CONNECTING)

        engine.transition_to(State.BACKFILLING)
        self.assertEqual(engine.state, State.BACKFILLING)

        engine.transition_to(State.LIVE)
        self.assertEqual(engine.state, State.LIVE)

    def test_graceful_stop_signal(self):
        cfg = Config.from_env()
        engine = CollectorStateEngine(cfg)
        self.assertFalse(engine.stop_event.is_set())

        engine.stop()
        self.assertTrue(engine.stop_event.is_set())

if __name__ == "__main__":
    unittest.main()
