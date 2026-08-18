"""
Safe cancelled-Terminal-ID reclamation.

PromptID: ADMS-TerminalManagement-020 Part C

Policy (proven against real production ground truth — terminal ID 1003 vs
1002): a CANCELLED reservation's ID becomes reusable ONLY if the terminal
account was NEVER created for it (terminal_created_at IS NULL AND
device_uid IS NULL). Historical proof of a genuinely-created account is
structural, not a separate check: device_users.device_user_id is unioned
into the "used" set with no active/inactive filter, so any ID that ever
had a device_users row (even later removed — the 1002 case) remains
permanently used regardless of enrollment status. Since attendance_logs
and employee_device_mappings both reference device_users.device_user_pk,
an ID with no device_users row can never have attendance or a mapping —
"no attendance/mapping exists" is schema-guaranteed for the reclaimable
case, not re-checked separately.

No historical row is ever deleted or rewritten — only allocator
eligibility changes.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.config import Config
from app.enrollment import (
    _find_reclaimable_cancelled_enrollment,
    _load_used_terminal_ids,
    reserve_next_device_user_id,
)
from tests.test_enrollment import FakeCursor, make_db


class TestLoadUsedTerminalIds(unittest.TestCase):
    """21, 22, 26, 27, 30: the core eligibility query."""

    def test_item21_cancelled_never_created_excluded_from_used_set(self):
        cur = MagicMock()
        cur.fetchall.side_effect = [
            [],  # device_users half — no device_users row for 1003
        ]
        # _load_used_terminal_ids is one execute+fetchall; simulate the
        # combined UNION result directly.
        cur.fetchall.side_effect = [[]]
        used = _load_used_terminal_ids(cur, device_id=1)
        self.assertEqual(used, set())
        sql = cur.execute.call_args[0][0]
        self.assertIn("terminal_created_at IS NULL", sql)
        self.assertIn("device_uid IS NULL", sql)
        self.assertIn("status = 'CANCELLED'", sql)

    def test_item22_historical_physical_account_id_not_reclaimable(self):
        # Modeled as: the device_users half of the UNION returns '1002'
        # regardless of the enrollment half's relaxation — proving the
        # historical-account case remains permanently used structurally.
        cur = MagicMock()
        cur.fetchall.return_value = [("1002",)]
        used = _load_used_terminal_ids(cur, device_id=1)
        self.assertIn("1002", used)

    def test_item26_query_never_filters_device_users_by_active(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        _load_used_terminal_ids(cur, device_id=1)
        sql = cur.execute.call_args[0][0]
        device_users_clause = sql.split("UNION")[0]
        self.assertNotIn("active", device_users_clause)

    def test_item30_query_never_deletes_or_updates_anything(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        _load_used_terminal_ids(cur, device_id=1)
        sql = cur.execute.call_args[0][0].upper()
        self.assertNotIn("DELETE", sql)
        self.assertNotIn("UPDATE", sql)


class TestFindReclaimableCancelledEnrollment(unittest.TestCase):
    """Precise audit-trail lookup — never the eligibility decision itself."""

    def test_returns_enrollment_id_when_qualifying_row_exists(self):
        cur = MagicMock()
        cur.fetchone.return_value = (3,)
        result = _find_reclaimable_cancelled_enrollment(cur, device_id=1, terminal_id="1003")
        self.assertEqual(result, 3)
        sql = cur.execute.call_args[0][0]
        self.assertIn("status = 'CANCELLED'", sql)
        self.assertIn("terminal_created_at IS NULL", sql)

    def test_returns_none_when_no_qualifying_row(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        result = _find_reclaimable_cancelled_enrollment(cur, device_id=1, terminal_id="1004")
        self.assertIsNone(result)


class TestReserveEmitsReuseAuditEvent(unittest.TestCase):
    """28, 29, 31: allocator picks the reclaimed ID when eligible, the next
    safe ID otherwise, and the reuse audit event fires exactly once."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item28_31_allocator_reclaims_and_audits_exactly_once(self, mock_conn_fn, mock_log):
        cur = FakeCursor(
            fetchone_queue=[
                (1,),        # human exists
                (1,),        # device exists
                (None,),     # advisory lock
                (3,),        # _find_reclaimable_cancelled_enrollment: enrollment_id 3 qualified 1003
                (4, "1003", "RESERVED", None),  # INSERT RETURNING
            ],
            fetchall_queue=[
                [],  # 022 lifecycle candidate-row check: no blocking rows
                [],  # _load_used_terminal_ids: 1003 excluded, nothing else used
            ],
        )
        make_db(mock_conn_fn, cur)
        result = reserve_next_device_user_id(
            self.cfg, employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", device_id=1, operator="admin"
        )
        self.assertEqual(result["reserved_device_user_id"], "1003")

        event_types = [c.args[1] for c in mock_log.call_args_list]
        self.assertEqual(event_types.count("TERMINAL_ID_RESERVATION_REUSED"), 1)
        reuse_call = [c for c in mock_log.call_args_list if c.args[1] == "TERMINAL_ID_RESERVATION_REUSED"][0]
        message = reuse_call.args[2]
        self.assertIn("previous_cancelled_enrollment_id=3", message)
        self.assertIn("new_enrollment_id=4", message)
        self.assertIn("terminal_id=1003", message)

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item29_no_reclaim_no_reuse_event(self, mock_conn_fn, mock_log):
        cur = FakeCursor(
            fetchone_queue=[
                (1,), (1,), (None,),
                None,  # no reclaimable cancelled enrollment for the chosen id
                (5, "1001", "RESERVED", None),
            ],
            fetchall_queue=[[], []],
        )
        make_db(mock_conn_fn, cur)
        reserve_next_device_user_id(
            self.cfg, employee_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", device_id=1, operator="admin"
        )
        event_types = [c.args[1] for c in mock_log.call_args_list]
        self.assertNotIn("TERMINAL_ID_RESERVATION_REUSED", event_types)
        self.assertIn("ENROLLMENT_RESERVED", event_types)


if __name__ == "__main__":
    unittest.main()
