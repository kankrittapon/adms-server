"""Human Master endpoints.

PromptID: ADMS-Frontend-F1-API-001 / ADMS-Frontend-I18n-RBAC-Personnel-004 /
ADMS-Personnel-MasterData-024

Frontend-safe Human fields only. Rank is metadata — never identity.
All Personnel master-data writes (create, edit, CSV import commit,
scan-exempt, deactivate / reactivate, leave-unit scanner removal) belong to
the personnel section: OPERATOR or ADMIN (owner decision 2026-10-28), gated by
API_WRITE_ENABLED, but NOT by the Work Session: they are database-only and
audited, and the Work Session exists to guard scanner-touching fingerprint
work (enrollment, terminal management). CSV preview and export are
read-only.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.api import repository
from app.api.auth import ROLES_ENROLLMENT_READ, ROLES_OPERATOR_PLUS
from app.api.dependencies import (
    OperatorContext,
    get_cfg,
    pagination,
    require_roles,
    require_write_session,
    require_writes,
)
from app.api.errors import ApiError, not_found
from app.api.schemas import (
    BulkScanExemptRequest,
    BulkScanExemptResponse,
    CreateHumanRequest,
    CsvImportCommitResponse,
    CsvImportPreviewResponse,
    DeactivateHumanRequest,
    Human,
    HumanTerminalAccount,
    SyncTerminalNameResponse,
    TerminalNameMismatch,
    TerminalNameSyncSummary,
    Page,
    PersonnelSummary,
    ReactivateHumanRequest,
    UpdateHumanRequest,
)
from app.config import Config
from app.personnel import (
    PersonnelDuplicateError,
    PersonnelError,
    bulk_set_scan_exempt,
    create_human,
    deactivate_human,
    reactivate_human,
    update_human,
)
from app.personnel_csv import (
    PersonnelCsvError,
    build_csv_template,
    classify_csv_rows,
    commit_csv_rows,
    export_humans_csv,
)

router = APIRouter(tags=["humans"])


def _require_uuid(value: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", f"invalid UUID: {value!r}")
    return value


@router.get(
    "/api/v1/humans",
    response_model=Page[Human],
    dependencies=[Depends(require_roles(ROLES_ENROLLMENT_READ))],
)
def list_humans(
    production_scope: Optional[bool] = Query(None),
    active: Optional[bool] = Query(None, description="filter to active-only (true) or inactive-only (false); omit for all"),
    search: Optional[str] = Query(None, max_length=100),
    category: Optional[str] = Query(None),
    scan_status: Optional[str] = Query(
        None,
        description="workflow filter: needs_enrollment | enrolled | exempt | left_with_account",
    ),
    branch: Optional[str] = Query(None, max_length=100),
    page: tuple = Depends(pagination),
    cfg: Config = Depends(get_cfg),
):
    limit, offset = page
    if scan_status is not None and scan_status not in repository.SCAN_STATUS_VALUES:
        raise ApiError(422, "VALIDATION_ERROR", f"invalid scan_status: {scan_status!r}")
    return repository.list_humans(
        cfg,
        limit=limit,
        offset=offset,
        production_scope=production_scope,
        active=active,
        search=search,
        category=category,
        scan_status=scan_status,
        branch=branch,
    )


@router.get(
    "/api/v1/humans/branches",
    response_model=list[str],
    dependencies=[Depends(require_roles(ROLES_ENROLLMENT_READ))],
)
def humans_branches(cfg: Config = Depends(get_cfg)):
    return repository.list_branches(cfg)


class DepartmentsRequest(BaseModel):
    names: list[str] = Field(default_factory=list, max_length=100)


@router.put(
    "/api/v1/humans/branches",
    response_model=list[str],
    dependencies=[Depends(require_roles(ROLES_OPERATOR_PLUS)), Depends(require_writes)],
)
def put_humans_branches(
    payload: DepartmentsRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_OPERATOR_PLUS)),
    cfg: Config = Depends(get_cfg),
):
    """Replace the managed department list (the order is the dropdown order)."""
    if any(len(n.strip()) > 100 for n in payload.names):
        raise ApiError(400, "DEPARTMENT_NAME_TOO_LONG", "Department name exceeds 100 characters")
    return repository.set_departments(cfg, ctx.username, payload.names)


@router.post(
    "/api/v1/humans/scan-exempt",
    response_model=BulkScanExemptResponse,
    dependencies=[
        Depends(require_roles(ROLES_OPERATOR_PLUS)),
        Depends(require_writes),
    ],
)
def bulk_scan_exempt(
    payload: BulkScanExemptRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_OPERATOR_PLUS)),
    cfg: Config = Depends(get_cfg),
):
    """Set or clear scan-exempt for many people at once (e.g. finance staff,
    commander's office). Registered before /humans/{employee_id}."""
    for i in payload.employee_ids:
        _require_uuid(i)
    try:
        changed = bulk_set_scan_exempt(
            cfg, ctx.username, payload.employee_ids, payload.scan_exempt, payload.scan_exempt_reason
        )
    except PersonnelError as e:
        raise ApiError(422, "VALIDATION_ERROR", str(e))
    return {"changed": changed}


@router.get(
    "/api/v1/humans/summary",
    response_model=PersonnelSummary,
    dependencies=[Depends(require_roles(ROLES_ENROLLMENT_READ))],
)
def humans_summary(cfg: Config = Depends(get_cfg)):
    """Counts for the Personnel workflow hub. Registered before
    /humans/{employee_id} for the same route-ordering reason as export.csv."""
    return repository.personnel_summary(cfg)


@router.get(
    "/api/v1/humans/export.csv",
    dependencies=[Depends(require_roles(ROLES_ENROLLMENT_READ))],
)
def export_humans(
    active: Optional[bool] = Query(None),
    cfg: Config = Depends(get_cfg),
):
    """Read-only — never gated by Write Session. Registered BEFORE
    /humans/{employee_id} — both are 2-segment GET routes, and FastAPI/
    Starlette matches route patterns in registration order, so this must
    come first or "/export.csv" would be swallowed as an employee_id path
    parameter (and rejected as an invalid UUID)."""
    csv_text = export_humans_csv(cfg, active=active)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="personnel_export.csv"'},
    )


