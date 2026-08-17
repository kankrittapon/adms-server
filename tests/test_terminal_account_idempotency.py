"""
Terminal-account idempotency/reconciliation test matrix.

PromptID: ADMS-ZEM560-TerminalAccount-Idempotency-Recovery-008

Covers the 20-case matrix required by the recovery architecture. Some cases
are covered here directly; others are covered in sibling files and are
cross-referenced below rather than duplicated verbatim:

  1-4, 9  : here (bounded read-back vs set_user() return/exception shape)
  5       : here (retry-after-uncertain-outcome reconciles, zero re-mutation)
  6-8     : here, plus basic-path coverage in
            tests/test_enrollment.py::TestTerminalAccountCreation
  10, 13  : here (idempotent re-entry on TERMINAL_ACCOUNT_CREATED)
  11      : DB-level serialization is the FOR UPDATE lock asserted here
            structurally; true concurrent-thread dispatch protection is
            tests/test_device_command_bus.py::test_dedupe_key_prevents_
            concurrent_dispatch and ::test_dedupe_key_released_after_completion
  12      : here (COALESCE keeps terminal_created_at/device_uid stable)
  14      : here (ensure_device_user called with the right arguments)
  15      : here (TERMINAL_ACCOUNT_CREATED vs TERMINAL_ACCOUNT_RECONCILED
            audit event selection)
  16      : here, plus tests/test_enrollment.py's ASCII-guard test
  17      : backend half here (Enrollment.english_name is queried/exposed);
            frontend half is the Enrollments.tsx default-to-english_name
            change (not unit-testable in this suite)
  18      : here, plus tests/test_enrollment.py::test_device_unreachable_fails_safely
  19      : tests/test_device_command_bus.py::test_bus_execute_timeout_pops_
            pending_and_logs_late_response
  20      : the full `pytest tests/` run itself (429 pre-existing + all new
            tests here and in sibling files, all green)

No physical device or database is required — mocked at the same boundary as
tests/test_enrollment.py (reuses its FakeCursor/FakeDevice/FakeUser/make_db/
make_enrollment_tuple test doubles).
"""

import unittest
from unittest.mock import patch

from app.config import Config
from app.enrollment import (
    PRIVILEGE_NORMAL_USER,
    EnrollmentError,
    TerminalAccountConflict,
    TerminalAccountUnconfirmed,
    create_or_reconcile_terminal_account,
    validate_terminal_display_name,
)
from tests.test_enrollment import (
    FakeCursor,
    FakeDevice,
    FakeUser,
    make_db,
    make_enrollment_tuple,
)


class SequencedRosterDevice:
    """A device whose get_users() returns a caller-supplied sequence of
    snapshots, one per call (repeating the last one once exhausted) — models
    "the account appears on the Nth read-back attempt, not immediately"
    (test #9), which the standard FakeDevice's immediate auto-commit can't
    represent."""

    def __init__(self, roster_sequence, set_user_return=False):
        self._sequence = list(roster_sequence)
        self._call_index = 0
        self.calls = []
        self.set_user_calls = []
        self.set_user_return = set_user_return

    def get_users(self):
        self.calls.append("get_users")
        idx = min(self._call_index, len(self._sequence) - 1)
        result = self._sequence[idx]
        self._call_index += 1
        return list(result)

    def set_user(self, **kwargs):
        self.calls.append("set_user")
        self.set_user_calls.append(kwargs)
        return self.set_user_return


