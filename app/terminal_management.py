"""
Terminal Management — physical ZEM560 account/fingerprint lifecycle.

PromptID: ADMS-TerminalManagement-020

Strictly separate from Personnel Lifecycle (app/personnel.py, "does this
person currently belong here?") and from Enrollment (app/enrollment.py,
"onboard a new terminal account"). This module answers "what
credentials/accounts belonging to a person currently exist on a physical
terminal, and how do we safely remove them?"

Four distinct concepts, never conflated:
  A. Human            — the real person (human_employees).
  B. Terminal Account  — the account/user ID physically on the ZEM560
                         (device_users + the device's own roster).
  C. Fingerprint Template — biometric data physically tied to (B).
  D. Historical Identity Evidence — enrollment/mapping/attendance/audit
                         rows. NEVER deleted or rewritten by this module.

Deleting C does not delete B. Deleting B does not delete A. Deactivating A
(Personnel Lifecycle) does not delete B or C — it only stops future scans
from attributing to A; physical cleanup of B/C remains a separate,
explicit, destructive hardware operation performed here.

All functions in this module that touch the physical device accept a
`device` parameter and are designed to be called ONLY from
CollectorStateEngine._execute_owned_command() on the Collector's main
(owner) thread — see app/device_owner.py. Nothing here opens a second ZK
connection or calls pyzk from any other thread. Callers reach this module
exclusively through the DeviceCommandBus/MQTT command-request path, the
same architecture used for CREATE_TERMINAL_ACCOUNT since PromptID 014.

Never logs/stores raw fingerprint template bytes — pyzk's own `Finger`
object embeds partial template bytes even in its `.mark` attribute
(verified by reading zk/finger.py directly); only `.uid`, `.fid`, `.valid`,
and `.size` (byte length, not content) are ever used here.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import Config
from app.db import get_db_connection, log_sync_event

log = logging.getLogger(__name__)


class TerminalManagementError(Exception):
    """Base class for Terminal Management failures."""

    def __init__(self, message: str, error_code: str = "TERMINAL_MANAGEMENT_ERROR"):
        super().__init__(message)
        self.error_code = error_code


class TerminalAccountNotFound(TerminalManagementError):
    def __init__(self, message: str):
        super().__init__(message, "TERMINAL_ACCOUNT_NOT_FOUND")


class TerminalIdentityConflict(TerminalManagementError):
    """The DB's expected identity (device_user_pk/incarnation) does not
    match what the physical roster currently shows — refuse to mutate
    rather than guess."""

    def __init__(self, message: str):
        super().__init__(message, "TERMINAL_IDENTITY_CONFLICT")


class ActiveHumanProtection(TerminalManagementError):
    """The Human is still ACTIVE with an open VERIFIED mapping to this
    account — the caller must acknowledge this explicitly (a distinct
    request flag) before the account can be removed."""

    def __init__(self, message: str):
        super().__init__(message, "ACTIVE_HUMAN_PROTECTION")


# ---------------------------------------------------------------------------
# Read-only inventory (Phase 3)
# ---------------------------------------------------------------------------


def read_terminal_inventory(device: Any) -> List[Dict[str, Any]]:
    """Owner-thread-only. Reads the physical roster and fingerprint
    template index in one pass. Returns a list of
    {device_user_id, uid, name, privilege, fingerprint_count} — never
    template bytes, never the Finger.mark hex preview.

    Raises whatever the underlying pyzk call raises on transport failure —
    callers must treat that as "device unreachable," never as "no
    fingerprints" (a device that cannot be read is UNKNOWN state, not
    empty state).
    """
    users = device.get_users() or []
    try:
        templates = device.get_templates() or []
    except Exception as e:
        log.warning("get_templates() failed (%s) — reporting fingerprint_count as None (unknown), not zero", e)
        templates = None

    fingerprint_counts: Optional[Dict[int, int]] = None
    if templates is not None:
        fingerprint_counts = {}
        for finger in templates:
            fingerprint_counts[finger.uid] = fingerprint_counts.get(finger.uid, 0) + 1

    inventory = []
    for u in users:
        uid = getattr(u, "uid", None)
        inventory.append({
            "device_user_id": str(u.user_id),
            "uid": uid,
            "name": getattr(u, "name", None),
            "privilege": getattr(u, "privilege", None),
            "fingerprint_count": (fingerprint_counts.get(uid, 0) if fingerprint_counts is not None else None),
        })
    return inventory


# ---------------------------------------------------------------------------
# Fingerprint removal (Phase 4)
# ---------------------------------------------------------------------------


def remove_terminal_fingerprint(
    cfg: Config,
    device: Any,
    device_id: int,
    device_user_id: str,
    operator: str,
    finger_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Owner-thread-only. Removes fingerprint template(s) for a terminal
    account, leaving the account itself present.

    finger_id=None removes ALL templates currently present for this
    account (deterministic: reads the actual set first, deletes exactly
    those). finger_id=<int> removes only that specific finger slot.

    Read-before-write, read-after-write: the target account and its
    current templates are read fresh immediately before any delete call;
    remaining templates are read again after, to positively confirm
    removal rather than assuming success from delete_user_template()'s
    return value alone (the same "never trust the mutation call's own
    return value" principle as set_user() — PromptID 010).
    """
    users = device.get_users() or []
    matches = [u for u in users if str(u.user_id) == str(device_user_id)]
    if not matches:
        raise TerminalAccountNotFound(
            "terminal account %s not found on device %s" % (device_user_id, device_id)
        )
    uid = matches[0].uid

    try:
        templates_before = device.get_templates() or []
    except Exception as e:
        raise TerminalManagementError(
            "failed to read fingerprint templates before mutation: %s" % e,
            "DEVICE_UNAVAILABLE",
        )
    target_fids = [f.fid for f in templates_before if f.uid == uid]
    if finger_id is not None:
        target_fids = [fid for fid in target_fids if fid == finger_id]
    if not target_fids:
        # Idempotent — already absent (PromptID-020 Phase 13).
        return {
            "device_user_id": device_user_id,
            "already_absent": True,
            "removed_fids": [],
            "remaining_count": 0,
        }

    for fid in target_fids:
        device.delete_user_template(uid=uid, temp_id=fid, user_id=str(device_user_id))

    try:
        templates_after = device.get_templates() or []
    except Exception as e:
        raise TerminalManagementError(
            "fingerprint delete attempted but read-back failed: %s — outcome unconfirmed" % e,
            "TERMINAL_FINGERPRINT_UNCONFIRMED",
        )
    # Only the TARGETED fids must be confirmed gone — other fingers for the
    # same uid legitimately remain when finger_id scoped this call to one
    # slot (a real bug caught by tests/test_terminal_management.py's
    # test_specific_finger_id_removes_only_that_one: checking "any
    # remaining template for this uid" would falsely flag a successful
    # single-finger removal as unconfirmed).
    still_present = [f.fid for f in templates_after if f.uid == uid and f.fid in target_fids]
    if still_present:
        raise TerminalManagementError(
            "fingerprint delete attempted but fid(s) %s still present for uid %s"
            % (still_present, uid),
            "TERMINAL_FINGERPRINT_UNCONFIRMED",
        )
    remaining_count = len([f for f in templates_after if f.uid == uid])

    _log_terminal_event(
        cfg,
        "TERMINAL_FINGERPRINT_REMOVED",
        device_id=device_id,
        device_user_id=device_user_id,
        operator=operator,
        extra="removed_fids=%s" % target_fids,
    )
    return {
        "device_user_id": device_user_id,
        "already_absent": False,
        "removed_fids": target_fids,
        "remaining_count": remaining_count,
    }


