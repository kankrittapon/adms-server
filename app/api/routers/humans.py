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
from app.api.schemas import Human, Page, UpdateHumanEnglishNameRequest
from app.config import Config

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
