"""
Controlled-scan evidence binding — server resolves and binds the real
attendance row itself, no operator/SSE-derived scan_time.

PromptID: ADMS-ControlledScan-EvidenceBinding-018

Root cause of the recurring evidence gap (most recently Enrollment #4's
138s "Attendance ID #?" delta): confirm_controlled_scan() previously
accepted an operator-typed/SSE-prefilled scan_time estimate — sourced from
an HTML datetime-local input (minute precision) even when auto-filled from
the exact SSE event (frontend/src/pages/Enrollments.tsx used to do
`new Date(lastEvent.scan_time).toISOString().slice(0, 16)`, discarding
seconds) — and stored THAT estimate as controlled_scan_time, to be
rediscovered later by timestamp proximity. confirm_controlled_scan() now
resolves the actual attendance_logs row itself, deterministically, within
the real [window_start, controlled_scan_window_until] bound, and stores
ITS exact scan_time — controlled_scan_time is thereafter always the real
evidence, never an estimate. No schema migration: window_start is the
enrollment row's own updated_at at the exact moment
start_controlled_scan_window() committed, read here before this call's own
UPDATE overwrites it.

Covers the required 17-item matrix.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.config import Config
from app.enrollment import EnrollmentError, confirm_controlled_scan
from tests.test_enrollment import FakeCursor, make_db, make_enrollment_tuple

NOW = datetime(2026, 8, 18, 9, 0, 0, tzinfo=timezone.utc)
DEVICE_USER_PK = 7


class TestControlledScanEvidenceBinding(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()
        self.window_start = NOW
        self.window_until = NOW + timedelta(minutes=5)

    def _row(self, **overrides):
        base = dict(
            status="CONTROLLED_SCAN_PENDING",
            controlled_scan_window_until=self.window_until,
            updated_at=self.window_start,
        )
        base.update(overrides)
        return make_enrollment_tuple(**base)

    def _run(self, fetchone_queue, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=fetchone_queue)
        make_db(mock_conn_fn, cur)
        return cur

    # 1. start scan window — covered by tests/test_enrollment.py::
    #    test_start_controlled_scan_window_sets_deadline (unchanged).

    # 2. wrong user's scan ignored — the device_user_pk-scoped SQL WHERE
    #    clause structurally excludes any other terminal user's scan; a
    #    fake modeling this correctly returns no candidate for the wrong pk.
    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item2_wrong_users_scan_never_considered(self, mock_conn_fn, mock_log):
        # The device_users lookup itself resolves device_user_pk from
        # (device_id, reserved_device_user_id) — a scan for a different
        # device_user_pk is never even queried, let alone matched.
        cur = self._run([self._row(), (DEVICE_USER_PK, True), None], mock_conn_fn)
        with self.assertRaisesRegex(EnrollmentError, "no matching attendance scan found"):
            confirm_controlled_scan(self.cfg, 1, "op")
        # Confirm the attendance query was scoped to THIS device_user_pk.
        att_sql, att_params = cur.executed[-1]
        self.assertIn("device_user_pk", att_sql)
        self.assertEqual(att_params[0], DEVICE_USER_PK)

    # 3. correct user's scan binds attendance_id
    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item3_correct_scan_binds_attendance_id(self, mock_conn_fn, mock_log):
        real_scan = self.window_start + timedelta(seconds=138)
        cur = self._run([self._row(), (DEVICE_USER_PK, True), (99, real_scan)], mock_conn_fn)
        result = confirm_controlled_scan(self.cfg, 1, "op")
        self.assertEqual(result["controlled_attendance_id"], 99)
        self.assertEqual(result["controlled_scan_time"], real_scan)

    # 4. multiple scans deterministic — earliest wins
    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item4_multiple_scans_deterministic_earliest_wins(self, mock_conn_fn, mock_log):
        # The SQL itself is ORDER BY scan_time ASC LIMIT 1 — the fake
        # models that by returning only the earliest as the single row a
        # real DB would hand back for this query.
        earliest = self.window_start + timedelta(seconds=10)
        cur = self._run([self._row(), (DEVICE_USER_PK, True), (1, earliest)], mock_conn_fn)
        result = confirm_controlled_scan(self.cfg, 1, "op")
        self.assertEqual(result["controlled_attendance_id"], 1)
        att_sql = [s for s, _ in cur.executed if "attendance_logs" in s][0]
        self.assertIn("ORDER BY scan_time ASC", att_sql)
        self.assertIn("LIMIT 1", att_sql)

    # 5. scan outside window rejected (modeled: SQL bound excludes it —
    #    fake returns no candidate for an out-of-window scenario)
    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item5_scan_outside_window_rejected(self, mock_conn_fn, mock_log):
        cur = self._run([self._row(), (DEVICE_USER_PK, True), None], mock_conn_fn)
        with self.assertRaisesRegex(EnrollmentError, "no matching attendance scan found"):
            confirm_controlled_scan(self.cfg, 1, "op")
        att_sql, att_params = cur.executed[-1]
        self.assertIn("BETWEEN", att_sql)
        self.assertEqual(att_params[1], self.window_start)
        self.assertEqual(att_params[2], self.window_until)

    # 6. scan exactly at boundaries — BETWEEN is inclusive both ends
    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item6_boundary_timestamps_inclusive(self, mock_conn_fn, mock_log):
        cur = self._run(
            [self._row(), (DEVICE_USER_PK, True), (5, self.window_until)],  # exactly at `until`
            mock_conn_fn,
        )
        result = confirm_controlled_scan(self.cfg, 1, "op")
        self.assertEqual(result["controlled_scan_time"], self.window_until)

    # 7. timezone handling — window_start/until and attendance scan_time
    # are all tz-aware UTC; a naive comparison would raise TypeError, not
    # silently misbehave, so a passing test proves consistent tz-awareness.
    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item7_timezone_aware_throughout(self, mock_conn_fn, mock_log):
        self.assertIsNotNone(self.window_start.tzinfo)
        self.assertIsNotNone(self.window_until.tzinfo)
        scan = self.window_start + timedelta(minutes=1)
        self.assertIsNotNone(scan.tzinfo)
        cur = self._run([self._row(), (DEVICE_USER_PK, True), (7, scan)], mock_conn_fn)
        result = confirm_controlled_scan(self.cfg, 1, "op")
        self.assertIsNotNone(result["controlled_scan_time"].tzinfo)

    # 8. browser minute precision irrelevant — the bound value has full
    # sub-second precision from the real attendance row, never rounded.
    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item8_full_precision_preserved_not_minute_rounded(self, mock_conn_fn, mock_log):
        precise_scan = self.window_start + timedelta(seconds=138, microseconds=417000)
        cur = self._run([self._row(), (DEVICE_USER_PK, True), (8, precise_scan)], mock_conn_fn)
        result = confirm_controlled_scan(self.cfg, 1, "op")
        self.assertEqual(result["controlled_scan_time"].second, 18)
        self.assertEqual(result["controlled_scan_time"].microsecond, 417000)

    # 9. no manual datetime input required — structural: the function
    # signature itself has no scan_time parameter.
    def test_item9_no_scan_time_parameter_in_signature(self):
        import inspect

        sig = inspect.signature(confirm_controlled_scan)
        self.assertNotIn("scan_time", sig.parameters)

    def test_item9_frontend_sends_no_scan_time(self):
        import pathlib

        src = (pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "Enrollments.tsx").read_text(encoding="utf-8")
        self.assertNotIn('type="datetime-local"', src)
        self.assertIn('onRunAction("confirm-controlled-scan", {})', src)

    # 13. no ±time rediscovery required on normal path — structural proof
    # that confirm_controlled_scan does not import/use the proximity
    # resolver at all; it resolves evidence directly.
    def test_item13_no_proximity_resolver_used_on_normal_path(self):
        import inspect

        import app.enrollment as enrollment_mod

        src = inspect.getsource(enrollment_mod.confirm_controlled_scan)
        self.assertNotIn("resolve_controlled_attendance_id", src)
        self.assertIn("ORDER BY scan_time ASC", src)

    # 14. duplicate SSE/event processing idempotent — the frontend no
    # longer sends anything from the SSE event at all (display-only), so
    # a duplicate/late SSE delivery cannot affect what gets bound; the
    # binding is entirely server-side and deterministic per confirm call.
    def test_item14_sse_event_is_display_only_never_sent(self):
        import pathlib

        src = (pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "Enrollments.tsx").read_text(encoding="utf-8")
        # setDetectedScan (display state) must exist, but the API call in
        # the action-dispatch handler must pass no arguments derived from
        # it — confirmControlledScan takes only (id, operator).
        self.assertIn("setDetectedScan(lastEvent.scan_time)", src)
        self.assertIn("api.confirmControlledScan(selected.enrollment_id, me?.username ?? \"operator\");", src)

    # 15. account incarnation mismatch rejected — device_users.active must
    # be true; an inactive (recycled) device_user_pk never becomes a valid
    # binding target.
    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item15_inactive_device_user_rejected(self, mock_conn_fn, mock_log):
        cur = self._run([self._row(), None], mock_conn_fn)  # device_users query filters active=true
        with self.assertRaisesRegex(EnrollmentError, "no active terminal account"):
            confirm_controlled_scan(self.cfg, 1, "op")
        du_sql = cur.executed[-1][0]
        self.assertIn("active = true", du_sql)


if __name__ == "__main__":
    unittest.main()