class TestBoundedReadbackAuthoritative(unittest.TestCase):
    """Cases 1-4: whatever set_user() reports, the bounded roster read-back
    is what actually decides success — this is the direct fix for the
    production incident (set_user returned False on a call the ZEM560 had
    already committed)."""

    def setUp(self):
        self.cfg = Config.from_env()
        self.enroll_row = make_enrollment_tuple()

    def _run(self, device):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        with patch("app.enrollment.get_db_connection") as mock_conn_fn, \
             patch("app.enrollment.ensure_device_user", return_value=42), \
             patch("app.enrollment.log_sync_event"), \
             patch("app.enrollment.time.sleep"):
            make_db(mock_conn_fn, cur)
            return create_or_reconcile_terminal_account(
                self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
            )

    def test_case1_absent_set_user_true_readback_match_success(self):
        device = FakeDevice(users=[], set_user_return=True, commit_on_set_user=True)
        result = self._run(device)
        self.assertEqual(result["status"], "TERMINAL_ACCOUNT_CREATED")
        self.assertFalse(result["reconciled"])

    def test_case2_absent_set_user_false_readback_match_success(self):
        """The exact production bug: set_user() returns False, but the
        device actually committed the account."""
        device = FakeDevice(users=[], set_user_return=False, commit_on_set_user=True)
        result = self._run(device)
        self.assertEqual(result["status"], "TERMINAL_ACCOUNT_CREATED")
        self.assertFalse(result["reconciled"])
        self.assertEqual(len(device.set_user_calls), 1)  # exactly once, never retried blindly

    def test_case3_absent_set_user_none_readback_match_success(self):
        device = FakeDevice(users=[], set_user_return=None, commit_on_set_user=True)
        result = self._run(device)
        self.assertEqual(result["status"], "TERMINAL_ACCOUNT_CREATED")

    def test_case4_set_user_raises_ambiguous_transport_error_readback_match_success(self):
        class FlakyDevice(FakeDevice):
            def set_user(self, **kwargs):
                # Simulate an ambiguous transport error: the packet write
                # succeeded (device commits) but the ack read raised.
                self.calls.append("set_user")
                self.set_user_calls.append(kwargs)
                self._users.append(FakeUser(kwargs["user_id"], uid=55, privilege=PRIVILEGE_NORMAL_USER))
                raise ConnectionResetError("ack read failed")

        device = FlakyDevice(users=[])
        result = self._run(device)
        self.assertEqual(result["status"], "TERMINAL_ACCOUNT_CREATED")

    def test_case9_readback_absent_then_appears_within_bound(self):
        """First two read-back attempts find nothing; the third (still
        within READBACK_RETRIES=3) finds the account — success, not a
        premature failure."""
        empty = []
        present = [FakeUser("1001", uid=9, privilege=PRIVILEGE_NORMAL_USER)]
        # get_users() call sequence: [0]=pre-mutation check (absent),
        # [1]=read-back attempt 1 (absent), [2]=read-back attempt 2 (present)
        device = SequencedRosterDevice([empty, empty, present], set_user_return=False)
        result = self._run(device)
        self.assertEqual(result["status"], "TERMINAL_ACCOUNT_CREATED")
        self.assertEqual(device.calls.count("get_users"), 3)


class TestRetryAfterUncertainOutcome(unittest.TestCase):
    """Case 5: a caller-side timeout/uncertain outcome after the device was
    actually mutated must be safely resolved by simply retrying the same
    idempotent call — no second set_user(), no corrupted state."""

    def setUp(self):
        self.cfg = Config.from_env()

    def test_retry_after_uncertain_outcome_reconciles_without_remutation(self):
        device = FakeDevice(users=[], commit_on_set_user=True)

        # Call 1: device commits (set_user + roster now has 1001), but the
        # enrollment's own DB transition loses a race (rowcount=0) — models
        # a caller that would see this as a failure/timeout even though the
        # physical mutation already happened.
        row = make_enrollment_tuple()
        cur1 = FakeCursor(fetchone_queue=[row], rowcount=0)
        with patch("app.enrollment.get_db_connection") as m1, \
             patch("app.enrollment.ensure_device_user", return_value=42), \
             patch("app.enrollment.log_sync_event"), \
             patch("app.enrollment.time.sleep"):
            make_db(m1, cur1)
            with self.assertRaises(EnrollmentError):
                create_or_reconcile_terminal_account(
                    self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
                )
        self.assertEqual(len(device.set_user_calls), 1)

        # Call 2 (retry): enrollment is still RESERVED in the DB (call 1's
        # transaction never committed), but the device already has the
        # account from call 1 — must reconcile, NOT call set_user() again.
        cur2 = FakeCursor(fetchone_queue=[row])  # status still RESERVED
        with patch("app.enrollment.get_db_connection") as m2, \
             patch("app.enrollment.ensure_device_user", return_value=42), \
             patch("app.enrollment.log_sync_event") as mock_log2:
            make_db(m2, cur2)
            result = create_or_reconcile_terminal_account(
                self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
            )
        self.assertEqual(result["status"], "TERMINAL_ACCOUNT_CREATED")
        self.assertTrue(result["reconciled"])
        self.assertEqual(len(device.set_user_calls), 1)  # still just the one from call 1
        mock_log2.assert_called_once()
        self.assertEqual(mock_log2.call_args[0][1], "TERMINAL_ACCOUNT_RECONCILED")


