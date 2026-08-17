"""
Narrow ADMIN-only controlled-scan evidence reconciliation.

PromptID: ADMS-ControlledScan-EvidenceBinding-018-Deploy

Covers app.enrollment.reconcile_controlled_scan_evidence — a one-time
correction path for enrollments whose controlled_scan_time was recorded
under the pre-018 estimate-based architecture (real-world case:
Enrollment #4, 138s off from its real attendance evidence). Re-verifies
all five canonical binding criteria inside the same transaction before
writing anything; never touches the terminal account, fingerprint,
attendance row, device_user, or any mapping.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.config import Config
from app.enrollment import (
    DEFAULT_CONTROLLED_SCAN_WINDOW_MINUTES,
    EnrollmentError,
    reconcile_controlled_scan_evidence,
)
from tests.test_enrollment import FakeCursor, make_db, make_enrollment_tuple

DEVICE_USER_PK = 29
ATTENDANCE_ID = 38
UNTIL = datetime(2026, 8, 17, 16, 46, 42, 293778, tzinfo=timezone.utc)
REAL_SCAN_TIME = datetime(2026, 8, 17, 16, 44, 18, tzinfo=timezone.utc)
OLD_ESTIMATE = datetime(2026, 8, 17, 16, 42, 0, tzinfo=timezone.utc)


class TestReconcileControlledScanEvidence(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def _row(self, **overrides):
        base = dict(
            status="READY_FOR_MAPPING",
            device_id=1,
            reserved_device_user_id="1004",
            controlled_scan_window_until=UNTIL,
            controlled_scan_time=OLD_ESTIMATE,
        )
        base.update(overrides)
        return make_enrollment_tuple(enrollment_id=4, **base)

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_happy_path_reconciles_and_emits_one_audit_event(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[
            self._row(),                                        # locked enrollment fetch
            (DEVICE_USER_PK, True, 1),                          # device_users
            (ATTENDANCE_ID, DEVICE_USER_PK, REAL_SCAN_TIME),    # attendance row
            None,                                                # no conflicting VERIFIED mapping
        ], fetchall_result=[(ATTENDANCE_ID,)])                  # no-competing-scan check
        make_db(mock_conn_fn, cur)

        result = reconcile_controlled_scan_evidence(self.cfg, 4, ATTENDANCE_ID, "admin")

        self.assertEqual(result["controlled_scan_time"], REAL_SCAN_TIME)
        self.assertEqual(result["controlled_attendance_id"], ATTENDANCE_ID)
        # Status is untouched by this operation.
        self.assertEqual(result["status"], "READY_FOR_MAPPING")

        update_sql, update_params = [
            (s, p) for s, p in cur.executed if s.startswith("UPDATE")
        ][0]
        self.assertIn("controlled_scan_time = %s", update_sql)
        self.assertNotIn("status", update_sql.split("SET")[1].split("WHERE")[0])
        self.assertEqual(update_params[0], REAL_SCAN_TIME)

        mock_log.assert_called_once()
        event_type, message = mock_log.call_args[0][1], mock_log.call_args[0][2]
        self.assertEqual(event_type, "ENROLLMENT_SCAN_EVIDENCE_RECONCILED")
        self.assertIn("enrollment_id=4", message)
        self.assertIn("attendance_id=38", message)

    @patch("app.enrollment.get_db_connection")
    def test_attendance_outside_reconstructed_window_rejected(self, mock_conn_fn):
        out_of_window = UNTIL + timedelta(minutes=10)
        cur = FakeCursor(fetchone_queue=[
            self._row(),
            (DEVICE_USER_PK, True, 1),
            (ATTENDANCE_ID, DEVICE_USER_PK, out_of_window),
        ])
        make_db(mock_conn_fn, cur)
        with self.assertRaisesRegex(EnrollmentError, "outside the reconstructed"):
            reconcile_controlled_scan_evidence(self.cfg, 4, ATTENDANCE_ID, "admin")

    @patch("app.enrollment.get_db_connection")
    def test_wrong_device_user_pk_rejected(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[
            self._row(),
            (DEVICE_USER_PK, True, 1),
            (ATTENDANCE_ID, 999, REAL_SCAN_TIME),  # mismatched device_user_pk
        ])
        make_db(mock_conn_fn, cur)
        with self.assertRaisesRegex(EnrollmentError, "mismatched terminal user"):
            reconcile_controlled_scan_evidence(self.cfg, 4, ATTENDANCE_ID, "admin")

    @patch("app.enrollment.get_db_connection")
    def test_inactive_device_user_rejected(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[
            self._row(),
            (DEVICE_USER_PK, False, 1),  # inactive
        ])
        make_db(mock_conn_fn, cur)
        with self.assertRaisesRegex(EnrollmentError, "inactive"):
            reconcile_controlled_scan_evidence(self.cfg, 4, ATTENDANCE_ID, "admin")

    @patch("app.enrollment.get_db_connection")
    def test_competing_scan_ambiguity_rejected(self, mock_conn_fn):
        cur = FakeCursor(
            fetchone_queue=[
                self._row(),
                (DEVICE_USER_PK, True, 1),
                (ATTENDANCE_ID, DEVICE_USER_PK, REAL_SCAN_TIME),
            ],
            fetchall_result=[(ATTENDANCE_ID,), (39,)],  # a second candidate exists
        )
        make_db(mock_conn_fn, cur)
        with self.assertRaisesRegex(EnrollmentError, "ambiguous evidence"):
            reconcile_controlled_scan_evidence(self.cfg, 4, ATTENDANCE_ID, "admin")

    @patch("app.enrollment.get_db_connection")
    def test_existing_verified_mapping_blocks_reconciliation(self, mock_conn_fn):
        cur = FakeCursor(
            fetchone_queue=[
                self._row(),
                (DEVICE_USER_PK, True, 1),
                (ATTENDANCE_ID, DEVICE_USER_PK, REAL_SCAN_TIME),
                (1,),  # conflicting VERIFIED mapping found
            ],
            fetchall_result=[(ATTENDANCE_ID,)],
        )
        make_db(mock_conn_fn, cur)
        with self.assertRaisesRegex(EnrollmentError, "conflicting VERIFIED mapping"):
            reconcile_controlled_scan_evidence(self.cfg, 4, ATTENDANCE_ID, "admin")

    @patch("app.enrollment.get_db_connection")
    def test_no_recorded_window_rejected(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[
            self._row(controlled_scan_window_until=None, controlled_scan_time=None),
        ])
        make_db(mock_conn_fn, cur)
        with self.assertRaisesRegex(EnrollmentError, "nothing to reconcile"):
            reconcile_controlled_scan_evidence(self.cfg, 4, ATTENDANCE_ID, "admin")

    def test_operator_required(self):
        with self.assertRaises(EnrollmentError):
            reconcile_controlled_scan_evidence(self.cfg, 4, ATTENDANCE_ID, "  ")

    def test_endpoint_is_admin_only_and_write_session_gated(self):
        import inspect

        import app.api.routers.enrollments as router_mod

        src = inspect.getsource(router_mod)
        idx = src.find("reconcile-scan-evidence")
        segment = src[idx:idx + 400]
        self.assertIn("ROLES_ADMIN_ONLY", segment)
        self.assertIn("require_writes", segment)
        self.assertIn("require_write_session", segment)

    def test_endpoint_never_touches_terminal_fingerprint_attendance_mapping(self):
        import inspect

        import app.enrollment as enrollment_mod

        src = inspect.getsource(enrollment_mod.reconcile_controlled_scan_evidence)
        self.assertNotIn("device.set_user", src)
        self.assertNotIn("fingerprint_confirmed_at = ", src)
        self.assertNotIn("UPDATE attendance_logs", src)
        self.assertNotIn("UPDATE device_users", src)
        self.assertNotIn("INSERT INTO employee_device_mappings", src)


if __name__ == "__main__":
    unittest.main()
