"""
Personnel (Human) lifecycle — ACTIVE / INACTIVE.

PromptID: ADMS-Personnel-Lifecycle-019

Answers "does this person currently belong here?" — strictly separate from
Terminal Management (PromptID 020), which will answer "what
credentials/accounts belonging to this person currently exist on a
physical terminal?" This module never touches a device, never deletes a
terminal account or fingerprint, and never mutates historical data.

Deactivation:
  - Sets human_employees.active = false (column already existed — no
    migration).
  - Atomically closes (valid_to = the deactivation transaction's own
    timestamp) any currently-open VERIFIED mapping(s) for this Human, so a
    scan after departure can never attribute to them again.
  - Never deletes the mapping row, never touches attendance_logs, never
    touches device_users, never touches the terminal.
  - Idempotent: deactivating an already-inactive Human is a friendly no-op,
    not an error (distinct from enrollment cancellation's strict
    CANCELLED->CANCELLED rejection — this operation was explicitly
    specified as idempotent).

Reactivation:
  - Sets active = true only. Does NOT reopen any closed mapping and does
    NOT restore any prior terminal credential validity — a returning
    person requires a fresh Enrollment/Terminal-lifecycle pass and a new
    VERIFIED mapping at a new evidence boundary, by design (old mapping
    intervals remain historical/closed, per PromptID 019's Phase 5).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import Config
from app.db import get_db_connection, log_sync_event

log = logging.getLogger(__name__)


class PersonnelError(Exception):
    """Raised when a personnel-lifecycle operation violates a safety rule."""


def deactivate_human(
    cfg: Config,
    employee_id: str,
    operator: str,
    reason: str,
) -> Dict[str, Any]:
    if not operator or not str(operator).strip():
        raise PersonnelError("operator is required to deactivate a person")
    if not reason or not str(reason).strip():
        raise PersonnelError("a reason is required to deactivate a person")

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT active FROM human_employees WHERE employee_id = %s FOR UPDATE;",
                (employee_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise PersonnelError("human %s does not exist" % employee_id)
            already_inactive = not row[0]
            if already_inactive:
                # Idempotent/friendly, per explicit spec — not an error.
                conn.rollback()
                return {
                    "employee_id": employee_id,
                    "active": False,
                    "already_inactive": True,
                    "mappings_closed": [],
                }

            effective_time = datetime.now(timezone.utc)
            cur.execute(
                "UPDATE human_employees SET active = false, updated_at = now() "
                "WHERE employee_id = %s;",
                (employee_id,),
            )
            cur.execute(
                "SELECT mapping_id, device_user_pk FROM employee_device_mappings "
                "WHERE employee_id = %s AND mapping_status = 'VERIFIED' AND valid_to IS NULL;",
                (employee_id,),
            )
            open_mappings: List[Any] = cur.fetchall()
            for mapping_id, _device_user_pk in open_mappings:
                cur.execute(
                    "UPDATE employee_device_mappings SET valid_to = %s "
                    "WHERE mapping_id = %s;",
                    (effective_time, mapping_id),
                )
            conn.commit()

    log_sync_event(
        cfg,
        "PERSONNEL_DEACTIVATED",
        "employee_id=%s reason=%s deactivated_by=%s effective_time=%s"
        % (employee_id, reason, operator, effective_time.isoformat()),
    )
    for mapping_id, device_user_pk in open_mappings:
        log_sync_event(
            cfg,
            "MAPPING_CLOSED_DUE_TO_PERSONNEL_DEACTIVATION",
            "mapping_id=%s employee_id=%s device_user_pk=%s valid_to=%s"
            % (mapping_id, employee_id, device_user_pk, effective_time.isoformat()),
        )
    return {
        "employee_id": employee_id,
        "active": False,
        "already_inactive": False,
        "mappings_closed": [m[0] for m in open_mappings],
        "effective_time": effective_time,
    }


def reactivate_human(
    cfg: Config,
    employee_id: str,
    operator: str,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    if not operator or not str(operator).strip():
        raise PersonnelError("operator is required to reactivate a person")

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT active FROM human_employees WHERE employee_id = %s FOR UPDATE;",
                (employee_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise PersonnelError("human %s does not exist" % employee_id)
            already_active = bool(row[0])
            if already_active:
                conn.rollback()
                return {"employee_id": employee_id, "active": True, "already_active": True}

            cur.execute(
                "UPDATE human_employees SET active = true, updated_at = now() "
                "WHERE employee_id = %s;",
                (employee_id,),
            )
            conn.commit()

    log_sync_event(
        cfg,
        "PERSONNEL_REACTIVATED",
        "employee_id=%s reactivated_by=%s reason=%s" % (employee_id, operator, reason or ""),
    )
    return {"employee_id": employee_id, "active": True, "already_active": False}
