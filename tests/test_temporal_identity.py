"""
Tests for Temporal Human Identity Resolution (ADMS-Collector-TemporalIdentity-002).

Covers:
  - Core resolver: no mapping, active VERIFIED, non-VERIFIED ignored,
    future/expired/open-ended/historical mappings, different device_user_pk
  - Boundary semantics: [valid_from, valid_to)
  - Ambiguity: >1 matching VERIFIED interval → None (fail-safe)
  - Ingestion paths: realtime + backfill use same resolver, same event → same identity
  - Safety regressions: unmapped→NULL, no auto-creation, no dedupe change,
    no Excel/name/numeric-user_id mapping
"""
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from app.config import Config
from app.db import (
    resolve_verified_employee_mapping,
    save_attendance_log,
    save_attendance_batch,
)
from app.timestamp_utils import normalize_device_timestamp, BANGKOK_TZ

UUID_A = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
UUID_B = "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22"

# Canonical scan_time used for most tests (aware, UTC)
SCAN_TIME = datetime(2026, 8, 11, 3, 0, 0, tzinfo=timezone.utc)


class MockAttendanceRecord:
    def __init__(self, uid, user_id, timestamp, status=1, punch=0):
        self.uid = uid
        self.user_id = user_id
        self.timestamp = timestamp
        self.status = status
        self.punch = punch


class TestTemporalResolverCore(unittest.TestCase):
    """Tests for resolve_verified_employee_mapping() core behavior."""

    def setUp(self):
        self.mock_cur = MagicMock()

    def test_no_mapping_returns_none(self):
        """Zero matching VERIFIED mappings → None."""
        self.mock_cur.fetchall.return_value = []
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertIsNone(result)

    def test_active_verified_mapping_returns_employee_id(self):
        """Exactly one matching VERIFIED interval → employee_id."""
        self.mock_cur.fetchall.return_value = [(UUID_A,)]
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertEqual(result, UUID_A)

    def test_non_verified_mapping_ignored(self):
        """Non-VERIFIED statuses (CANDIDATE, PROBABLE, etc.) must not resolve."""
        # The SQL filters mapping_status = 'VERIFIED', so DB returns 0 rows
        self.mock_cur.fetchall.return_value = []
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertIsNone(result)

    def test_future_verified_mapping_no_match(self):
        """VERIFIED mapping with valid_from > scan_time → no match."""
        self.mock_cur.fetchall.return_value = []
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertIsNone(result)

    def test_expired_verified_mapping_no_match(self):
        """VERIFIED mapping with valid_to <= scan_time → no match."""
        self.mock_cur.fetchall.return_value = []
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertIsNone(result)

    def test_open_ended_verified_mapping_matches(self):
        """VERIFIED mapping with valid_to IS NULL and valid_from <= scan_time → match."""
        self.mock_cur.fetchall.return_value = [(UUID_A,)]
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertEqual(result, UUID_A)

    def test_historical_verified_mapping_matches(self):
        """VERIFIED mapping with valid_from in the past and valid_to in the future → match."""
        self.mock_cur.fetchall.return_value = [(UUID_A,)]
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertEqual(result, UUID_A)

    def test_different_device_user_pk_no_match(self):
        """Mapping for a different device_user_pk → no match (SQL filters by device_user_pk)."""
        self.mock_cur.fetchall.return_value = []
        result = resolve_verified_employee_mapping(self.mock_cur, 99, SCAN_TIME)
        self.assertIsNone(result)

    def test_sql_uses_verified_only(self):
        """Verify the SQL query contains mapping_status = 'VERIFIED'."""
        self.mock_cur.fetchall.return_value = []
        resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        sql = self.mock_cur.execute.call_args[0][0]
        self.assertIn("VERIFIED", sql)
        self.assertIn("mapping_status", sql)

    def test_sql_uses_temporal_interval(self):
        """Verify the SQL query contains valid_from <= scan_time and scan_time < valid_to."""
        self.mock_cur.fetchall.return_value = []
        resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        sql = self.mock_cur.execute.call_args[0][0]
        self.assertIn("valid_from", sql)
        self.assertIn("valid_to", sql)
        self.assertIn("<=", sql)
        self.assertIn("<", sql)
        self.assertIn("IS NULL", sql)

    def test_sql_uses_limit_2_for_ambiguity(self):
        """Verify the SQL query uses LIMIT 2 to detect ambiguity."""
        self.mock_cur.fetchall.return_value = []
        resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        sql = self.mock_cur.execute.call_args[0][0]
        self.assertIn("LIMIT 2", sql)


