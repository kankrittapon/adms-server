"""
Tests for controlled VERIFIED mapping creation (ADMS-Data-HumanDeviceMapping-003,
simplified contract per ADMS-FullEnrollment-E2E-Closure-017).

Covers:
  - Happy path: exactly one VERIFIED mapping with valid_from =
    controlled_scan_time, valid_to NULL, CONTROLLED_SCAN method
  - employee_id/device_user_pk/controlled_attendance_id are ALL derived
    server-side from enrollment_id — the caller supplies only
    (enrollment_id, verified_by, verification_note)
  - Precondition failures: enrollment missing/wrong state/missing evidence,
    missing/inactive device user, missing/inactive Human, unresolvable
    controlled-scan attendance evidence, conflicting VERIFIED mapping
  - Safety: no attendance mutation, no terminal access, no bulk/auto mapping,
    verified_by and note required

No physical device or database is required — DB access is mocked at the
app.mapping boundary (same convention as tests/test_enrollment.py). The
FakeCursor here supports both fetchone() (five sequential precondition/
insert reads) and fetchall() (the canonical evidence resolver's bounded
candidate query, called exactly once per create_verified_mapping call).
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.config import Config
from app.mapping import MappingError, create_verified_mapping

PILOT_EMPLOYEE_ID = "039c4486-b30f-4ce1-b780-783cd268858d"
DEVICE_ID = 1
RESERVED_DEVICE_USER_ID = "1001"
DEVICE_USER_PK = 7
ENROLLMENT_ID = 1
ATTENDANCE_ID = 12
SCAN_TIME = datetime(2026, 8, 12, 8, 47, 37, tzinfo=timezone.utc)
NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)


class FakeCursor:
    """Records executed SQL; serves canned fetchone() results in order and
    a single canned fetchall() result (the evidence resolver's candidate
    rows)."""

    def __init__(self, fetchone_queue=None, fetchall_result=None, rowcount=1):
        self.executed = []
        self._fetchone_queue = list(fetchone_queue or [])
        self._fetchall_result = list(fetchall_result if fetchall_result is not None else [])
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self._fetchone_queue:
            return self._fetchone_queue.pop(0)
        return None

    def fetchall(self):
        return self._fetchall_result

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


def happy_path_queue(
    employee_id=PILOT_EMPLOYEE_ID,
    status="READY_FOR_MAPPING",
    scan_time=SCAN_TIME,
    device_user_active=True,
    human_active=True,
    conflict=None,
):
    """Builds the fetchone() queue matching create_verified_mapping's actual
    call order: enrollment -> device_users -> human_employees -> [resolver
    uses fetchall(), not fetchone()] -> conflict-check -> INSERT RETURNING."""
    return [
        (employee_id, DEVICE_ID, RESERVED_DEVICE_USER_ID, status, scan_time, "owner-krittaphol"),  # enrollment
        (DEVICE_USER_PK, device_user_active),  # device_users
        (human_active,),                       # human_employees
        conflict,                              # conflicting VERIFIED mapping?
        (1, scan_time, NOW),                   # INSERT RETURNING
    ]


def happy_path_attendance_candidates(attendance_id=ATTENDANCE_ID, scan_time=SCAN_TIME):
    """The evidence resolver's fetchall() result — a single exact-match
    candidate within the window."""
    return [(attendance_id, scan_time)]


class TestMappingHappyPath(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()
        self.note = (
            "Pilot evidence: production account 1001, physical fingerprint "
            "enrollment, controlled attendance evidence, explicit owner "
            "confirmation, PromptID ADMS-Data-DeviceEnrollmentPilot-001"
        )

    @patch("app.mapping.log_sync_event")
    @patch("app.mapping.get_db_connection")
    def test_creates_exactly_one_verified_mapping(self, mock_conn_fn, mock_log):
        cur = FakeCursor(
            fetchone_queue=happy_path_queue(),
            fetchall_result=happy_path_attendance_candidates(),
        )
        conn = make_db(mock_conn_fn, cur)

        result = create_verified_mapping(
            self.cfg,
            enrollment_id=ENROLLMENT_ID,
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
        self.assertIn("NULL", inserts[0].split("VALUES")[1].split(")")[0])

        conn.commit.assert_called()
        mock_log.assert_called_once()
        self.assertIn("MAPPING_VERIFIED", mock_log.call_args[0][1])

    @patch("app.mapping.get_db_connection")
    def test_verified_by_required(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=happy_path_queue(), fetchall_result=happy_path_attendance_candidates())
        make_db(mock_conn_fn, cur)
        with self.assertRaises(MappingError):
            create_verified_mapping(
                self.cfg, enrollment_id=ENROLLMENT_ID, verified_by="  ", verification_note="note",
            )

    @patch("app.mapping.get_db_connection")
    def test_verification_note_required(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=happy_path_queue(), fetchall_result=happy_path_attendance_candidates())
        make_db(mock_conn_fn, cur)
        with self.assertRaises(MappingError):
            create_verified_mapping(
                self.cfg, enrollment_id=ENROLLMENT_ID, verified_by="owner", verification_note="  ",
            )

    @patch("app.mapping.get_db_connection")
    def test_evidence_matched_within_minute_precision_gap(self, mock_conn_fn):
        """Regression: the operator-recorded controlled_scan_time (minute
        precision) and the real attendance_logs.scan_time (full precision)
        differ by tens of seconds — the canonical resolver must still find
        it, unlike the old exact-equality check that produced the
        'Attendance ID #?' / 422 class of failure."""
        near_scan_time = SCAN_TIME.replace(second=22, microsecond=417000)
        cur = FakeCursor(
            fetchone_queue=happy_path_queue(scan_time=SCAN_TIME),
            fetchall_result=[(ATTENDANCE_ID, near_scan_time)],
        )
        make_db(mock_conn_fn, cur)
        with patch("app.mapping.log_sync_event"):
            result = create_verified_mapping(
                self.cfg, enrollment_id=ENROLLMENT_ID, verified_by="owner", verification_note="note",
            )
        self.assertEqual(result["mapping_id"], 1)


class TestEnrollmentCompletionSemantics(unittest.TestCase):
    """ADMS-UX-FinalPolish-021 Part B: an Enrollment must never keep showing
    as READY_FOR_MAPPING (open work) once its VERIFIED mapping actually
    exists. RETIRED already existed as a valid terminal state in the
    enrollment state machine and its DB CHECK constraint — it was simply
    never driven. No migration; the fix is entirely query/transaction-level."""

    def setUp(self):
        self.cfg = Config.from_env()
        self.note = "Pilot evidence note"

    @patch("app.mapping.log_sync_event")
    @patch("app.mapping.get_db_connection")
    def test_successful_mapping_atomically_retires_enrollment(self, mock_conn_fn, mock_log):
        cur = FakeCursor(
            fetchone_queue=happy_path_queue(),
            fetchall_result=happy_path_attendance_candidates(),
        )
        conn = make_db(mock_conn_fn, cur)

        create_verified_mapping(
            self.cfg, enrollment_id=ENROLLMENT_ID, verified_by="owner", verification_note=self.note,
        )

        retire_calls = [
            (s, p) for s, p in cur.executed
            if "device_user_enrollments" in s and "RETIRED" in s
        ]
        self.assertEqual(len(retire_calls), 1)
        self.assertIn("READY_FOR_MAPPING", retire_calls[0][0])
        self.assertEqual(retire_calls[0][1], (ENROLLMENT_ID,))
        # Same transaction/commit as the mapping insert — genuinely atomic,
        # not a second best-effort write.
        conn.commit.assert_called_once()

    @patch("app.mapping.log_sync_event")
    @patch("app.mapping.get_db_connection")
    def test_retire_race_fails_closed_no_mapping_left_dangling(self, mock_conn_fn, mock_log):
        """If the UPDATE affects 0 rows (concurrent state change between the
        initial read and the retire step), the whole call must fail — never
        leave a VERIFIED mapping whose enrollment silently stayed open."""
        cur = FakeCursor(
            fetchone_queue=happy_path_queue(),
            fetchall_result=happy_path_attendance_candidates(),
            rowcount=1,
        )
        conn = make_db(mock_conn_fn, cur)

        orig_execute = cur.execute

        def flaky_execute(sql, params=None):
            orig_execute(sql, params)
            if "RETIRED" in sql:
                cur.rowcount = 0

        cur.execute = flaky_execute

        with self.assertRaises(MappingError):
            create_verified_mapping(
                self.cfg, enrollment_id=ENROLLMENT_ID, verified_by="owner", verification_note=self.note,
            )
        conn.commit.assert_not_called()

    @patch("app.mapping.get_db_connection")
    def test_duplicate_step6_is_idempotent_not_a_second_mapping(self, mock_conn_fn):
        """A second confirmation attempt on an already-RETIRED enrollment
        must return the existing VERIFIED mapping, not error and not create
        a second row."""
        cur = FakeCursor(
            fetchone_queue=[
                (PILOT_EMPLOYEE_ID, DEVICE_ID, RESERVED_DEVICE_USER_ID, "RETIRED", SCAN_TIME, "owner"),
                (DEVICE_USER_PK, True),  # device_users
                (5, SCAN_TIME, None, NOW),  # existing VERIFIED mapping lookup
            ],
        )
        make_db(mock_conn_fn, cur)

        result = create_verified_mapping(
            self.cfg, enrollment_id=ENROLLMENT_ID, verified_by="owner", verification_note="note",
        )

        self.assertTrue(result["already_completed"])
        self.assertEqual(result["mapping_id"], 5)
        self.assertEqual(result["device_user_pk"], DEVICE_USER_PK)
        inserts = [s for s in cur.sql() if "INSERT INTO employee_device_mappings" in s]
        self.assertEqual(len(inserts), 0)

    @patch("app.mapping.get_db_connection")
    def test_retired_with_no_existing_mapping_is_an_inconsistency_error(self, mock_conn_fn):
        """RETIRED with zero VERIFIED mappings means something else is
        wrong (e.g. manual DB tampering) — must not fabricate a result."""
        cur = FakeCursor(
            fetchone_queue=[
                (PILOT_EMPLOYEE_ID, DEVICE_ID, RESERVED_DEVICE_USER_ID, "RETIRED", SCAN_TIME, "owner"),
                (DEVICE_USER_PK, True),
                None,  # no VERIFIED mapping found
            ],
        )
        make_db(mock_conn_fn, cur)
        with self.assertRaises(MappingError):
            create_verified_mapping(
                self.cfg, enrollment_id=ENROLLMENT_ID, verified_by="owner", verification_note="note",
            )

    @patch("app.mapping.log_sync_event")
    @patch("app.mapping.get_db_connection")
    def test_fresh_completion_marks_already_completed_false(self, mock_conn_fn, mock_log):
        cur = FakeCursor(
            fetchone_queue=happy_path_queue(),
            fetchall_result=happy_path_attendance_candidates(),
        )
        make_db(mock_conn_fn, cur)
        result = create_verified_mapping(
            self.cfg, enrollment_id=ENROLLMENT_ID, verified_by="owner", verification_note=self.note,
        )
        self.assertFalse(result["already_completed"])


class TestMappingPreconditions(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def _run(self, fetchone_queue, fetchall_result=None, **kwargs):
        cur = FakeCursor(fetchone_queue=fetchone_queue, fetchall_result=fetchall_result)
        make_db(kwargs.pop("_conn_fn"), cur)
        args = dict(
            enrollment_id=ENROLLMENT_ID,
            verified_by="owner-krittaphol",
            verification_note="note referencing pilot evidence",
        )
        args.update(kwargs)
        with patch("app.mapping.log_sync_event"):
            return create_verified_mapping(self.cfg, **args)

    def test_enrollment_missing(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "does not exist"):
                self._run([None], _conn_fn=m)

    def test_enrollment_wrong_state(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "expected READY_FOR_MAPPING"):
                self._run(
                    [(PILOT_EMPLOYEE_ID, DEVICE_ID, RESERVED_DEVICE_USER_ID, "RESERVED", SCAN_TIME, "owner")],
                    _conn_fn=m,
                )

    def test_enrollment_missing_scan_time(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "controlled_scan_time"):
                self._run(
                    [(PILOT_EMPLOYEE_ID, DEVICE_ID, RESERVED_DEVICE_USER_ID, "READY_FOR_MAPPING", None, "owner")],
                    _conn_fn=m,
                )

    def test_enrollment_missing_confirmed_by(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "confirmed_by"):
                self._run(
                    [(PILOT_EMPLOYEE_ID, DEVICE_ID, RESERVED_DEVICE_USER_ID, "READY_FOR_MAPPING", SCAN_TIME, None)],
                    _conn_fn=m,
                )

    def test_device_user_missing(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "no device_users row"):
                self._run(happy_path_queue()[:1] + [None], _conn_fn=m)

    def test_device_user_inactive(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "inactive"):
                self._run(happy_path_queue()[:1] + [(DEVICE_USER_PK, False)], _conn_fn=m)

    def test_human_missing(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "does not exist"):
                self._run(happy_path_queue()[:2] + [None], _conn_fn=m)

    def test_human_inactive(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "inactive"):
                self._run(happy_path_queue()[:2] + [(False,)], _conn_fn=m)

    def test_no_controlled_attendance_evidence_resolves(self):
        """The evidence resolver's fetchall() returns nothing within the
        window — must fail with a clear evidence-missing message, not a
        generic error, and must never fall back to guessing."""
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "no controlled-scan attendance evidence resolves"):
                self._run(
                    happy_path_queue()[:3],
                    fetchall_result=[],  # no candidates at all
                    _conn_fn=m,
                )

    def test_conflicting_verified_mapping_blocks(self):
        with patch("app.mapping.get_db_connection") as m:
            with self.assertRaisesRegex(MappingError, "conflicting VERIFIED mapping"):
                self._run(
                    happy_path_queue(conflict=(1,)),
                    fetchall_result=happy_path_attendance_candidates(),
                    _conn_fn=m,
                )


if __name__ == "__main__":
    unittest.main()
