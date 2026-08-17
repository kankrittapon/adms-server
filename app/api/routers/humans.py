"""Human Master endpoints.

PromptID: ADMS-Frontend-F1-API-001 / ADMS-Frontend-I18n-RBAC-Personnel-004

Frontend-safe Human fields only. Rank is metadata — never identity.
English name editing is strictly ADMIN-only + protected by API_WRITE_ENABLED.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

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
    DeactivateHumanRequest,
    Human,
    Page,
    ReactivateHumanRequest,
    UpdateHumanEnglishNameRequest,
)
from app.config import Config
from app.personnel import PersonnelError, deactivate_human, reactivate_human

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
    page: tuple = Depends(pagination),
    cfg: Config = Depends(get_cfg),
):
    limit, offset = page
    return repository.list_humans(
        cfg,
        limit=limit,
        offset=offset,
        production_scope=production_scope,
        active=active,
        search=search,
        category=category,
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


@router.patch(
    "/api/v1/humans/{employee_id}",
    response_model=Human,
    dependencies=[
        Depends(require_roles(ROLES_ADMIN_ONLY)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def update_human_english_name(
    employee_id: str,
    payload: UpdateHumanEnglishNameRequest,
    ctx: OperatorContext = Depends(require_roles(ROLES_ADMIN_ONLY)),
    cfg: Config = Depends(get_cfg),
):
    _require_uuid(employee_id)
    updated = repository.update_human_english_name(
        cfg,
        employee_id=employee_id,
        english_name=payload.english_name,
        operator_username=ctx.username,
    )
    if updated is None:
        raise not_found("human", employee_id)
    return updated


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