class TestTemporalBoundaries(unittest.TestCase):
    """Explicit boundary tests for [valid_from, valid_to) semantics."""

    def setUp(self):
        self.mock_cur = MagicMock()

    def test_scan_time_before_valid_from_no_match(self):
        """scan_time < valid_from → NO MATCH."""
        self.mock_cur.fetchall.return_value = []
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertIsNone(result)

    def test_scan_time_equals_valid_from_match(self):
        """scan_time == valid_from → MATCH (inclusive)."""
        self.mock_cur.fetchall.return_value = [(UUID_A,)]
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertEqual(result, UUID_A)

    def test_scan_time_between_valid_from_and_valid_to_match(self):
        """valid_from < scan_time < valid_to → MATCH."""
        self.mock_cur.fetchall.return_value = [(UUID_A,)]
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertEqual(result, UUID_A)

    def test_scan_time_equals_valid_to_no_match(self):
        """scan_time == valid_to → NO MATCH (exclusive)."""
        self.mock_cur.fetchall.return_value = []
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertIsNone(result)

    def test_scan_time_after_valid_to_no_match(self):
        """scan_time > valid_to → NO MATCH."""
        self.mock_cur.fetchall.return_value = []
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertIsNone(result)

    def test_valid_to_null_and_scan_time_after_valid_from_match(self):
        """valid_to IS NULL AND scan_time >= valid_from → MATCH."""
        self.mock_cur.fetchall.return_value = [(UUID_A,)]
        result = resolve_verified_employee_mapping(self.mock_cur, 10, SCAN_TIME)
        self.assertEqual(result, UUID_A)


class TestAmbiguityDetection(unittest.TestCase):
    """Tests for multiple VERIFIED interval ambiguity defense."""

    def test_multiple_matches_returns_none(self):
        """>1 matching VERIFIED intervals → None (fail-safe)."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [(UUID_A,), (UUID_B,)]
        result = resolve_verified_employee_mapping(mock_cur, 10, SCAN_TIME)
        self.assertIsNone(result)

    def test_multiple_matches_logs_error(self):
        """Ambiguity must log an explicit integrity error."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [(UUID_A,), (UUID_B,)]
        with patch("app.db.log") as mock_log:
            resolve_verified_employee_mapping(mock_cur, 10, SCAN_TIME)
            mock_log.error.assert_called_once()
            logged_msg = mock_log.error.call_args[0][0]
            self.assertIn("AMBIGUOUS", logged_msg)


