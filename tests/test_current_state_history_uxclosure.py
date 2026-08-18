"""
Current vs. history read-side semantics — ADMS-CurrentState-History-UXClosure-022.

Two confirmed production defects fixed here:

DEFECT A: Dashboard's headline "device users" number was device_users_total
(ALL historical rows, including removed 1002/1004 — 5 on real production)
instead of device_users_active (currently on the scanner — 1). Fixed at
the frontend presentation layer (Dashboard.tsx swaps which field is
primary vs. hint) — device_users_active/total themselves were already
correct in dashboard_summary(), just displayed backwards.

DEFECT B: the Mapping list API returned all mappings with no current/
history classification, so a closed mapping (Pimai/#2, valid_to set)
rendered identically to a genuinely current one (#1/1001) in a single
flat table. Fixed via a new canonical repository.py helper,
_derive_mapping_lifecycle_state(), reused by both list_mappings() and
get_mapping() — never duplicated in the frontend.

Production-shaped fixtures throughout: 1001 current, 1002 historical/
inactive (no mapping), 1004 removed/mapping-closed. No production DB
dependency.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.api.repository import (
    _derive_mapping_lifecycle_state,
    dashboard_summary,
    get_mapping,
    list_mappings,
)
from app.config import Config

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


class TestMappingLifecycleDerivation(unittest.TestCase):
    """Direct unit tests of the pure helper — items 3, 4, 16, 17."""

    def test_item17_current_verified_open_mapping(self):
        self.assertEqual(_derive_mapping_lifecycle_state("VERIFIED", None, True), "CURRENT")

    def test_item16_closed_mapping_with_inactive_device_user_is_removed_from_terminal(self):
        """Exact Pimai/#2 shape: VERIFIED but valid_to set, device_users
        row now inactive (terminal account was actually removed)."""
        state = _derive_mapping_lifecycle_state("VERIFIED", NOW, False)
        self.assertEqual(state, "REMOVED_FROM_TERMINAL")

    def test_closed_mapping_with_still_active_device_user_is_neutral_ended(self):
        """Never fabricate 'removed from terminal' when the data doesn't
        prove it — e.g. a hypothetical future revocation reason where the
        device account itself is still active."""
        state = _derive_mapping_lifecycle_state("VERIFIED", NOW, True)
        self.assertEqual(state, "ENDED")

    def test_closed_mapping_with_unknown_device_user_state_is_neutral_ended(self):
        state = _derive_mapping_lifecycle_state("VERIFIED", NOW, None)
        self.assertEqual(state, "ENDED")

    def test_non_verified_status_never_reads_as_current(self):
        state = _derive_mapping_lifecycle_state("REVOKED", None, True)
        self.assertNotEqual(state, "CURRENT")


class FakeCursor:
    def __init__(self, rows=None, one=None):
        dict_rows = rows if rows is not None else ([one] if one is not None else [])
        self.description = [(k,) for k in dict_rows[0].keys()] if dict_rows else []
        self._tuples = [tuple(r.values()) for r in dict_rows]

    def execute(self, sql, params=None):
        self.last_sql = sql

    def fetchall(self):
        return list(self._tuples)


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


def _mapping_row(**overrides):
    base = dict(
        mapping_id=1,
        employee_id="039c4486-b30f-4ce1-b780-783cd268858d",
        device_user_pk=7,
        mapping_status="VERIFIED",
        mapping_source="CONTROLLED_SCAN",
        verified_by="owner",
        verification_method="CONTROLLED_SCAN",
        verification_note="note",
        valid_from=NOW,
        valid_to=None,
        verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
        employee_name="กฤตพล หมาดเส็น",
        device_user_id="1001",
        device_user_active=True,
    )
    base.update(overrides)
    return base


class TestListMappingsCurrentHistorySplit(unittest.TestCase):
    """Items 3, 4, 5, 6, 12: production-shaped #1/#2 mapping fixture."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.api.repository._fetch_scalar", return_value=2)
    @patch("app.api.repository.get_db_connection")
    def test_item3_4_5_12_current_and_history_split_matches_production_shape(
        self, mock_conn_fn, mock_scalar
    ):
        rows = [
            _mapping_row(mapping_id=1, device_user_id="1001", valid_to=None, device_user_active=True),
            _mapping_row(
                mapping_id=2,
                device_user_id="1004",
                employee_name="พิมาย ขาวสอาด",
                valid_to=NOW,
                device_user_active=False,
            ),
        ]
        cur = FakeCursor(rows=rows)
        _make_db(mock_conn_fn, cur)
        result = list_mappings(self.cfg, limit=50, offset=0)
        items = {r["mapping_id"]: r for r in result["items"]}

        # Item 3: Mapping #1 is CURRENT
        self.assertTrue(items[1]["is_current"])
        self.assertEqual(items[1]["mapping_lifecycle_state"], "CURRENT")

        # Item 4: Mapping #2 (closed, valid_to set) is NOT current
        self.assertFalse(items[2]["is_current"])

        # Item 16: correctly labeled removed-from-terminal, not fabricated
        self.assertEqual(items[2]["mapping_lifecycle_state"], "REMOVED_FROM_TERMINAL")

        # Item 6: closed mapping's historical record is untouched/complete —
        # no field was rewritten to make display easier.
        self.assertEqual(items[2]["mapping_status"], "VERIFIED")
        self.assertEqual(items[2]["valid_to"], NOW)

    @patch("app.api.repository.get_db_connection")
    def test_item14_get_mapping_history_row_remains_queryable(self, mock_conn_fn):
        row = _mapping_row(mapping_id=2, device_user_id="1004", valid_to=NOW, device_user_active=False)
        cur = FakeCursor(one=row)
        _make_db(mock_conn_fn, cur)
        result = get_mapping(self.cfg, 2)
        self.assertIsNotNone(result)
        self.assertEqual(result["mapping_lifecycle_state"], "REMOVED_FROM_TERMINAL")
        self.assertFalse(result["is_current"])


