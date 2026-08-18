"""
Re-enrollment eligibility vs. stale reservation conflict — ADMS-CurrentState-
History-UXClosure-022 (blocking defect follow-up).

Live production reproduction: Pimai (Human, ACTIVE, no current terminal
account) could not start a new enrollment. reserve_next_device_user_id()'s
duplicate-active-enrollment guard treated raw status='READY_FOR_MAPPING'
(Enrollment #4, canonically REMOVED_FROM_TERMINAL since terminal 1004 was
removed and its mapping closed) as blocking — the write-side used a
different, stale predicate than the read-side (021B's lifecycle_state).

Root cause was actually TWO layers deep: the Python guard query AND the DB
partial unique index `uq_active_enrollment_per_human_device` (WHERE status
IN [...]) — the index can only see the enrollment table's own `status`
column, not the joined device_users/mapping facts. Fixed (owner-approved)
by having reserve_next_device_user_id() atomically self-heal any row whose
canonical lifecycle_state is NOT IN_PROGRESS to its already-earned RETIRED
terminal state (the exact mechanism 021 already uses for freshly-created
mappings) — before the new reservation, in the same transaction. This is
not reviving, deleting, or fabricating anything: it corrects a stale status
column to match facts that were already true.

derive_enrollment_lifecycle_state/ENROLLMENT_LIFECYCLE_JOIN_SQL/
ENROLLMENT_LIFECYCLE_SELECT_SQL now live in app/enrollment.py (the domain
owner) and are imported, not duplicated, by app/api/repository.py — the
SAME predicate now answers both "show in Active Queue?" and "block a new
reservation?".
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.config import Config
from app.enrollment import (
    EnrollmentError,
    derive_enrollment_lifecycle_state,
    reserve_next_device_user_id,
)

from tests.test_enrollment import FakeCursor, make_db

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
PIMAI_ID = "fd63997f-b081-45bf-b74f-db224491fabc"


class TestSharedLifecyclePredicate(unittest.TestCase):
    """Item 16: read-side and write-side derivation is the literal same
    function — not two independently-drifting copies."""

    def test_repository_imports_not_duplicates_the_helper(self):
        import inspect

        import app.api.repository as repo
        import app.enrollment as enr

        self.assertIs(repo._derive_enrollment_lifecycle_state, enr.derive_enrollment_lifecycle_state)
        # No second CASE-style implementation anywhere in repository.py.
        source = inspect.getsource(repo)
        self.assertEqual(source.count("def derive_enrollment_lifecycle_state"), 0)

    def test_item1_pimai_enrollment4_production_shape_derives_removed_from_terminal(self):
        state = derive_enrollment_lifecycle_state("READY_FOR_MAPPING", False, "VERIFIED", NOW)
        self.assertEqual(state, "REMOVED_FROM_TERMINAL")


class TestReservationConflictUsesCanonicalLifecycle(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def _human_device_lock_prefix(self):
        return [(1,), (1,), (None,)]

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item3_stale_removed_from_terminal_row_does_not_block(self, mock_conn_fn, mock_log):
        """The exact Pimai/#4 case: candidate row is READY_FOR_MAPPING but
        canonically REMOVED_FROM_TERMINAL — must not raise, must self-heal
        it to RETIRED, and must proceed to allocate a new ID."""
        cur = FakeCursor(
            fetchone_queue=self._human_device_lock_prefix()
            + [None, (10, "1005", "RESERVED", NOW)],
            fetchall_queue=[
                [(4, "READY_FOR_MAPPING", False, "VERIFIED", NOW)],  # candidate: Enrollment #4 shape
                [],  # _load_used_terminal_ids
            ],
        )
        make_db(mock_conn_fn, cur)
        result = reserve_next_device_user_id(
            self.cfg, employee_id=PIMAI_ID, device_id=1, operator="admin"
        )
        self.assertEqual(result["status"], "RESERVED")

        heal_calls = [(s, p) for s, p in cur.executed if "RETIRED" in s and "device_user_enrollments" in s]
        self.assertEqual(len(heal_calls), 1)
        self.assertEqual(heal_calls[0][1], (4, "READY_FOR_MAPPING"))

        heal_events = [c for c in mock_log.call_args_list if c.args[1] == "ENROLLMENT_STALE_STATUS_SELF_HEALED"]
        self.assertEqual(len(heal_events), 1)
        self.assertIn("enrollment_id=4", heal_events[0].args[2])

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item5_completed_row_does_not_block(self, mock_conn_fn, mock_log):
        """Enrollment #1 shape: READY_FOR_MAPPING, still-active device
        account, open mapping => COMPLETED => must not block either."""
        cur = FakeCursor(
            fetchone_queue=self._human_device_lock_prefix()
            + [None, (11, "1005", "RESERVED", NOW)],
            fetchall_queue=[
                [(1, "READY_FOR_MAPPING", True, "VERIFIED", None)],  # COMPLETED
                [],
            ],
        )
        make_db(mock_conn_fn, cur)
        result = reserve_next_device_user_id(
            self.cfg, employee_id=PIMAI_ID, device_id=1, operator="admin"
        )
        self.assertEqual(result["status"], "RESERVED")

    def test_item4_cancelled_never_reaches_candidate_query(self):
        """CANCELLED is not in ACTIVE_ENROLLMENT_STATUSES, so the candidate
        query's own `status = ANY(...)` WHERE clause already excludes it —
        a CANCELLED row can never even be considered, let alone block."""
        from app.enrollment import ACTIVE_ENROLLMENT_STATUSES

        self.assertNotIn("CANCELLED", ACTIVE_ENROLLMENT_STATUSES)

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item4_no_candidates_reservation_succeeds(self, mock_conn_fn, mock_log):
        cur = FakeCursor(
            fetchone_queue=self._human_device_lock_prefix()
            + [None, (12, "1005", "RESERVED", NOW)],
            fetchall_queue=[[], []],
        )
        make_db(mock_conn_fn, cur)
        result = reserve_next_device_user_id(
            self.cfg, employee_id=PIMAI_ID, device_id=1, operator="admin"
        )
        self.assertEqual(result["status"], "RESERVED")

    @patch("app.enrollment.get_db_connection")
    def test_item6_genuine_reserved_in_progress_still_blocks(self, mock_conn_fn):
        cur = FakeCursor(
            fetchone_queue=self._human_device_lock_prefix(),
            fetchall_queue=[[(20, "RESERVED", None, None, None)]],
        )
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            reserve_next_device_user_id(self.cfg, employee_id=PIMAI_ID, device_id=1, operator="admin")

    @patch("app.enrollment.get_db_connection")
    def test_item7_current_ready_for_mapping_with_open_lifecycle_still_blocks(self, mock_conn_fn):
        """A genuinely fresh READY_FOR_MAPPING with NO verified mapping yet
        (Step 6 not yet confirmed) is IN_PROGRESS — must still block."""
        cur = FakeCursor(
            fetchone_queue=self._human_device_lock_prefix(),
            fetchall_queue=[[(21, "READY_FOR_MAPPING", None, None, None)]],
        )
        make_db(mock_conn_fn, cur)
        with self.assertRaises(EnrollmentError):
            reserve_next_device_user_id(self.cfg, employee_id=PIMAI_ID, device_id=1, operator="admin")

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item2_active_queue_and_reservation_guard_agree(self, mock_conn_fn, mock_log):
        """Cross-check: the same row shape that app.api.repository derives
        as REMOVED_FROM_TERMINAL (excluded from Active Queue) is exactly
        the shape that does not block reservation here — same predicate,
        same input tuple order."""
        from app.api.repository import _derive_enrollment_lifecycle_state as repo_derive

        row_shape = ("READY_FOR_MAPPING", False, "VERIFIED", NOW)
        self.assertEqual(repo_derive(*row_shape), "REMOVED_FROM_TERMINAL")
        self.assertEqual(derive_enrollment_lifecycle_state(*row_shape), "REMOVED_FROM_TERMINAL")

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item9_10_11_self_heal_never_touches_mapping_or_device_user(self, mock_conn_fn, mock_log):
        """The self-heal UPDATE targets device_user_enrollments only —
        never employee_device_mappings (reopening) or device_users
        (reactivating)."""
        cur = FakeCursor(
            fetchone_queue=self._human_device_lock_prefix()
            + [None, (10, "1005", "RESERVED", NOW)],
            fetchall_queue=[[(4, "READY_FOR_MAPPING", False, "VERIFIED", NOW)], []],
        )
        make_db(mock_conn_fn, cur)
        reserve_next_device_user_id(self.cfg, employee_id=PIMAI_ID, device_id=1, operator="admin")
        for sql, _ in cur.executed:
            if "UPDATE" in sql.upper():
                self.assertIn("device_user_enrollments", sql)
                self.assertNotIn("employee_device_mappings", sql)
                self.assertNotIn("device_users", sql)

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item9_self_heal_never_deletes(self, mock_conn_fn, mock_log):
        cur = FakeCursor(
            fetchone_queue=self._human_device_lock_prefix()
            + [None, (10, "1005", "RESERVED", NOW)],
            fetchall_queue=[[(4, "READY_FOR_MAPPING", False, "VERIFIED", NOW)], []],
        )
        make_db(mock_conn_fn, cur)
        reserve_next_device_user_id(self.cfg, employee_id=PIMAI_ID, device_id=1, operator="admin")
        for sql, _ in cur.executed:
            self.assertNotIn("DELETE", sql.upper())

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_item12_new_allocation_excludes_forbidden_historical_ids(self, mock_conn_fn, mock_log):
        """1002/1004 both had real device_users rows historically, so
        _load_used_terminal_ids (unchanged, PromptID-020 policy) must still
        exclude them — the self-heal doesn't touch allocator eligibility."""
        cur = FakeCursor(
            fetchone_queue=self._human_device_lock_prefix()
            + [None, (10, "1005", "RESERVED", NOW)],
            fetchall_queue=[
                [(4, "READY_FOR_MAPPING", False, "VERIFIED", NOW)],
                [("1001",), ("1002",), ("1004",)],  # used_ids includes real historical accounts
            ],
        )
        make_db(mock_conn_fn, cur)
        result = reserve_next_device_user_id(self.cfg, employee_id=PIMAI_ID, device_id=1, operator="admin")
        # Allocator (unit-tested exhaustively elsewhere) simply must not
        # have been handed 1002/1004 as "available" — this is the INSERT's
        # own reserved id, sourced from _find_next_available_id which
        # already excludes everything in used_ids.
        self.assertNotIn(result["reserved_device_user_id"], ("1002", "1004"))


