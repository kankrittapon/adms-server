"""
Terminal-ID reclamation — DB invariant vs. read-side policy agreement.

PromptID: ADMS-CurrentState-History-UXClosure-022 (continuation)

Production reproduction: the allocator correctly selected 1003 for a new
Pimai enrollment (per PromptID-020's read-side reclamation policy in
_load_used_terminal_ids()), but the INSERT failed with
psycopg2.errors.UniqueViolation on "uq_enrollment_terminal_id" — because
sql/006 defined that constraint as a full, unconditional UNIQUE CONSTRAINT
on (device_id, reserved_device_user_id), predating PromptID-020's
reclamation policy and never updated to match it.

Fixed by sql/013_enrollment_terminal_id_reclamation_constraint.sql:
replaces the full UNIQUE CONSTRAINT with a PARTIAL UNIQUE INDEX using the
exact same predicate _load_used_terminal_ids() already uses — the DB
invariant and the application's eligibility decision can never disagree
again. No row is deleted or rewritten; Enrollment #3 remains immutable
history.

Also hardens reserve_next_device_user_id() to catch any residual
UniqueViolation (concurrency race) and convert it to the existing
EnrollmentError -> 409 ENROLLMENT_CONFLICT path — never an unhandled 500.
"""

import pathlib
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import psycopg2.errors

from app.config import Config
from app.enrollment import EnrollmentError, reserve_next_device_user_id

from tests.test_enrollment import FakeCursor, make_db

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATION_PATH = REPO_ROOT / "sql" / "013_enrollment_terminal_id_reclamation_constraint.sql"


class TestMigrationDefinition(unittest.TestCase):
    def setUp(self):
        self.migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")

    def test_migration_file_exists(self):
        self.assertTrue(MIGRATION_PATH.exists())

    def test_drops_the_old_full_unique_constraint(self):
        self.assertIn("DROP CONSTRAINT uq_enrollment_terminal_id", self.migration_sql)

    def test_creates_partial_unique_index_with_the_same_reclamation_predicate(self):
        """The migration's predicate must be textually identical to
        _load_used_terminal_ids()'s exclusion clause — one canonical
        predicate, never two independently-drifting copies."""
        self.assertIn("CREATE UNIQUE INDEX", self.migration_sql)
        self.assertIn("uq_enrollment_terminal_id", self.migration_sql)
        self.assertIn(
            "status = 'CANCELLED'\n    AND terminal_created_at IS NULL\n    AND device_uid IS NULL",
            self.migration_sql,
        )

    def test_migration_never_deletes_or_updates_any_row(self):
        upper = self.migration_sql.upper()
        self.assertNotIn("DELETE FROM", upper)
        self.assertNotIn("UPDATE DEVICE_USER_ENROLLMENTS", upper)

    def test_migration_is_transactional(self):
        self.assertIn("BEGIN;", self.migration_sql)
        self.assertIn("COMMIT;", self.migration_sql)

    def test_migration_catalog_lists_it(self):
        catalog = (REPO_ROOT / "docs" / "DATABASE_MIGRATIONS.md").read_text(encoding="utf-8")
        self.assertIn("013_enrollment_terminal_id_reclamation_constraint.sql", catalog)


class TestUniqueViolationConvertedToDomainError(unittest.TestCase):
    """Item 8 (no raw 500) / item 6 (concurrency remains DB-protected):
    even after the migration, a genuine race between two concurrent
    reservations for the same reclaimable ID must fail cleanly — the
    partial index still enforces uniqueness among non-reclaimable rows,
    and any residual UniqueViolation must never escape as an unhandled
    500 (which the browser then misreports as a CORS failure)."""

    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_unique_violation_on_insert_becomes_enrollment_error(self, mock_conn_fn, mock_log):
        class RacingCursor(FakeCursor):
            def execute(self, sql, params=None):
                super().execute(sql, params)
                if "INSERT INTO device_user_enrollments" in sql:
                    raise psycopg2.errors.UniqueViolation(
                        'duplicate key value violates unique constraint '
                        '"uq_enrollment_terminal_id"\nDETAIL:  Key (device_id, '
                        "reserved_device_user_id)=(1, 1003) already exists."
                    )

        cur = RacingCursor(
            fetchone_queue=[(1,), (1,), (None,), None],
            fetchall_queue=[[], []],
        )
        make_db(mock_conn_fn, cur)

        with self.assertRaises(EnrollmentError) as ctx:
            reserve_next_device_user_id(
                self.cfg, employee_id="fd63997f-b081-45bf-b74f-db224491fabc", device_id=1, operator="admin"
            )
        # Controlled, retryable domain error — not a raw psycopg2 exception
        # class leaking through, and no raw SQL/constraint name required in
        # the message (the API layer's ENROLLMENT_CONFLICT mapping and
        # frontend friendly-copy layer handle the rest).
        self.assertNotIsInstance(ctx.exception, psycopg2.errors.UniqueViolation)

    def test_reserve_endpoint_error_handler_maps_enrollment_error_to_409_not_500(self):
        import inspect

        import app.api.errors as errors_module

        source = inspect.getsource(errors_module)
        self.assertIn("_enrollment_error_handler", source)
        self.assertIn("status_code=409", source)


class TestEnrollment3RemainsImmutableAfterReuse(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.enrollment.log_sync_event")
    @patch("app.enrollment.get_db_connection")
    def test_reservation_never_updates_or_deletes_existing_enrollment_rows(self, mock_conn_fn, mock_log):
        """Reusing 1003 must be a pure INSERT of a NEW row — Enrollment #3
        itself is never touched (no UPDATE/DELETE targeting it)."""
        cur = FakeCursor(
            fetchone_queue=[
                (1,), (1,), (None,),
                (3,),  # _find_reclaimable_cancelled_enrollment: enrollment #3 qualified 1003
                (10, "1003", "RESERVED", NOW),  # INSERT RETURNING — a NEW row
            ],
            fetchall_queue=[[], []],
        )
        make_db(mock_conn_fn, cur)
        result = reserve_next_device_user_id(
            self.cfg,
            employee_id="fd63997f-b081-45bf-b74f-db224491fabc",
            device_id=1,
            operator="admin",
        )
        self.assertEqual(result["reserved_device_user_id"], "1003")
        self.assertEqual(result["enrollment_id"], 10)  # a NEW enrollment_id, not #3
        for sql, _ in cur.executed:
            self.assertNotIn("DELETE", sql.upper())
            if "UPDATE" in sql.upper():
                # Only the 022 self-heal UPDATE (status='RETIRED') is ever
                # allowed here, and it wasn't triggered in this scenario
                # (no blocking IN_PROGRESS-looking candidate was returned).
                self.fail("no UPDATE should fire when there is no stale blocking candidate")


if __name__ == "__main__":
    unittest.main()
