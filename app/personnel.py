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
from app.rtn_ranks import RTN_RANK_CATALOG

log = logging.getLogger(__name__)

# ADMS-Personnel-MasterData-024: Humans created through the web UI are
# tagged distinctly from the bulk Excel roster import — never silently
# blended into the same provenance, so a future re-import's own dedup
# logic (keyed on its own source rows) never has to guess which existing
# rows it owns versus which were entered by an ADMIN by hand.
SOURCE_ADMS_MANUAL = "ADMS_MANUAL"

_EDITABLE_HUMAN_FIELDS = (
    "display_name", "english_name", "rank", "position", "branch", "category", "personnel_id",
    "scan_exempt", "scan_exempt_reason",
)


class PersonnelError(Exception):
    """Raised when a personnel-lifecycle operation violates a safety rule."""


class PersonnelDuplicateError(PersonnelError):
    """Raised when a create/update would collide with an existing Human's
    stable business identifier (personnel_id) — never raised for a mere
    name match, since Thai names legitimately repeat."""


def _validate_rank(rank: Optional[str]) -> None:
    if rank is None or rank == "":
        return
    if rank not in RTN_RANK_CATALOG:
        raise PersonnelError(
            "rank %r is not a recognized canonical rank abbreviation" % rank
        )


def _fetch_human_columns(cur: Any) -> str:
    return (
        "employee_id, personnel_id, display_name, english_name, rank, position, branch, "
        "category, notes, active, production_scope, scan_exempt, scan_exempt_reason, source, created_at, updated_at"
    )


