"""
Controlled device enrollment infrastructure.

PromptID: ADMS-Data-DeviceEnrollmentWorkflow-002

Implements the minimum infrastructure for the controlled production enrollment
workflow:

    Human Master -> reserve production device_user_id -> create terminal account
    -> physical fingerprint enrollment -> controlled scan -> operator confirmation
    -> READY_FOR_MAPPING

Safety invariants enforced here:

- No Human <-> Device mapping is created. employee_device_mappings remains the
  sole authoritative source of VERIFIED ownership and is never touched here.
- No Human Master records are created or modified.
- No attendance rows are modified.
- No fingerprint template data is read, exported, or stored.
- Terminal account creation requires an explicit reserved ID, an explicit
  Human, an explicit device, an explicit operator action, and an injected
  device connection. It never overwrites an existing terminal account.
- Production terminal IDs start at 1001; legacy test IDs 1/2 are never reused.
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from app.config import Config
from app.db import get_db_connection, ensure_device_user, log_sync_event

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRODUCTION_NAMESPACE_START = 1001
LEGACY_TEST_IDS = frozenset({"1", "2"})
DEFAULT_CONTROLLED_SCAN_WINDOW_MINUTES = 5
MAX_TERMINAL_NAME_LENGTH = 20

# pyzk const.USER_DEFAULT — normal (non-admin) user privilege.
PRIVILEGE_NORMAL_USER = 0

ACTIVE_ENROLLMENT_STATUSES = (
    "RESERVED",
    "TERMINAL_ACCOUNT_CREATED",
    "FINGERPRINT_ENROLLMENT_PENDING",
    "FINGERPRINT_ENROLLED",
    "CONTROLLED_SCAN_PENDING",
    "CONTROLLED_SCAN_CONFIRMED",
    "READY_FOR_MAPPING",
)

ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "RESERVED": {"TERMINAL_ACCOUNT_CREATED", "CANCELLED"},
    "TERMINAL_ACCOUNT_CREATED": {
        "FINGERPRINT_ENROLLMENT_PENDING",
        "FINGERPRINT_ENROLLED",
        "CANCELLED",
    },
    "FINGERPRINT_ENROLLMENT_PENDING": {"FINGERPRINT_ENROLLED", "CANCELLED"},
    "FINGERPRINT_ENROLLED": {"CONTROLLED_SCAN_PENDING", "CANCELLED"},
    "CONTROLLED_SCAN_PENDING": {"CONTROLLED_SCAN_CONFIRMED", "CANCELLED"},
    "CONTROLLED_SCAN_CONFIRMED": {"READY_FOR_MAPPING", "CANCELLED", "RETIRED"},
    "READY_FOR_MAPPING": {"RETIRED"},
    "CANCELLED": set(),
    "RETIRED": set(),
}

# Canonical API action catalog for the enrollment workflow. The frontend uses
# GET /api/v1/enrollments/{id}/next-actions to learn which actions are valid
# in the current state — the state machine is NEVER duplicated in the UI.
#
# Note: role requirements are NOT declared per-action here. The single source
# of truth for "who may mutate an enrollment" is ROLES_ENROLLMENT_MUTATE in
# app/api/auth.py, enforced by the router's Depends(enrollment_mutate) and
# echoed back to the frontend by the next-actions endpoint. A hand-typed
# per-action role string here previously drifted from that enforcement
# (it said "OPERATOR" while ENROLLMENT_OPERATOR was also permitted) — do not
# reintroduce a second, parallel role declaration.
ENROLLMENT_ACTIONS: Dict[str, Dict[str, Any]] = {
    "create-terminal-account": {"target": "TERMINAL_ACCOUNT_CREATED"},
    "start-fingerprint-enrollment": {"target": "FINGERPRINT_ENROLLMENT_PENDING"},
    "confirm-fingerprint": {"target": "FINGERPRINT_ENROLLED"},
    "start-controlled-scan": {"target": "CONTROLLED_SCAN_PENDING"},
    "confirm-controlled-scan": {"target": "CONTROLLED_SCAN_CONFIRMED"},
    "mark-ready-for-mapping": {"target": "READY_FOR_MAPPING"},
    "cancel": {"target": "CANCELLED"},
}

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
GENERIC_PLACEHOLDER_RE = re.compile(r"^Device User\s+\d+$", re.IGNORECASE)

_ENROLLMENT_COLUMNS = [
    "enrollment_id",
    "employee_id",
    "device_id",
    "reserved_device_user_id",
    "status",
    "reserved_by",
    "reserved_at",
    "terminal_created_at",
    "device_uid",
    "fingerprint_confirmed_at",
    "controlled_scan_window_until",
    "controlled_scan_time",
    "confirmed_by",
    "confirmed_at",
    "notes",
]

# Columns _transition() is permitted to write via its extra dict. Anything
# else is rejected to keep dynamic SQL column-safe (defense in depth).
_TRANSITION_COLUMNS = frozenset(
    {
        "fingerprint_confirmed_at",
        "controlled_scan_window_until",
        "controlled_scan_time",
        "confirmed_by",
        "confirmed_at",
    }
)


class EnrollmentError(Exception):
    """Raised when an enrollment operation violates a safety or workflow rule."""


class TerminalAccountConflict(EnrollmentError):
    """Terminal ID exists on the device but cannot be proven to belong to this
    enrollment (identity fields don't match what we expect). The caller must
    never overwrite, inherit, or delete in response to this — it requires a
    human to look at the device and the enrollment and decide."""


class TerminalAccountUnconfirmed(EnrollmentError):
    """A set_user() attempt was made (or the account was expected to already
    exist) but the terminal ID could not be confirmed present via bounded
    roster read-back. This is a genuine failure, distinct from a conflict —
    retrying (which re-enters this same function) is safe and expected."""


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def validate_status_transition(current: str, target: str) -> bool:
    """Returns True if the transition is allowed by the enrollment state model."""
    return target in ALLOWED_TRANSITIONS.get(current, set())


def _find_next_available_id(
    used_ids: Optional[Set[str]] = None,
    roster_ids: Optional[Set[str]] = None,
) -> str:
    """
    Deterministically finds the next available production terminal ID (>= 1001).

    Legacy test IDs 1/2 are always blocked. Both database history/reservations
    (used_ids) and the live terminal roster (roster_ids) are considered.
    IDs progress monotonically; no immediate recycling.
    """
    blocked = set(str(x) for x in (used_ids or ()))
    blocked.update(LEGACY_TEST_IDS)
    if roster_ids:
        blocked.update(str(x) for x in roster_ids)
    candidate = PRODUCTION_NAMESPACE_START
    while str(candidate) in blocked:
        candidate += 1
    return str(candidate)


def validate_terminal_display_name(name: str) -> str:
    """
    Validates and returns a safe terminal display name.

    ZEM560 legacy firmware Thai rendering is not yet verified, so names are
    restricted to ASCII printable text. UUIDs, generic placeholders, pure
    numbers, and Excel-row-style identifiers are rejected.
    """
    if not isinstance(name, str) or not name.strip():
        raise EnrollmentError("display name must be a non-empty string")
    name = name.strip()
    if len(name) > MAX_TERMINAL_NAME_LENGTH:
        raise EnrollmentError(
            "display name exceeds %d characters" % MAX_TERMINAL_NAME_LENGTH
        )
    if not name.isascii() or not name.isprintable():
        raise EnrollmentError(
            "display name must be ASCII printable (Thai rendering on ZEM560 "
            "is not yet verified)"
        )
    if UUID_RE.match(name):
        raise EnrollmentError("display name must not be a UUID")
    if GENERIC_PLACEHOLDER_RE.match(name):
        raise EnrollmentError("generic placeholder display names are not allowed")
    if not re.search(r"[A-Za-z]", name):
        raise EnrollmentError("display name must contain at least one letter")
    return name


def _normalize_scan_time(scan_time: datetime) -> datetime:
    """
    Returns a timezone-aware scan_time.

    Contract: controlled-scan evidence is compared against the DB-stored
    window deadline (TIMESTAMPTZ, UTC). A naive datetime is interpreted as
    UTC, so callers feeding device-local normalized timestamps MUST pass
    tz-aware values (the collector's normalize_device_timestamp returns
    tz-aware UTC) or the window comparison will be skewed.
    """
    if scan_time is None:
        raise EnrollmentError("scan_time is required evidence")
    if scan_time.tzinfo is None:
        scan_time = scan_time.replace(tzinfo=timezone.utc)
    return scan_time


# ---------------------------------------------------------------------------
# Internal DB helpers
# ---------------------------------------------------------------------------


def _fetch_enrollment(cur: Any, enrollment_id: int) -> Dict[str, Any]:
    cur.execute(
        "SELECT %s FROM device_user_enrollments WHERE enrollment_id = %%s;"
        % ", ".join(_ENROLLMENT_COLUMNS),
        (enrollment_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise EnrollmentError("enrollment %s not found" % enrollment_id)
    return dict(zip(_ENROLLMENT_COLUMNS, row))


def _fetch_enrollment_locked(cur: Any, enrollment_id: int) -> Dict[str, Any]:
    """Same as _fetch_enrollment but takes a row lock (FOR UPDATE) so a
    second concurrent call for the same enrollment_id blocks until this
    transaction commits/rolls back — the DB-level half of double-submit
    protection for terminal-account creation (see create_or_reconcile_
    terminal_account). Only used on the terminal-account write path; plain
    reads elsewhere should keep using _fetch_enrollment."""
    cur.execute(
        "SELECT %s FROM device_user_enrollments WHERE enrollment_id = %%s FOR UPDATE;"
        % ", ".join(_ENROLLMENT_COLUMNS),
        (enrollment_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise EnrollmentError("enrollment %s not found" % enrollment_id)
    return dict(zip(_ENROLLMENT_COLUMNS, row))


def _load_used_terminal_ids(cur: Any, device_id: int) -> Set[str]:
    cur.execute(
        "SELECT device_user_id FROM device_users WHERE device_id = %s "
        "UNION "
        "SELECT reserved_device_user_id FROM device_user_enrollments WHERE device_id = %s;",
        (device_id, device_id),
    )
    return {str(r[0]) for r in cur.fetchall()}


def _transition(
    cfg: Config,
    enrollment_id: int,
    target_status: str,
    extra: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            enroll = _fetch_enrollment(cur, enrollment_id)
            if not validate_status_transition(enroll["status"], target_status):
                raise EnrollmentError(
                    "invalid enrollment transition %s -> %s"
                    % (enroll["status"], target_status)
                )
            sets = ["status = %s", "updated_at = now()"]
            params: List[Any] = [target_status]
            if notes is not None:
                sets.append("notes = %s")
                params.append(notes)
            for col, val in (extra or {}).items():
                if col not in _TRANSITION_COLUMNS:
                    raise EnrollmentError(
                        "unsafe transition column %r is not whitelisted" % col
                    )
                sets.append("%s = %%s" % col)
                params.append(val)
            params.append(enrollment_id)
            params.append(enroll["status"])
            cur.execute(
                "UPDATE device_user_enrollments SET %s "
                "WHERE enrollment_id = %%s AND status = %%s;" % ", ".join(sets),
                params,
            )
            if cur.rowcount != 1:
                raise EnrollmentError(
                    "enrollment %s not updated (concurrent state change?)" % enrollment_id
                )
            conn.commit()
    return {"enrollment_id": enrollment_id, "status": target_status}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_enrollment(cfg: Config, enrollment_id: int) -> Dict[str, Any]:
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            return _fetch_enrollment(cur, enrollment_id)


def reserve_next_device_user_id(
    cfg: Config,
    employee_id: str,
    device_id: int,
    operator: str,
    roster_user_ids: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Reserves the next safe production terminal ID for a Human on a device.

    Validates the Human and device exist, that no active enrollment already
    binds the Human to this device, and that the chosen ID is not used on the
    terminal, not reserved, and not a retired/legacy ID. Serializes concurrent
    allocations per device with a transactional advisory lock.

    Creates a RESERVED enrollment row. Does NOT create a terminal account.
    """
    if not operator or not str(operator).strip():
        raise EnrollmentError("operator is required for reservation")
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM human_employees "
                "WHERE employee_id = %s AND active = true AND production_scope = true;",
                (employee_id,),
            )
            if not cur.fetchone():
                raise EnrollmentError(
                    "Human %s does not exist or is inactive (or is excluded "
                    "from production scope)" % employee_id
                )

            cur.execute(
                "SELECT 1 FROM devices WHERE device_id = %s AND active = true;",
                (device_id,),
            )
            if not cur.fetchone():
                raise EnrollmentError(
                    "Device %s does not exist or is inactive" % device_id
                )

            # Serialize allocations per device (concurrency safety)
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext('adms_enroll_' || %s::text));",
                (device_id,),
            )
            cur.fetchone()

            # Defense-in-depth: reject duplicate active enrollment for the same
            # Human + device (the partial unique index enforces this too).
            cur.execute(
                "SELECT enrollment_id FROM device_user_enrollments "
                "WHERE employee_id = %s AND device_id = %s "
                "AND status = ANY(%s) LIMIT 1;",
                (employee_id, device_id, list(ACTIVE_ENROLLMENT_STATUSES)),
            )
            if cur.fetchone():
                raise EnrollmentError(
                    "Human %s already has an active enrollment on device %s"
                    % (employee_id, device_id)
                )

            used_ids = _load_used_terminal_ids(cur, device_id)
            next_id = _find_next_available_id(used_ids, roster_user_ids)

            cur.execute(
                "INSERT INTO device_user_enrollments "
                "(employee_id, device_id, reserved_device_user_id, status, reserved_by) "
                "VALUES (%s, %s, %s, 'RESERVED', %s) "
                "RETURNING enrollment_id, reserved_device_user_id, status, reserved_at;",
                (employee_id, device_id, next_id, operator),
            )
            row = cur.fetchone()
            if row is None:
                raise EnrollmentError("reservation insert failed")
            conn.commit()

    log_sync_event(
        cfg,
        "ENROLLMENT_RESERVED",
        "enrollment_id=%s terminal_id=%s device_id=%s reserved_by=%s"
        % (row[0], row[1], device_id, operator),
    )
    return {
        "enrollment_id": row[0],
        "reserved_device_user_id": row[1],
        "status": row[2],
        "reserved_at": row[3],
        "employee_id": employee_id,
        "device_id": device_id,
    }


