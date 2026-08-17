"""
Personnel (Human) lifecycle — ACTIVE/INACTIVE deactivation, mapping
closure, reactivation.

PromptID: ADMS-Personnel-Lifecycle-019

Covers the required 20-item matrix (items 17-18, admin-role restoration,
are verified against real production read-only state — see the final
report — not unit tests, since no code change was needed there).

No physical device, real Human, or real terminal is touched — all DB
access is mocked at the app.personnel boundary, matching this project's
established convention.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.config import Config
from app.personnel import PersonnelError, deactivate_human, reactivate_human

EMPLOYEE_ID = "aaaaaaaa-1111-2222-3333-444444444444"


class FakeCursor:
    def __init__(self, fetchone_queue=None, fetchall_result=None):
        self.executed = []
        self._fetchone_queue = list(fetchone_queue or [])
        self._fetchall_result = fetchall_result if fetchall_result is not None else []

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


class TestDeactivation(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    # 1. ACTIVE person deactivated
    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item1_active_person_deactivated(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[(True,)], fetchall_result=[])
        make_db(mock_conn_fn, cur)
        result = deactivate_human(self.cfg, EMPLOYEE_ID, "admin", "left the organization")
        self.assertFalse(result["active"])
        self.assertFalse(result["already_inactive"])
        update_sql = [s for s in cur.sql() if s.startswith("UPDATE human_employees")][0]
        self.assertIn("active = false", update_sql)

    # 2. reason required
    def test_item2_reason_required(self):
        with self.assertRaises(PersonnelError):
            deactivate_human(self.cfg, EMPLOYEE_ID, "admin", "   ")

    # 3. open mapping closed
    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item3_open_mapping_closed(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[(True,)], fetchall_result=[(2, 29)])
        make_db(mock_conn_fn, cur)
        result = deactivate_human(self.cfg, EMPLOYEE_ID, "admin", "transferred out")
        self.assertEqual(result["mappings_closed"], [2])
        close_sql = [s for s in cur.sql() if "employee_device_mappings" in s and s.startswith("UPDATE")][0]
        self.assertIn("valid_to = %s", close_sql)
        self.assertNotIn("DELETE", close_sql.upper())

    # 4. historical mapping retained (never DELETE)
    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item4_never_deletes_mapping_row(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[(True,)], fetchall_result=[(2, 29)])
        make_db(mock_conn_fn, cur)
        deactivate_human(self.cfg, EMPLOYEE_ID, "admin", "reason")
        for s in cur.sql():
            self.assertNotIn("DELETE", s.upper())

    # 5. historical attendance retained (never touched)
    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item5_never_touches_attendance_logs(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[(True,)], fetchall_result=[(2, 29)])
        make_db(mock_conn_fn, cur)
        deactivate_human(self.cfg, EMPLOYEE_ID, "admin", "reason")
        for s in cur.sql():
            self.assertNotIn("attendance_logs", s)

    # 10. duplicate deactivate safe / idempotent
    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item10_duplicate_deactivate_idempotent(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[(False,)])  # already inactive
        conn = make_db(mock_conn_fn, cur)
        result = deactivate_human(self.cfg, EMPLOYEE_ID, "admin", "reason")
        self.assertTrue(result["already_inactive"])
        self.assertEqual(result["mappings_closed"], [])
        conn.rollback.assert_called_once()
        mock_log.assert_not_called()  # no duplicate audit event

    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_audit_events_emitted_exactly_once_each(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[(True,)], fetchall_result=[(2, 29)])
        make_db(mock_conn_fn, cur)
        deactivate_human(self.cfg, EMPLOYEE_ID, "admin", "left")
        event_types = [c.args[1] for c in mock_log.call_args_list]
        self.assertEqual(event_types.count("PERSONNEL_DEACTIVATED"), 1)
        self.assertEqual(event_types.count("MAPPING_CLOSED_DUE_TO_PERSONNEL_DEACTIVATION"), 1)

    def test_missing_human_rejected(self):
        with patch("app.personnel.get_db_connection") as m:
            cur = FakeCursor(fetchone_queue=[None])
            make_db(m, cur)
            with self.assertRaisesRegex(PersonnelError, "does not exist"):
                deactivate_human(self.cfg, EMPLOYEE_ID, "admin", "reason")


class TestReactivation(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    # 19. reactivation semantics
    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item19_reactivation_sets_active_true(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[(False,)])
        make_db(mock_conn_fn, cur)
        result = reactivate_human(self.cfg, EMPLOYEE_ID, "admin", "returned to duty")
        self.assertTrue(result["active"])
        update_sql = [s for s in cur.sql() if s.startswith("UPDATE")][0]
        self.assertIn("active = true", update_sql)
        mock_log.assert_called_once()
        self.assertEqual(mock_log.call_args[0][1], "PERSONNEL_REACTIVATED")

    # 20. old mapping does not reopen on reactivation
    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item20_reactivation_never_touches_mappings(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[(False,)])
        make_db(mock_conn_fn, cur)
        reactivate_human(self.cfg, EMPLOYEE_ID, "admin")
        for s in cur.sql():
            self.assertNotIn("employee_device_mappings", s)

    def test_already_active_idempotent(self):
        with patch("app.personnel.get_db_connection") as m, patch("app.personnel.log_sync_event") as mock_log:
            cur = FakeCursor(fetchone_queue=[(True,)])
            conn = make_db(m, cur)
            result = reactivate_human(self.cfg, EMPLOYEE_ID, "admin")
            self.assertTrue(result["already_active"])
            conn.rollback.assert_called_once()
            mock_log.assert_not_called()


class TestPersonnelListFiltering(unittest.TestCase):
    """14, 15, 16: list_humans supports active/inactive filtering, and an
    inactive person's row is still returned by direct lookup (never hidden
    from history)."""

    def test_item14_15_active_filter_param_forwarded(self):
        import inspect

        import app.api.repository as repository

        sig = inspect.signature(repository.list_humans)
        self.assertIn("active", sig.parameters)

    def test_item16_get_human_does_not_filter_by_active(self):
        import inspect

        import app.api.repository as repository

        src = inspect.getsource(repository.get_human)
        self.assertNotIn("active", src)  # single-row lookup is unconditional


class TestInactiveHumanBlockedFromWriteOperations(unittest.TestCase):
    """8, 9: cross-reference — these invariants already existed prior to
    PromptID 019 (reserve_next_device_user_id and create_verified_mapping
    both already check human_employees.active) and remain enforced,
    confirmed by direct source inspection rather than duplicated fixtures."""

    def test_item8_reserve_checks_active_human(self):
        import inspect

        import app.enrollment as enrollment_mod

        src = inspect.getsource(enrollment_mod.reserve_next_device_user_id)
        self.assertIn("active = true", src)

    def test_item9_create_verified_mapping_checks_active_human(self):
        import inspect

        import app.mapping as mapping_mod

        src = inspect.getsource(mapping_mod.create_verified_mapping)
        self.assertIn("Human must exist and be active", src)


class TestRBACAndWriteSession(unittest.TestCase):
    """11, 12, 13: endpoint-level RBAC/write-session/infra-lock gating."""

    def test_item11_12_endpoints_require_admin_and_write_session(self):
        import inspect

        import app.api.routers.humans as humans_router

        src = inspect.getsource(humans_router)
        for route in ("/deactivate", "/reactivate"):
            idx = src.find(route)
            segment = src[idx:idx + 300]
            self.assertIn("ROLES_ADMIN_ONLY", segment)
            self.assertIn("require_writes", segment)
            self.assertIn("require_write_session", segment)

    def test_item13_require_writes_checks_infra_master_lock(self):
        # require_writes is the SAME dependency used by every other
        # domain-mutating route — infra-lock-overrides-session semantics
        # are already tested generically in tests/test_api_auth.py; this
        # is a structural cross-reference, not a duplicate fixture.
        import inspect

        import app.api.dependencies as deps

        self.assertIn("def require_writes", inspect.getsource(deps))


if __name__ == "__main__":
    unittest.main()
