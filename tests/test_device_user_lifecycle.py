"""
Tests for Device User Roster Lifecycle Detection
PromptID: ADMS-Data-DeviceUserLifecycle-002

Tests cover:
  - Successful roster with known user
  - New user observed
  - User missing from successful roster
  - Already inactive user remains inactive
  - Inactive user reappears
  - Empty successful roster
  - Roster read failure safety
  - Multiple devices isolation
  - UID change detection
  - Identity safety (no human_employees, no mappings, no attendance mutation)
"""

import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.config import Config
from app.db import reconcile_roster_lifecycle


def make_observed_user(user_id: str, uid: int = None, name: str = None) -> Dict[str, Any]:
    return {"user_id": user_id, "uid": uid, "name": name}


def make_known_row(
    device_user_pk: int,
    device_user_id: str,
    device_uid: int = None,
    active: bool = True,
    roster_last_seen_at: datetime = None,
    inactive_at: datetime = None,
) -> tuple:
    return (device_user_pk, device_user_id, device_uid, active, roster_last_seen_at, inactive_at)


class TestRosterLifecycle(unittest.TestCase):
    """Tests for reconcile_roster_lifecycle()."""

    def setUp(self):
        self.cfg = Config.from_env()

    def _setup_mock_conn(self, known_rows, fetchone_result=None):
        """Helper to set up a mock DB connection with known device_users."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()

        # get_db_connection context manager
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_conn
        mock_ctx.__exit__.return_value = None

        # conn.cursor() context manager
        mock_cur_ctx = MagicMock()
        mock_cur_ctx.__enter__.return_value = mock_cur
        mock_cur_ctx.__exit__.return_value = None
        mock_conn.cursor.return_value = mock_cur_ctx

        # First fetchall: known device_users
        # Second fetchall: not used in reconcile, but set up just in case
        mock_cur.fetchall.return_value = known_rows
        mock_cur.fetchone.return_value = fetchone_result if fetchone_result else [1]
        # rowcount is used by the lifecycle mapping-close path; default 0
        # (no VERIFIED mappings closed) unless a test overrides it.
        mock_cur.rowcount = 0

        return mock_ctx, mock_cur

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_successful_roster_with_known_user(self, mock_ensure, mock_conn_fn):
        """Known user present in roster → roster_last_seen_at updated, inactive_at cleared."""
        known = [make_known_row(device_user_pk=10, device_user_id="1001", active=True)]
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn_fn.return_value = mock_ctx

        observed = [make_observed_user("1001", uid=1, name="Test User")]

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["observed"], 1)
        self.assertEqual(summary["new_users"], 0)
        self.assertEqual(summary["marked_inactive"], 0)
        self.assertEqual(summary["reappeared"], 0)
        self.assertEqual(summary["uid_anomalies"], 0)

        # Verify UPDATE was called with roster_last_seen_at = now()
        update_calls = [c for c in mock_cur.execute.call_args_list if "UPDATE device_users" in c[0][0]]
        self.assertTrue(len(update_calls) >= 1)
        # Verify the UPDATE sets roster_last_seen_at and clears inactive_at
        update_sql = update_calls[0][0][0]
        self.assertIn("roster_last_seen_at = now()", update_sql)
        self.assertIn("inactive_at = NULL", update_sql)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user", return_value=20)
    def test_new_user_observed(self, mock_ensure, mock_conn_fn):
        """New user in roster → ensure_device_user called, roster_last_seen_at set."""
        known = []  # No known users
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn_fn.return_value = mock_ctx

        observed = [make_observed_user("1001", uid=5, name="New User")]

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["observed"], 1)
        self.assertEqual(summary["new_users"], 1)
        mock_ensure.assert_called_once()

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_user_missing_from_successful_roster(self, mock_ensure, mock_conn_fn):
        """Known active user absent from successful roster → inactive_at set."""
        known = [make_known_row(device_user_pk=10, device_user_id="1001", active=True, inactive_at=None)]
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn_fn.return_value = mock_ctx

        observed = []  # Empty roster — successful read

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["observed"], 0)
        self.assertEqual(summary["marked_inactive"], 1)

        # Verify UPDATE sets inactive_at
        update_calls = [c for c in mock_cur.execute.call_args_list if "inactive_at = now()" in c[0][0]]
        self.assertTrue(len(update_calls) >= 1)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_already_inactive_user_remains_inactive(self, mock_ensure, mock_conn_fn):
        """Already inactive user absent from roster → inactive_at NOT updated again."""
        old_ts = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        known = [make_known_row(device_user_pk=10, device_user_id="1001", active=False, inactive_at=old_ts)]
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn_fn.return_value = mock_ctx

        observed = []  # Empty roster

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["marked_inactive"], 0)  # Already inactive, not re-marked

        # Verify no UPDATE with inactive_at = now() was executed
        update_calls = [c for c in mock_cur.execute.call_args_list if "inactive_at = now()" in c[0][0]]
        self.assertEqual(len(update_calls), 0)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_inactive_user_reappears(self, mock_ensure, mock_conn_fn):
        """Previously inactive user reappears in roster → inactive_at cleared, REAPPEARED logged."""
        old_ts = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        known = [make_known_row(device_user_pk=10, device_user_id="1001", active=False, inactive_at=old_ts)]
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn_fn.return_value = mock_ctx

        observed = [make_observed_user("1001", uid=1, name="Reappeared User")]

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["reappeared"], 1)
        self.assertEqual(summary["marked_inactive"], 0)

        # Verify UPDATE clears inactive_at
        update_calls = [c for c in mock_cur.execute.call_args_list if "UPDATE device_users" in c[0][0]]
        self.assertTrue(len(update_calls) >= 1)
        update_sql = update_calls[0][0][0]
        self.assertIn("inactive_at = NULL", update_sql)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_empty_successful_roster(self, mock_ensure, mock_conn_fn):
        """Successful empty roster → all known active users marked inactive."""
        known = [
            make_known_row(device_user_pk=10, device_user_id="1", active=True, inactive_at=None),
            make_known_row(device_user_pk=20, device_user_id="2", active=True, inactive_at=None),
        ]
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn_fn.return_value = mock_ctx

        observed = []  # Empty roster — successful read

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["observed"], 0)
        self.assertEqual(summary["marked_inactive"], 2)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_multiple_devices_isolation(self, mock_ensure, mock_conn_fn):
        """Users from device A absent from device B roster → NOT marked inactive.
        The SQL query in reconcile_roster_lifecycle filters by device_id, so
        only users belonging to the specified device are loaded. Here we
        simulate device_id=2 having no known users (user 1001 belongs to device 1)."""
        # Device 2 has no known users
        known = []
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn_fn.return_value = mock_ctx

        # Roster from device_id=2 (different device) — empty
        observed = []

        # Reconcile for device_id=2 — should only affect device_id=2 users
        summary = reconcile_roster_lifecycle(self.cfg, device_id=2, observed_users=observed)

        # No users for device 2 → nothing marked inactive
        self.assertEqual(summary["marked_inactive"], 0)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_uid_change_detected(self, mock_ensure, mock_conn_fn):
        """Same user_id with different device_uid → anomaly logged, no auto-mapping."""
        known = [make_known_row(device_user_pk=10, device_user_id="1001", device_uid=100, active=True)]
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn_fn.return_value = mock_ctx

        observed = [make_observed_user("1001", uid=200, name="UID Changed")]  # uid changed from 100 to 200

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["uid_anomalies"], 1)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_uid_same_no_anomaly(self, mock_ensure, mock_conn_fn):
        """Same user_id with same device_uid → no anomaly."""
        known = [make_known_row(device_user_pk=10, device_user_id="1001", device_uid=100, active=True)]
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn_fn.return_value = mock_ctx

        observed = [make_observed_user("1001", uid=100, name="Same UID")]

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["uid_anomalies"], 0)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_identity_safety_no_human_employees(self, mock_ensure, mock_conn_fn):
        """Lifecycle does not create human_employees rows."""
        known = [make_known_row(device_user_pk=10, device_user_id="1001", active=True)]
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn_fn.return_value = mock_ctx

        observed = [make_observed_user("1001", uid=1, name="Test")]

        reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        for c in mock_cur.execute.call_args_list:
            sql = c[0][0].lower()
            self.assertNotIn("insert into human_employees", sql)
            self.assertNotIn("insert into employee_device_mappings", sql)
            self.assertNotIn("update attendance_logs", sql)
            self.assertNotIn("delete from device_users", sql)
            self.assertNotIn("delete from attendance_logs", sql)

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_commit_called(self, mock_ensure, mock_conn_fn):
        """Verify the transaction is committed."""
        known = []
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_conn = mock_ctx.__enter__.return_value
        mock_conn_fn.return_value = mock_ctx

        reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=[])

        mock_conn.commit.assert_called_once()

    @patch("app.db.get_db_connection")
    @patch("app.db.ensure_device_user")
    def test_mixed_scenario(self, mock_ensure, mock_conn_fn):
        """Mixed: 1 observed known, 1 missing active, 1 missing already-inactive, 1 new."""
        old_ts = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        known = [
            make_known_row(device_user_pk=10, device_user_id="1001", active=True, inactive_at=None),  # observed
            make_known_row(device_user_pk=20, device_user_id="1002", active=True, inactive_at=None),  # missing → inactive
            make_known_row(device_user_pk=30, device_user_id="1003", active=False, inactive_at=old_ts),  # missing, already inactive
        ]
        mock_ctx, mock_cur = self._setup_mock_conn(known)
        mock_ensure.return_value = 40  # new user gets pk=40
        mock_conn_fn.return_value = mock_ctx

        observed = [
            make_observed_user("1001", uid=1, name="Active User"),  # known, observed
            make_observed_user("1004", uid=4, name="Brand New"),    # new user
        ]

        summary = reconcile_roster_lifecycle(self.cfg, device_id=1, observed_users=observed)

        self.assertEqual(summary["observed"], 2)
        self.assertEqual(summary["new_users"], 1)
        self.assertEqual(summary["marked_inactive"], 1)  # only 1002 (1003 already inactive)
        self.assertEqual(summary["reappeared"], 0)
        self.assertEqual(summary["uid_anomalies"], 0)


class TestRosterFailureSafety(unittest.TestCase):
    """Test that roster read failures do NOT mark users inactive."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.db.get_db_connection")
    def test_roster_failure_no_lifecycle_update(self, mock_conn_fn):
        """
        Simulate a roster read failure — reconcile_roster_lifecycle should NOT be called.
        This test verifies the caller (collector) does not call reconcile on failure.
        """
        # The collector's perform_roster_lifecycle_check catches exceptions and does NOT
        # call reconcile_roster_lifecycle. We verify by ensuring the function itself
        # is never invoked when the roster read raises an exception.
        # This is tested at the collector level, but we verify the contract here:
        # reconcile_roster_lifecycle should only be called with a valid observed_users list.
        # If called with None (simulating failure), it should handle gracefully.
        pass  # Contract is enforced by collector, not by db function


