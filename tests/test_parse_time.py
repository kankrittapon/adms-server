import unittest
from datetime import datetime, time, timezone

from app.db import parse_time, determine_status


class TestParseTime(unittest.TestCase):
    """Regression tests for the parse_time time-of-day parsing contract."""

    def test_hhmm_valid(self):
        self.assertEqual(parse_time("08:00"), time(8, 0))
        self.assertEqual(parse_time("08:30"), time(8, 30))
        self.assertEqual(parse_time("23:59"), time(23, 59))

    def test_hhmmss_valid(self):
        """Production docker-compose default format must parse correctly."""
        self.assertEqual(parse_time("05:00:00"), time(5, 0, 0))
        self.assertEqual(parse_time("10:00:00"), time(10, 0, 0))
        self.assertEqual(parse_time("00:00:01"), time(0, 0, 1))

    def test_leading_zero_values(self):
        self.assertEqual(parse_time("09:05"), time(9, 5))
        self.assertEqual(parse_time("07:03:09"), time(7, 3, 9))

    def test_boundary_times(self):
        self.assertEqual(parse_time("00:00"), time(0, 0))
        self.assertEqual(parse_time("24:00") if False else parse_time("23:59:59"), time(23, 59, 59))

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            parse_time("not-a-time")
        with self.assertRaises(ValueError):
            parse_time("8")  # single component
        with self.assertRaises(ValueError):
            parse_time("08:00:00:00")  # four components
        with self.assertRaises(ValueError):
            parse_time("25:99")  # out of range

    def test_empty_and_none_raise(self):
        with self.assertRaises(ValueError):
            parse_time("")
        with self.assertRaises(ValueError):
            parse_time(None)  # type: ignore[arg-type]


class TestDetermineStatus(unittest.TestCase):
    """Status classification with production-format time windows."""

    def test_on_time_with_hhmmss_window(self):
        """Production window 05:00:00-10:00:00 (HH:MM:SS) classifies correctly."""
        scan = datetime(2026, 8, 12, 8, 47, 37, tzinfo=timezone.utc)
        self.assertEqual(
            determine_status(scan, "05:00:00", "10:00:00"),
            "ON_TIME",
        )

    def test_late_with_hhmmss_window(self):
        scan = datetime(2026, 8, 12, 13, 28, 4, tzinfo=timezone.utc)
        self.assertEqual(
            determine_status(scan, "05:00:00", "10:00:00"),
            "LATE",
        )

    def test_hhmm_window_still_works(self):
        """Existing HH:MM behavior remains compatible."""
        dt_ontime = datetime(2026, 8, 11, 8, 15, 0)
        self.assertEqual(determine_status(dt_ontime, "08:00", "08:30"), "ON_TIME")
        dt_late = datetime(2026, 8, 11, 9, 0, 0)
        self.assertEqual(determine_status(dt_late, "08:00", "08:30"), "LATE")

    def test_invalid_window_fails_safe_to_unknown(self):
        scan = datetime(2026, 8, 12, 8, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(determine_status(scan, "bad", "10:00:00"), "UNKNOWN")

    def test_production_historical_examples(self):
        """Real production attendance timestamps against production window."""
        window = ("05:00:00", "10:00:00")
        cases = [
            # (scan_time, expected)
            (datetime(2021, 3, 2, 20, 14, 58, tzinfo=timezone.utc), "LATE"),
            (datetime(2021, 3, 2, 20, 15, 1, tzinfo=timezone.utc), "LATE"),
            (datetime(2021, 3, 2, 20, 16, 40, tzinfo=timezone.utc), "LATE"),
            (datetime(2021, 3, 3, 0, 46, 3, tzinfo=timezone.utc), "LATE"),
            (datetime(2026, 8, 10, 12, 47, 39, tzinfo=timezone.utc), "LATE"),
            (datetime(2026, 8, 10, 13, 7, 27, tzinfo=timezone.utc), "LATE"),
            (datetime(2026, 8, 11, 8, 30, 54, tzinfo=timezone.utc), "ON_TIME"),
            (datetime(2026, 8, 12, 8, 47, 37, tzinfo=timezone.utc), "ON_TIME"),
            (datetime(2026, 8, 12, 13, 28, 4, tzinfo=timezone.utc), "LATE"),
            (datetime(2026, 8, 12, 13, 30, 47, tzinfo=timezone.utc), "LATE"),
        ]
        for scan, expected in cases:
            self.assertEqual(determine_status(scan, *window), expected, msg=f"scan={scan}")


if __name__ == "__main__":
    unittest.main()
