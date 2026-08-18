"""
Canonical cross-lifecycle derived state — ADMS-UX-CrossLifecycleClosure-021B.

Acceptance model: the real historical Pimai / old Terminal ID 1004 incident.
Human ACTIVE, fingerprint removed, terminal account removed (device_users
inactive), VERIFIED mapping #2 closed (valid_to set), Enrollment #4
preserved as history. The operator must see this as NOT-an-unfinished-
enrollment, without any DB migration or backfill — the derivation is
computed at read time from current facts, so it self-heals even a real
production row that is still literally 'READY_FOR_MAPPING' in the DB.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.api.repository import (
    _derive_enrollment_lifecycle_state,
    get_enrollment_row,
    list_enrollments,
)
from app.config import Config

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


class TestDeriveEnrollmentLifecycleState(unittest.TestCase):
    """Direct unit tests of the pure derivation function — item 1-4, 10, 11."""

    def test_item1_retired_with_active_account_and_open_mapping_is_completed(self):
        state = _derive_enrollment_lifecycle_state("RETIRED", True, "VERIFIED", None)
        self.assertEqual(state, "COMPLETED")

    def test_item3_inactive_device_user_and_closed_mapping_is_removed_from_terminal(self):
        """The exact Pimai/1004 shape: RETIRED, device_user inactive, mapping closed."""
        state = _derive_enrollment_lifecycle_state("RETIRED", False, "VERIFIED", NOW)
        self.assertEqual(state, "REMOVED_FROM_TERMINAL")

    def test_pimai_1004_self_heals_even_with_stale_stored_status(self):
        """The REAL production row: status is still literally READY_FOR_MAPPING
        (021's atomic RETIRED transition hadn't been deployed when mapping #2
        was created) yet a VERIFIED mapping already exists and was later
        closed by terminal removal. Must derive REMOVED_FROM_TERMINAL anyway
        — no migration/backfill required."""
        state = _derive_enrollment_lifecycle_state(
            "READY_FOR_MAPPING", False, "VERIFIED", NOW
        )
        self.assertEqual(state, "REMOVED_FROM_TERMINAL")
        self.assertNotIn(state, ("IN_PROGRESS",))

    def test_item2_cancelled_stays_cancelled_regardless_of_mapping_facts(self):
        state = _derive_enrollment_lifecycle_state("CANCELLED", None, None, None)
        self.assertEqual(state, "CANCELLED")

    def test_item11_ready_for_mapping_without_any_mapping_is_still_in_progress(self):
        """Normal, genuinely unfinished Step 6 — must not be misclassified."""
        state = _derive_enrollment_lifecycle_state("READY_FOR_MAPPING", None, None, None)
        self.assertEqual(state, "IN_PROGRESS")

    def test_early_steps_are_in_progress(self):
        for status in (
            "RESERVED",
            "TERMINAL_ACCOUNT_CREATED",
            "FINGERPRINT_ENROLLMENT_PENDING",
            "FINGERPRINT_ENROLLED",
            "CONTROLLED_SCAN_PENDING",
            "CONTROLLED_SCAN_CONFIRMED",
        ):
            with self.subTest(status=status):
                self.assertEqual(
                    _derive_enrollment_lifecycle_state(status, None, None, None),
                    "IN_PROGRESS",
                )

    def test_item10_removed_account_never_reported_as_in_progress(self):
        """A physically-removed terminal account must never look like it
        still needs Step 5/6 attention."""
        state = _derive_enrollment_lifecycle_state("RETIRED", False, "VERIFIED", NOW)
        self.assertNotEqual(state, "IN_PROGRESS")

    def test_retired_with_no_mapping_at_all_is_an_inconsistency_but_fails_safe(self):
        state = _derive_enrollment_lifecycle_state("RETIRED", None, None, None)
        self.assertEqual(state, "REMOVED_FROM_TERMINAL")  # never IN_PROGRESS, never crashes


class FakeCursor:
    """_fetch_all/_fetch_one zip cur.description[i][0] with each fetchall()
    tuple in order — this fake accepts dict rows (matching the real SQL's
    column order, since Python dicts preserve insertion order) and adapts
    them to that (description, tuple-rows) shape."""

    def __init__(self, rows=None, one=None):
        dict_rows = rows if rows is not None else ([one] if one is not None else [])
        self.description = [(k,) for k in dict_rows[0].keys()] if dict_rows else []
        self._tuples = [tuple(r.values()) for r in dict_rows]

    def execute(self, sql, params=None):
        self.last_sql = sql

    def fetchall(self):
        return list(self._tuples)


def _make_db(mock_conn_fn, cur, scalar=0):
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


def _row(**overrides):
    base = dict(
        enrollment_id=4,
        employee_id="fd63997f-b081-45bf-b74f-db224491fabc",
        device_id=1,
        reserved_device_user_id="1004",
        status="READY_FOR_MAPPING",
        reserved_by="admin",
        reserved_at=NOW,
        terminal_created_at=NOW,
        device_uid=2,
        fingerprint_confirmed_at=NOW,
        controlled_scan_window_until=None,
        controlled_scan_time=NOW,
        confirmed_by="admin",
        confirmed_at=NOW,
        notes=None,
        created_at=NOW,
        updated_at=NOW,
        employee_name="พิมาย ขาวสอาด",
        english_name="Pimai Khawsaad",
        rank=None,
        device_name="ZEM560",
        device_user_active=False,
        verified_mapping_status="VERIFIED",
        mapping_valid_to=NOW,
    )
    base.update(overrides)
    return base


class TestPimai1004AcceptanceSimulation(unittest.TestCase):
    """Phase 9 — using fakes only, reproduce the exact historical state and
    assert the API-level result. No production mutation."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.api.repository._fetch_scalar", return_value=1)
    @patch("app.api.repository.get_db_connection")
    def test_item12_list_enrollments_reports_removed_from_terminal_not_active(
        self, mock_conn_fn, mock_scalar
    ):
        cur = FakeCursor(rows=[_row()])
        _make_db(mock_conn_fn, cur)
        result = list_enrollments(self.cfg, limit=50, offset=0)
        item = result["items"][0]
        self.assertEqual(item["lifecycle_state"], "REMOVED_FROM_TERMINAL")
        self.assertNotIn("device_user_active", item)  # internal join fields not leaked
        self.assertNotIn("verified_mapping_status", item)
        self.assertNotIn("mapping_valid_to", item)

    @patch("app.api.repository.get_db_connection")
    def test_get_enrollment_row_same_derivation_as_list(self, mock_conn_fn):
        cur = FakeCursor(one=_row())
        _make_db(mock_conn_fn, cur)
        row = get_enrollment_row(self.cfg, 4)
        self.assertEqual(row["lifecycle_state"], "REMOVED_FROM_TERMINAL")
        self.assertEqual(row["status"], "READY_FOR_MAPPING")  # raw status preserved, not overwritten