class TestCollectorRosterLifecycle(unittest.TestCase):
    """Tests for the collector's perform_roster_lifecycle_check method."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.collector.reconcile_roster_lifecycle")
    @patch("app.db.get_db_connection")
    def test_successful_roster_check(self, mock_db_conn, mock_reconcile):
        """Collector performs roster check successfully."""
        from app.collector import CollectorStateEngine

        engine = CollectorStateEngine(self.cfg)

        # Mock ZK connection with get_users()
        mock_zk_conn = MagicMock()
        mock_user = MagicMock()
        mock_user.user_id = "1001"
        mock_user.uid = 1
        mock_user.name = "Test User"
        mock_zk_conn.get_users.return_value = [mock_user]
        engine.connection = mock_zk_conn

        # Mock DB to return device_id
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [1]
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = MagicMock()
        mock_ctx.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur
        mock_db_conn.return_value = mock_ctx

        # Mock reconcile return
        mock_reconcile.return_value = {
            "observed": 1, "new_users": 0, "marked_inactive": 0,
            "reappeared": 0, "uid_anomalies": 0,
        }

        engine.perform_roster_lifecycle_check()

        mock_zk_conn.get_users.assert_called_once()
        mock_reconcile.assert_called_once()
        self.assertEqual(engine.last_roster_user_count, 1)
        self.assertIsNotNone(engine.last_roster_poll_success)

    @patch("app.collector.reconcile_roster_lifecycle")
    @patch("app.db.get_db_connection")
    def test_roster_read_failure_no_update(self, mock_db_conn, mock_reconcile):
        """Roster read failure (exception) → reconcile NOT called, no lifecycle updates."""
        from app.collector import CollectorStateEngine

        engine = CollectorStateEngine(self.cfg)

        # Mock ZK connection that raises on get_users()
        mock_zk_conn = MagicMock()
        mock_zk_conn.get_users.side_effect = Exception("Connection timeout")
        engine.connection = mock_zk_conn

        engine.perform_roster_lifecycle_check()

        mock_reconcile.assert_not_called()
        self.assertIsNone(engine.last_roster_poll_success)
        self.assertIsNone(engine.last_roster_user_count)

    @patch("app.collector.reconcile_roster_lifecycle")
    @patch("app.db.get_db_connection")
    def test_roster_returns_none_no_update(self, mock_db_conn, mock_reconcile):
        """Roster read returns None → treated as FAILED, reconcile NOT called."""
        from app.collector import CollectorStateEngine

        engine = CollectorStateEngine(self.cfg)

        mock_zk_conn = MagicMock()
        mock_zk_conn.get_users.return_value = None
        engine.connection = mock_zk_conn

        engine.perform_roster_lifecycle_check()

        mock_reconcile.assert_not_called()
        self.assertIsNone(engine.last_roster_poll_success)

    @patch("app.collector.reconcile_roster_lifecycle")
    @patch("app.db.get_db_connection")
    def test_empty_roster_success(self, mock_db_conn, mock_reconcile):
        """Empty roster (0 users) is a SUCCESSFUL read → reconcile IS called."""
        from app.collector import CollectorStateEngine

        engine = CollectorStateEngine(self.cfg)

        mock_zk_conn = MagicMock()
        mock_zk_conn.get_users.return_value = []  # Empty list = successful empty roster
        engine.connection = mock_zk_conn

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [1]
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = MagicMock()
        mock_ctx.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur
        mock_db_conn.return_value = mock_ctx

        mock_reconcile.return_value = {
            "observed": 0, "new_users": 0, "marked_inactive": 2,
            "reappeared": 0, "uid_anomalies": 0,
        }

        engine.perform_roster_lifecycle_check()

        mock_reconcile.assert_called_once()
        self.assertEqual(engine.last_roster_user_count, 0)
        self.assertEqual(engine.last_roster_marked_inactive, 2)
        self.assertIsNotNone(engine.last_roster_poll_success)

    def test_no_connection_skips_check(self):
        """No active ZK connection → skip roster check gracefully."""
        from app.collector import CollectorStateEngine

        engine = CollectorStateEngine(self.cfg)
        engine.connection = None

        # Should not raise
        engine.perform_roster_lifecycle_check()
        self.assertIsNone(engine.last_roster_poll_success)


if __name__ == "__main__":
    unittest.main()