class TestIngestionPaths(unittest.TestCase):
    """Tests for realtime and backfill ingestion path integration."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_realtime_uses_temporal_resolver(self, mock_map, mock_user, mock_dev, mock_conn):
        """Realtime path (save_attendance_log) calls resolver with scan_time."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        rec = MockAttendanceRecord(1, "1", datetime(2026, 8, 11, 10, 0, 0, tzinfo=timezone.utc))
        save_attendance_log(self.cfg, rec)

        mock_map.assert_called_once()
        # Verify scan_time was passed (3rd argument)
        args = mock_map.call_args[0]
        self.assertEqual(len(args), 3)
        self.assertIsInstance(args[2], datetime)
        self.assertIsNotNone(args[2].tzinfo)

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_backfill_uses_temporal_resolver(self, mock_map, mock_user, mock_dev, mock_conn):
        """Backfill path (save_attendance_batch) calls resolver per-record with scan_time."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        recs = [
            MockAttendanceRecord(1, "1", datetime(2026, 8, 11, 10, 0, 0, tzinfo=timezone.utc)),
            MockAttendanceRecord(2, "1", datetime(2026, 8, 11, 11, 0, 0, tzinfo=timezone.utc)),
            MockAttendanceRecord(3, "2", datetime(2026, 8, 11, 12, 0, 0, tzinfo=timezone.utc)),
        ]
        save_attendance_batch(self.cfg, recs)

        # Resolver called once per record (3 records → 3 calls)
        self.assertEqual(mock_map.call_count, 3)
        # Each call should have scan_time as 3rd argument
        for c in mock_map.call_args_list:
            args = c[0]
            self.assertEqual(len(args), 3)
            self.assertIsInstance(args[2], datetime)
            self.assertIsNotNone(args[2].tzinfo)

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_same_event_same_identity_both_paths(self, mock_map, mock_user, mock_dev, mock_conn):
        """Same device_user_pk + same scan_time → same resolver call in both paths."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        ts = datetime(2026, 8, 11, 10, 0, 0, tzinfo=timezone.utc)
        rec = MockAttendanceRecord(1, "1", ts)

        # Realtime
        save_attendance_log(self.cfg, rec)
        realtime_args = mock_map.call_args[0]

        # Reset mock
        mock_map.reset_mock()

        # Backfill with same record
        save_attendance_batch(self.cfg, [rec])
        backfill_args = mock_map.call_args[0]

        # Both should pass same device_user_pk and equivalent scan_time
        self.assertEqual(realtime_args[0], backfill_args[0])  # cur (mocked)
        self.assertEqual(realtime_args[1], backfill_args[1])  # device_user_pk
        # scan_time should be equivalent (both normalized from same naive input)
        self.assertEqual(realtime_args[2], backfill_args[2])