@router.get(
    "/api/v1/humans/terminal-name-mismatches",
    response_model=list[TerminalNameMismatch],
    dependencies=[Depends(require_roles(ROLES_ENROLLMENT_READ))],
)
def get_terminal_name_mismatches(cfg: Config = Depends(get_cfg)):
    """Accounts whose scanner name differs from rank + English name."""
    return terminal_name_mismatches(cfg)


@router.get(
    "/api/v1/humans/{employee_id}",
    response_model=Human,
    dependencies=[Depends(require_roles(ROLES_ENROLLMENT_READ))],
)
def get_human(employee_id: str, cfg: Config = Depends(get_cfg)):
    _require_uuid(employee_id)
    row = repository.get_human(cfg, employee_id)
    if row is None:
        raise not_found("human", employee_id)
    return row


@router.get(
    "/api/v1/humans/{employee_id}/terminal-accounts",
    response_model=list[HumanTerminalAccount],
    dependencies=[Depends(require_roles(ROLES_ENROLLMENT_READ))],
)
def get_human_terminal_accounts(employee_id: str, cfg: Config = Depends(get_cfg)):
    """Read-only: active terminal accounts linked to this person, used by
    the offboarding flow to remove them from the device."""
    _require_uuid(employee_id)
    expected = _expected_name(cfg, employee_id)
    rows = repository.human_terminal_accounts(cfg, employee_id)
    for r in rows:
        r["expected_name"] = expected
    return rows


def _expected_name(cfg: Config, employee_id: str) -> str:
    from app.terminal_management import expected_terminal_name

    human = repository.get_human(cfg, employee_id)
    if human is None:
        raise not_found("human", employee_id)
    meta = human.get("rank_metadata") or {}
    return expected_terminal_name(human.get("english_name"), meta.get("rank_en_abbreviation"))


def terminal_name_mismatches(cfg: Config, employee_id: Optional[str] = None) -> list:
    from app.terminal_management import expected_terminal_name
    from app.rtn_ranks import normalize_rtn_rank

    out = []
    for r in repository.terminal_name_rows(cfg, employee_id):
        meta = normalize_rtn_rank(r.get("rank") or "") or {}
        expected = expected_terminal_name(r.get("english_name"), meta.get("rank_en_abbreviation"))
        if (r.get("device_display_name") or "") != expected:
            r["expected_name"] = expected
            out.append(r)
    return out


def sync_terminal_names(cfg: Config, operator: str, employee_id: Optional[str] = None) -> dict:
    """Best-effort push of roster-derived names to the scanner for accounts
    whose name differs (one person, or everyone). Never raises: a device
    that is offline leaves the mismatch visible for a manual retry."""
    from app.api.routers.terminal_management import _dispatch

    summary = {"attempted": 0, "renamed": 0, "failed": 0, "skipped_no_english_name": 0, "errors": []}
    try:
        mismatches = terminal_name_mismatches(cfg, employee_id)
    except Exception as e:
        summary["errors"].append("lookup: %s" % type(e).__name__)
        return summary
    for m in mismatches:
        if not m["expected_name"]:
            summary["skipped_no_english_name"] += 1
            continue
        summary["attempted"] += 1
        try:
            _dispatch(
                "RENAME_TERMINAL_ACCOUNT",
                {
                    "device_id": m["device_id"],
                    "device_user_id": m["device_user_id"],
                    "name": m["expected_name"],
                    "operator": operator,
                },
                cfg,
            )
            summary["renamed"] += 1
        except ApiError as e:
            summary["failed"] += 1
            summary["errors"].append("%s: %s" % (m["device_user_id"], e.code))
        except Exception as e:  # never fail the roster write because of the device
            summary["failed"] += 1
            summary["errors"].append("%s: %s" % (m["device_user_id"], type(e).__name__))
    return summary


