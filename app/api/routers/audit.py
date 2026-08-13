"""Audit-trail endpoints (F5 hardening, admin-only).

PromptID: ADMS-Frontend-F5-Hardening-001

GET /api/v1/audit/events       -> paginated sync_events (event_type + date filters)
GET /api/v1/audit/event-types  -> distinct event types for the filter UI

The sync_events table already captures AUTH_LOGIN / AUTH_LOGIN_FAILED /
AUTH_LOGOUT / AUTH_PASSWORD_CHANGE / OPERATOR_* / ENROLLMENT_* /
MAPPING_VERIFIED / RATE_LIMITED events. This is read-only.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api import repository
from app.api.dependencies import get_cfg, pagination, require_role
from app.api.errors import ApiError
from app.api.schemas import AuditEvent, Page
from app.config import Config

router = APIRouter(tags=["audit"])

admin_only = require_role("ADMIN")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", f"invalid datetime: {value!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@router.get(
    "/api/v1/audit/events",
    response_model=Page[AuditEvent],
    dependencies=[Depends(admin_only)],
)
def list_events(
    event_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: tuple = Depends(pagination),
    cfg: Config = Depends(get_cfg),
):
    limit, offset = page
    return repository.list_audit_events(
        cfg,
        limit=limit,
        offset=offset,
        event_type=event_type,
        date_from=_parse_dt(date_from),
        date_to=_parse_dt(date_to),
    )


@router.get(
    "/api/v1/audit/event-types",
    dependencies=[Depends(admin_only)],
)
def event_types(cfg: Config = Depends(get_cfg)):
    return {"event_types": repository.list_audit_event_types(cfg)}
