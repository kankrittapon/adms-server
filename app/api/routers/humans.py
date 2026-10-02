"""Human Master endpoints.

PromptID: ADMS-Frontend-F1-API-001 / ADMS-Frontend-I18n-RBAC-Personnel-004 /
ADMS-Personnel-MasterData-024

Frontend-safe Human fields only. Rank is metadata — never identity.
All Personnel master-data writes (create, edit, CSV import commit) are
ADMIN-only, gated by both write layers (API_WRITE_ENABLED AND an active
Write Session) — CSV preview and export are read-only and gated by
neither.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import PlainTextResponse

from app.api import repository
from app.api.auth import ROLES_ADMIN_ONLY, ROLES_ENROLLMENT_READ
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


@router.post(
    "/api/v1/humans/scan-exempt",
    response_model=BulkScanExemptResponse,
    dependencies=[
        Depends(require_roles(ROLES_ADMIN_ONLY)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def bulk_scan_exempt(
    payload: BulkScanExemptRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_ADMIN_ONLY)),
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
    return repository.human_terminal_accounts(cfg, employee_id)


@router.post(
    "/api/v1/humans",
    response_model=Human,
    status_code=201,
    dependencies=[
        Depends(require_roles(ROLES_ADMIN_ONLY)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def create_human_endpoint(
    payload: CreateHumanRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_ADMIN_ONLY)),
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
        Depends(require_roles(ROLES_ADMIN_ONLY)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def update_human_endpoint(
    employee_id: str,
    payload: UpdateHumanRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_ADMIN_ONLY)),
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
    return row


@router.get(
    "/api/v1/humans/import/template.csv",
    dependencies=[Depends(require_roles(ROLES_ADMIN_ONLY))],
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
    dependencies=[Depends(require_roles(ROLES_ADMIN_ONLY))],
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
        Depends(require_roles(ROLES_ADMIN_ONLY)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
async def commit_import(
    file: UploadFile,
    ctx: OperatorContext = Depends(require_roles(ROLES_ADMIN_ONLY)),
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
        return commit_csv_rows(cfg, text, operator=ctx.username)
    except PersonnelCsvError as e:
        raise ApiError(422, "CSV_MALFORMED", str(e))


@router.post(
    "/api/v1/humans/{employee_id}/deactivate",
    response_model=Human,
    dependencies=[
        Depends(require_roles(ROLES_ADMIN_ONLY)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def deactivate(
    employee_id: str,
    payload: DeactivateHumanRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_ADMIN_ONLY)),
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
    "/api/v1/humans/{employee_id}/reactivate",
    response_model=Human,
    dependencies=[
        Depends(require_roles(ROLES_ADMIN_ONLY)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def reactivate(
    employee_id: str,
    payload: ReactivateHumanRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_ADMIN_ONLY)),
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
