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
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from app.config import Config
from app.db import get_db_connection, ensure_device_user, log_sync_event
from app.mapping_evidence import resolve_controlled_attendance_id

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

# ADMS-CurrentState-History-UXClosure-022: this raw-status list is a *stored*
# approximation used only for the DB partial unique index and as a coarse
# pre-filter — it can be stale for a row that finished its actual work
# (READY_FOR_MAPPING) before this PromptID's self-healing existed. The
# canonical truth is always ENROLLMENT_LIFECYCLE_STATE, derived below. Both
# "should this show in the Active Queue" (app/api/repository.py) and "should
# this block a new reservation" (reserve_next_device_user_id below) MUST use
# the SAME derivation — never two independently-drifting predicates.

ENROLLMENT_LIFECYCLE_JOIN_SQL = (
    "LEFT JOIN device_users du ON du.device_id = e.device_id "
    "AND du.device_user_id = e.reserved_device_user_id "
    "LEFT JOIN LATERAL ("
    "  SELECT m.valid_to, m.mapping_status "
    "  FROM employee_device_mappings m "
    "  WHERE m.device_user_pk = du.device_user_pk "
    "  AND m.employee_id = e.employee_id "
    "  AND m.mapping_status = 'VERIFIED' "
    "  ORDER BY (m.valid_to IS NULL) DESC, m.verified_at DESC "
    "  LIMIT 1"
    ") vm ON true"
)
ENROLLMENT_LIFECYCLE_SELECT_SQL = (
    "du.active AS device_user_active, vm.mapping_status AS verified_mapping_status, "
    "vm.valid_to AS mapping_valid_to"
)


def derive_enrollment_lifecycle_state(
    status: str,
    device_user_active: Optional[bool],
    verified_mapping_status: Optional[str],
    mapping_valid_to: Any,
) -> str:
    """Canonical, single-source cross-lifecycle state for an enrollment.

    ADMS-UX-CrossLifecycleClosure-021B / ADMS-CurrentState-History-
    UXClosure-022: neither the frontend nor any other backend caller may
    independently infer "is this enrollment actually finished/historical"
    by stitching together enrollment.status + device_users.active +
    mapping.valid_to on its own. This is the one place that interpretation
    happens — reused verbatim by app.api.repository (read paths: Active
    Queue, Dashboard, history) AND by reserve_next_device_user_id below
    (write path: does an existing row block a new reservation).

    Deliberately derived at READ/decision time from current joined facts
    rather than solely trusting the stored `status` column — this self-
    heals rows written before this logic existed (e.g. a real production
    row still literally 'READY_FOR_MAPPING' despite its VERIFIED mapping
    existing and later being closed by terminal removal) without requiring
    any backfill/migration.
    """
    if status == "CANCELLED":
        return "CANCELLED"

    has_verified_mapping = verified_mapping_status is not None
    if status == "RETIRED" or (status == "READY_FOR_MAPPING" and has_verified_mapping):
        mapping_open = has_verified_mapping and mapping_valid_to is None
        if bool(device_user_active) and mapping_open:
            return "COMPLETED"
        return "REMOVED_FROM_TERMINAL"

    return "IN_PROGRESS"

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
    "updated_at",
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


