"""
Tests for Device User Lifecycle Hardening
PromptID: ADMS-Data-DeviceUserLifecycleHardening-001

Covers (fixture-only — no production simulation, no physical device):
  - Active account normal polling: incarnation unchanged
  - Confirmed disappearance closes an open VERIFIED mapping at the lifecycle
    boundary (valid_to = now(), same transaction boundary as inactive_at)
  - Repeated empty-roster polls do not rewrite inactive_at / valid_to
  - Reappearance increments account_incarnation exactly once
  - Reappearance does NOT reopen or inherit the previous (closed) mapping
  - Old attendance remains historically attributable (before valid_to)
  - New attendance after reappearance is NULL/unmapped until re-verification
  - Same Human re-enrollment still requires a fresh VERIFIED mapping
  - Different Human reuse cannot resolve to the previous Human
  - Roster failure != confirmed disappearance (collector contract, retained)
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from app.config import Config
from app.db import reconcile_roster_lifecycle, resolve_verified_employee_mapping
from app.mapping import MappingError, create_verified_mapping

UUID_A = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
UUID_B = "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22"

BASE = datetime(2026, 8, 13, 0, 0, 0, tzinfo=timezone.utc)


def make_observed_user(user_id: str, uid: int = None, name: str = None):
    return {"user_id": user_id, "uid": uid, "name": name}


def make_known_row(
    device_user_pk: int,
    device_user_id: str,
    device_uid: int = None,
    active: bool = True,
    roster_last_seen_at: datetime = None,
    inactive_at: datetime = None,
):
    return (device_user_pk, device_user_id, device_uid, active, roster_last_seen_at, inactive_at)


def setup_conn(mock_conn_fn, known_rows, rowcount=0):
    """Standard reconcile mock: context-manager conn + cursor with known rows."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = known_rows
    mock_cur.fetchone.return_value = [1]
    mock_cur.rowcount = rowcount
    cur_ctx = MagicMock()
    cur_ctx.__enter__.return_value = mock_cur
    cur_ctx.__exit__.return_value = None
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cur_ctx
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    mock_ctx.__exit__.return_value = None
    mock_conn_fn.return_value = mock_ctx
    return mock_cur


def sql_calls(mock_cur):
    return [c[0][0] for c in mock_cur.execute.call_args_list]


class TestLifecycleNormalPolling(unittest.TestCase):
    """Active account normal polling must NOT change incarnation."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_active_poll_incarnation_unchanged(self, mock_ensure, mock_conn_fn):
        known = [make_known_row(device_user_pk=10, device_user_id="1001", active=True)]
        mock_cur = setup_conn(mock_conn_fn, known)
        observed = [make_observed_user("1001", uid=1, name="Active")]

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["reappeared"], 0)
        self.assertEqual(summary["marked_inactive"], 0)
        self.assertEqual(summary["mappings_closed"], 0)
        # The reactivation UPDATE must bump incarnation by 0 (unchanged)
        updates = [c for c in mock_cur.execute.call_args_list if "account_incarnation" in c[0][0]]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][0][1][1], 0)  # inc_bump param = 0
        # No DEVICE_USER_REAPPEARED audit event
        for sql in sql_calls(mock_cur):
            self.assertNotIn("DEVICE_USER_REAPPEARED", sql)
            self.assertNotIn("DEVICE_USER_INACTIVE", sql)


class TestDisappearanceClosesMapping(unittest.TestCase):
    """Confirmed disappearance must close any open VERIFIED mapping."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_disappearance_closes_open_mapping(self, mock_ensure, mock_conn_fn):
        known = [make_known_row(device_user_pk=10, device_user_id="1001", active=True)]
        # 1 VERIFIED mapping exists and gets closed (rowcount reflects the UPDATE)
        mock_cur = setup_conn(mock_conn_fn, known, rowcount=1)
        observed = []

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["marked_inactive"], 1)
        self.assertEqual(summary["mappings_closed"], 1)

        # inactive_at boundary set
        inactive_updates = [c for c in mock_cur.execute.call_args_list if "inactive_at = now()" in c[0][0]]
        self.assertEqual(len(inactive_updates), 1)

        # open VERIFIED mapping closed with valid_to = now(), guarded by valid_to IS NULL
        mapping_updates = [c for c in mock_cur.execute.call_args_list if "employee_device_mappings" in c[0][0]]
        self.assertEqual(len(mapping_updates), 1)
        m_sql = mapping_updates[0][0][0]
        self.assertIn("valid_to = now()", m_sql)
        self.assertIn("mapping_status = 'VERIFIED'", m_sql)
        self.assertIn("valid_to IS NULL", m_sql)
        self.assertNotIn("DELETE", m_sql.upper())

        # audit events written (event type + message are SQL params)
        all_text = " ".join(sql_calls(mock_cur)) + " " + " ".join(
            " ".join(str(a) for a in c[0][1]) for c in mock_cur.execute.call_args_list if c[0][1]
        )
        self.assertIn("DEVICE_USER_INACTIVE", all_text)
        self.assertIn("MAPPING_CLOSED_BY_DEVICE_USER_LIFECYCLE", all_text)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_repeated_empty_polls_do_not_rewrite(self, mock_ensure, mock_conn_fn):
        """Already-inactive user absent again → no inactive_at rewrite, no mapping re-close."""
        old_ts = BASE - timedelta(days=1)
        known = [make_known_row(device_user_pk=10, device_user_id="1001", active=False, inactive_at=old_ts)]
        mock_cur = setup_conn(mock_conn_fn, known)
        observed = []

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["marked_inactive"], 0)
        self.assertEqual(summary["mappings_closed"], 0)
        for c in mock_cur.execute.call_args_list:
            self.assertNotIn("inactive_at = now()", c[0][0])
            self.assertNotIn("employee_device_mappings", c[0][0])


