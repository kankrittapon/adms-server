-- SQL Migration 012: Runtime Write Session (Layer 2 of the two-layer write-control model)
-- PromptID: ADMS-FullSystem-P0P1-Hardening-007
-- Description: Additive, reversible schema for a short-lived, ADMIN-opened,
--              auditable "work session" that authorizes domain writes.
--
--   write_sessions : at most one currently-open (closed_at IS NULL) row.
--                     "Active" for authorization purposes additionally
--                     requires expires_at > now() — expiry is time-based and
--                     checked at read time by application code (see
--                     app/write_session.py); this migration does not attempt
--                     to encode expires_at > now() in the index predicate
--                     (Postgres partial indexes require immutable predicates,
--                     which now() is not).
--
-- Concurrency:
--   The partial unique index below guarantees at most one row with
--   closed_at IS NULL at the database level, independent of expiry — this is
--   a hard backstop. The actual "open a session" operation additionally
--   takes a Postgres transaction-scoped advisory lock
--   (pg_advisory_xact_lock) before evaluating/reaping any expired-but-
--   unclosed row and inserting a new one, so concurrent open attempts
--   (including across multiple API worker processes in a future
--   multi-worker deployment) serialize correctly and cannot both succeed.
--   See app/write_session.py:open_write_session for the transactional logic.
--
-- Safety:
--   - Additive only. No existing table is altered.
--   - ADMIN-only open/close, enforced at the API layer (RBAC), not here.
--   - This table governs Layer 2 (runtime write session) only. Layer 1
--     (the API_WRITE_ENABLED infrastructure master gate) remains an env var
--     and unconditionally overrides Layer 2 — see app/api/dependencies.py.
--   - A session with closed_at IS NULL and a future expires_at remains valid
--     across an API process restart by design (an ADMIN should not lose
--     their work window just because the API process recycled). A session
--     past expires_at is inert whether or not the process restarted — there
--     is no invisible-unlimited-write-window failure mode.

BEGIN;

CREATE TABLE IF NOT EXISTS write_sessions (
  session_id    BIGSERIAL PRIMARY KEY,
  opened_by     BIGINT NOT NULL REFERENCES operators(operator_id),
  opened_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at    TIMESTAMPTZ NOT NULL,
  reason        TEXT NOT NULL,
  closed_by     BIGINT REFERENCES operators(operator_id),
  closed_at     TIMESTAMPTZ,
  close_reason  TEXT CHECK (close_reason IN ('ADMIN_CLOSED', 'EXPIRED')),
  CONSTRAINT chk_write_sessions_expiry CHECK (expires_at > opened_at),
  CONSTRAINT chk_write_sessions_close_consistency CHECK (
    (closed_at IS NULL AND close_reason IS NULL)
    OR (closed_at IS NOT NULL AND close_reason IS NOT NULL)
  )
);

-- At most one row may be "unclosed" (closed_at IS NULL) at any time. This is
-- a database-level backstop; the advisory-lock-guarded open logic in
-- app/write_session.py is what actually makes open/reap/insert atomic.
CREATE UNIQUE INDEX IF NOT EXISTS uq_write_sessions_one_unclosed
  ON write_sessions ((true))
  WHERE closed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_write_sessions_opened_by
  ON write_sessions (opened_by);

COMMIT;