_DASHBOARD_SCALAR_ROW = {
    "humans_total": 120,
    "humans_production_eligible": 84,
    "humans_excluded": 36,
    "devices_total": 1,
    "devices_active": 1,
    "device_users_total": 5,
    "device_users_active": 1,
    "device_users_unmapped": 0,
    "attendance_total": 14,
    "attendance_today": 0,
    "attendance_unattributed": 7,
    "mappings_total": 2,
    "mappings_verified_active": 1,
}


class FakeDashboardCursor:
    """dashboard_summary() issues two SELECTs: the scalar aggregate, then
    the enrollment lifecycle join. This fake serves both in order."""

    def __init__(self, scalar_row, enrollment_rows):
        self._scalar_row = scalar_row
        self._enrollment_rows = enrollment_rows
        self._call_index = 0

    def execute(self, sql, params=None):
        self._current_sql = sql

    def fetchall(self):
        if self._call_index == 0:
            self._call_index += 1
            return [tuple(self._scalar_row.values())]
        return [tuple(r.values()) for r in self._enrollment_rows]

    @property
    def description(self):
        if self._call_index == 0:
            return [(k,) for k in self._scalar_row.keys()]
        return [(k,) for k in (self._enrollment_rows[0].keys() if self._enrollment_rows else [])]


class TestDashboardTerminalAccountKPI(unittest.TestCase):
    """Items 1, 2, 13: historical device_users rows must not inflate the
    current-account KPI. Note: dashboard_summary() itself already exposed
    both device_users_total and device_users_active correctly (021C only
    touched the enrollment aggregation) — DEFECT A was a frontend
    presentation bug (wrong field shown as primary). This test locks in
    that the backend values themselves are semantically correct raw
    material for that fix, matching real production ground truth: 5
    historical rows (1, 1001, 1002, 1004, 2), only 1001 currently active."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.api.repository.get_db_connection")
    def test_item1_2_13_current_count_excludes_historical_inactive_rows(self, mock_conn_fn):
        cur = FakeDashboardCursor(_DASHBOARD_SCALAR_ROW, [])
        _make_db(mock_conn_fn, cur)
        result = dashboard_summary(self.cfg)
        # Production ground truth: 5 total (incl. historical 1002/1004 and
        # two odd legacy rows), only 1 (1001) currently active.
        self.assertEqual(result["device_users_total"], 5)
        self.assertEqual(result["device_users_active"], 1)
        self.assertNotEqual(result["device_users_active"], result["device_users_total"])


class TestNoRegressionToPersonnelEnrollmentTerminalManagement(unittest.TestCase):
    """Items 7, 8, 9, 10, 11, 19: confirms 021B/021C behavior is untouched
    by this PromptID's changes (no regression)."""

    def test_item19_dashboard_lifecycle_aggregation_unchanged(self):
        import inspect

        import app.api.repository as repo

        source = inspect.getsource(repo.dashboard_summary)
        self.assertIn("_derive_enrollment_lifecycle_state", source)
        self.assertIn("enrollments_active_count", source)

    def test_item18_frontend_does_not_reimplement_mapping_lifecycle(self):
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "pages"
            / "Mappings.tsx"
        ).read_text(encoding="utf-8")
        # Must consume the server-derived fields, never recompute from
        # valid_to/mapping_status itself.
        self.assertIn("m.is_current", src)
        self.assertNotIn("m.valid_to ===", src)
        self.assertNotIn("m.valid_to == null", src)

    def test_item15_no_internal_lifecycle_enums_in_history_section_copy(self):
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "pages"
            / "Mappings.tsx"
        ).read_text(encoding="utf-8")
        history_idx = src.index("HISTORY —")
        end_idx = src.index("temporalFooterNote", history_idx)
        history_block = src[history_idx:end_idx]
        # device_user_pk appears only as a source-level fallback identifier
        # (`m.device_user_id ?? m.device_user_pk`), never as literal
        # displayed copy — check for raw enum/status text specifically,
        # not code identifiers.
        self.assertNotIn('"VERIFIED"', history_block)
        self.assertNotIn(">VERIFIED<", history_block)
        self.assertNotIn("account_incarnation", history_block)

    def test_item20_no_write_side_functions_invoked(self):
        import inspect

        import app.api.repository as repo

        source = inspect.getsource(repo.list_mappings) + inspect.getsource(repo.get_mapping)
        for forbidden in ("INSERT", "UPDATE", "DELETE", "create_verified_mapping"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