class TestReappearance(unittest.TestCase):
    """Reappearance = new account incarnation; previous mapping stays closed."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_reappearance_increments_incarnation_exactly_once(self, mock_ensure, mock_conn_fn):
        old_ts = BASE - timedelta(days=1)
        known = [make_known_row(device_user_pk=10, device_user_id="1001", active=False, inactive_at=old_ts)]
        mock_cur = setup_conn(mock_conn_fn, known)
        observed = [make_observed_user("1001", uid=1, name="Reappeared")]

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["reappeared"], 1)
        updates = [c for c in mock_cur.execute.call_args_list if "account_incarnation" in c[0][0]]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][0][1][1], 1)  # inc_bump = 1 exactly once
        all_text = " ".join(sql_calls(mock_cur)) + " " + " ".join(
            " ".join(str(a) for a in c[0][1]) for c in mock_cur.execute.call_args_list if c[0][1]
        )
        self.assertIn("DEVICE_USER_REAPPEARED", all_text)
        self.assertIn("incarnation_bump=+1", all_text)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_reappearance_does_not_reopen_or_inherit_mapping(self, mock_ensure, mock_conn_fn):
        old_ts = BASE - timedelta(days=1)
        known = [make_known_row(device_user_pk=10, device_user_id="1001", active=False, inactive_at=old_ts)]
        mock_cur = setup_conn(mock_conn_fn, known)
        observed = [make_observed_user("1001", uid=1, name="Reappeared")]

        reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        # No mapping UPDATE at all on reappearance — the closed mapping stays closed.
        for c in mock_cur.execute.call_args_list:
            self.assertNotIn("employee_device_mappings", c[0][0])

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_new_user_incarnation_defaults_to_one(self, mock_ensure, mock_conn_fn):
        """Brand-new user: INSERT via ensure_device_user (incarnation default 1)."""
        mock_cur = setup_conn(mock_conn_fn, [])
        observed = [make_observed_user("1005", uid=5, name="New")]

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["new_users"], 1)
        self.assertEqual(summary["reappeared"], 0)
        mock_ensure.assert_called_once()


class FakeResolveCursor:
    """
    Minimal fake cursor that evaluates the temporal resolver's WHERE clause
    against canned mapping rows, so interval semantics are actually exercised
    (fixture-only — no database).
    """

    def __init__(self, mappings):
        # mappings: list of dicts with device_user_pk, employee_id, valid_from, valid_to
        self.mappings = mappings
        self.results = []

    def execute(self, sql, params=None):
        # resolver SQL: WHERE device_user_pk = %s AND mapping_status = 'VERIFIED'
        #   AND valid_from <= %s AND (valid_to IS NULL OR %s < valid_to) LIMIT 2
        dpk, scan = params[0], params[1]
        matches = [
            m for m in self.mappings
            if m["device_user_pk"] == dpk
            and m["valid_from"] <= scan
            and (m["valid_to"] is None or scan < m["valid_to"])
        ]
        self.results = [(m["employee_id"],) for m in matches[:2]]

    def fetchall(self):
        return self.results


class TestResolverLifecycleSafety(unittest.TestCase):
    """Temporal resolver stays correct across the close/reuse boundary."""

    def test_old_attendance_remains_historically_attributable(self):
        """Attendance before the closed mapping's valid_to resolves to the old Human."""
        boundary = BASE + timedelta(hours=1)
        cur = FakeResolveCursor([
            {"device_user_pk": 10, "employee_id": UUID_A,
             "valid_from": BASE, "valid_to": boundary},
        ])
        result = resolve_verified_employee_mapping(cur, 10, BASE + timedelta(minutes=30))
        self.assertEqual(result, UUID_A)

    def test_scan_at_or_after_valid_to_unmapped(self):
        """Attendance at/after the boundary does NOT resolve through the old mapping."""
        boundary = BASE + timedelta(hours=1)
        cur = FakeResolveCursor([
            {"device_user_pk": 10, "employee_id": UUID_A,
             "valid_from": BASE, "valid_to": boundary},
        ])
        self.assertIsNone(resolve_verified_employee_mapping(cur, 10, boundary))
        self.assertIsNone(resolve_verified_employee_mapping(cur, 10, boundary + timedelta(minutes=1)))

    def test_different_human_reuse_cannot_resolve_to_previous_human(self):
        """Old mapping closed, new Human mapping starts later — gap stays unmapped."""
        boundary = BASE + timedelta(hours=1)
        new_start = BASE + timedelta(hours=2)
        cur = FakeResolveCursor([
            {"device_user_pk": 10, "employee_id": UUID_A,
             "valid_from": BASE, "valid_to": boundary},
            {"device_user_pk": 10, "employee_id": UUID_B,
             "valid_from": new_start, "valid_to": None},
        ])
        # during the gap between valid_to and new valid_from → unmapped
        self.assertIsNone(resolve_verified_employee_mapping(cur, 10, boundary + timedelta(minutes=30)))
        # after new mapping begins → only the NEW Human
        self.assertEqual(
            resolve_verified_employee_mapping(cur, 10, new_start + timedelta(minutes=1)),
            UUID_B,
        )

    def test_no_overlap_means_no_ambiguity(self):
        """Closed old + open new mappings never overlap → exactly one match."""
        boundary = BASE + timedelta(hours=1)
        new_start = BASE + timedelta(hours=2)
        cur = FakeResolveCursor([
            {"device_user_pk": 10, "employee_id": UUID_A,
             "valid_from": BASE, "valid_to": boundary},
            {"device_user_pk": 10, "employee_id": UUID_B,
             "valid_from": new_start, "valid_to": None},
        ])
        # old interval still resolves historically
        self.assertEqual(resolve_verified_employee_mapping(cur, 10, BASE + timedelta(minutes=1)), UUID_A)
        # no scan can match both (intervals are disjoint) — ambiguity absent
        self.assertEqual(len(cur.mappings), 2)


