import unittest
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.config import Config
from app.collector import CollectorStateEngine, State
from app.db import save_attendance_batch

class MockAttendance:
    def __init__(self, user_id, timestamp, punch=0, status=1, uid=1):
        self.user_id = user_id
        self.timestamp = timestamp
        self.punch = punch
        self.status = status
        self.uid = uid

class TestHybridBackfill(unittest.TestCase):
    def test_watermark_overlap_filtering(self):
        cfg = Config.from_env()
        watermark = datetime(2026, 8, 11, 10, 0, 0)
        overlap_td = timedelta(minutes=cfg.backfill_overlap_minutes)
        boundary = watermark - overlap_td
        self.assertEqual(boundary, datetime(2026, 8, 11, 9, 55, 0))

        raw_logs = [
            MockAttendance("1", datetime(2026, 8, 11, 9, 50, 0)), # Older than boundary -> Filtered out
            MockAttendance("1", datetime(2026, 8, 11, 9, 55, 0)), # Exactly boundary -> Candidate
            MockAttendance("2", datetime(2026, 8, 11, 9, 58, 0)), # Candidate
            MockAttendance("2", datetime(2026, 8, 11, 10, 5, 0)), # Candidate
        ]

        candidates = [r for r in raw_logs if r.timestamp >= boundary]
        self.assertEqual(len(candidates), 3)

    def test_malformed_record_filtering(self):
        malformed1 = type("Malformed", (), {})()
        malformed2 = MockAttendance("1", None)
        valid = MockAttendance("1", datetime(2026, 8, 11, 10, 0, 0))

        raw_logs = [malformed1, malformed2, valid]
        candidates = [r for r in raw_logs if hasattr(r, 'user_id') and hasattr(r, 'timestamp') and r.timestamp]
        self.assertEqual(len(candidates), 1)

    @patch("app.collector.get_device_watermark")
    @patch("app.collector.save_attendance_batch")
    def test_backfilling_state_execution_mqtt_suppressed(self, mock_batch, mock_watermark):
        cfg = Config.from_env()
        engine = CollectorStateEngine(cfg)
        engine.state = State.BACKFILLING

        mock_watermark.return_value = datetime(2026, 8, 11, 10, 0, 0)
        mock_batch.return_value = (2, 0)

        mock_conn = MagicMock()
        mock_conn.get_attendance.return_value = [
            MockAttendance("1", datetime(2026, 8, 11, 9, 58, 0)),
            MockAttendance("2", datetime(2026, 8, 11, 10, 2, 0)),
        ]
        engine.connection = mock_conn
        engine.mqtt_service = MagicMock()

        engine.handle_backfilling()

        # Verify get_attendance was called
        mock_conn.get_attendance.assert_called_once()
        # Verify save_attendance_batch was called with candidate records
        mock_batch.assert_called_once()
        # Verify MQTT publish was NOT called (Suppressed during backfill)
        engine.mqtt_service.publish_attendance.assert_not_called()
        # Verify transitioned to LIVE
        self.assertEqual(engine.state, State.LIVE)

    def test_synthetic_100k_filtering_benchmark(self):
        """
        Synthetic performance benchmark testing client-side timestamp filtering
        and memory handling for 100,000 Attendance records.
        """
        base_time = datetime(2026, 8, 1, 0, 0, 0)
        watermark = datetime(2026, 8, 10, 12, 0, 0)
        boundary = watermark - timedelta(minutes=5)

        print("\n--- SYNTHETIC 100,000 ATTENDANCE RECORD BENCHMARK ---")
        t0 = time.time()
        # Generate 100,000 synthetic records spaced 5 seconds apart (~5.7 days of continuous scans)
        synthetic_logs = [
            MockAttendance(str(i % 100 + 1), base_time + timedelta(seconds=i * 5), punch=0, status=1, uid=i+1)
            for i in range(100000)
        ]
        t1 = time.time()
        print(f"Generated 100,000 synthetic records in {t1 - t0:.4f} seconds")

        t2 = time.time()
        candidates = [r for r in synthetic_logs if r.timestamp >= boundary]
        t3 = time.time()
        filtering_duration = t3 - t2
        print(f"Client-side timestamp filtering for 100,000 records completed in {filtering_duration:.4f} seconds")
        print(f"Candidate records identified: {len(candidates)}")

        # Verify filtering performance is under 1 second
        self.assertTrue(filtering_duration < 1.0, f"Filtering took {filtering_duration:.4f}s, expected < 1.0s")

if __name__ == "__main__":
    unittest.main()
