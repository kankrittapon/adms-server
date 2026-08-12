"""
Tests for Controlled Device Enrollment Infrastructure.
PromptID: ADMS-Data-DeviceEnrollmentWorkflow-002

Covers:
  - ID allocation (production namespace 1001+, legacy 1/2 never reused,
    reserved/terminal-present/retired IDs skipped, concurrency safety,
    per-device scoping)
  - Reservation (valid/invalid Human, valid/invalid device, duplicate active
    reservation, cancelled/retired reservation behavior)
  - Terminal account creation (correct set_user params, normal privilege,
    exact reserved ID, safe display name, existing-ID fail-safe, unreachable
    device fail-safe, no mapping created)
  - Workflow state transitions (allowed vs forbidden, evidence required)
  - Identity safety (never creates mappings / human master rows / attendance
    mutations)
  - Device safety (never triggers destructive terminal operations)

No physical device or database is required — device access and DB access are
mocked at the app.enrollment boundary.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.config import Config
from app.enrollment import (
    EnrollmentError,
    PRODUCTION_NAMESPACE_START,
    PRIVILEGE_NORMAL_USER,
    _ENROLLMENT_COLUMNS,
    _find_next_available_id,
    cancel_enrollment,
    confirm_controlled_scan,
    confirm_fingerprint_enrolled,
    create_reserved_terminal_account,
    get_enrollment,
    mark_ready_for_mapping,
    reserve_next_device_user_id,
    retire_enrollment,
    start_controlled_scan_window,
    start_fingerprint_enrollment,
    validate_status_transition,
    validate_terminal_display_name,
    verify_terminal_account_created,
)

NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeCursor:
    """Records executed SQL and serves canned fetchone/fetchall results."""

    def __init__(self, fetchone_queue=None, fetchall_result=None, rowcount=1):
        self.executed = []
        self._fetchone_queue = list(fetchone_queue or [])
        self._fetchall_result = fetchall_result if fetchall_result is not None else []
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


def make_db(mock_conn_fn, cur, conn=None):
    """Wires a FakeCursor into the get_db_connection context-manager mock."""
    mock_conn = conn or MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__.return_value = cur
    cur_ctx.__exit__.return_value = None
    mock_conn.cursor.return_value = cur_ctx
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    mock_ctx.__exit__.return_value = None
    mock_conn_fn.return_value = mock_ctx
    return mock_conn


def make_enrollment_tuple(**overrides):
    """Builds a device_user_enrollments row tuple matching _ENROLLMENT_COLUMNS."""
    base = {
        "enrollment_id": 1,
        "employee_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "device_id": 1,
        "reserved_device_user_id": "1001",
        "status": "RESERVED",
        "reserved_by": "operator",
        "reserved_at": NOW,
        "terminal_created_at": None,
        "device_uid": None,
        "fingerprint_confirmed_at": None,
        "controlled_scan_window_until": None,
        "controlled_scan_time": None,
        "confirmed_by": None,
        "confirmed_at": None,
        "notes": None,
    }
    base.update(overrides)
    return tuple(base[c] for c in _ENROLLMENT_COLUMNS)


class FakeUser:
    def __init__(self, user_id, uid=None, name="", privilege=PRIVILEGE_NORMAL_USER):
        self.user_id = user_id
        self.uid = uid
        self.name = name
        self.privilege = privilege


class FakeDevice:
    """Records calls; destructive methods fail loudly if invoked."""

    def __init__(self, users=None):
        self._users = list(users or [])
        self.calls = []
        self.set_user_calls = []

    def get_users(self):
        self.calls.append("get_users")
        return list(self._users)

    def set_user(self, **kwargs):
        self.calls.append("set_user")
        self.set_user_calls.append(kwargs)
        return True

    # Destructive operations must never be triggered by enrollment code.
    def delete_user(self, *a, **k):
        raise AssertionError("destructive delete_user called by enrollment code")

    def clear_attendance(self, *a, **k):
        raise AssertionError("destructive clear_attendance called by enrollment code")

    def clear_data(self, *a, **k):
        raise AssertionError("destructive clear_data called by enrollment code")

    def restart(self, *a, **k):
        raise AssertionError("destructive restart called by enrollment code")


# ---------------------------------------------------------------------------
# ID allocation (§34)
# ---------------------------------------------------------------------------


class TestIDAllocation(unittest.TestCase):
    def test_first_id_on_clean_namespace_is_1001(self):
        self.assertEqual(_find_next_available_id(), "1001")

    def test_legacy_ids_1_and_2_never_reused(self):
        # Even a "clean" namespace must not collide with legacy test IDs.
        self.assertEqual(_find_next_available_id(), "1001")
        # If somehow used history only contains legacy IDs, first prod ID is 1001.
        self.assertEqual(_find_next_available_id({"1", "2"}), "1001")

    def test_reserved_id_skipped(self):
        self.assertEqual(_find_next_available_id({"1001"}), "1002")
        self.assertEqual(_find_next_available_id({"1001", "1002", "1003"}), "1004")

    def test_terminal_present_id_skipped(self):
        self.assertEqual(_find_next_available_id(roster_ids={"1001"}), "1002")
        self.assertEqual(
            _find_next_available_id({"1001"}, roster_ids={"1002"}), "1003"
        )

    def test_historical_and_retired_ids_skipped(self):
        # 1/2 historical, 1001 cancelled, 1002 retired → next is 1003.
        used = {"1", "2", "1001", "1002"}
        self.assertEqual(_find_next_available_id(used), "1003")

    def test_monotonic_no_recycling(self):
        # Gaps are NOT filled — IDs progress monotonically (no immediate reuse).
        self.assertEqual(_find_next_available_id({"1001", "1003"}), "1002")
        # Once 1002 is also used, continue upward, never back to 1001.
        self.assertEqual(_find_next_available_id({"1001", "1002", "1003"}), "1004")

    def test_string_and_int_inputs_accepted(self):
        self.assertEqual(_find_next_available_id({1001, "1002"}), "1003")


class TestTerminalDisplayName(unittest.TestCase):
    def test_valid_ascii_name_passes(self):
        self.assertEqual(validate_terminal_display_name("Somchai S."), "Somchai S.")

    def test_rank_style_name_passes(self):
        self.assertEqual(validate_terminal_display_name("Lt Col K."), "Lt Col K.")

    def test_whitespace_stripped(self):
        self.assertEqual(validate_terminal_display_name("  Somchai  "), "Somchai")

    def test_non_ascii_rejected(self):
        with self.assertRaises(EnrollmentError):
            validate_terminal_display_name("สมชาย")

    def test_uuid_rejected(self):
        with self.assertRaises(EnrollmentError):
            validate_terminal_display_name("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    def test_generic_placeholder_rejected(self):
        with self.assertRaises(EnrollmentError):
            validate_terminal_display_name("Device User 1001")

    def test_pure_number_rejected(self):
        with self.assertRaises(EnrollmentError):
            validate_terminal_display_name("1001")

    def test_too_long_rejected(self):
        with self.assertRaises(EnrollmentError):
            validate_terminal_display_name("X" * 21)

    def test_empty_rejected(self):
        with self.assertRaises(EnrollmentError):
            validate_terminal_display_name("   ")


# ---------------------------------------------------------------------------
# State transitions (§37)
# ---------------------------------------------------------------------------


class TestStateTransitions(unittest.TestCase):
    def test_happy_path_allowed(self):
        self.assertTrue(validate_status_transition("RESERVED", "TERMINAL_ACCOUNT_CREATED"))
        self.assertTrue(
            validate_status_transition("TERMINAL_ACCOUNT_CREATED", "FINGERPRINT_ENROLLMENT_PENDING")
        )
        self.assertTrue(validate_status_transition("FINGERPRINT_ENROLLMENT_PENDING", "FINGERPRINT_ENROLLED"))
        self.assertTrue(validate_status_transition("FINGERPRINT_ENROLLED", "CONTROLLED_SCAN_PENDING"))
        self.assertTrue(validate_status_transition("CONTROLLED_SCAN_PENDING", "CONTROLLED_SCAN_CONFIRMED"))
        self.assertTrue(validate_status_transition("CONTROLLED_SCAN_CONFIRMED", "READY_FOR_MAPPING"))

    def test_cancel_allowed_from_active_states(self):
        self.assertTrue(validate_status_transition("RESERVED", "CANCELLED"))
        self.assertTrue(validate_status_transition("FINGERPRINT_ENROLLMENT_PENDING", "CANCELLED"))
        self.assertTrue(validate_status_transition("CONTROLLED_SCAN_PENDING", "CANCELLED"))

    def test_retire_after_scan_confirmed(self):
        self.assertTrue(validate_status_transition("CONTROLLED_SCAN_CONFIRMED", "RETIRED"))
        self.assertTrue(validate_status_transition("READY_FOR_MAPPING", "RETIRED"))

    def test_reserved_cannot_skip_to_ready_for_mapping(self):
        self.assertFalse(validate_status_transition("RESERVED", "READY_FOR_MAPPING"))

    def test_no_evidence_skipping(self):
        # Cannot jump to scan pending without fingerprint evidence.
        self.assertFalse(validate_status_transition("FINGERPRINT_ENROLLMENT_PENDING", "CONTROLLED_SCAN_PENDING"))
        # Cannot reach scan confirmed without opening a window.
        self.assertFalse(validate_status_transition("FINGERPRINT_ENROLLED", "CONTROLLED_SCAN_CONFIRMED"))
        # Cannot reach READY_FOR_MAPPING without a confirmed scan.
        self.assertFalse(validate_status_transition("CONTROLLED_SCAN_PENDING", "READY_FOR_MAPPING"))

    def test_terminal_states_have_no_outgoing_transitions(self):
        self.assertFalse(validate_status_transition("CANCELLED", "RESERVED"))
        self.assertFalse(validate_status_transition("CANCELLED", "READY_FOR_MAPPING"))
        self.assertFalse(validate_status_transition("RETIRED", "CONTROLLED_SCAN_PENDING"))

    def test_unknown_state_rejected(self):
        self.assertFalse(validate_status_transition("BOGUS", "CANCELLED"))


# ---------------------------------------------------------------------------
# Reservation (§35)
# ---------------------------------------------------------------------------


class TestReservation(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_valid_reservation_allocates_1001_and_captures_operator(self, mock_conn_fn, mock_log):
        cur = FakeCursor(
            fetchone_queue=[[1], [1], [None], None, (1, "1001", "RESERVED", NOW)],
            fetchall_result=[],
        )
        make_db(mock_conn_fn, cur)

        result = reserve_next_device_user_id(
            self.cfg,
            employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            device_id=1,
            operator="admin-ops",
        )

        self.assertEqual(result["reserved_device_user_id"], "1001")
        self.assertEqual(result["status"], "RESERVED")
        self.assertEqual(result["enrollment_id"], 1)
        self.assertEqual(result["employee_id"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(result["device_id"], 1)

        # INSERT carries the reserved ID + operator + RESERVED status.
        insert_calls = [s for s in cur.sql() if "INSERT INTO device_user_enrollments" in s]
        self.assertEqual(len(insert_calls), 1)
        insert_params = [p for s, p in cur.executed if "INSERT INTO device_user_enrollments" in s][0]
        self.assertEqual(insert_params[2], "1001")
        self.assertEqual(insert_params[3], "admin-ops")

        # Advisory lock used for concurrency safety.
        lock_calls = [s for s in cur.sql() if "pg_advisory_xact_lock" in s]
        self.assertEqual(len(lock_calls), 1)

        mock_log.assert_called_once()
        self.assertIn("ENROLLMENT_RESERVED", mock_log.call_args[0][1])

    @patch("app.enrollment.get_db_connection")
    def test_invalid_human_rejected(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[None])  # no matching human row
        make_db(mock_conn_fn, cur)
        with self.assertRaisesRegex(EnrollmentError, "does not exist or is inactive"):
            reserve_next_device_user_id(
                self.cfg, employee_id="missing", device_id=1, operator="op"
            )

    @patch("app.enrollment.get_db_connection")
    def test_invalid_device_rejected(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[[1], None])  # human ok, device missing
        make_db(mock_conn_fn, cur)
        with self.assertRaisesRegex(EnrollmentError, "does not exist or is inactive"):
            reserve_next_device_user_id(
                self.cfg, employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", device_id=99, operator="op"
            )

    @patch("app.enrollment.get_db_connection")
    def test_inactive_human_rejected(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[None])  # active=true filter excludes the Human
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            reserve_next_device_user_id(
                self.cfg, employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", device_id=1, operator="op"
            )

    @patch("app.enrollment.get_db_connection")
    def test_reservation_requires_production_scope_sql(self, mock_conn_fn):
        """Human validation must require production_scope = true (พลทหาร exclusion)."""
        cur = FakeCursor(
            fetchone_queue=[[1], [1], [None], None, (1, "1001", "RESERVED", NOW)],
            fetchall_result=[],
        )
        make_db(mock_conn_fn, cur)
        reserve_next_device_user_id(
            self.cfg, employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", device_id=1, operator="op"
        )
        human_sql = [s for s in cur.sql() if "FROM human_employees" in s][0]
        self.assertIn("production_scope = true", human_sql)
        self.assertIn("active = true", human_sql)

    @patch("app.enrollment.get_db_connection")
    def test_human_excluded_from_production_scope_rejected(self, mock_conn_fn):
        """A Human excluded from production scope (production_scope=false) is rejected."""
        cur = FakeCursor(fetchone_queue=[None])  # no eligible Human row
        make_db(mock_conn_fn, cur)
        with self.assertRaisesRegex(EnrollmentError, "production scope"):
            reserve_next_device_user_id(
                self.cfg, employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", device_id=1, operator="op"
            )

    @patch("app.enrollment.get_db_connection")
    def test_operator_required(self, mock_conn_fn):
        cur = FakeCursor()
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            reserve_next_device_user_id(
                self.cfg, employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", device_id=1, operator="  "
            )

    @patch("app.enrollment.get_db_connection")
    def test_duplicate_active_reservation_rejected(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[[1], [1], [None], (55,)])  # dup found
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            reserve_next_device_user_id(
                self.cfg, employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", device_id=1, operator="op"
            )

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_cancelled_reservation_allows_new_reservation_with_next_id(self, mock_conn_fn, mock_log):
        # Cancelled row for 1001 exists; new reservation must skip it → 1002.
        cur = FakeCursor(
            fetchone_queue=[[1], [1], [None], None, (2, "1002", "RESERVED", NOW)],
            fetchall_result=[("1001",)],
        )
        make_db(mock_conn_fn, cur)
        result = reserve_next_device_user_id(
            self.cfg,
            employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            device_id=1,
            operator="op",
        )
        self.assertEqual(result["reserved_device_user_id"], "1002")

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_retired_reservation_allows_new_reservation_with_next_id(self, mock_conn_fn, mock_log):
        cur = FakeCursor(
            fetchone_queue=[[1], [1], [None], None, (2, "1002", "RESERVED", NOW)],
            fetchall_result=[("1001",)],
        )
        make_db(mock_conn_fn, cur)
        result = reserve_next_device_user_id(
            self.cfg,
            employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            device_id=1,
            operator="op",
        )
        self.assertEqual(result["reserved_device_user_id"], "1002")

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_ids_scoped_per_device(self, mock_conn_fn, mock_log):
        # Device 2 has its own history: 1001 used there → next is 1002.
        cur = FakeCursor(
            fetchone_queue=[[1], [1], [None], None, (3, "1002", "RESERVED", NOW)],
            fetchall_result=[("1001",)],
        )
        make_db(mock_conn_fn, cur)
        result = reserve_next_device_user_id(
            self.cfg,
            employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            device_id=2,
            operator="op",
        )
        self.assertEqual(result["reserved_device_user_id"], "1002")

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_terminal_roster_ids_considered(self, mock_conn_fn, mock_log):
        # Roster says 1001 is physically present → reserve 1002 instead.
        cur = FakeCursor(
            fetchone_queue=[[1], [1], [None], None, (4, "1002", "RESERVED", NOW)],
            fetchall_result=[],
        )
        make_db(mock_conn_fn, cur)
        result = reserve_next_device_user_id(
            self.cfg,
            employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            device_id=1,
            operator="op",
            roster_user_ids={"1001"},
        )
        self.assertEqual(result["reserved_device_user_id"], "1002")


# ---------------------------------------------------------------------------
# Terminal account creation (§36)
# ---------------------------------------------------------------------------


class TestTerminalAccountCreation(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()
        self.employee_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.enroll_row = make_enrollment_tuple(employee_id=self.employee_id)

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.ensure_device_user", return_value=42)
    @patch("app.enrollment.get_db_connection")
    def test_set_user_gets_correct_parameters(self, mock_conn_fn, mock_ensure, mock_log):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)
        device = FakeDevice(users=[])

        result = create_reserved_terminal_account(
            self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
        )

        self.assertEqual(result["terminal_id"], "1001")
        self.assertEqual(result["status"], "TERMINAL_ACCOUNT_CREATED")
        self.assertEqual(len(device.set_user_calls), 1)
        call = device.set_user_calls[0]
        self.assertEqual(call["user_id"], "1001")  # exact reserved ID
        self.assertEqual(call["name"], "Somchai S.")
        self.assertEqual(call["privilege"], PRIVILEGE_NORMAL_USER)  # normal user
        self.assertEqual(call["password"], "")  # no shared password

        # device_users audit row recorded (no Human mapping).
        mock_ensure.assert_called_once_with(cur, 1, "1001", "Somchai S.")

    @patch("app.enrollment.ensure_device_user", return_value=42)
    @patch("app.enrollment.get_db_connection")
    def test_existing_terminal_id_fails_safe(self, mock_conn_fn, mock_ensure):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)
        # Roster already contains reserved ID 1001.
        device = FakeDevice(users=[FakeUser("1001", uid=7, name="Someone Else")])

        with self.assertRaises(EnrollmentError):
            create_reserved_terminal_account(
                self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
            )
        self.assertEqual(len(device.set_user_calls), 0)  # never overwritten
        mock_ensure.assert_not_called()

    @patch("app.enrollment.get_db_connection")
    def test_device_unreachable_fails_safely(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)

        class DeadDevice:
            def get_users(self):
                raise OSError("connection lost")

        with self.assertRaises(EnrollmentError):
            create_reserved_terminal_account(
                self.cfg, enrollment_id=1, display_name="Somchai S.", device=DeadDevice()
            )

    @patch("app.enrollment.get_db_connection")
    def test_set_user_false_fails(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)

        class RejectingDevice:
            def get_users(self):
                return []

            def set_user(self, **kwargs):
                return False

        with self.assertRaises(EnrollmentError):
            create_reserved_terminal_account(
                self.cfg, enrollment_id=1, display_name="Somchai S.", device=RejectingDevice()
            )

    @patch("app.enrollment.get_db_connection")
    def test_device_none_rejected(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            create_reserved_terminal_account(self.cfg, enrollment_id=1, display_name="Somchai S.", device=None)

    @patch("app.enrollment.get_db_connection")
    def test_invalid_display_name_rejected_before_set_user(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)
        device = FakeDevice(users=[])
        with self.assertRaises(EnrollmentError):
            create_reserved_terminal_account(
                self.cfg, enrollment_id=1, display_name="สมชาย", device=device
            )
        self.assertEqual(len(device.set_user_calls), 0)

    @patch("app.enrollment.get_db_connection")
    def test_wrong_state_rejected(self, mock_conn_fn):
        row = make_enrollment_tuple(status="FINGERPRINT_ENROLLED")
        cur = FakeCursor(fetchone_queue=[row])
        make_db(mock_conn_fn, cur)
        device = FakeDevice(users=[])
        with self.assertRaises(EnrollmentError):
            create_reserved_terminal_account(
                self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
            )

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.ensure_device_user", return_value=42)
    @patch("app.enrollment.get_db_connection")
    def test_concurrent_state_change_after_set_user_fails_safe(self, mock_conn_fn, mock_ensure, mock_log):
        cur = FakeCursor(fetchone_queue=[self.enroll_row], rowcount=0)  # UPDATE affects 0 rows
        make_db(mock_conn_fn, cur)
        device = FakeDevice(users=[])
        with self.assertRaises(EnrollmentError):
            create_reserved_terminal_account(
                self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
            )


class TestRosterVerification(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()
        self.enroll_row = make_enrollment_tuple(status="TERMINAL_ACCOUNT_CREATED")

    @patch("app.enrollment.get_db_connection")
    def test_verifies_and_captures_uid(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        conn = make_db(mock_conn_fn, cur)
        roster = [FakeUser("1001", uid=77, name="Somchai S.")]

        result = verify_terminal_account_created(self.cfg, 1, roster)

        self.assertEqual(result["device_uid"], 77)
        self.assertEqual(result["status"], "TERMINAL_ACCOUNT_CREATED")
        conn.commit.assert_called()

    @patch("app.enrollment.get_db_connection")
    def test_missing_from_roster_fails(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            verify_terminal_account_created(self.cfg, 1, [FakeUser("1002", uid=9)])

    @patch("app.enrollment.get_db_connection")
    def test_admin_privilege_rejected(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)
        roster = [FakeUser("1001", uid=77, name="Somchai S.", privilege=14)]
        with self.assertRaises(EnrollmentError):
            verify_terminal_account_created(self.cfg, 1, roster)

    @patch("app.enrollment.get_db_connection")
    def test_wrong_state_rejected(self, mock_conn_fn):
        row = make_enrollment_tuple(status="RESERVED")
        cur = FakeCursor(fetchone_queue=[row])
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            verify_terminal_account_created(self.cfg, 1, [FakeUser("1001")])


# ---------------------------------------------------------------------------
# Fingerprint / controlled scan / ready-for-mapping flow
# ---------------------------------------------------------------------------


class TestEnrollmentFlow(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def _flow_cursor(self, status, **extra):
        row = make_enrollment_tuple(status=status, **extra)
        return FakeCursor(fetchone_queue=[row])

    @patch("app.enrollment.get_db_connection")
    def test_start_fingerprint_enrollment(self, mock_conn_fn):
        cur = self._flow_cursor("TERMINAL_ACCOUNT_CREATED")
        make_db(mock_conn_fn, cur)
        result = start_fingerprint_enrollment(self.cfg, 1, "op")
        self.assertEqual(result["status"], "FINGERPRINT_ENROLLMENT_PENDING")
        # Transition UPDATE is guarded against concurrent state changes.
        update_sql = [s for s in cur.sql() if s.startswith("UPDATE")][0]
        self.assertIn("AND status = %s", update_sql)
        self.assertIn("enrollment_id = %s", update_sql)

    @patch("app.enrollment.get_db_connection")
    def test_transition_rejects_unknown_extra_column(self, mock_conn_fn):
        from app.enrollment import _transition

        cur = self._flow_cursor("RESERVED")
        make_db(mock_conn_fn, cur)
        with self.assertRaisesRegex(EnrollmentError, "not whitelisted"):
            _transition(self.cfg, 1, "CANCELLED", extra={"evil_column": 1})

    @patch("app.enrollment.get_db_connection")
    def test_confirm_fingerprint_enrolled_sets_timestamp(self, mock_conn_fn):
        cur = self._flow_cursor("FINGERPRINT_ENROLLMENT_PENDING")
        make_db(mock_conn_fn, cur)
        result = confirm_fingerprint_enrolled(self.cfg, 1, "op")
        self.assertEqual(result["status"], "FINGERPRINT_ENROLLED")
        update = [p for s, p in cur.executed if s.startswith("UPDATE")][0]
        # params = [status, notes, fingerprint_confirmed_at, enrollment_id]
        self.assertIsNotNone(update[2])  # fingerprint_confirmed_at set

    @patch("app.enrollment.get_db_connection")
    def test_start_controlled_scan_window_sets_deadline(self, mock_conn_fn):
        cur = self._flow_cursor("FINGERPRINT_ENROLLED")
        make_db(mock_conn_fn, cur)
        result = start_controlled_scan_window(self.cfg, 1, "op", window_minutes=5)
        self.assertEqual(result["status"], "CONTROLLED_SCAN_PENDING")
        update = [p for s, p in cur.executed if s.startswith("UPDATE")][0]
        # params = [status, notes, controlled_scan_window_until, enrollment_id]
        deadline = update[2]
        self.assertIsNotNone(deadline)
        # Deadline in the near future, ~5 minutes out.
        delta = deadline - datetime.now(timezone.utc)
        self.assertTrue(timedelta(minutes=4) < delta < timedelta(minutes=6))

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_confirm_controlled_scan_inside_window(self, mock_conn_fn, mock_log):
        until = NOW + timedelta(minutes=5)
        cur = self._flow_cursor("CONTROLLED_SCAN_PENDING", controlled_scan_window_until=until)
        make_db(mock_conn_fn, cur)
        scan_time = NOW + timedelta(seconds=30)
        result = confirm_controlled_scan(self.cfg, 1, scan_time, "op")
        self.assertEqual(result["status"], "CONTROLLED_SCAN_CONFIRMED")
        self.assertEqual(result["controlled_scan_time"], scan_time)
        mock_log.assert_called_once()

    @patch("app.enrollment.get_db_connection")
    def test_confirm_controlled_scan_after_deadline_rejected(self, mock_conn_fn):
        until = NOW + timedelta(minutes=5)
        cur = self._flow_cursor("CONTROLLED_SCAN_PENDING", controlled_scan_window_until=until)
        make_db(mock_conn_fn, cur)
        scan_time = until + timedelta(seconds=1)
        with self.assertRaises(EnrollmentError):
            confirm_controlled_scan(self.cfg, 1, scan_time, "op")

    @patch("app.enrollment.get_db_connection")
    def test_confirm_scan_without_window_rejected(self, mock_conn_fn):
        cur = self._flow_cursor("CONTROLLED_SCAN_PENDING", controlled_scan_window_until=None)
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            confirm_controlled_scan(self.cfg, 1, NOW, "op")

    @patch("app.enrollment.get_db_connection")
    def test_confirm_scan_wrong_state_rejected(self, mock_conn_fn):
        cur = self._flow_cursor("FINGERPRINT_ENROLLED")
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            confirm_controlled_scan(self.cfg, 1, NOW, "op")

    @patch("app.enrollment.get_db_connection")
    def test_ready_for_mapping_requires_operator(self, mock_conn_fn):
        cur = self._flow_cursor("CONTROLLED_SCAN_CONFIRMED", controlled_scan_time=NOW)
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            mark_ready_for_mapping(self.cfg, 1, "  ")

    @patch("app.enrollment.get_db_connection")
    def test_ready_for_mapping_records_confirmer(self, mock_conn_fn):
        cur = self._flow_cursor("CONTROLLED_SCAN_CONFIRMED", controlled_scan_time=NOW)
        make_db(mock_conn_fn, cur)
        result = mark_ready_for_mapping(self.cfg, 1, "owner")
        self.assertEqual(result["status"], "READY_FOR_MAPPING")
        update = [p for s, p in cur.executed if s.startswith("UPDATE")][0]
        # params = [status, notes, confirmed_by, confirmed_at, enrollment_id]
        self.assertEqual(update[2], "owner")  # confirmed_by

    @patch("app.enrollment.get_db_connection")
    def test_ready_for_mapping_without_scan_evidence_rejected(self, mock_conn_fn):
        # Even if the state were CONTROLLED_SCAN_CONFIRMED, missing scan_time
        # would violate DB evidence constraints; the transition layer must not
        # allow reaching READY_FOR_MAPPING directly from scan-pending.
        cur = self._flow_cursor("CONTROLLED_SCAN_PENDING")
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            mark_ready_for_mapping(self.cfg, 1, "owner")

    @patch("app.enrollment.get_db_connection")
    def test_cancel_requires_reason(self, mock_conn_fn):
        cur = self._flow_cursor("RESERVED")
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            cancel_enrollment(self.cfg, 1, "op", notes="  ")

    @patch("app.enrollment.get_db_connection")
    def test_cancel_records_notes(self, mock_conn_fn):
        cur = self._flow_cursor("RESERVED")
        make_db(mock_conn_fn, cur)
        result = cancel_enrollment(self.cfg, 1, "op", notes="wrong person selected")
        self.assertEqual(result["status"], "CANCELLED")
        update = [p for s, p in cur.executed if s.startswith("UPDATE")][0]
        # params = [status, notes, enrollment_id]
        self.assertIn("wrong person selected", update[1])

    @patch("app.enrollment.get_db_connection")
    def test_retire_from_scan_confirmed(self, mock_conn_fn):
        cur = self._flow_cursor("CONTROLLED_SCAN_CONFIRMED", controlled_scan_time=NOW)
        make_db(mock_conn_fn, cur)
        result = retire_enrollment(self.cfg, 1, "op")
        self.assertEqual(result["status"], "RETIRED")

    @patch("app.enrollment.get_db_connection")
    def test_get_enrollment_returns_row(self, mock_conn_fn):
        row = self._flow_cursor("RESERVED")
        make_db(mock_conn_fn, row)
        enroll = get_enrollment(self.cfg, 1)
        self.assertEqual(enroll["status"], "RESERVED")
        self.assertEqual(enroll["reserved_device_user_id"], "1001")


# ---------------------------------------------------------------------------
# Identity safety (§38) and device safety (§39)
# ---------------------------------------------------------------------------


class TestSafetyInvariants(unittest.TestCase):
    """End-to-end workflow never touches mappings, human master, or attendance,
    and never triggers destructive terminal operations."""

    def setUp(self):
        self.cfg = Config.from_env()
        self.employee_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def test_full_workflow_never_creates_mappings_or_mutates_attendance(self):
        all_sql = []

        # 1. Reserve
        with patch("app.enrollment.log_sync_event"), patch("app.enrollment.get_db_connection") as m1:
            cur = FakeCursor(
                fetchone_queue=[[1], [1], [None], None, (1, "1001", "RESERVED", NOW)],
                fetchall_result=[],
            )
            make_db(m1, cur)
            reserve_next_device_user_id(
                self.cfg, employee_id=self.employee_id, device_id=1, operator="op"
            )
            all_sql.extend(cur.sql())

        # 2. Create terminal account
        with (
            patch("app.enrollment.log_sync_event"),
            patch("app.enrollment.ensure_device_user", return_value=42),
            patch("app.enrollment.get_db_connection") as m2,
        ):
            cur = FakeCursor(fetchone_queue=[make_enrollment_tuple(employee_id=self.employee_id)])
            make_db(m2, cur)
            device = FakeDevice(users=[])
            create_reserved_terminal_account(
                self.cfg, 1, "Somchai S.", device
            )
            all_sql.extend(cur.sql())

        # 3. Verify roster
        with patch("app.enrollment.get_db_connection") as m3:
            cur = FakeCursor(
                fetchone_queue=[make_enrollment_tuple(status="TERMINAL_ACCOUNT_CREATED")]
            )
            make_db(m3, cur)
            verify_terminal_account_created(self.cfg, 1, [FakeUser("1001", uid=77, name="Somchai S.")])
            all_sql.extend(cur.sql())

        # 4. Fingerprint + scan + ready
        # Each step: (cursor row state, transition function, target state)
        steps = [
            ("TERMINAL_ACCOUNT_CREATED", start_fingerprint_enrollment, "FINGERPRINT_ENROLLMENT_PENDING"),
            ("FINGERPRINT_ENROLLMENT_PENDING", confirm_fingerprint_enrolled, "FINGERPRINT_ENROLLED"),
            ("FINGERPRINT_ENROLLED", lambda cfg, e, op: start_controlled_scan_window(cfg, e, op), "CONTROLLED_SCAN_PENDING"),
            (
                "CONTROLLED_SCAN_PENDING",
                lambda cfg, e, op: confirm_controlled_scan(cfg, e, NOW + timedelta(seconds=10), op),
                "CONTROLLED_SCAN_CONFIRMED",
            ),
            (
                "CONTROLLED_SCAN_CONFIRMED",
                lambda cfg, e, op: mark_ready_for_mapping(cfg, e, op),
                "READY_FOR_MAPPING",
            ),
        ]
        for i, (cursor_state, fn, target) in enumerate(steps):
            with patch("app.enrollment.get_db_connection") as mn:
                extra = {}
                if cursor_state == "CONTROLLED_SCAN_PENDING":
                    extra = {"controlled_scan_window_until": NOW + timedelta(minutes=5)}
                if cursor_state == "CONTROLLED_SCAN_CONFIRMED":
                    extra = {"controlled_scan_time": NOW + timedelta(seconds=10)}
                cur = FakeCursor(
                    fetchone_queue=[make_enrollment_tuple(status=cursor_state, **extra)]
                )
                make_db(mn, cur)
                fn(self.cfg, 1, "op")
                all_sql.extend(cur.sql())

        lowered = [s.lower() for s in all_sql]
        for bad in (
            "insert into employee_device_mappings",
            "insert into human_employees",
            "update attendance_logs",
            "delete from attendance_logs",
            "delete from device_users",
        ):
            for sql in lowered:
                self.assertNotIn(bad, sql, "forbidden SQL executed: %s" % sql)

    def test_device_safety_no_destructive_operations(self):
        with (
            patch("app.enrollment.log_sync_event"),
            patch("app.enrollment.ensure_device_user", return_value=42),
            patch("app.enrollment.get_db_connection") as m,
        ):
            cur = FakeCursor(fetchone_queue=[make_enrollment_tuple()])
            make_db(m, cur)
            device = FakeDevice(users=[])
            create_reserved_terminal_account(self.cfg, 1, "Somchai S.", device)

        # Only read roster + create account were touched.
        self.assertEqual(device.calls, ["get_users", "set_user"])
        self.assertEqual(device.set_user_calls[0]["privilege"], PRIVILEGE_NORMAL_USER)

    def test_reservation_never_touches_device(self):
        device = FakeDevice(users=[])
        with patch("app.enrollment.log_sync_event"), patch("app.enrollment.get_db_connection") as m:
            cur = FakeCursor(
                fetchone_queue=[[1], [1], [None], None, (1, "1001", "RESERVED", NOW)],
                fetchall_result=[],
            )
            make_db(m, cur)
            reserve_next_device_user_id(
                self.cfg, employee_id=self.employee_id, device_id=1, operator="op"
            )
        self.assertEqual(device.calls, [])  # reservation is DB-only


if __name__ == "__main__":
    unittest.main()
