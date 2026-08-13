"""Human Master read endpoints.

PromptID: ADMS-Frontend-F1-API-001

Frontend-safe Human fields only. Rank is metadata — never identity.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api import repository
from app.api.dependencies import get_cfg, pagination
from app.api.errors import ApiError, not_found
from app.api.schemas import Human, Page
from app.config import Config

router = APIRouter(tags=["humans"])


def _require_uuid(value: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", f"invalid UUID: {value!r}")
    return value


@router.get("/api/v1/humans", response_model=Page[Human])
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


@router.get("/api/v1/humans/{employee_id}", response_model=Human)
def get_human(employee_id: str, cfg: Config = Depends(get_cfg)):
    _require_uuid(employee_id)
    row = repository.get_human(cfg, employee_id)
    if row is None:
        raise not_found("human", employee_id)
    return row