def create_human(
    cfg: Config,
    operator: str,
    display_name: str,
    rank: Optional[str] = None,
    english_name: Optional[str] = None,
    personnel_id: Optional[str] = None,
    position: Optional[str] = None,
    branch: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a new Human (ADMS-managed, not Excel-imported).

    Starts active=true, production_scope=true — the same defaults every
    existing Excel-imported row uses. Never creates a terminal account,
    Enrollment, or mapping; those remain the operator's separate, explicit
    next actions.

    Duplicate prevention is keyed ONLY on personnel_id (the schema's own
    UNIQUE constraint) — never on display_name, which Thai naming
    conventions make an unreliable identity signal on its own.
    """
    if not operator or not str(operator).strip():
        raise PersonnelError("operator is required to create a person")
    display_name = (display_name or "").strip()
    if not display_name:
        raise PersonnelError("display_name is required")
    _validate_rank(rank)
    personnel_id = (personnel_id or "").strip() or None
    english_name = (english_name or "").strip() or None

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            if personnel_id is not None:
                cur.execute(
                    "SELECT employee_id FROM human_employees WHERE personnel_id = %s;",
                    (personnel_id,),
                )
                if cur.fetchone() is not None:
                    raise PersonnelDuplicateError(
                        "a Human with personnel_id %s already exists" % personnel_id
                    )
            cur.execute(
                "INSERT INTO human_employees "
                "(display_name, rank, english_name, personnel_id, position, branch, category, "
                " active, production_scope, source) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, true, true, %s) "
                f"RETURNING {_fetch_human_columns(cur)};",
                (display_name, rank, english_name, personnel_id, position, branch, category, SOURCE_ADMS_MANUAL),
            )
            row = cur.fetchone()
            if row is None:
                raise PersonnelError("insert failed")
            cols = [d[0] for d in cur.description]
            result = dict(zip(cols, row))
            conn.commit()

    log_sync_event(
        cfg,
        "PERSONNEL_CREATED",
        "employee_id=%s display_name=%s personnel_id=%s rank=%s created_by=%s"
        % (result["employee_id"], display_name, personnel_id or "", rank or "", operator),
    )
    return result


def update_human(
    cfg: Config,
    employee_id: str,
    operator: str,
    **fields: Any,
) -> Optional[Dict[str, Any]]:
    """Edits an existing Human's editable master-data fields.

    Only whitelisted columns may be changed (_EDITABLE_HUMAN_FIELDS) —
    employee_id, active, production_scope, source, created_at are never
    touched here (lifecycle/system-owned). Preserves attendance/mapping/
    enrollment history unconditionally: this function never references
    any of those tables.
    """
    if not operator or not str(operator).strip():
        raise PersonnelError("operator is required to edit a person")
    unknown = set(fields) - set(_EDITABLE_HUMAN_FIELDS)
    if unknown:
        raise PersonnelError("unsafe/unknown field(s): %s" % ", ".join(sorted(unknown)))
    if "rank" in fields:
        _validate_rank(fields["rank"])
    if "display_name" in fields:
        fields["display_name"] = (fields["display_name"] or "").strip()
        if not fields["display_name"]:
            raise PersonnelError("display_name cannot be blanked out")
    if "personnel_id" in fields:
        fields["personnel_id"] = (fields["personnel_id"] or "").strip() or None
    if "english_name" in fields:
        fields["english_name"] = (fields["english_name"] or "").strip() or None
    if "scan_exempt_reason" in fields:
        fields["scan_exempt_reason"] = (fields["scan_exempt_reason"] or "").strip() or None
    if "scan_exempt" in fields:
        if fields["scan_exempt"] is None:
            raise PersonnelError("scan_exempt must be true or false")
        fields["scan_exempt"] = bool(fields["scan_exempt"])
        if fields["scan_exempt"] and not fields.get("scan_exempt_reason"):
            raise PersonnelError("a reason is required to mark a person scan-exempt")
        if not fields["scan_exempt"]:
            fields["scan_exempt_reason"] = None
    if not fields:
        raise PersonnelError("no editable fields supplied")

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_fetch_human_columns(cur)} FROM human_employees WHERE employee_id = %s;",
                (employee_id,),
            )
            before_row = cur.fetchone()
            if before_row is None:
                return None
            before_cols = [d[0] for d in cur.description]
            before = dict(zip(before_cols, before_row))

            if "personnel_id" in fields and fields["personnel_id"] is not None:
                cur.execute(
                    "SELECT employee_id FROM human_employees WHERE personnel_id = %s AND employee_id <> %s;",
                    (fields["personnel_id"], employee_id),
                )
                if cur.fetchone() is not None:
                    raise PersonnelDuplicateError(
                        "a different Human already has personnel_id %s" % fields["personnel_id"]
                    )

            set_clauses = ["%s = %%s" % col for col in fields]
            params = list(fields.values()) + [employee_id]
            cur.execute(
                "UPDATE human_employees SET %s, updated_at = now() "
                "WHERE employee_id = %%s RETURNING %s;"
                % (", ".join(set_clauses), _fetch_human_columns(cur)),
                params,
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                return None
            cols = [d[0] for d in cur.description]
            after = dict(zip(cols, row))
            conn.commit()

    changed = {
        k: {"old": before.get(k), "new": after.get(k)}
        for k in fields
        if before.get(k) != after.get(k)
    }
    if changed:
        log_sync_event(
            cfg,
            "PERSONNEL_UPDATED",
            "employee_id=%s updated_by=%s changed_fields=%s"
            % (employee_id, operator, ",".join(sorted(changed.keys()))),
        )
    return after


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


def bulk_set_scan_exempt(
    cfg: Config,
    operator: str,
    employee_ids: List[str],
    scan_exempt: bool,
    reason: Optional[str],
) -> int:
    """Marks many people scan-exempt (or scan-required) at once, e.g. a
    whole section. Same rule as the single edit: exempting needs a reason;
    clearing clears it. Returns the number of rows changed."""
    if not operator or not str(operator).strip():
        raise PersonnelError("operator is required")
    ids = sorted({str(i) for i in employee_ids if i})
    if not ids:
        raise PersonnelError("no people selected")
    reason = (reason or "").strip() or None
    if scan_exempt and not reason:
        raise PersonnelError("a reason is required to mark people scan-exempt")
    if not scan_exempt:
        reason = None
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE human_employees SET scan_exempt = %s, scan_exempt_reason = %s, updated_at = now() "
                "WHERE employee_id = ANY(%s::uuid[]) "
                "AND (scan_exempt IS DISTINCT FROM %s OR scan_exempt_reason IS DISTINCT FROM %s);",
                (scan_exempt, reason, ids, scan_exempt, reason),
            )
            changed = cur.rowcount
            conn.commit()
    log_sync_event(
        cfg,
        "PERSONNEL_SCAN_EXEMPT_BULK",
        "scan_exempt=%s reason=%s count=%s by=%s ids=%s" % (scan_exempt, reason or "", changed, operator, ",".join(ids)),
    )
    return changed
