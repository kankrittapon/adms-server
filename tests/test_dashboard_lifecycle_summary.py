"""
Dashboard lifecycle-summary consistency — ADMS-Dashboard-LifecycleSummary-021C.

Confirmed root cause: app/api/repository.py::dashboard_summary() grouped
enrollments by raw `status` (`GROUP BY status`), independently of the
canonical lifecycle_state derivation introduced in 021B for Enrollment
Workspace/Personnel/Terminal Management/Mapping — so the Dashboard kept
counting already-COMPLETED and REMOVED_FROM_TERMINAL enrollments (whose
stored `status` column is still READY_FOR_MAPPING) as "Ready to Confirm
Identity," disagreeing with every other page.

Fix reuses _derive_enrollment_lifecycle_state() directly — no duplicated
CASE logic.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.api.repository import dashboard_summary
from app.config import Config

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


class FakeCursor:
    """Mirrors the _fetch_all contract: description + tuple rows, built
    from dict rows in column order (see tests/test_enrollment_lifecycle_state.py
    for the same pattern)."""

    def __init__(self, dashboard_row, enrollment_rows):
        self._dashboard_row = dashboard_row
        self._enrollment_rows = enrollment_rows
        self._call_index = 0

    def execute(self, sql, params=None):
        self._current_sql = sql
        self._is_enrollment_query = "device_user_enrollments" in sql and "GROUP BY" not in sql

    def fetchall(self):
        if self._call_index == 0:
            self._call_index += 1
            return [tuple(self._dashboard_row.values())]
        return [tuple(r.values()) for r in self._enrollment_rows]

    @property
    def description(self):
        if self._call_index == 0:
            return [(k,) for k in self._dashboard_row.keys()]
        return [(k,) for k in (self._enrollment_rows[0].keys() if self._enrollment_rows else [])]


def _make_db(mock_conn_fn, cur):
    mock_conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__.return_value = cur
    cur_ctx.__exit__.return_value = None
    mock_conn.cursor.return_value = cur_ctx
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    mock_ctx.__exit__.return_value = None
    mock_conn_fn.return_value = mock_ctx


_DASHBOARD_SCALAR_ROW = {
    "humans_total": 120,
    "humans_production_eligible": 84,
    "humans_excluded": 36,
    "devices_total": 1,
    "devices_active": 1,
    "device_users_total": 2,
    "device_users_active": 1,
    "device_users_unmapped": 0,
    "attendance_total": 14,
    "attendance_today": 0,
    "attendance_unattributed": 7,
    "mappings_total": 2,
    "mappings_verified_active": 1,
}


def _enrollment_row(status, device_user_active, verified_mapping_status, mapping_valid_to):
    return {
        "status": status,
        "device_user_active": device_user_active,
        "verified_mapping_status": verified_mapping_status,
        "mapping_valid_to": mapping_valid_to,
    }


class TestDashboardLifecycleSummary(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.api.repository.get_db_connection")
    def test_item1_completed_excluded_from_active_count(self, mock_conn_fn):
        """Enrollment #1: raw READY_FOR_MAPPING, open VERIFIED mapping,
        active device account => COMPLETED => NOT counted as active."""
        rows = [_enrollment_row("READY_FOR_MAPPING", True, "VERIFIED", None)]
        cur = FakeCursor(_DASHBOARD_SCALAR_ROW, rows)
        _make_db(mock_conn_fn, cur)
        result = dashboard_summary(self.cfg)
        self.assertEqual(result["enrollments_active_count"], 0)
        self.assertEqual(result["enrollments_by_lifecycle_state"], {"COMPLETED": 1})
        self.assertNotIn("IN_PROGRESS", result["enrollments_by_lifecycle_state"])

    @patch("app.api.repository.get_db_connection")
    def test_item2_removed_from_terminal_excluded_from_active_count(self, mock_conn_fn):
        """Enrollment #4 (Pimai/1004): raw READY_FOR_MAPPING, inactive
        device_user, closed mapping => REMOVED_FROM_TERMINAL => NOT active."""
        rows = [_enrollment_row("READY_FOR_MAPPING", False, "VERIFIED", NOW)]
        cur = FakeCursor(_DASHBOARD_SCALAR_ROW, rows)
        _make_db(mock_conn_fn, cur)
        result = dashboard_summary(self.cfg)
        self.assertEqual(result["enrollments_active_count"], 0)
        self.assertEqual(result["enrollments_by_lifecycle_state"], {"REMOVED_FROM_TERMINAL": 1})

    @patch("app.api.repository.get_db_connection")
    def test_item3_genuinely_unfinished_is_included(self, mock_conn_fn):
        rows = [_enrollment_row("FINGERPRINT_ENROLLED", None, None, None)]
        cur = FakeCursor(_DASHBOARD_SCALAR_ROW, rows)
        _make_db(mock_conn_fn, cur)
        result = dashboard_summary(self.cfg)
        self.assertEqual(result["enrollments_active_count"], 1)
        self.assertEqual(result["enrollments_by_lifecycle_state"], {"IN_PROGRESS": 1})

    @patch("app.api.repository.get_db_connection")
    def test_item4_cancelled_excluded(self, mock_conn_fn):
        rows = [_enrollment_row("CANCELLED", None, None, None)]
        cur = FakeCursor(_DASHBOARD_SCALAR_ROW, rows)
        _make_db(mock_conn_fn, cur)
        result = dashboard_summary(self.cfg)
        self.assertEqual(result["enrollments_active_count"], 0)
        self.assertEqual(result["enrollments_by_lifecycle_state"], {"CANCELLED": 1})

    @patch("app.api.repository.get_db_connection")
    def test_item5_pimai_1004_shape_matches_real_production_facts(self, mock_conn_fn):
        """The exact real production mix: enrollment #1 COMPLETED, #2/#3
        CANCELLED, #4 REMOVED_FROM_TERMINAL — active count must be 0,
        matching the Enrollment Workspace's empty Active Queue."""
        rows = [
            _enrollment_row("READY_FOR_MAPPING", True, "VERIFIED", None),  # #1 -> COMPLETED
            _enrollment_row("CANCELLED", None, None, None),  # #2
            _enrollment_row("CANCELLED", None, None, None),  # #3
            _enrollment_row("READY_FOR_MAPPING", False, "VERIFIED", NOW),  # #4 -> REMOVED_FROM_TERMINAL
        ]
        cur = FakeCursor(_DASHBOARD_SCALAR_ROW, rows)
        _make_db(mock_conn_fn, cur)
        result = dashboard_summary(self.cfg)
        self.assertEqual(result["enrollments_active_count"], 0)
        self.assertEqual(
            result["enrollments_by_lifecycle_state"],
            {"COMPLETED": 1, "CANCELLED": 2, "REMOVED_FROM_TERMINAL": 1},
        )

    def test_item6_no_duplicated_lifecycle_logic(self):
        """dashboard_summary must call the same canonical helper 021B
        introduced, not reimplement lifecycle CASE logic independently."""
        import inspect

        import app.api.repository as repo

        source = inspect.getsource(repo.dashboard_summary)
        self.assertIn("_derive_enrollment_lifecycle_state", source)
        self.assertNotIn("CASE WHEN", source.upper())

    def test_no_raw_status_group_by_remains(self):
        # Only the docstring/comment may mention the old query shape (as
        # history); the actual executed SQL string must not contain it.
        import inspect

        import app.api.repository as repo

        source = inspect.getsource(repo.dashboard_summary)
        code_lines = [
            line for line in source.splitlines() if not line.strip().startswith("#")
        ]
        code_only = "\n".join(code_lines)
        self.assertNotIn("GROUP BY status", code_only)
        self.assertNotIn("GROUP BY e.status", code_only)


if __name__ == "__main__":
    unittest.main()