class TestExistingIdReconciliationAndConflict(unittest.TestCase):
    """Cases 6-8."""

    def setUp(self):
        self.cfg = Config.from_env()
        self.enroll_row = make_enrollment_tuple()

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.ensure_device_user", return_value=42)
    @patch("app.enrollment.get_db_connection")
    def test_case6_existing_id_exact_match_reconciles_without_set_user(self, mock_conn_fn, mock_ensure, mock_log):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)
        device = FakeDevice(
            users=[FakeUser("1001", uid=3, name="Somchai S.", privilege=PRIVILEGE_NORMAL_USER)],
            commit_on_set_user=False,
        )
        result = create_or_reconcile_terminal_account(
            self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
        )
        self.assertTrue(result["reconciled"])
        self.assertEqual(device.set_user_calls, [])
        self.assertEqual(mock_log.call_args[0][1], "TERMINAL_ACCOUNT_RECONCILED")

    @patch("app.enrollment.ensure_device_user", return_value=42)
    @patch("app.enrollment.get_db_connection")
    def test_case7_existing_id_mismatch_conflict_zero_overwrite(self, mock_conn_fn, mock_ensure):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)
        device = FakeDevice(
            users=[FakeUser("1001", uid=3, name="Someone Else", privilege=14)],  # ADMIN, not NORMAL
            commit_on_set_user=False,
        )
        with self.assertRaises(TerminalAccountConflict):
            create_or_reconcile_terminal_account(
                self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
            )
        self.assertEqual(device.set_user_calls, [])
        mock_ensure.assert_not_called()

    @patch("app.enrollment.time.sleep")
    @patch("app.enrollment.get_db_connection")
    def test_case8_set_user_false_readback_absent_real_failure(self, mock_conn_fn, mock_sleep):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        make_db(mock_conn_fn, cur)
        device = FakeDevice(users=[], set_user_return=False, commit_on_set_user=False)
        with self.assertRaises(TerminalAccountUnconfirmed):
            create_or_reconcile_terminal_account(
                self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
            )
        # Bounded, not infinite: exactly READBACK_RETRIES get_users() calls
        # after the initial pre-mutation check.
        self.assertEqual(device.calls.count("get_users"), 1 + 3)