# ---------------------------------------------------------------------------
# Terminal account removal (Phase 6)
# ---------------------------------------------------------------------------


def remove_terminal_account(
    cfg: Config,
    device: Any,
    device_id: int,
    device_user_id: str,
    operator: str,
    acknowledge_active_human: bool = False,
) -> Dict[str, Any]:
    """Owner-thread-only. Removes a terminal account from the physical
    device. Never touches Human, attendance, enrollment history, or
    mapping history — only device_users.active is reconciled to reflect
    physical reality, exactly as the existing roster-reconciliation
    pipeline already does for a naturally-disappeared account (see
    app.db.reconcile_roster_lifecycle).

    Active-Human safety rule: if the resolved Human is currently ACTIVE
    and holds an open VERIFIED mapping to this device_user_pk, the caller
    must pass acknowledge_active_human=True (a distinct, explicit request
    flag — never inferred) or this raises ActiveHumanProtection without
    touching the device at all.
    """
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT device_user_pk FROM device_users WHERE device_id = %s AND device_user_id = %s;",
                (device_id, device_user_id),
            )
            du = cur.fetchone()
            device_user_pk = du[0] if du else None
            if device_user_pk is not None:
                cur.execute(
                    "SELECT h.active FROM employee_device_mappings m "
                    "JOIN human_employees h ON h.employee_id = m.employee_id "
                    "WHERE m.device_user_pk = %s AND m.mapping_status = 'VERIFIED' "
                    "AND m.valid_to IS NULL LIMIT 1;",
                    (device_user_pk,),
                )
                open_mapping = cur.fetchone()
                if open_mapping is not None and open_mapping[0] and not acknowledge_active_human:
                    raise ActiveHumanProtection(
                        "device_user_id %s belongs to a currently ACTIVE Human with an open "
                        "VERIFIED mapping — explicit acknowledgement required before removal"
                        % device_user_id
                    )

    users = device.get_users() or []
    matches = [u for u in users if str(u.user_id) == str(device_user_id)]
    if not matches:
        # Idempotent — already absent physically; still reconcile DB.
        _reconcile_device_user_inactive(cfg, device_id, device_user_id)
        return {"device_user_id": device_user_id, "already_absent": True}

    uid = matches[0].uid
    device.delete_user(uid=uid, user_id=str(device_user_id))

    try:
        users_after = device.get_users() or []
    except Exception as e:
        raise TerminalManagementError(
            "account delete attempted but read-back failed: %s — outcome unconfirmed" % e,
            "TERMINAL_ACCOUNT_UNCONFIRMED",
        )
    if any(str(u.user_id) == str(device_user_id) for u in users_after):
        raise TerminalManagementError(
            "account delete attempted but %s is still present on the device" % device_user_id,
            "TERMINAL_ACCOUNT_UNCONFIRMED",
        )

    _reconcile_device_user_inactive(cfg, device_id, device_user_id)
    _log_terminal_event(
        cfg,
        "TERMINAL_ACCOUNT_REMOVED",
        device_id=device_id,
        device_user_id=device_user_id,
        operator=operator,
        extra="",
    )
    return {"device_user_id": device_user_id, "already_absent": False}


def _reconcile_device_user_inactive(cfg: Config, device_id: int, device_user_id: str) -> None:
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE device_users SET active = false, updated_at = now() "
                "WHERE device_id = %s AND device_user_id = %s AND active = true;",
                (device_id, device_user_id),
            )
            conn.commit()


def _log_terminal_event(
    cfg: Config, event_type: str, device_id: int, device_user_id: str, operator: str, extra: str
) -> None:
    log_sync_event(
        cfg,
        event_type,
        "device_id=%s device_user_id=%s operator=%s %s"
        % (device_id, device_user_id, operator, extra),
    )
