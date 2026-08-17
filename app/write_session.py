"""
Runtime write session — Layer 2 of the two-layer write-control model.

PromptID: ADMS-FullSystem-P0P1-Hardening-007

Layer 1 (API_WRITE_ENABLED, app/api/dependencies.py:require_writes) is the
env-controlled infrastructure master gate — server-owner controlled, fail
closed, unconditional. Layer 2 (this module) is a short-lived, ADMIN-opened,
auditable permission window that authorizes domain writes ON TOP OF Layer 1.
Both must be open for a domain-mutating endpoint to succeed; neither implies
the other.

Concurrency model:

  At most one write session may be open (closed_at IS NULL) at a time. Every
  operation that opens, closes, or reads session state holds a Postgres
  transaction-scoped advisory lock (pg_advisory_xact_lock) for the duration
  of a single DB transaction, so:

    - "detect + reap an expired-but-unclosed session" and "check whether a
      session is currently active" are always evaluated atomically relative
      to any concurrent open/close/read.
    - Two concurrent open attempts cannot both succeed: the second blocks on
      the advisory lock until the first transaction commits, then sees the
      row the first transaction just inserted and is rejected with
      WriteSessionAlreadyActive.
    - Reaping an expired session is idempotent — once reaped, closed_at is
      set, so no later caller reaps (and therefore audits) it again. This is
      what keeps WRITE_SESSION_EXPIRED audit events to at most one per
      session regardless of how many GET/status or write requests race to
      discover the expiry.

  The advisory lock is transaction-scoped (pg_advisory_xact_lock), not
  session-scoped, so it is always released automatically on commit/rollback
  — a crashed connection can never leak a permanent lock.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.config import Config
from app.db import get_db_connection, log_sync_event

log = logging.getLogger(__name__)

DEFAULT_DURATION_MINUTES = 30

# Fixed advisory lock key for the single write-session "slot". Arbitrary but
# stable — must never collide with another advisory lock use in this codebase
# (there is none today; grep for pg_advisory before reusing this constant).
_ADVISORY_LOCK_KEY = 7_931_004_215_678


class WriteSessionError(Exception):
    """Base class for write-session domain errors."""


class WriteSessionAlreadyActive(WriteSessionError):
    """Raised when open() is attempted while a session is already active."""


def _acquire_lock(cur: Any) -> None:
    cur.execute("SELECT pg_advisory_xact_lock(%s);", (_ADVISORY_LOCK_KEY,))


def _reap_expired(cur: Any) -> Optional[Dict[str, Any]]:
    """Closes the unclosed row iff it has expired. Must be called while
    holding the advisory lock. Returns the reaped session's info (for a
    one-time audit event) or None if nothing was reaped."""
    cur.execute(
        "UPDATE write_sessions SET closed_at = now(), closed_by = NULL, "
        "close_reason = 'EXPIRED' "
        "WHERE closed_at IS NULL AND expires_at <= now() "
        "RETURNING session_id, opened_by, opened_at, expires_at, reason;",
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "session_id": row[0],
        "opened_by": row[1],
        "opened_at": row[2],
        "expires_at": row[3],
        "reason": row[4],
    }


def _fetch_open_session(cur: Any) -> Optional[Dict[str, Any]]:
    """Returns the currently unclosed row (if any), joined to the opener's
    display name. Must be called after _reap_expired in the same
    transaction, so an unclosed row here is genuinely active (expires_at in
    the future)."""
    cur.execute(
        "SELECT ws.session_id, ws.opened_by, o.display_name, ws.opened_at, "
        "ws.expires_at, ws.reason "
        "FROM write_sessions ws JOIN operators o ON o.operator_id = ws.opened_by "
        "WHERE ws.closed_at IS NULL LIMIT 1;",
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "session_id": row[0],
        "opened_by": row[1],
        "opened_by_name": row[2],
        "opened_at": row[3],
        "expires_at": row[4],
        "reason": row[5],
    }


def _status_dict(active_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if active_row is None:
        return {"active": False}
    return {
        "active": True,
        "session_id": active_row["session_id"],
        "opened_by": active_row["opened_by"],
        "opened_by_name": active_row["opened_by_name"],
        "opened_at": active_row["opened_at"],
        "expires_at": active_row["expires_at"],
        "reason": active_row["reason"],
    }


def _audit_expired(cfg: Config, expired: Dict[str, Any]) -> None:
    log_sync_event(
        cfg,
        "WRITE_SESSION_EXPIRED",
        "session_id=%s opened_by=%s reason=%r expires_at=%s"
        % (
            expired["session_id"],
            expired["opened_by"],
            expired["reason"],
            expired["expires_at"].isoformat(),
        ),
    )


def get_write_session_status(cfg: Config) -> Dict[str, Any]:
    """Read-only status check. Also reaps (and audits, at most once) an
    expired-but-unclosed session as a side effect — this is the mechanism by
    which WRITE_SESSION_EXPIRED gets emitted even if no one ever calls
    close() on an expired session."""
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            _acquire_lock(cur)
            expired = _reap_expired(cur)
            active = _fetch_open_session(cur)
            conn.commit()
    if expired is not None:
        _audit_expired(cfg, expired)
    return _status_dict(active)


def is_write_session_active(cfg: Config) -> tuple[bool, bool]:
    """Cheap variant for the require_write_session dependency: returns
    (active, was_just_reaped_as_expired) without building the full status
    payload. was_just_reaped_as_expired distinguishes "your session just
    expired" (WRITE_SESSION_EXPIRED) from "no session was ever open"
    (WRITE_SESSION_REQUIRED) for this specific request."""
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            _acquire_lock(cur)
            expired = _reap_expired(cur)
            active = _fetch_open_session(cur)
            conn.commit()
    if expired is not None:
        _audit_expired(cfg, expired)
    return (active is not None, expired is not None)


def open_write_session(
    cfg: Config,
    opened_by_operator_id: int,
    opened_by_username: str,
    reason: str,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
) -> Dict[str, Any]:
    """ADMIN-only (enforced by the caller/router). Opens a new write session
    if none is currently active, reaping an expired-but-unclosed session
    first so it never blocks a legitimate new open."""
    if not reason or not str(reason).strip():
        raise WriteSessionError("reason is required to open a write session")
    if duration_minutes <= 0:
        raise WriteSessionError("duration_minutes must be positive")

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            _acquire_lock(cur)
            expired = _reap_expired(cur)
            existing = _fetch_open_session(cur)
            if existing is not None:
                conn.rollback()
                if expired is not None:
                    _audit_expired(cfg, expired)
                    log_sync_event(
                        cfg,
                        "WRITE_SESSION_OPEN_FAILED",
                        "attempted_by=%s reason=%r — a session is already active "
                        "(session_id=%s opened_by=%s)"
                        % (opened_by_username, reason, existing["session_id"], existing["opened_by_name"]),
                    )
                else:
                    log_sync_event(
                        cfg,
                        "WRITE_SESSION_OPEN_FAILED",
                        "attempted_by=%s reason=%r — a session is already active "
                        "(session_id=%s opened_by=%s)"
                        % (opened_by_username, reason, existing["session_id"], existing["opened_by_name"]),
                    )
                raise WriteSessionAlreadyActive(
                    "a write session is already active (opened by %s)" % existing["opened_by_name"]
                )

            expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
            cur.execute(
                "INSERT INTO write_sessions (opened_by, expires_at, reason) "
                "VALUES (%s, %s, %s) "
                "RETURNING session_id, opened_at, expires_at;",
                (opened_by_operator_id, expires_at, reason),
            )
            row = cur.fetchone()
            conn.commit()

    if expired is not None:
        _audit_expired(cfg, expired)
    log_sync_event(
        cfg,
        "WRITE_SESSION_OPENED",
        "session_id=%s opened_by=%s reason=%r expires_at=%s"
        % (row[0], opened_by_username, reason, row[2].isoformat()),
    )
    return {
        "active": True,
        "session_id": row[0],
        "opened_by": opened_by_operator_id,
        "opened_by_name": opened_by_username,
        "opened_at": row[1],
        "expires_at": row[2],
        "reason": reason,
    }


def close_write_session(
    cfg: Config,
    closed_by_operator_id: int,
    closed_by_username: str,
) -> Dict[str, Any]:
    """ADMIN-only (enforced by the caller/router). Idempotent: closing when
    nothing is active simply reports {active: False} — it is not an error,
    since two ADMINs racing to close is a benign, expected case."""
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            _acquire_lock(cur)
            expired = _reap_expired(cur)
            existing = _fetch_open_session(cur)
            if existing is None:
                conn.commit()
                if expired is not None:
                    _audit_expired(cfg, expired)
                return {"active": False, "closed_at": None}

            cur.execute(
                "UPDATE write_sessions SET closed_at = now(), closed_by = %s, "
                "close_reason = 'ADMIN_CLOSED' WHERE session_id = %s "
                "RETURNING closed_at;",
                (closed_by_operator_id, existing["session_id"]),
            )
            closed_row = cur.fetchone()
            conn.commit()

    if expired is not None:
        _audit_expired(cfg, expired)
    log_sync_event(
        cfg,
        "WRITE_SESSION_CLOSED",
        "session_id=%s closed_by=%s (opened_by=%s)"
        % (existing["session_id"], closed_by_username, existing["opened_by_name"]),
    )
    return {"active": False, "closed_at": closed_row[0]}