class TestPersonnelTerminalManagementConsistency(unittest.TestCase):
    """Items 12/13: Personnel must not disagree with Enrollment/Terminal
    Management about whether a Human currently has a working terminal
    account. Verifies the query used by GET /api/v1/humans (list + detail)
    includes the same has_active_terminal_account derivation."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.api.repository.get_db_connection")
    def test_get_human_query_includes_terminal_account_derivation(self, mock_conn_fn):
        from app.api.repository import get_human

        row = {
            "employee_id": "fd63997f-b081-45bf-b74f-db224491fabc",
            "personnel_id": None,
            "display_name": "พิมาย ขาวสอาด",
            "english_name": "Pimai Khawsaad",
            "rank": None,
            "position": None,
            "branch": None,
            "category": None,
            "notes": None,
            "active": True,
            "production_scope": True,
            "source": "EXCEL_IMPORT",
            "created_at": NOW,
            "updated_at": NOW,
            "has_active_terminal_account": False,
        }
        cur = FakeCursor(one=row)
        _make_db(mock_conn_fn, cur)
        result = get_human(self.cfg, "fd63997f-b081-45bf-b74f-db224491fabc")
        self.assertTrue(result["active"])  # Human stays ACTIVE
        self.assertFalse(result["has_active_terminal_account"])  # but no working account
        self.assertIn("has_active_terminal_account", cur.last_sql)
        self.assertIn("EXISTS", cur.last_sql)

    def test_item13_consistent_field_name_across_human_and_enrollment_derivation(self):
        # Both derivations key off the same underlying facts (device_users.active
        # + employee_device_mappings VERIFIED/valid_to) — not two independent
        # reimplementations that could silently drift.
        from app.api.repository import _HAS_ACTIVE_TERMINAL_ACCOUNT_SQL

        self.assertIn("mapping_status = 'VERIFIED'", _HAS_ACTIVE_TERMINAL_ACCOUNT_SQL)
        self.assertIn("valid_to IS NULL", _HAS_ACTIVE_TERMINAL_ACCOUNT_SQL)
        self.assertIn("du.active = true", _HAS_ACTIVE_TERMINAL_ACCOUNT_SQL)


if __name__ == "__main__":
    unittest.main()
