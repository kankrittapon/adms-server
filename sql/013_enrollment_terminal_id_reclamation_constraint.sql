-- SQL Migration 013: Terminal-ID reclamation — fix the DB uniqueness invariant
-- PromptID: ADMS-CurrentState-History-UXClosure-022
--
-- PromptID-020 introduced a read-side reclamation policy in
-- app/enrollment.py::_load_used_terminal_ids(): a CANCELLED reservation
-- whose terminal account was NEVER created (terminal_created_at IS NULL AND
-- device_uid IS NULL) no longer permanently burns its terminal ID. That
-- policy was never reflected in the DB schema — sql/006's
-- uq_enrollment_terminal_id was a full, unconditional UNIQUE CONSTRAINT
-- (comment: "never immediately recyclable"), which still rejects a second
-- INSERT for the same (device_id, reserved_device_user_id) even when the
-- allocator has correctly decided the ID is safely reclaimable.
--
-- Production reproduction: Enrollment #3 (device 1, terminal ID 1003) was
-- CANCELLED before any terminal account was ever created. The allocator
-- correctly selects 1003 for a new reservation, but the unconditional
-- UNIQUE CONSTRAINT rejects the INSERT with a raw UniqueViolation.
--
-- Fix: replace the full UNIQUE CONSTRAINT with a PARTIAL UNIQUE INDEX that
-- excludes exactly the reclaimable case — the SAME predicate
-- _load_used_terminal_ids() already uses, so the DB invariant and the
-- application's eligibility decision can never disagree again. A terminal
-- ID that ever had a real device_users/terminal-account incarnation (1001,
-- 1002, 1004) is untouched by this change and remains permanently unique
-- — this migration only relaxes the CANCELLED-and-never-created case.
--
-- Concurrency: this is still a real DB-level constraint (an index, not an
-- application-level check) — two concurrent INSERTs attempting to reserve
-- the same reclaimable ID will still conflict at the index (neither new row
-- is CANCELLED, so both satisfy the partial predicate and collide), on top
-- of the existing pg_advisory_xact_lock serialization per device in
-- reserve_next_device_user_id().
--
-- Does NOT delete or modify any existing row. Enrollment #3 remains
-- immutable history.

BEGIN;

ALTER TABLE device_user_enrollments
  DROP CONSTRAINT uq_enrollment_terminal_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_enrollment_terminal_id
  ON device_user_enrollments (device_id, reserved_device_user_id)
  WHERE NOT (
    status = 'CANCELLED'
    AND terminal_created_at IS NULL
    AND device_uid IS NULL
  );

COMMIT;