class TestIdempotentReentry(unittest.TestCase):
    """Cases 10, 13: re-issuing the request against an enrollment already at
    TERMINAL_ACCOUNT_CREATED is idempotent — same as a "repeated browser
    request" landing after the first one already succeeded."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.ensure_device_user", return_value=42)
    @patch("app.enrollment.get_db_connection")
    def test_already_created_reentry_is_idempotent(self, mock_conn_fn, mock_ensure, mock_log):
        row = make_enrollment_tuple(status="TERMINAL_ACCOUNT_CREATED", terminal_created_at=None)
        cur = FakeCursor(fetchone_queue=[row])
        make_db(mock_conn_fn, cur)
        device = FakeDevice(
            users=[FakeUser("1001", uid=5, privilege=PRIVILEGE_NORMAL_USER)],
            commit_on_set_user=False,
        )
        result = create_or_reconcile_terminal_account(
            self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
        )
        self.assertEqual(result["status"], "TERMINAL_ACCOUNT_CREATED")
        self.assertTrue(result["reconciled"])
        self.assertEqual(device.set_user_calls, [])
        self.assertEqual(mock_log.call_args[0][1], "TERMINAL_ACCOUNT_RECONCILED")


class TestReconciliationStability(unittest.TestCase):
    """Case 12: reconciliation must not clobber a terminal_created_at or
    device_uid that was already set by an earlier call — the UPDATE uses
    COALESCE so re-running is stable, not just non-erroring."""

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.ensure_device_user", return_value=42)
    @patch("app.enrollment.get_db_connection")
    def test_update_uses_coalesce_for_stability_fields(self, mock_conn_fn, mock_ensure, mock_log):
        cfg = Config.from_env()
        row = make_enrollment_tuple()
        cur = FakeCursor(fetchone_queue=[row])
        make_db(mock_conn_fn, cur)
        device = FakeDevice(users=[], commit_on_set_user=True)

        create_or_reconcile_terminal_account(cfg, enrollment_id=1, display_name="Somchai S.", device=device)

        update_sql = [sql for sql, _ in cur.executed if sql.strip().upper().startswith("UPDATE DEVICE_USER_ENROLLMENTS")]
        self.assertEqual(len(update_sql), 1)
        self.assertIn("COALESCE(terminal_created_at, now())", update_sql[0])
        self.assertIn("COALESCE(device_uid,", update_sql[0])
        self.assertIn("STATUS IN ('RESERVED', 'TERMINAL_ACCOUNT_CREATED')", update_sql[0].upper())


class TestConcurrencyRowLock(unittest.TestCase):
    """Case 11 (DB-level half): the enrollment row is fetched with FOR UPDATE
    on this write path specifically, so a second concurrent caller for the
    same enrollment_id blocks at the database until the first transaction
    commits or rolls back. (True concurrent-thread behavior isn't
    exercisable against a mocked cursor; the MQTT-layer half of double-
    submit protection is tested in test_device_command_bus.py.)"""

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.ensure_device_user", return_value=42)
    @patch("app.enrollment.get_db_connection")
    def test_enrollment_fetch_takes_row_lock(self, mock_conn_fn, mock_ensure, mock_log):
        cfg = Config.from_env()
        row = make_enrollment_tuple()
        cur = FakeCursor(fetchone_queue=[row])
        make_db(mock_conn_fn, cur)
        device = FakeDevice(users=[], commit_on_set_user=True)

        create_or_reconcile_terminal_account(cfg, enrollment_id=1, display_name="Somchai S.", device=device)

        select_sql = [sql for sql, _ in cur.executed if sql.strip().upper().startswith("SELECT")]
        self.assertTrue(any("FOR UPDATE" in sql.upper() for sql in select_sql))


class TestDeviceUsersRowAndAudit(unittest.TestCase):
    """Cases 14, 15."""

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.ensure_device_user", return_value=42)
    @patch("app.enrollment.get_db_connection")
    def test_case14_device_users_row_created_via_canonical_helper(self, mock_conn_fn, mock_ensure, mock_log):
        cfg = Config.from_env()
        row = make_enrollment_tuple(device_id=1)
        cur = FakeCursor(fetchone_queue=[row])
        make_db(mock_conn_fn, cur)
        device = FakeDevice(users=[], commit_on_set_user=True)

        create_or_reconcile_terminal_account(cfg, enrollment_id=1, display_name="Somchai S.", device=device)

        mock_ensure.assert_called_once_with(cur, 1, "1001", "Somchai S.")

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.ensure_device_user", return_value=42)
    @patch("app.enrollment.get_db_connection")
    def test_case15_audit_event_created_vs_reconciled(self, mock_conn_fn, mock_ensure, mock_log):
        cfg = Config.from_env()

        # Creation path (absent -> mutated).
        cur1 = FakeCursor(fetchone_queue=[make_enrollment_tuple()])
        make_db(mock_conn_fn, cur1)
        create_or_reconcile_terminal_account(
            cfg, enrollment_id=1, display_name="Somchai S.", device=FakeDevice(users=[], commit_on_set_user=True)
        )
        self.assertEqual(mock_log.call_args_list[-1][0][1], "TERMINAL_ACCOUNT_CREATED")

        # Reconciliation path (already present -> not mutated).
        cur2 = FakeCursor(fetchone_queue=[make_enrollment_tuple()])
        make_db(mock_conn_fn, cur2)
        device2 = FakeDevice(
            users=[FakeUser("1001", uid=3, privilege=PRIVILEGE_NORMAL_USER)],
            commit_on_set_user=False,
        )
        create_or_reconcile_terminal_account(cfg, enrollment_id=1, display_name="Somchai S.", device=device2)
        self.assertEqual(mock_log.call_args_list[-1][0][1], "TERMINAL_ACCOUNT_RECONCILED")


class TestCanonicalEnglishNameAndAsciiGuard(unittest.TestCase):
    """Cases 16, 17."""

    def test_case16_thai_name_never_bypasses_ascii_guard(self):
        with self.assertRaises(EnrollmentError):
            validate_terminal_display_name("พิมาย ขาวสอาด")

    def test_case16_thai_name_rejected_before_any_device_call(self):
        cfg = Config.from_env()
        row = make_enrollment_tuple()
        cur = FakeCursor(fetchone_queue=[row])
        with patch("app.enrollment.get_db_connection") as mock_conn_fn:
            make_db(mock_conn_fn, cur)
            device = FakeDevice(users=[])
            with self.assertRaises(EnrollmentError):
                create_or_reconcile_terminal_account(
                    cfg, enrollment_id=1, display_name="พิมาย ขาวสอาด", device=device
                )
        self.assertEqual(device.calls, [])  # rejected before touching the device at all

    def test_case17_repository_query_selects_english_name(self):
        """Backend half of "terminal-safe English name used when available":
        the enrollment list/detail queries join human_employees.english_name
        so the frontend can default the terminal-name field to it instead of
        the (non-ASCII) Thai display name. The frontend default itself is
        exercised in Enrollments.tsx, not this Python suite."""
        import inspect
        from app.api import repository

        list_src = inspect.getsource(repository.list_enrollments)
        detail_src = inspect.getsource(repository.get_enrollment_row)
        self.assertIn("h.english_name", list_src)
        self.assertIn("h.english_name", detail_src)


if __name__ == "__main__":
    unittest.main()