# Bounded read-back tuning. ZEM560/pyzk set_user() return values are not
# authoritative (observed in production: returns False on a call the device
# actually committed) — ground truth is always a subsequent roster read.
READBACK_RETRIES = 3
READBACK_DELAY_SECONDS = 2.0

# States from which terminal-account creation/reconciliation may run. RESERVED
# is the normal entry point; TERMINAL_ACCOUNT_CREATED makes a repeat call
# idempotent (retry after a timeout, browser double-submit that lost the
# race, or an explicit "Verify / Reconcile" action) instead of erroring.
_TERMINAL_ACCOUNT_ALLOWED_STATES = ("RESERVED", "TERMINAL_ACCOUNT_CREATED")


def _match_roster_user(roster: List[Any], target_id: str) -> Optional[Any]:
    for u in roster or []:
        if str(getattr(u, "user_id", "")) == str(target_id):
            return u
    return None


def _identity_matches(user: Any, target_id: str) -> bool:
    """Verifies only the fields this device/library combination can reliably
    expose: user_id (matched by the caller before this is invoked) and
    privilege. Display name is intentionally NOT used as a match criterion —
    ZK firmware can truncate/alter it, so treating it as authoritative would
    invent a guarantee the hardware doesn't provide."""
    privilege = getattr(user, "privilege", None)
    if privilege is None:
        return False
    try:
        return int(privilege) == PRIVILEGE_NORMAL_USER
    except (TypeError, ValueError):
        return False