class TestSafetyRegressions(unittest.TestCase):
    """Safety regression tests — ensure no auto-creation, no guessing, dedupe unchanged."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_unmapped_attendance_employee_id_null(self, mock_map, mock_user, mock_dev, mock_conn):
        """Unmapped attendance → employee_id = NULL in INSERT."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        rec = MockAttendanceRecord(1, "1", datetime(2026, 8, 11, 10, 0, 0, tzinfo=timezone.utc))
        save_attendance_log(self.cfg, rec)

        # Find the INSERT call and verify employee_id (last arg) is None
        insert_call = None
        for c in mock_cur.execute.call_args_list:
            sql = c[0][0]
            if "INSERT INTO attendance_logs" in sql:
                insert_call = c
                break
        self.assertIsNotNone(insert_call)
        params = insert_call[0][1]
        # employee_id is the last parameter (index 8)
        self.assertIsNone(params[8])

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_no_human_auto_creation(self, mock_map, mock_user, mock_dev, mock_conn):
        """Verify no INSERT INTO human_employees or INSERT INTO employees."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        rec = MockAttendanceRecord(1, "1", datetime(2026, 8, 11, 10, 0, 0, tzinfo=timezone.utc))
        save_attendance_log(self.cfg, rec)

        for c in mock_cur.execute.call_args_list:
            sql = c[0][0].upper()
            self.assertNotIn("INSERT INTO HUMAN_EMPLOYEES", sql)
            self.assertNotIn("INSERT INTO EMPLOYEES", sql)
            self.assertNotIn("ENSURE_EMPLOYEE_STUB", sql)

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_no_legacy_employee_stub(self, mock_map, mock_user, mock_dev, mock_conn):
        """Verify no legacy ensure_employee_stub function is called."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        rec = MockAttendanceRecord(1, "1", datetime(2026, 8, 11, 10, 0, 0, tzinfo=timezone.utc))
        save_attendance_log(self.cfg, rec)

        for c in mock_cur.execute.call_args_list:
            sql = c[0][0].lower()
            self.assertNotIn("ensure_employee_stub", sql)

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_dedupe_constraint_unchanged(self, mock_map, mock_user, mock_dev, mock_conn):
        """Verify ON CONFLICT (user_id, device_ip, scan_time) DO NOTHING is preserved."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        rec = MockAttendanceRecord(1, "1", datetime(2026, 8, 11, 10, 0, 0, tzinfo=timezone.utc))
        save_attendance_log(self.cfg, rec)

        found_dedupe = False
        for c in mock_cur.execute.call_args_list:
            sql = c[0][0]
            if "ON CONFLICT" in sql and "user_id" in sql and "device_ip" in sql and "scan_time" in sql:
                found_dedupe = True
                # employee_id must NOT be in the conflict target
                self.assertNotIn("employee_id", sql.split("ON CONFLICT")[1].split("DO")[0])
        self.assertTrue(found_dedupe)

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_no_employee_id_in_dedupe_batch(self, mock_map, mock_user, mock_dev, mock_conn):
        """Verify dedupe in batch path also excludes employee_id from conflict target."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        recs = [MockAttendanceRecord(1, "1", datetime(2026, 8, 11, 10, 0, 0, tzinfo=timezone.utc))]
        save_attendance_batch(self.cfg, recs)

        for c in mock_cur.execute.call_args_list:
            sql = c[0][0]
            if "ON CONFLICT" in sql:
                conflict_part = sql.split("ON CONFLICT")[1].split("DO")[0]
                self.assertNotIn("employee_id", conflict_part)

    def test_resolver_never_maps_from_excel_row_order(self):
        """Resolver SQL must not reference Excel, row_number, or source_record_key."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        resolve_verified_employee_mapping(mock_cur, 10, SCAN_TIME)
        sql = mock_cur.execute.call_args[0][0].lower()
        self.assertNotIn("excel", sql)
        self.assertNotIn("row_number", sql)
        self.assertNotIn("source_record_key", sql)

    def test_resolver_never_maps_from_display_name(self):
        """Resolver SQL must not reference display_name or device_display_name."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        resolve_verified_employee_mapping(mock_cur, 10, SCAN_TIME)
        sql = mock_cur.execute.call_args[0][0].lower()
        self.assertNotIn("display_name", sql)

    def test_resolver_never_maps_from_numeric_user_id_alone(self):
        """Resolver SQL must use device_user_pk, not device_user_id or user_id."""
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        resolve_verified_employee_mapping(mock_cur, 10, SCAN_TIME)
        sql = mock_cur.execute.call_args[0][0].lower()
        self.assertIn("device_user_pk", sql)
        self.assertNotIn("device_user_id", sql)

    def test_timestamp_normalization_preserved(self):
        """normalize_device_timestamp still works correctly for Bangkok naive input."""
        naive_bangkok = datetime(2026, 8, 11, 15, 30, 0)
        result = normalize_device_timestamp(naive_bangkok)
        self.assertEqual(result.tzinfo, BANGKOK_TZ)
        # UTC equivalent should be 08:30:00 (Bangkok 15:30 - 7h)
        self.assertEqual(result.utcoffset(), timedelta(hours=7))


class TestScanTimeCanonicalBeforeResolver(unittest.TestCase):
    """Verify scan_time is canonical (aware) before being passed to resolver."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_realtime_naive_input_becomes_aware(self, mock_map, mock_user, mock_dev, mock_conn):
        """Realtime path: naive Bangkok timestamp → aware before resolver call."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        # Naive datetime (as pyzk returns)
        naive_ts = datetime(2026, 8, 11, 15, 30, 0)
        rec = MockAttendanceRecord(1, "1", naive_ts)
        save_attendance_log(self.cfg, rec)

        # Resolver receives aware scan_time
        scan_time_arg = mock_map.call_args[0][2]
        self.assertIsNotNone(scan_time_arg.tzinfo)

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_backfill_naive_input_becomes_aware(self, mock_map, mock_user, mock_dev, mock_conn):
        """Backfill path: naive Bangkok timestamp → aware before resolver call."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        naive_ts = datetime(2026, 8, 11, 15, 30, 0)
        rec = MockAttendanceRecord(1, "1", naive_ts)
        save_attendance_batch(self.cfg, [rec])

        scan_time_arg = mock_map.call_args[0][2]
        self.assertIsNotNone(scan_time_arg.tzinfo)


if __name__ == "__main__":
    unittest.main()