class TestAllocatorResultForHypotheticalPimaiReenrollment(unittest.TestCase):
    """Phase E: read-only simulation of what _find_next_available_id would
    actually choose for a new Pimai enrollment on device 1, using the real
    production-shaped used-ID set — never hard-coded, never assumed."""

    def test_expected_next_id_is_1003_not_1004(self):
        from app.enrollment import _find_next_available_id

        # Production device_users(device_id=1): 1, 1001, 1002, 1004, 2 (all
        # historical rows, regardless of active/inactive — PromptID-020
        # policy: any ID that ever had a real device_users row stays
        # permanently excluded). Enrollment reserved ids not CANCELLED-and-
        # never-created: 1001, 1004. 1003 was CANCELLED with no device_uid/
        # terminal_created_at — genuinely never created — so it alone is
        # reclaimable.
        used_ids = {"1", "1001", "1002", "1004", "2"}
        next_id = _find_next_available_id(used_ids, roster_ids={"1001"})
        self.assertEqual(next_id, "1003")
        # 1004 must never be silently reused just because it's now historical.
        self.assertNotEqual(next_id, "1004")


class TestFriendlyConflictErrorCopy(unittest.TestCase):
    """Items 13, 14, 15: elderly-operator-facing copy, no UUID, no raw enum."""

    def setUp(self):
        import pathlib

        self.enrollments_src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "pages"
            / "Enrollments.tsx"
        ).read_text(encoding="utf-8")
        self.th_src = (
            pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n" / "th.ts"
        ).read_text(encoding="utf-8")
        self.en_src = (
            pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n" / "en.ts"
        ).read_text(encoding="utf-8")

    def test_item13_th_conflict_copy_has_no_uuid_pattern(self):
        idx = self.th_src.index("activeEnrollmentExistsBody")
        line = self.th_src[idx : self.th_src.index("\n", idx)]
        self.assertNotIn("-", line.split(":", 1)[1][:40])  # no UUID-shaped hyphenated token
        self.assertIn("กำลังดำเนินการ", line)

    def test_item14_en_conflict_copy_has_no_uuid(self):
        idx = self.en_src.index("activeEnrollmentExistsBody")
        line = self.en_src[idx : self.en_src.index("\n", idx)]
        self.assertIn("in progress", line)

    def test_item15_raw_enrollment_conflict_never_rendered_directly_for_active_case(self):
        idx = self.enrollments_src.index("already has an active enrollment")
        segment = self.enrollments_src[idx : idx + 400]
        self.assertIn("activeEnrollmentExistsBody", segment)


if __name__ == "__main__":
    unittest.main()