def _bounded_roster_readback(
    device: Any,
    target_id: str,
    retries: int = READBACK_RETRIES,
    delay: float = READBACK_DELAY_SECONDS,
    sleep_fn: Optional[Any] = None,
) -> Optional[Any]:
    """Polls the roster up to `retries` times, waiting `delay` seconds between
    attempts, until the target ID appears. Returns the matching roster entry,
    or None if it never appeared within the bound. A transport error on any
    individual read is treated as "not yet visible" and retried, not raised —
    only exhausting all retries is reported to the caller.

    sleep_fn defaults to None and resolves to time.sleep at call time (not as
    a bound default-argument value) specifically so tests can patch
    app.enrollment.time.sleep — a default argument bound at function-
    definition time would capture the function object directly and be immune
    to later patching of the time module attribute.
    """
    _sleep = sleep_fn or time.sleep
    for attempt in range(retries):
        try:
            roster = device.get_users() or []
        except Exception as e:
            log.warning(
                "roster read-back attempt %d/%d failed for terminal ID %s: %s",
                attempt + 1, retries, target_id, e,
            )
            roster = []
        match = _match_roster_user(roster, target_id)
        if match is not None:
            return match
        if attempt < retries - 1:
            _sleep(delay)
    return None


def create_or_reconcile_terminal_account(
    cfg: Config,
    enrollment_id: int,
    display_name: str,
    device: Any,
) -> Dict[str, Any]:
    """
    Idempotently creates OR reconciles the terminal account for an enrollment.

    This is the single canonical entry point for turning a RESERVED enrollment
    into TERMINAL_ACCOUNT_CREATED, safe against:
      - set_user() returning False/None/raising on a call the device actually
        committed (observed ZEM560/pyzk behavior — never trusted alone).
      - retries after a DeviceCommandBus timeout of unknown outcome.
      - duplicate browser clicks / concurrent callers for the same enrollment
        (serialized via a DB row lock on the enrollment; see
        _fetch_enrollment_locked).
      - re-entry on an enrollment that is already TERMINAL_ACCOUNT_CREATED
        (idempotent success, no second set_user() call, no state corruption).

    Algorithm:
      1. Lock + load the enrollment row; must be RESERVED or
         TERMINAL_ACCOUNT_CREATED.
      2. Read the roster once, before any mutation decision.
      3. If the reserved ID is absent: call set_user() exactly once (its
         return value is logged but never treated as authoritative), then
         perform a bounded read-back. Still absent after the bound -> raise
         TerminalAccountUnconfirmed (genuine failure; state unchanged, safe
         to retry — retry re-enters this same function).
      4. If the reserved ID is present (either from the start, or from the
         read-back above): verify identity (privilege only — see
         _identity_matches). Mismatch -> raise TerminalAccountConflict
         (STOP; never overwrite/inherit/delete). Match -> reconcile.
      5. Reconcile: idempotently transition to TERMINAL_ACCOUNT_CREATED
         (no-op if already there), set terminal_created_at only if unset,
         capture device_uid, ensure the canonical device_users row. Emits a
         TERMINAL_ACCOUNT_CREATED audit event if this call performed the
         set_user() mutation, or TERMINAL_ACCOUNT_RECONCILED if it didn't
         (the account already existed on entry, from a prior attempt whose
         result was previously unknown to this enrollment).

    No Human mapping is created or touched here, ever.
    """
    name = validate_terminal_display_name(display_name)
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            enroll = _fetch_enrollment_locked(cur, enrollment_id)
            if enroll["status"] not in _TERMINAL_ACCOUNT_ALLOWED_STATES:
                raise EnrollmentError(
                    "enrollment %s is in state %s, expected one of %s"
                    % (enrollment_id, enroll["status"], _TERMINAL_ACCOUNT_ALLOWED_STATES)
                )
            if device is None:
                raise EnrollmentError(
                    "a device connection is required for terminal account creation"
                )

            target_id = enroll["reserved_device_user_id"]
            was_reserved = enroll["status"] == "RESERVED"

            try:
                roster = device.get_users() or []
            except Exception as e:
                raise EnrollmentError(
                    "failed to read terminal roster for device %s: %s"
                    % (enroll["device_id"], e)
                )
            match = _match_roster_user(roster, target_id)

            mutated = False
            if match is None:
                mutated = True
                try:
                    ok = device.set_user(
                        user_id=target_id,
                        name=name,
                        privilege=PRIVILEGE_NORMAL_USER,
                        password="",
                    )
                    log.info(
                        "set_user(%s) returned %r for enrollment %s — not treated as "
                        "authoritative, confirming via roster read-back",
                        target_id, ok, enrollment_id,
                    )
                except Exception as e:
                    log.warning(
                        "set_user raised for terminal ID %s (enrollment %s), continuing "
                        "to bounded read-back rather than failing immediately: %s",
                        target_id, enrollment_id, e,
                    )
                match = _bounded_roster_readback(device, target_id)
                if match is None:
                    raise TerminalAccountUnconfirmed(
                        "terminal account creation for %s could not be confirmed "
                        "after bounded read-back (%d attempts) — enrollment remains "
                        "%s; safe to retry" % (target_id, READBACK_RETRIES, enroll["status"])
                    )

            if not _identity_matches(match, target_id):
                raise TerminalAccountConflict(
                    "terminal ID %s exists on the device but does not match the "
                    "expected identity (privilege=%s, expected %s) — refusing to "
                    "overwrite, inherit, or delete. Manual review required."
                    % (target_id, getattr(match, "privilege", None), PRIVILEGE_NORMAL_USER)
                )

            uid = getattr(match, "uid", None)

            # Canonical device_users row (idempotent — safe to call repeatedly).
            ensure_device_user(cur, enroll["device_id"], target_id, name)

            cur.execute(
                "UPDATE device_user_enrollments "
                "SET status = 'TERMINAL_ACCOUNT_CREATED', "
                "    terminal_created_at = COALESCE(terminal_created_at, now()), "
                "    device_uid = COALESCE(device_uid, %s), "
                "    updated_at = now() "
                "WHERE enrollment_id = %s AND status IN ('RESERVED', 'TERMINAL_ACCOUNT_CREATED');",
                (uid, enrollment_id),
            )
            if cur.rowcount != 1:
                raise EnrollmentError(
                    "enrollment state changed concurrently during terminal account "
                    "reconciliation; manual roster review required"
                )
            conn.commit()

    event_type = "TERMINAL_ACCOUNT_CREATED" if mutated else "TERMINAL_ACCOUNT_RECONCILED"
    log_sync_event(
        cfg,
        event_type,
        "enrollment_id=%s terminal_id=%s display_name=%s device_uid=%s "
        "mutated=%s was_reserved=%s"
        % (enrollment_id, target_id, name, uid, mutated, was_reserved),
    )
    return {
        "enrollment_id": enrollment_id,
        "status": "TERMINAL_ACCOUNT_CREATED",
        "terminal_id": target_id,
        "device_uid": uid,
        "reconciled": not mutated,
    }


