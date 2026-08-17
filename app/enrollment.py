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


def create_reserved_terminal_account(
    cfg: Config,
    enrollment_id: int,
    display_name: str,
    device: Any,
) -> Dict[str, Any]:
    """
    Creates the terminal account for a RESERVED enrollment using set_user().

    Requires an injected device connection (never auto-connects: the LIVE
    collector holds the terminal's single connection). Verifies the reservation
    state, refuses to overwrite an existing terminal account, and creates the
    account with NORMAL user privilege only. No Human mapping is created.
    """
    name = validate_terminal_display_name(display_name)
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            enroll = _fetch_enrollment(cur, enrollment_id)
            if enroll["status"] != "RESERVED":
                raise EnrollmentError(
                    "enrollment %s is in state %s, expected RESERVED"
                    % (enrollment_id, enroll["status"])
                )
            if device is None:
                raise EnrollmentError(
                    "a device connection is required for terminal account creation"
                )

            target_id = enroll["reserved_device_user_id"]
            try:
                roster = device.get_users() or []
            except Exception as e:
                raise EnrollmentError(
                    "failed to read terminal roster for device %s: %s"
                    % (enroll["device_id"], e)
                )
            roster_ids = {str(getattr(u, "user_id", "")) for u in roster}
            if target_id in roster_ids:
                raise EnrollmentError(
                    "terminal account %s already exists — FAIL SAFE, refusing to "
                    "overwrite" % target_id
                )

            try:
                ok = device.set_user(
                    user_id=target_id,
                    name=name,
                    privilege=PRIVILEGE_NORMAL_USER,
                    password="",
                )
            except Exception as e:
                raise EnrollmentError(
                    "set_user failed for terminal ID %s: %s" % (target_id, e)
                )
            if not ok:
                raise EnrollmentError(
                    "set_user returned False for terminal ID %s" % target_id
                )

            # Record the device_users row (audit only; no Human mapping)
            ensure_device_user(cur, enroll["device_id"], target_id, name)

            cur.execute(
                "UPDATE device_user_enrollments "
                "SET status = 'TERMINAL_ACCOUNT_CREATED', terminal_created_at = now(), "
                "updated_at = now() "
                "WHERE enrollment_id = %s AND status = 'RESERVED';",
                (enrollment_id,),
            )
            if cur.rowcount != 1:
                raise EnrollmentError(
                    "enrollment state changed concurrently; terminal account may "
                    "exist — manual roster review required"
                )
            conn.commit()

    log_sync_event(
        cfg,
        "ENROLLMENT_ACCOUNT_CREATED",
        "enrollment_id=%s terminal_id=%s display_name=%s"
        % (enrollment_id, target_id, name),
    )
    return {
        "enrollment_id": enrollment_id,
        "status": "TERMINAL_ACCOUNT_CREATED",
        "terminal_id": target_id,
    }


def verify_terminal_account_created(
    cfg: Config,
    enrollment_id: int,
    roster_users: List[Any],
) -> Dict[str, Any]:
    """
    Verifies a successful roster snapshot contains the reserved terminal ID,
    captures the terminal device_uid, and confirms NORMAL user privilege.
    Does NOT create any Human mapping.
    """
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            enroll = _fetch_enrollment(cur, enrollment_id)
            if enroll["status"] != "TERMINAL_ACCOUNT_CREATED":
                raise EnrollmentError(
                    "enrollment %s is in state %s, expected TERMINAL_ACCOUNT_CREATED"
                    % (enrollment_id, enroll["status"])
                )
            target_id = enroll["reserved_device_user_id"]
            match = None
            for u in roster_users or []:
                if str(getattr(u, "user_id", "")) == target_id:
                    match = u
                    break
            if match is None:
                raise EnrollmentError(
                    "terminal ID %s not found in roster — account not verified"
                    % target_id
                )
            privilege = getattr(match, "privilege", None)
            # 0 is the NORMAL user privilege — must not be treated as missing.
            if privilege is None or int(privilege) != PRIVILEGE_NORMAL_USER:
                raise EnrollmentError(
                    "terminal ID %s has privilege %s, expected %s (normal user)"
                    % (target_id, privilege, PRIVILEGE_NORMAL_USER)
                )
            uid = getattr(match, "uid", None)
            cur.execute(
                "UPDATE device_user_enrollments SET device_uid = %s, updated_at = now() "
                "WHERE enrollment_id = %s;",
                (uid, enrollment_id),
            )
            cur.execute(
                "UPDATE device_users "
                "SET device_uid = COALESCE(%s, device_uid), privilege = %s, "
                "device_display_name = COALESCE(device_display_name, %s), "
                "updated_at = now() "
                "WHERE device_id = %s AND device_user_id = %s;",
                (
                    uid,
                    PRIVILEGE_NORMAL_USER,
                    getattr(match, "name", None),
                    enroll["device_id"],
                    target_id,
                ),
            )
            conn.commit()
    return {
        "enrollment_id": enrollment_id,
        "status": "TERMINAL_ACCOUNT_CREATED",
        "device_uid": uid,
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
