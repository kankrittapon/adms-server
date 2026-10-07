"""Terminal clock guard: a reset clock back-dates scans, so the collector
corrects drift beyond 60s and never lets a clock error break the loop."""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.collector import CLOCK_MAX_DRIFT_SECONDS, CollectorStateEngine
from app.timestamp_utils import BANGKOK_TZ


def _engine(device_time):
    eng = CollectorStateEngine.__new__(CollectorStateEngine)
    eng.cfg = SimpleNamespace()
    eng.connection = MagicMock()
    eng.connection.get_time.return_value = device_time
    eng.last_clock_check_at = eng.last_clock_drift_seconds = eng.last_clock_corrected_at = None
    return eng


class TestDeviceClock(unittest.TestCase):
    @patch("app.collector.log_sync_event")
    def test_reset_clock_is_corrected_and_verified(self, log):
        now = datetime.now(BANGKOK_TZ).replace(tzinfo=None)
        eng = _engine(None)
        eng.connection.get_time.side_effect = [now - timedelta(days=9, hours=18), now]
        eng.sync_device_clock()
        eng.connection.disable_device.assert_called_once()
        eng.connection.set_time.assert_called_once()
        eng.connection.refresh_data.assert_called_once()
        eng.connection.enable_device.assert_called_once()
        self.assertEqual(log.call_args.args[1], "DEVICE_CLOCK_CORRECTED")

    @patch("app.collector.log_sync_event")
    def test_correction_that_did_not_apply_is_reported(self, log):
        old = datetime.now(BANGKOK_TZ).replace(tzinfo=None) - timedelta(days=9)
        eng = _engine(old)
        eng.sync_device_clock()
        self.assertEqual(log.call_args.args[1], "DEVICE_CLOCK_CORRECTION_FAILED")
        self.assertIsNone(eng.last_clock_corrected_at)

    @patch("app.collector.log_sync_event")
    def test_small_drift_left_alone(self, log):
        eng = _engine(datetime.now(BANGKOK_TZ).replace(tzinfo=None) + timedelta(seconds=5))
        eng.sync_device_clock()
        eng.connection.set_time.assert_not_called()
        log.assert_not_called()

    def test_device_error_never_raises(self):
        eng = _engine(None)
        eng.connection.get_time.side_effect = OSError("timeout")
        eng.sync_device_clock()
        eng.connection.set_time.assert_not_called()


if __name__ == "__main__":
    unittest.main()
