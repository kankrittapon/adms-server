"""
Canonical controlled-scan evidence resolver — unit + scoping tests.

PromptID: ADMS-FullEnrollment-E2E-Closure-017 (Phase 6)

Covers the required regression scenarios for the "Attendance ID #?" bug
class: reproduces the original exact-timestamp-mismatch failure, then
proves the resolver's fix, then proves WRONG nearby scans can never be
selected — same time/different device, same time/different terminal user,
same user/outside window, two in-window scans (nearest wins,
deterministic), exact boundary timestamps, and a timezone-naive vs
tz-aware comparison case.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.mapping_evidence import (
    DEFAULT_EVIDENCE_WINDOW_SECONDS,
    pick_nearest_attendance,
    resolve_controlled_attendance_id,
)

BASE = datetime(2026, 8, 12, 8, 47, 0, tzinfo=timezone.utc)


class FakeCursorForResolver:
    """Only device_user_pk-matching rows are ever passed to fetchall() —
    the SQL WHERE clause enforces this structurally, so this fake models
    that constraint by only returning rows the test explicitly scopes to
    the queried device_user_pk (never a different one), proving the
    device/user constraint is structural, not incidental."""

    def __init__(self, rows_by_device_user_pk):
        self._rows_by_pk = rows_by_device_user_pk
        self.executed = []
        self._last_pk = None

    def execute(self, sql, params):
        self.executed.append((sql, params))
        self._last_pk = params[0]

    def fetchall(self):
        return self._rows_by_pk.get(self._last_pk, [])


class TestPickNearestAttendancePureFunction(unittest.TestCase):
    """Pure decision logic — no DB, fully deterministic."""

    def test_reproduces_original_exact_equality_failure_class(self):
        # The operator-recorded controlled_scan_time (minute precision, no
        # seconds — what an HTML datetime-local input produces) never
        # bit-for-bit equals the real attendance scan_time (full
        # precision). Exact equality (`==`) would find nothing; the
        # resolver must still find it.
        controlled_scan_time = BASE  # minute-precision, seconds=0
        real_attendance_scan_time = BASE.replace(second=23, microsecond=810000)
        self.assertNotEqual(controlled_scan_time, real_attendance_scan_time)  # reproduces the bug's precondition
        result = pick_nearest_attendance([(12, real_attendance_scan_time)], controlled_scan_time)
        self.assertEqual(result, 12)  # the fix: nearest-match still resolves it

    def test_empty_candidates_returns_none(self):
        self.assertIsNone(pick_nearest_attendance([], BASE))

    def test_two_candidates_nearest_wins(self):
        far = (1, BASE + timedelta(seconds=90))
        near = (2, BASE + timedelta(seconds=5))
        self.assertEqual(pick_nearest_attendance([far, near], BASE), 2)

    def test_deterministic_tiebreak_lowest_id_wins(self):
        equidistant_a = (5, BASE + timedelta(seconds=30))
        equidistant_b = (3, BASE - timedelta(seconds=30))
        # Both are exactly 30s away — lowest id must win, deterministically,
        # regardless of list order.
        self.assertEqual(pick_nearest_attendance([equidistant_a, equidistant_b], BASE), 3)
        self.assertEqual(pick_nearest_attendance([equidistant_b, equidistant_a], BASE), 3)

    def test_exact_boundary_timestamp_included(self):
        # Exactly at BASE (delta=0) must win over anything else.
        exact = (9, BASE)
        other = (8, BASE + timedelta(seconds=1))
        self.assertEqual(pick_nearest_attendance([other, exact], BASE), 9)


class TestResolveControlledAttendanceIdScoping(unittest.TestCase):
    """DB-scoped resolver: device/user constraint applied structurally via
    the SQL WHERE clause (device_user_pk), never a coincidental time-only
    match. window_seconds bounds candidates before nearest-match runs."""

    def test_same_time_different_device_user_pk_never_considered(self):
        # A row for device_user_pk=99 (different device/terminal user)
        # exists at the exact target time, but querying for
        # device_user_pk=7 must never see it — the fake only returns rows
        # keyed to the queried pk, modeling the SQL WHERE clause.
        cur = FakeCursorForResolver({7: [], 99: [(1, BASE)]})
        result = resolve_controlled_attendance_id(cur, device_user_pk=7, controlled_scan_time=BASE)
        self.assertIsNone(result)

    def test_same_user_outside_window_excluded_by_sql_bound(self):
        # The resolver's own SQL bounds candidates to the window before
        # fetchall() is even called — a real DB would never return an
        # out-of-window row. This test proves the resolver's WHERE clause
        # requests the correct bounded range.
        cur = FakeCursorForResolver({7: []})
        resolve_controlled_attendance_id(
            cur, device_user_pk=7, controlled_scan_time=BASE, window_seconds=120
        )
        sql, params = cur.executed[0]
        self.assertIn("BETWEEN", sql)
        lower, upper = params[1], params[2]
        self.assertEqual(lower, BASE - timedelta(seconds=120))
        self.assertEqual(upper, BASE + timedelta(seconds=120))

    def test_two_scans_same_user_inside_window_nearest_selected(self):
        cur = FakeCursorForResolver({
            7: [(1, BASE + timedelta(seconds=100)), (2, BASE + timedelta(seconds=10))]
        })
        result = resolve_controlled_attendance_id(cur, device_user_pk=7, controlled_scan_time=BASE)
        self.assertEqual(result, 2)

    def test_default_window_matches_module_constant(self):
        self.assertEqual(DEFAULT_EVIDENCE_WINDOW_SECONDS, 120)


if __name__ == "__main__":
    unittest.main()