class TestReenrollmentRequiresFreshMapping(unittest.TestCase):
    """create_verified_mapping still enforces no-open-conflict after lifecycle close."""

    def setUp(self):
        self.cfg = Config.from_env()
        self.note = "fixture re-enrollment after lifecycle close"

    def test_open_mapping_blocks_new_verified_mapping(self):
        """Open VERIFIED mapping (valid_to IS NULL) blocks re-enrollment."""
        from tests.test_mapping_creation import (
            happy_path_queue, make_db, FakeCursor, PILOT_EMPLOYEE_ID,
        )
        with patch("app.mapping.get_db_connection") as m:
            cur = FakeCursor(fetchone_queue=happy_path_queue(conflict=(9,)))
            make_db(m, cur)
            with self.assertRaisesRegex(MappingError, "conflicting"):
                create_verified_mapping(
                    self.cfg, employee_id=PILOT_EMPLOYEE_ID, device_user_pk=7,
                    enrollment_id=1, controlled_attendance_id=12,
                    verified_by="operator", verification_note=self.note,
                )

    def test_closed_mapping_allows_fresh_verified_mapping(self):
        """After lifecycle close (conflict check returns no open row) a fresh
        VERIFIED mapping can be created — same Human re-enrollment is possible,
        but only through the full controlled evidence path."""
        from tests.test_mapping_creation import (
            happy_path_queue, make_db, FakeCursor, PILOT_EMPLOYEE_ID,
        )
        with patch("app.mapping.get_db_connection") as m:
            cur = FakeCursor(fetchone_queue=happy_path_queue(conflict=None))
            make_db(m, cur)
            result = create_verified_mapping(
                self.cfg, employee_id=PILOT_EMPLOYEE_ID, device_user_pk=7,
                enrollment_id=1, controlled_attendance_id=12,
                verified_by="operator", verification_note=self.note,
            )
            self.assertEqual(result["mapping_status"], "VERIFIED")
            self.assertEqual(result["valid_to"], None)
            # evidence-path SQL only — no rank/name/numeric inference
            for sql in cur.sql():
                lowered = sql.lower()
                self.assertNotIn("rank", lowered)
                self.assertNotIn("display_name", lowered)


if __name__ == "__main__":
    unittest.main()