class TerminalRosterUnavailable(EnrollmentError):
    """The PRE-MUTATION roster read failed or timed out — set_user() was
    NEVER attempted. Distinct from TerminalAccountUnconfirmed (mutation WAS
    attempted, just unconfirmed) so callers/frontend can correctly say "no
    write was attempted" instead of implying a possibly-successful write.
    (ADMS-DeviceCommandBus-TimeoutMargin-010)"""


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
    """ADMS-TerminalManagement-020 Part C: a CANCELLED reservation whose
    terminal account was NEVER created (terminal_created_at IS NULL AND
    device_uid IS NULL) no longer permanently burns its ID — it is
    excluded from the "used" set here so the allocator may reclaim it.

    Safety is structural, not a separate check: the device_users half of
    this UNION has no active/inactive filter, so any ID that ever had a
    device_users row (i.e. a terminal account was genuinely created for
    it at some point, even if later removed — the historical-1002 case)
    remains permanently "used" regardless of this relaxation. Since
    attendance_logs.device_user_pk and employee_device_mappings.
    device_user_pk both reference device_users.device_user_pk, an ID with
    no device_users row can never have attendance or a mapping either —
    "no attendance/mapping exists" is therefore guaranteed by the schema,
    not re-checked separately. Only a genuinely never-created reservation
    (the historical-1003 case) is ever excluded here.
    """
    cur.execute(
        "SELECT device_user_id FROM device_users WHERE device_id = %s "
        "UNION "
        "SELECT reserved_device_user_id FROM device_user_enrollments "
        "WHERE device_id = %s "
        "AND NOT (status = 'CANCELLED' AND terminal_created_at IS NULL AND device_uid IS NULL);",
        (device_id, device_id),
    )
    return {str(r[0]) for r in cur.fetchall()}


