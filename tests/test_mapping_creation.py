"""
Tests for controlled VERIFIED mapping creation (ADMS-Data-HumanDeviceMapping-003).

Covers:
  - Happy path: exactly one VERIFIED mapping with valid_from =
    controlled_scan_time, valid_to NULL, CONTROLLED_SCAN method
  - Precondition failures: missing/inactive device user, missing/inactive
    Human, enrollment not READY_FOR_MAPPING / wrong Human / wrong device /
    terminal mismatch / missing evidence, attendance evidence missing or
    mismatched, conflicting VERIFIED mapping
  - Safety: no attendance mutation, no terminal access, no bulk/auto mapping,
    verified_by and note required

No physical device or database is required — DB access is mocked at the
app.mapping boundary (same convention as tests/test_enrollment.py).
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.config import Config
from app.mapping import MappingError, create_verified_mapping

PILOT_EMPLOYEE_ID = "039c4486-b30f-4ce1-b780-783cd268858d"
DEVICE_USER_PK = 7
ENROLLMENT_ID = 1
ATTENDANCE_ID = 12
SCAN_TIME = datetime(2026, 8, 12, 8, 47, 37, tzinfo=timezone.utc)
NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)


class FakeCursor:
    """Records executed SQL and serves canned fetchone results."""

    def __init__(self, fetchone_queue=None, rowcount=1):
        self.executed = []
        self._queue = list(fetchone_queue or [])
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self._queue:
            return self._queue.pop(0)
        return None

    def sql(self):
        return [s for s, _ in self.executed]


def make_db(mock_conn_fn, cur):
    """Wires a FakeCursor into the get_db_connection context-manager mock."""
    mock_conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__.return_value = cur
    cur_ctx.__exit__.return_value = None
    mock_conn.cursor.return_value = cur_ctx
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    mock_ctx.__exit__.return_value = None
    mock_conn_fn.return_value = mock_ctx
    return mock_conn


def happy_path_queue(employee_id=PILOT_EMPLOYEE_ID, status="READY_FOR_MAPPING",
                     scan_time=SCAN_TIME, attendance_pk=DEVICE_USER_PK,
                     attendance_scan_time=SCAN_TIME, conflict=None):
    """Builds the fetchone queue for a precondition-passing run."""
    return [
        ("1001", 1, True),            # device_users (id, device_id, active)
        (True,),                      # human_employees (active)
        (employee_id, 1, "1001", status, scan_time, "owner-krittaphol"),  # enrollment
        (ATTENDANCE_ID, attendance_pk, attendance_scan_time, None),  # attendance
        conflict,                     # conflicting VERIFIED mapping?
        (1, scan_time, NOW),          # INSERT RETURNING
    ]


class TestMappingHappyPath(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()
        self.note = (
            "Pilot evidence: production account 1001, physical fingerprint "
            "enrollment, controlled attendance id 12, explicit owner "
            "confirmation, PromptID ADMS-Data-DeviceEnrollmentPilot-001"
        )

    @patch("app.mapping.log_sync_event")
    @patch("app.mapping.get_db_connection")
    def test_creates_exactly_one_verified_mapping(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=happy_path_queue())
        conn = make_db(mock_conn_fn, cur)

        result = create_verified_mapping(
            self.cfg,
            employee_id=PILOT_EMPLOYEE_ID,
            device_user_pk=DEVICE_USER_PK,
            enrollment_id=ENROLLMENT_ID,
            controlled_attendance_id=ATTENDANCE_ID,
            verified_by="owner-krittaphol",
            verification_note=self.note,
        )

        self.assertEqual(result["mapping_status"], "VERIFIED")
        self.assertEqual(result["valid_from"], SCAN_TIME)
        self.assertEqual(result["valid_to"], None)
        self.assertEqual(result["mapping_id"], 1)
        self.assertEqual(result["device_user_pk"], DEVICE_USER_PK)
        self.assertEqual(result["employee_id"], PILOT_EMPLOYEE_ID)

        inserts = [s for s in cur.sql() if "INSERT INTO employee_device_mappings" in s]
        self.assertEqual(len(inserts), 1)
        params = [p for s, p in cur.executed if "INSERT INTO employee_device_mappings" in s][0]
        self.assertEqual(params[0], PILOT_EMPLOYEE_ID)
        self.assertEqual(params[1], DEVICE_USER_PK)
        self.assertEqual(params[2], "CONTROLLED_SCAN")  # mapping_source
        self.assertEqual(params[3], "owner-krittaphol")  # verified_by
        self.assertEqual(params[4], "CONTROLLED_SCAN")  # verification_method
        self.assertEqual(params[5], self.note)
        self.assertEqual(params[6], SCAN_TIME)  # valid_from
        # valid_to must be NULL — the INSERT passes only 7 params + NULL literal.
        self.assertIn("NULL", inserts[0].split("VALUES")[1].split(")")[0])

        conn.commit.assert_called()
        mock_log.assert_called_once()
        self.assertIn("MAPPING_VERIFIED", mock_log.call_args[0][1])

    @patch("app.mapping.get_db_connection")
    def test_verified_by_required(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=happy_path_queue())
        make_db(mock_conn_fn, cur)
        with self.assertRaises(MappingError):
            create_verified_mapping(
                self.cfg, employee_id=PILOT_EMPLOYEE_ID, device_user_pk=DEVICE_USER_PK,
                enrollment_id=ENROLLMENT_ID, controlled_attendance_id=ATTENDANCE_ID,
                verified_by="  ", verification_note="note",
            )

    @patch("app.mapping.get_db_connection")
    def test_verification_note_required(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=happy_path_queue())
        make_db(mock_conn_fn, cur)
        with self.assertRaises(MappingError):
            create_verified_mapping(
                self.cfg, employee_id=PILOT_EMPLOYEE_ID, device_user_pk=DEVICE_USER_PK,
                enrollment_id=ENROLLMENT_ID, controlled_attendance_id=ATTENDANCE_ID,
                verified_by="owner", verification_note="  ",
            )


class TestMappingPreconditions(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def _run(self, queue, **kwargs):
        cur = FakeCursor(fetchone_queue=queue)
        make_db(kwargs.pop("_conn_fn"), cur)
        args = dict(
            employee_id=PILOT_EMPLOYEE_ID,
            device_user_pk=DEVICE_USER_PK,
            enrollment_id=ENROLLMENT_ID,
            controlled_attendance_id=ATTENDANCE_ID,
            verified_by="owner-krittaphol",
            verification_note="note referencing pilot evidence",
        )
        args.update(kwargs)
        return create_verified_mapping(self.cfg, **args)

    def test_device_user_missing(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "does not exist"):
                self._run([None], _conn_fn=m)

    def test_device_user_inactive(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "inactive"):
                self._run([("1001", 1, False)], _conn_fn=m)

    def test_human_missing(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "Human"):
                self._run([("1001", 1, True), None], _conn_fn=m)

    def test_human_inactive(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "inactive"):
                self._run([("1001", 1, True), (False,)], _conn_fn=m)

    def test_enrollment_missing(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "enrollment"):
                self._run([("1001", 1, True), (True,), None], _conn_fn=m)

    def test_enrollment_not_ready(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "READY_FOR_MAPPING"):
                self._run(happy_path_queue(status="CONTROLLED_SCAN_CONFIRMED"), _conn_fn=m)

    def test_enrollment_wrong_human(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "different Human"):
                self._run(happy_path_queue(employee_id="00000000-0000-0000-0000-000000000000"), _conn_fn=m)

    def test_enrollment_wrong_device(self):
        with patch("app.mapping.get_db_connection") as m:
            queue = [
                ("1001", 1, True),
                (True,),
                (PILOT_EMPLOYEE_ID, 2, "1001", "READY_FOR_MAPPING", SCAN_TIME, "owner"),
                (ATTENDANCE_ID, DEVICE_USER_PK, SCAN_TIME, None),
                None,
                (1, SCAN_TIME, NOW),
            ]
            with self.assertRaisesRegex(MappingError, "different device"):
                self._run(queue, _conn_fn=m)

    def test_enrollment_terminal_mismatch(self):
        with patch("app.mapping.get_db_connection") as m:
            queue = [
                ("1001", 1, True),
                (True,),
                (PILOT_EMPLOYEE_ID, 1, "1002", "READY_FOR_MAPPING", SCAN_TIME, "owner"),
                (ATTENDANCE_ID, DEVICE_USER_PK, SCAN_TIME, None),
                None,
                (1, SCAN_TIME, NOW),
            ]
            with self.assertRaisesRegex(MappingError, "does not match device user"):
                self._run(queue, _conn_fn=m)

    def test_missing_controlled_scan_time(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "controlled_scan_time"):
                self._run(happy_path_queue(scan_time=None), _conn_fn=m)

    def test_missing_confirmed_by(self):
        with patch("app.mapping.get_db_connection") as m:
            queue = [
                ("1001", 1, True),
                (True,),
                (PILOT_EMPLOYEE_ID, 1, "1001", "READY_FOR_MAPPING", SCAN_TIME, None),
                (ATTENDANCE_ID, DEVICE_USER_PK, SCAN_TIME, None),
                None,
                (1, SCAN_TIME, NOW),
            ]
            with self.assertRaisesRegex(MappingError, "confirmed_by"):
                self._run(queue, _conn_fn=m)

    def test_attendance_evidence_missing(self):
        with patch("app.mapping.get_db_connection") as m:
            queue = happy_path_queue()
            queue[3] = None  # attendance row missing
            with self.assertRaisesRegex(MappingError, "does not exist"):
                self._run(queue, _conn_fn=m)

    def test_attendance_wrong_device_user(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "device_user_pk"):
                self._run(happy_path_queue(attendance_pk=99), _conn_fn=m)

    def test_attendance_scan_time_mismatch(self):
        with patch("app.mapping.get_db_connection") as m:
            wrong = datetime(2026, 8, 12, 9, 0, 0, tzinfo=timezone.utc)
            with self.assertRaisesRegex(MappingError, "does not match"):
                self._run(happy_path_queue(attendance_scan_time=wrong), _conn_fn=m)

    def test_conflicting_open_ended_verified_mapping(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "conflicting"):
                self._run(happy_path_queue(conflict=(9,)), _conn_fn=m)


class TestMappingSafety(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.mapping.log_sync_event")
    @patch("app.mapping.get_db_connection")
    def test_no_attendance_mutation(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=happy_path_queue())
        make_db(mock_conn_fn, cur)
        create_verified_mapping(
            self.cfg, employee_id=PILOT_EMPLOYEE_ID, device_user_pk=DEVICE_USER_PK,
            enrollment_id=ENROLLMENT_ID, controlled_attendance_id=ATTENDANCE_ID,
            verified_by="owner", verification_note="pilot evidence",
        )
        for sql in cur.sql():
            self.assertNotIn("UPDATE attendance_logs", sql)
            self.assertNotIn("DELETE FROM attendance_logs", sql)

    @patch("app.mapping.log_sync_event")
    @patch("app.mapping.get_db_connection")
    def test_only_one_mapping_insert(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=happy_path_queue())
        make_db(mock_conn_fn, cur)
        create_verified_mapping(
            self.cfg, employee_id=PILOT_EMPLOYEE_ID, device_user_pk=DEVICE_USER_PK,
            enrollment_id=ENROLLMENT_ID, controlled_attendance_id=ATTENDANCE_ID,
            verified_by="owner", verification_note="pilot evidence",
        )
        inserts = [s for s in cur.sql() if "INSERT INTO employee_device_mappings" in s]
        self.assertEqual(len(inserts), 1)

    @patch("app.mapping.log_sync_event")
    @patch("app.mapping.get_db_connection")
    def test_no_human_master_or_enrollment_mutation(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=happy_path_queue())
        make_db(mock_conn_fn, cur)
        create_verified_mapping(
            self.cfg, employee_id=PILOT_EMPLOYEE_ID, device_user_pk=DEVICE_USER_PK,
            enrollment_id=ENROLLMENT_ID, controlled_attendance_id=ATTENDANCE_ID,
            verified_by="owner", verification_note="pilot evidence",
        )
        for sql in cur.sql():
            self.assertNotIn("INSERT INTO human_employees", sql)
            self.assertNotIn("UPDATE device_user_enrollments", sql)
            self.assertNotIn("UPDATE device_users", sql)

    def test_no_mapping_based_on_rank_or_name(self):
        # The SQL must be keyed by device_user_pk and employee_id only.
        cur = FakeCursor(fetchone_queue=happy_path_queue())
        with patch("app.mapping.get_db_connection") as m:
            make_db(m, cur)
            create_verified_mapping(
                self.cfg, employee_id=PILOT_EMPLOYEE_ID, device_user_pk=DEVICE_USER_PK,
                enrollment_id=ENROLLMENT_ID, controlled_attendance_id=ATTENDANCE_ID,
                verified_by="owner", verification_note="pilot evidence",
            )
        insert_sql = [s for s in cur.sql() if "INSERT INTO employee_device_mappings" in s][0]
        lowered = insert_sql.lower()
        self.assertNotIn("rank", lowered)
        self.assertNotIn("display_name", lowered)
        self.assertNotIn("excel", lowered)
        self.assertNotIn("source_record_key", lowered)


if __name__ == "__main__":
    unittest.main()