def start_fingerprint_enrollment(
    cfg: Config,
    enrollment_id: int,
    operator: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Marks FINGERPRINT_ENROLLMENT_PENDING (physical enrollment on terminal)."""
    return _transition(
        cfg,
        enrollment_id,
        "FINGERPRINT_ENROLLMENT_PENDING",
        notes=notes or ("fingerprint enrollment window started by %s" % operator),
    )


def confirm_fingerprint_enrolled(
    cfg: Config,
    enrollment_id: int,
    operator: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Records operator confirmation that physical fingerprint enrollment occurred."""
    return _transition(
        cfg,
        enrollment_id,
        "FINGERPRINT_ENROLLED",
        extra={"fingerprint_confirmed_at": datetime.now(timezone.utc)},
        notes=notes or ("fingerprint enrollment confirmed by %s" % operator),
    )


def start_controlled_scan_window(
    cfg: Config,
    enrollment_id: int,
    operator: str,
    window_minutes: int = DEFAULT_CONTROLLED_SCAN_WINDOW_MINUTES,
) -> Dict[str, Any]:
    """
    Opens a narrow controlled-scan confirmation window. The window is
    supporting evidence only; Human identity confirmation stays explicit.
    """
    window_minutes = max(1, int(window_minutes))
    until = datetime.now(timezone.utc) + timedelta(minutes=window_minutes)
    return _transition(
        cfg,
        enrollment_id,
        "CONTROLLED_SCAN_PENDING",
        extra={"controlled_scan_window_until": until},
        notes="controlled scan window of %d minutes opened by %s" % (window_minutes, operator),
    )


def confirm_controlled_scan(
    cfg: Config,
    enrollment_id: int,
    scan_time: datetime,
    operator: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Records that a matching attendance event was observed inside the active
    controlled-scan window. Does NOT create a mapping.
    """
    scan_time = _normalize_scan_time(scan_time)
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            enroll = _fetch_enrollment(cur, enrollment_id)
            if enroll["status"] != "CONTROLLED_SCAN_PENDING":
                raise EnrollmentError(
                    "enrollment %s is in state %s, expected CONTROLLED_SCAN_PENDING"
                    % (enrollment_id, enroll["status"])
                )
            until = enroll["controlled_scan_window_until"]
            if until is None:
                raise EnrollmentError("no controlled scan window is active")
            if scan_time > until:
                raise EnrollmentError(
                    "scan_time %s is after window deadline %s — not accepted"
                    % (scan_time.isoformat(), until.isoformat())
                )
            cur.execute(
                "UPDATE device_user_enrollments "
                "SET status = 'CONTROLLED_SCAN_CONFIRMED', controlled_scan_time = %s, "
                "updated_at = now() "
                "WHERE enrollment_id = %s;",
                (scan_time, enrollment_id),
            )
            if cur.rowcount != 1:
                raise EnrollmentError("enrollment %s not updated" % enrollment_id)
            conn.commit()
    log_sync_event(
        cfg,
        "ENROLLMENT_SCAN_CONFIRMED",
        "enrollment_id=%s scan_time=%s confirmed_by=%s"
        % (enrollment_id, scan_time.isoformat(), operator),
    )
    return {
        "enrollment_id": enrollment_id,
        "status": "CONTROLLED_SCAN_CONFIRMED",
        "controlled_scan_time": scan_time,
    }


def mark_ready_for_mapping(
    cfg: Config,
    enrollment_id: int,
    operator: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Explicit operator confirmation that the controlled scan belongs to the
    reserved Human. Reaching READY_FOR_MAPPING requires a recorded
    controlled_scan_time (enforced here and by the DB). No mapping is created.
    """
    if not operator or not str(operator).strip():
        raise EnrollmentError("operator is required to confirm identity")
    return _transition(
        cfg,
        enrollment_id,
        "READY_FOR_MAPPING",
        extra={
            "confirmed_by": operator,
            "confirmed_at": datetime.now(timezone.utc),
        },
        notes=notes or ("Human identity confirmed by %s" % operator),
    )


def cancel_enrollment(
    cfg: Config,
    enrollment_id: int,
    operator: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Safely cancels an enrollment. Requires a reason (notes)."""
    if not notes or not str(notes).strip():
        raise EnrollmentError("cancellation requires a reason (notes)")
    return _transition(
        cfg,
        enrollment_id,
        "CANCELLED",
        notes="cancelled by %s: %s" % (operator, notes),
    )


def retire_enrollment(
    cfg: Config,
    enrollment_id: int,
    operator: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Retires an enrollment that already passed controlled-scan confirmation."""
    return _transition(
        cfg,
        enrollment_id,
        "RETIRED",
        notes=notes or ("retired by %s" % operator),
    )