@router.post(
    "/api/v1/humans/sync-terminal-names",
    response_model=TerminalNameSyncSummary,
    dependencies=[
        Depends(require_roles(ROLES_OPERATOR_PLUS)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def post_sync_all_terminal_names(
    ctx: OperatorContext = Depends(require_roles(ROLES_OPERATOR_PLUS)),
    cfg: Config = Depends(get_cfg),
):
    """Manual 'update all mismatched names on the scanner'."""
    return sync_terminal_names(cfg, ctx.username)


@router.post(
    "/api/v1/humans/{employee_id}/sync-terminal-name",
    response_model=SyncTerminalNameResponse,
    dependencies=[
        Depends(require_roles(ROLES_OPERATOR_PLUS)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def sync_terminal_name(
    employee_id: str,
    ctx: OperatorContext = Depends(require_roles(ROLES_OPERATOR_PLUS)),
    cfg: Config = Depends(get_cfg),
):
    """Push the roster-derived name (rank + English name) to every active
    scanner account of this person. Touches the device, so it keeps the
    Work Session gate (a no-op when the Work Session is disabled)."""
    from app.api.routers.terminal_management import _dispatch

    _require_uuid(employee_id)
    expected = _expected_name(cfg, employee_id)
    if not expected:
        raise ApiError(422, "ENGLISH_NAME_REQUIRED", "set the English name first")
    results = []
    for acc in repository.human_terminal_accounts(cfg, employee_id):
        results.append(
            _dispatch(
                "RENAME_TERMINAL_ACCOUNT",
                {
                    "device_id": acc["device_id"],
                    "device_user_id": acc["device_user_id"],
                    "name": expected,
                    "operator": ctx.username,
                },
                cfg,
            )
        )
    return {"expected_name": expected, "accounts": results}


@router.post(
    "/api/v1/humans",
    response_model=Human,
    status_code=201,
    dependencies=[
        Depends(require_roles(ROLES_OPERATOR_PLUS)),
        Depends(require_writes),
    ],
)
def create_human_endpoint(
    payload: CreateHumanRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_OPERATOR_PLUS)),
    cfg: Config = Depends(get_cfg),
):
    try:
        result = create_human(
            cfg,
            operator=ctx.username,
            display_name=payload.display_name,
            rank=payload.rank,
            english_name=payload.english_name,
            personnel_id=payload.personnel_id,
            position=payload.position,
            branch=payload.branch,
            category=payload.category,
        )
    except PersonnelDuplicateError as e:
        raise ApiError(409, "PERSONNEL_DUPLICATE", str(e))
    except PersonnelError as e:
        raise ApiError(422, "VALIDATION_ERROR", str(e))
    row = repository.get_human(cfg, str(result["employee_id"]))
    return row


@router.patch(
    "/api/v1/humans/{employee_id}",
    response_model=Human,
    dependencies=[
        Depends(require_roles(ROLES_OPERATOR_PLUS)),
        Depends(require_writes),
    ],
)
def update_human_endpoint(
    employee_id: str,
    payload: UpdateHumanRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_OPERATOR_PLUS)),
    cfg: Config = Depends(get_cfg),
):
    _require_uuid(employee_id)
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise ApiError(422, "VALIDATION_ERROR", "no fields supplied to update")
    try:
        updated = update_human(cfg, employee_id, ctx.username, **fields)
    except PersonnelDuplicateError as e:
        raise ApiError(409, "PERSONNEL_DUPLICATE", str(e))
    except PersonnelError as e:
        raise ApiError(422, "VALIDATION_ERROR", str(e))
    if updated is None:
        raise not_found("human", employee_id)
    row = repository.get_human(cfg, employee_id)
    if "rank" in fields or "english_name" in fields:
        row["terminal_name_sync"] = sync_terminal_names(cfg, ctx.username, employee_id=employee_id)
    return row


@router.get(
    "/api/v1/humans/import/template.csv",
    dependencies=[Depends(require_roles(ROLES_OPERATOR_PLUS))],
)
def download_import_template():
    return PlainTextResponse(
        content=build_csv_template(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="personnel_import_template.csv"'},
    )


@router.post(
    "/api/v1/humans/import/preview",
    response_model=CsvImportPreviewResponse,
    dependencies=[Depends(require_roles(ROLES_OPERATOR_PLUS))],
)
async def preview_import(
    file: UploadFile,
    cfg: Config = Depends(get_cfg),
):
    """Read-only — parses and validates only, never writes. Not gated by
    Write Session (Phase 12)."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ApiError(422, "VALIDATION_ERROR", "file is not valid UTF-8 text")
    try:
        return classify_csv_rows(cfg, text)
    except PersonnelCsvError as e:
        raise ApiError(422, "CSV_MALFORMED", str(e))


@router.post(
    "/api/v1/humans/import/commit",
    response_model=CsvImportCommitResponse,
    dependencies=[
        Depends(require_roles(ROLES_OPERATOR_PLUS)),
        Depends(require_writes),
    ],
)
async def commit_import(
    file: UploadFile,
    ctx: OperatorContext = Depends(require_roles(ROLES_OPERATOR_PLUS)),
    cfg: Config = Depends(get_cfg),
):
    """Re-validates the uploaded file itself (never trusts a client-held
    preview result) and writes NEW/UPDATE rows in one transaction."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ApiError(422, "VALIDATION_ERROR", "file is not valid UTF-8 text")
    try:
        result = commit_csv_rows(cfg, text, operator=ctx.username)
    except PersonnelCsvError as e:
        raise ApiError(422, "CSV_MALFORMED", str(e))
    if result.get("updated"):
        # Excel rank / English-name updates reach the scanner too.
        result["terminal_name_sync"] = sync_terminal_names(cfg, ctx.username)
    return result


@router.post(
    "/api/v1/humans/{employee_id}/deactivate",
    response_model=Human,
    dependencies=[
        Depends(require_roles(ROLES_OPERATOR_PLUS)),
        Depends(require_writes),
    ],
)
def deactivate(
    employee_id: str,
    payload: DeactivateHumanRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_OPERATOR_PLUS)),
    cfg: Config = Depends(get_cfg),
):
    _require_uuid(employee_id)
    try:
        deactivate_human(cfg, employee_id, ctx.username, payload.reason)
    except PersonnelError as e:
        raise ApiError(409, "PERSONNEL_CONFLICT", str(e))
    row = repository.get_human(cfg, employee_id)
    if row is None:
        raise not_found("human", employee_id)
    return row


@router.post(
    "/api/v1/humans/{employee_id}/remove-from-scanner",
    response_model=dict,
    dependencies=[
        Depends(require_roles(ROLES_OPERATOR_PLUS)),
        Depends(require_writes),
    ],
)
def remove_from_scanner(
    employee_id: str,
    ctx: OperatorContext = Depends(require_roles(ROLES_OPERATOR_PLUS)),
    cfg: Config = Depends(get_cfg),
):
    """Leave-unit step 2: remove every scanner account (and its fingerprints)
    of a person who has already been closed. Scoped to that one person, so
    the personnel section can do it without the general ADMIN-only
    Terminal Management endpoints."""
    from app.api.routers.terminal_management import _dispatch

    employee_id = _require_uuid(employee_id)
    human = repository.get_human(cfg, employee_id)
    if human is None:
        raise not_found("human", employee_id)
    if human.get("active"):
        raise ApiError(409, "HUMAN_STILL_ACTIVE", "Close the person (leave unit) before removing them from the scanner")
    removed, failed = [], []
    for a in repository.human_terminal_accounts(cfg, employee_id):
        try:
            _dispatch(
                "REMOVE_TERMINAL_ACCOUNT",
                {"device_id": a["device_id"], "device_user_id": a["device_user_id"],
                 "operator": ctx.username, "acknowledge_active_human": False},
                cfg,
            )
            removed.append(a["device_user_id"])
        except Exception as e:  # report per account; the caller can retry
            failed.append({"device_user_id": a["device_user_id"], "error": str(e)[:200]})
    return {"removed": removed, "failed": failed}


@router.post(
    "/api/v1/humans/{employee_id}/reactivate",
    response_model=Human,
    dependencies=[
        Depends(require_roles(ROLES_OPERATOR_PLUS)),
        Depends(require_writes),
    ],
)
def reactivate(
    employee_id: str,
    payload: ReactivateHumanRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_OPERATOR_PLUS)),
    cfg: Config = Depends(get_cfg),
):
    _require_uuid(employee_id)
    try:
        reactivate_human(cfg, employee_id, ctx.username, payload.reason)
    except PersonnelError as e:
        raise ApiError(409, "PERSONNEL_CONFLICT", str(e))
    row = repository.get_human(cfg, employee_id)
    if row is None:
        raise not_found("human", employee_id)
    return row
