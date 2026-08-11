import os
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from app.healthcheck import evaluate_health, STALE_THRESHOLDS
from app.config import Config
from app.collector import CollectorStateEngine, State, HEALTH_FILE_PATH

class TestHealthcheck(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.health_file = os.path.join(self.temp_dir.name, "collector_health.json")

    def tearDown(self):
        self.temp_dir.cleanup()
        if os.path.exists(HEALTH_FILE_PATH):
            try:
                os.remove(HEALTH_FILE_PATH)
            except Exception:
                pass

    def write_json(self, payload):
        with open(self.health_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_missing_health_file(self):
        res = evaluate_health(os.path.join(self.temp_dir.name, "non_existent.json"))
        self.assertEqual(res, 1)

    def test_malformed_json(self):
        with open(self.health_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json ")
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 1)

    def test_unsupported_schema_version(self):
        self.write_json({
            "schema_version": "2.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "state": "LIVE",
            "loop_alive": True
        })
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 1)

    def test_loop_alive_false(self):
        self.write_json({
            "schema_version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "state": "LIVE",
            "loop_alive": False
        })
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 1)

    def test_valid_live_health(self):
        self.write_json({
            "schema_version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "state": "LIVE",
            "loop_alive": True,
            "device_connected": True,
            "db_status": "HEALTHY",
            "mqtt_status": "HEALTHY"
        })
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 0)

    def test_stale_live_health(self):
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=150)
        self.write_json({
            "schema_version": "1.0",
            "updated_at": stale_time.isoformat(),
            "state": "LIVE",
            "loop_alive": True
        })
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 1)

    def test_valid_degraded_health(self):
        self.write_json({
            "schema_version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "state": "DEGRADED",
            "loop_alive": True,
            "device_connected": True,
            "db_status": "HEALTHY",
            "mqtt_status": "DEGRADED"
        })
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 0)

    def test_valid_backoff_health(self):
        self.write_json({
            "schema_version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "state": "BACKOFF",
            "loop_alive": True,
            "device_connected": False,
            "db_status": "HEALTHY",
            "mqtt_status": "UNKNOWN"
        })
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 0)

    def test_stale_backoff_health(self):
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=130)
        self.write_json({
            "schema_version": "1.0",
            "updated_at": stale_time.isoformat(),
            "state": "BACKOFF",
            "loop_alive": True
        })
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 1)

    def test_valid_backfilling_health(self):
        # 300 seconds old -> Valid for BACKFILLING (threshold 600s)
        backfill_time = datetime.now(timezone.utc) - timedelta(seconds=300)
        self.write_json({
            "schema_version": "1.0",
            "updated_at": backfill_time.isoformat(),
            "state": "BACKFILLING",
            "loop_alive": True
        })
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 0)

    def test_stale_backfilling_health(self):
        # 650 seconds old -> Stale for BACKFILLING (threshold 600s)
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=650)
        self.write_json({
            "schema_version": "1.0",
            "updated_at": stale_time.isoformat(),
            "state": "BACKFILLING",
            "loop_alive": True
        })
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 1)

    def test_terminal_stopped_state(self):
        self.write_json({
            "schema_version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "state": "STOPPED",
            "loop_alive": False
        })
        res = evaluate_health(self.health_file)
        self.assertEqual(res, 1)

    def test_collector_atomic_write_and_zero_secrets(self):
        cfg = Config.from_env()
        engine = CollectorStateEngine(cfg)
        engine.transition_to(State.LIVE)

        self.assertTrue(os.path.exists(HEALTH_FILE_PATH))
        with open(HEALTH_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["state"], "LIVE")
        self.assertEqual(data["schema_version"], "1.0")

        # Verify zero secrets or sensitive keys written
        self.assertNotIn("device_password", data)
        self.assertNotIn("db_password", data)
        self.assertNotIn("password", str(data).lower())
        self.assertNotIn("user_id", data)

        res = evaluate_health(HEALTH_FILE_PATH)
        self.assertEqual(res, 0)

if __name__ == "__main__":
    unittest.main()