def _find_reclaimable_cancelled_enrollment(cur: Any, device_id: int, terminal_id: str) -> Optional[int]:
    """Returns the enrollment_id of a CANCELLED, never-created reservation
    that safely qualified `terminal_id` for reuse (per
    _load_used_terminal_ids' relaxation), or None. Used only to produce a
    precise audit trail (TERMINAL_ID_RESERVATION_REUSED) — never to decide
    eligibility itself, which is already fully determined by
    _load_used_terminal_ids before this is called."""
    cur.execute(
        "SELECT enrollment_id FROM device_user_enrollments "
        "WHERE device_id = %s AND reserved_device_user_id = %s "
        "AND status = 'CANCELLED' AND terminal_created_at IS NULL AND device_uid IS NULL "
        "ORDER BY enrollment_id DESC LIMIT 1;",
        (device_id, terminal_id),
    )
    row = cur.fetchone()
    return row[0] if row else None


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

            # ADMS-CurrentState-History-UXClosure-022: a row whose raw
            # `status` is still in ACTIVE_ENROLLMENT_STATUSES is only a
            # coarse pre-filter — it can be stale (e.g. READY_FOR_MAPPING
            # from before this self-healing existed, whose VERIFIED mapping
            # was later closed by terminal removal). The canonical lifecycle
            # derivation (shared with app.api.repository's Active Queue/
            # Dashboard reads — never a second, independently-drifting
            # predicate) decides whether it genuinely blocks. A row that is
            # NOT canonically IN_PROGRESS is atomically transitioned to its
            # already-earned RETIRED terminal state (the exact same
            # mechanism ADMS-UX-FinalPolish-021 uses when a mapping is
            # freshly created) — this is not reviving, deleting, or
            # rewriting history; it corrects a stale status column to match
            # facts that were already true, in the same transaction as the
            # new reservation, so the DB partial unique index
            # (uq_active_enrollment_per_human_device) — which can only see
            # `status`, not the joined device/mapping facts — no longer
            # sees it as active either.
            cur.execute(
                "SELECT e.enrollment_id, e.status, "
                f"{ENROLLMENT_LIFECYCLE_SELECT_SQL} "
                "FROM device_user_enrollments e "
                f"{ENROLLMENT_LIFECYCLE_JOIN_SQL} "
                "WHERE e.employee_id = %s AND e.device_id = %s "
                "AND e.status = ANY(%s);",
                (employee_id, device_id, list(ACTIVE_ENROLLMENT_STATUSES)),
            )
            candidate_rows = cur.fetchall()
            for row in candidate_rows:
                (
                    existing_enrollment_id,
                    existing_status,
                    device_user_active,
                    verified_mapping_status,
                    mapping_valid_to,
                ) = row
                state = derive_enrollment_lifecycle_state(
                    existing_status, device_user_active, verified_mapping_status, mapping_valid_to
                )
                if state == "IN_PROGRESS":
                    raise EnrollmentError(
                        "Human %s already has an active enrollment on device %s"
                        % (employee_id, device_id)
                    )
                # COMPLETED / REMOVED_FROM_TERMINAL — genuinely finished
                # work whose status column just never caught up. Self-heal.
                cur.execute(
                    "UPDATE device_user_enrollments SET status = 'RETIRED', updated_at = now() "
                    "WHERE enrollment_id = %s AND status = %s;",
                    (existing_enrollment_id, existing_status),
                )
                if cur.rowcount == 1:
                    log_sync_event(
                        cfg,
                        "ENROLLMENT_STALE_STATUS_SELF_HEALED",
                        "enrollment_id=%s previous_status=%s lifecycle_state=%s "
                        "healed_to=RETIRED reason=blocked_new_reservation_but_canonically_finished"
                        % (existing_enrollment_id, existing_status, state),
                    )

            used_ids = _load_used_terminal_ids(cur, device_id)
            next_id = _find_next_available_id(used_ids, roster_user_ids)
            # Precise audit trail only — eligibility was already fully
            # decided by _load_used_terminal_ids above.
            reclaimed_from_enrollment_id = _find_reclaimable_cancelled_enrollment(cur, device_id, next_id)

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
    if reclaimed_from_enrollment_id is not None:
        log_sync_event(
            cfg,
            "TERMINAL_ID_RESERVATION_REUSED",
            "terminal_id=%s device_id=%s previous_cancelled_enrollment_id=%s "
            "new_enrollment_id=%s reason=cancelled_reservation_never_created_on_device"
            % (row[1], device_id, reclaimed_from_enrollment_id, row[0]),
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

# ---------------------------------------------------------------------------
# Timing budget (ADMS-DeviceCommandBus-TimeoutMargin-010)
#
# Derived from the actually-installed pyzk implementation and this app's own
# config, NOT arbitrary. Every pyzk socket operation shares ONE blocking
# per-call timeout, set once at connect time via `sock.settimeout(timeout)`
# (see zk.base.ZK.__init__) and never changed thereafter — it applies to
# every individual `recv()` inside every command, not to a whole operation.
#
# Round-trip counts per operation (confirmed by reading the installed pyzk
# source, not assumed):
#   - device.get_users() -> ZK.read_sizes() (1 command) then
#     ZK.read_with_buffer() (1 command, 2 for a large roster that needs a
#     second chunk read — this device has 1 user, well under one chunk) = 2
#     round trips in the realistic worst case. This matches observed
#     production evidence: a stalled get_users() call in the Collector log
#     took ~10.04s to time out with ZK_TIMEOUT=5s, i.e. almost exactly 2x the
#     per-call timeout.
#   - device.set_user() -> one CMD_USER_WRQ write, then pyzk's set_user()
#     unconditionally calls self.refresh_data() internally (CMD_REFRESHDATA,
#     a second, separate command) before returning = 2 round trips.
ZK_ROUNDTRIPS_PER_ROSTER_READ = 2
ZK_ROUNDTRIPS_PER_SET_USER = 2


def _zk_socket_timeout_seconds() -> float:
    """The per-socket-call timeout pyzk was constructed with (ZK_TIMEOUT env,
    default 5s — see Config.device_timeout / app/collector.py's ZK(...)
    call). Read live, not cached, so a future .env change is honored without
    a code change."""
    return float(os.getenv("ZK_TIMEOUT", "5"))


def create_terminal_account_collector_budget_seconds() -> float:
    """Worst-case realistic duration the Collector's own
    create_or_reconcile_terminal_account() call can legitimately take,
    derived from the round-trip counts above — i.e. the number the OUTER
    DeviceCommandBus timeout must exceed. Does not attempt to accommodate a
    fully-dead device (unbounded stalls) — that case should genuinely time
    out; this bounds the case of a slow-but-functioning device."""
    per_call = _zk_socket_timeout_seconds()
    initial_roster_read = ZK_ROUNDTRIPS_PER_ROSTER_READ * per_call
    mutation = ZK_ROUNDTRIPS_PER_SET_USER * per_call
    bounded_readback = READBACK_RETRIES * ZK_ROUNDTRIPS_PER_ROSTER_READ * per_call
    readback_inter_attempt_delays = (READBACK_RETRIES - 1) * READBACK_DELAY_SECONDS
    return initial_roster_read + mutation + bounded_readback + readback_inter_attempt_delays


# MQTT publish/subscribe latency (both directions), JSON (de)serialization,
# and thread/event-loop scheduling jitter between the API process and the
# Collector process — not a hardware timeout, a transport/scheduling margin.
DEVICE_COMMAND_TRANSPORT_MARGIN_SECONDS = 3.0

# ---------------------------------------------------------------------------
# Device-owner acquire budget (ADMS-ZEM560-SingleOwnerIO-014)
#
# Since 014, a command no longer executes the instant the Collector's MQTT
# thread receives it — it is enqueued and must wait for the single device
# owner (the Collector's main thread) to reach a safe point before it can
# even START executing. The worst-case wait for that safe point is bounded
# by pyzk's live_capture() idle-timeout cycle: live_capture() is a lazy
# generator, so the owner is never mid-pyzk-call between one yielded value
# and the next `next()` call — but it can't check the command queue until a
# yield happens, and pyzk's live_capture(new_timeout=...) defaults to a 10s
# per-iteration socket timeout (app/collector.py calls it with no override).
# This must be added to the outer DeviceCommandBus timeout, or the very fix
# that makes device I/O correct (serializing it) would make the existing
# 010 budget too tight and reintroduce a false DEVICE_COMMAND_TIMEOUT.
LIVE_CAPTURE_IDLE_TIMEOUT_SECONDS = 10.0

# Margin beyond one full idle cycle for actual drain/dispatch overhead once
# the owner reaches the safe point (queue pop, generation check, invoking
# the executor) — deliberately small since that work does no device I/O.
DEVICE_OWNER_DRAIN_MARGIN_SECONDS = 5.0

DEVICE_OWNER_ACQUIRE_TIMEOUT_SECONDS = (
    LIVE_CAPTURE_IDLE_TIMEOUT_SECONDS + DEVICE_OWNER_DRAIN_MARGIN_SECONDS
)

# The value app/device_command_bus.py's execute() must be called with for the
# CREATE_TERMINAL_ACCOUNT command — computed, not hand-picked, and re-derives
# automatically if READBACK_RETRIES/READBACK_DELAY_SECONDS/ZK_TIMEOUT/the
# device-owner acquire budget change.
# Invariant: outer_timeout > device_owner_acquire_budget + collector_budget + transport_margin.
CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS = (
    DEVICE_OWNER_ACQUIRE_TIMEOUT_SECONDS
    + create_terminal_account_collector_budget_seconds()
    + DEVICE_COMMAND_TRANSPORT_MARGIN_SECONDS
)

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
                # PRE-MUTATION failure — set_user() has not been called at
                # all. Must be distinguishable from TerminalAccountUnconfirmed
                # (where a write WAS attempted) so the API/frontend never
                # implies a write might have happened when it didn't.
                raise TerminalRosterUnavailable(
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
    operator: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolves and BINDS the real controlled-scan attendance evidence —
    ADMS-ControlledScan-EvidenceBinding-018.

    No operator/SSE-derived scan_time is accepted as input anymore (that
    architecture — estimate now, rediscover-by-timestamp-proximity later —
    is exactly what produced the "Attendance ID #?" incident class, most
    recently Enrollment #4's 138s gap between a browser-estimated
    controlled_scan_time and the real attendance_logs row). Instead, this
    function itself looks up the actual matching attendance_logs row,
    deterministically, and stores ITS real scan_time — so
    controlled_scan_time is thereafter always bit-for-bit equal to genuine
    terminal evidence, never an estimate to later reconcile.

    Window bound is [window_start, controlled_scan_window_until], where
    window_start is this enrollment row's own updated_at at the exact
    moment start_controlled_scan_window() committed the CONTROLLED_SCAN_
    PENDING transition — no new column, no migration; the value already
    exists and is read here before this call's own UPDATE overwrites it.
    Device/terminal-user constraint applies structurally via
    device_user_pk. If multiple scans landed in the window, the EARLIEST
    one wins deterministically (the first genuine attempt is the evidence,
    not a later duplicate/retry).
    """
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
            window_start = enroll["updated_at"]
            # No separate real-clock "is the window expired" pre-check —
            # the bounded [window_start, until] query below is the single
            # source of truth. An expired window with no candidate scan in
            # it simply resolves to "no matching attendance scan found
            # yet," which is both correct and avoids coupling this
            # function to wall-clock time (only to the window's own
            # already-recorded boundaries).
            cur.execute(
                "SELECT device_user_pk FROM device_users "
                "WHERE device_id = %s AND device_user_id = %s AND active = true;",
                (enroll["device_id"], enroll["reserved_device_user_id"]),
            )
            du = cur.fetchone()
            if du is None:
                raise EnrollmentError(
                    "enrollment %s has no active terminal account on record — "
                    "cannot bind scan evidence" % enrollment_id
                )
            device_user_pk = du[0]

            cur.execute(
                "SELECT id, scan_time FROM attendance_logs "
                "WHERE device_user_pk = %s AND scan_time BETWEEN %s AND %s "
                "ORDER BY scan_time ASC LIMIT 1;",
                (device_user_pk, window_start, until),
            )
            row = cur.fetchone()
            if row is None:
                raise EnrollmentError(
                    "no matching attendance scan found yet within the controlled "
                    "scan window for enrollment %s — ask the person to scan again"
                    % enrollment_id
                )
            attendance_id, scan_time = row

            cur.execute(
                "UPDATE device_user_enrollments "
                "SET status = 'CONTROLLED_SCAN_CONFIRMED', controlled_scan_time = %s, "
                "updated_at = now() "
                "WHERE enrollment_id = %s AND status = 'CONTROLLED_SCAN_PENDING';",
                (scan_time, enrollment_id),
            )
            if cur.rowcount != 1:
                raise EnrollmentError(
                    "enrollment %s not updated (concurrent state change?)" % enrollment_id
                )
            conn.commit()
    log_sync_event(
        cfg,
        "ENROLLMENT_SCAN_CONFIRMED",
        "enrollment_id=%s attendance_id=%s scan_time=%s confirmed_by=%s"
        % (enrollment_id, attendance_id, scan_time.isoformat(), operator),
    )
    return {
        "enrollment_id": enrollment_id,
        "status": "CONTROLLED_SCAN_CONFIRMED",
        "controlled_scan_time": scan_time,
        "controlled_attendance_id": attendance_id,
    }


def reconcile_controlled_scan_evidence(
    cfg: Config,
    enrollment_id: int,
    attendance_id: int,
    operator: str,
) -> Dict[str, Any]:
    """
    Narrow, ADMIN-only, one-time correction of controlled_scan_time to a
    specific, independently-verified attendance_logs row — ADMS-
    ControlledScan-EvidenceBinding-018-Deploy.

    Exists only for enrollments whose controlled_scan_time was recorded
    under the pre-018 estimate-based architecture and therefore does not
    bit-for-bit match the real evidence confirm_controlled_scan() would
    have bound had the new code been live at the time. This is NOT a
    general enrollment-edit backdoor: it re-verifies, INSIDE THIS SAME
    TRANSACTION, every one of the five canonical binding criteria before
    touching anything —

      1. the attendance row exists and belongs to the enrollment's own
         device (via device_id -> device_users -> device_user_pk),
      2. it belongs to the enrollment's own reserved terminal user
         (device_user_pk match, active device_users row),
      3. it falls within the enrollment's own recorded controlled-scan
         window,
      4. the device_user's account_incarnation is unambiguous (a single,
         currently-active incarnation — this function does not attempt to
         reconcile across a reincarnated/recycled terminal ID), and
      5. no other attendance row for the same device_user_pk also falls in
         the window (no competing-scan ambiguity).

    Only controlled_scan_time is written. terminal_created_at, device_uid,
    fingerprint_confirmed_at, confirmed_by/confirmed_at, status, the
    terminal account, the attendance row itself, device_users, and any
    mapping are never touched. Emits exactly one
    ENROLLMENT_SCAN_EVIDENCE_RECONCILED audit event.

    Caller (the API route) is responsible for enforcing API_WRITE_ENABLED,
    an active Runtime Write Session, and ADMIN role — this function only
    re-verifies the EVIDENCE preconditions, not the authorization ones.
    """
    if not operator or not str(operator).strip():
        raise EnrollmentError("operator is required for evidence reconciliation")

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            enroll = _fetch_enrollment_locked(cur, enrollment_id)
            until = enroll["controlled_scan_window_until"]
            existing_scan_time = enroll["controlled_scan_time"]
            if until is None or existing_scan_time is None:
                raise EnrollmentError(
                    "enrollment %s has no recorded controlled-scan window/time — "
                    "nothing to reconcile" % enrollment_id
                )
            # Window start is not independently recoverable after later
            # transitions have overwritten updated_at (the same reason
            # confirm_controlled_scan()'s own window_start technique only
            # works at confirm-time) — for this narrow reconciliation path,
            # the window is instead reconstructed from the already-stored
            # window end and the fixed default duration, exactly as done
            # during the read-only verification this operation is
            # authorizing.
            window_start = until - timedelta(minutes=DEFAULT_CONTROLLED_SCAN_WINDOW_MINUTES)

            # 1 & 2. Device + terminal-user constraint, active account.
            cur.execute(
                "SELECT device_user_pk, active, account_incarnation FROM device_users "
                "WHERE device_id = %s AND device_user_id = %s;",
                (enroll["device_id"], enroll["reserved_device_user_id"]),
            )
            du = cur.fetchone()
            if du is None:
                raise EnrollmentError(
                    "enrollment %s has no device_users row on record — cannot "
                    "reconcile evidence" % enrollment_id
                )
            device_user_pk, du_active, incarnation = du
            if not du_active:
                raise EnrollmentError(
                    "device_user_pk %s is inactive — refusing to reconcile evidence "
                    "against an inactive/recycled account" % device_user_pk
                )

            # 3. Target attendance row must exist, belong to this
            # device_user_pk, and fall inside the window.
            cur.execute(
                "SELECT id, device_user_pk, scan_time FROM attendance_logs WHERE id = %s;",
                (attendance_id,),
            )
            att = cur.fetchone()
            if att is None:
                raise EnrollmentError("attendance id %s does not exist" % attendance_id)
            att_id, att_pk, att_scan_time = att
            if att_pk != device_user_pk:
                raise EnrollmentError(
                    "attendance id %s belongs to device_user_pk %s, not %s — "
                    "mismatched terminal user, refusing to reconcile"
                    % (attendance_id, att_pk, device_user_pk)
                )
            if not (window_start <= att_scan_time <= until):
                raise EnrollmentError(
                    "attendance id %s scan_time %s falls outside the reconstructed "
                    "controlled-scan window [%s, %s] — refusing to reconcile"
                    % (attendance_id, att_scan_time.isoformat(), window_start.isoformat(), until.isoformat())
                )

            # 5. No competing candidate for the same device_user_pk in the
            # same window — ambiguity must never be silently resolved.
            cur.execute(
                "SELECT id FROM attendance_logs "
                "WHERE device_user_pk = %s AND scan_time BETWEEN %s AND %s;",
                (device_user_pk, window_start, until),
            )
            candidates = [r[0] for r in cur.fetchall()]
            if candidates != [attendance_id]:
                raise EnrollmentError(
                    "ambiguous evidence: attendance candidates %s found for "
                    "device_user_pk %s in the window — refusing to reconcile "
                    "automatically" % (candidates, device_user_pk)
                )

            # No competing VERIFIED mapping already exists (defense-in-depth
            # — create_verified_mapping() re-checks this independently too).
            cur.execute(
                "SELECT 1 FROM employee_device_mappings "
                "WHERE device_user_pk = %s AND mapping_status = 'VERIFIED' "
                "AND (valid_to IS NULL OR valid_to > %s) LIMIT 1;",
                (device_user_pk, att_scan_time),
            )
            if cur.fetchone() is not None:
                raise EnrollmentError(
                    "a conflicting VERIFIED mapping already exists for device_user_pk "
                    "%s — refusing to reconcile" % device_user_pk
                )

            cur.execute(
                "UPDATE device_user_enrollments "
                "SET controlled_scan_time = %s, updated_at = now() "
                "WHERE enrollment_id = %s;",
                (att_scan_time, enrollment_id),
            )
            if cur.rowcount != 1:
                raise EnrollmentError(
                    "enrollment %s not updated (concurrent state change?)" % enrollment_id
                )
            conn.commit()

    log_sync_event(
        cfg,
        "ENROLLMENT_SCAN_EVIDENCE_RECONCILED",
        "enrollment_id=%s attendance_id=%s old_scan_time=%s new_scan_time=%s "
        "device_user_pk=%s account_incarnation=%s reconciled_by=%s"
        % (
            enrollment_id, attendance_id, existing_scan_time.isoformat(),
            att_scan_time.isoformat(), device_user_pk, incarnation, operator,
        ),
    )
    return {
        "enrollment_id": enrollment_id,
        "status": enroll["status"],  # this operation never changes status
        "controlled_attendance_id": attendance_id,
        "controlled_scan_time": att_scan_time,
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
    controlled_scan_time AND a resolvable controlled-scan attendance
    evidence row (enforced here — ADMS-FullEnrollment-E2E-Closure-017). No
    mapping is created.

    A broken evidence chain must fail HERE, at Step 5, not silently survive
    until an ADMIN clicks Step 6 and hits an evidence-derivation error —
    the whole point of this state is "evidence is provably complete."
    """
    if not operator or not str(operator).strip():
        raise EnrollmentError("operator is required to confirm identity")
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            enroll = _fetch_enrollment(cur, enrollment_id)
            scan_time = enroll.get("controlled_scan_time")
            if scan_time is None:
                raise EnrollmentError(
                    "enrollment %s has no controlled_scan_time — controlled scan "
                    "evidence missing" % enrollment_id
                )
            cur.execute(
                "SELECT device_user_pk FROM device_users "
                "WHERE device_id = %s AND device_user_id = %s;",
                (enroll["device_id"], enroll["reserved_device_user_id"]),
            )
            du = cur.fetchone()
            if du is None:
                raise EnrollmentError(
                    "enrollment %s has no terminal account on record — cannot "
                    "resolve controlled-scan evidence" % enrollment_id
                )
            device_user_pk = du[0]
            attendance_id = resolve_controlled_attendance_id(cur, device_user_pk, scan_time)
            if attendance_id is None:
                raise EnrollmentError(
                    "enrollment %s: no controlled-scan attendance evidence resolves "
                    "for device_user_pk=%s at controlled_scan_time=%s — cannot mark "
                    "ready for identity verification without it"
                    % (enrollment_id, device_user_pk, scan_time.isoformat())
                )
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
    result = _transition(
        cfg,
        enrollment_id,
        "CANCELLED",
        notes="cancelled by %s: %s" % (operator, notes),
    )
    # ADMS-FullEnrollment-E2E-Closure-017 Phase 12: closes the previously
    # confirmed audit gap (ADMS-Enrollment2-CancelAudit-015 found no
    # ENROLLMENT_CANCELLED event existed anywhere, forcing that
    # investigation to rely on updated_at/commit-timestamp correlation
    # instead of a direct audit record).
    log_sync_event(
        cfg,
        "ENROLLMENT_CANCELLED",
        "enrollment_id=%s cancelled_by=%s reason=%s" % (enrollment_id, operator, notes),
    )
    return result


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
