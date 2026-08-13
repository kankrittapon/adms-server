"""Attendance read endpoints.

PromptID: ADMS-Frontend-F1-API-001

Normalized timestamp fields only. raw_payload is NOT exposed by default —
there is an explicit separate diagnostics endpoint for it.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api import repository
from app.api.dependencies import get_cfg, pagination
from app.api.errors import ApiError, not_found
from app.api.schemas import Attendance, AttendanceDetail, AttendanceRawPayload, Page
from app.config import Config

router = APIRouter(tags=["attendance"])

ALLOWED_STATUS = {"ON_TIME", "LATE", "UNKNOWN"}


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


@router.get("/api/v1/attendance", response_model=Page[Attendance])
def list_attendance(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    device_user_pk: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    page: tuple = Depends(pagination),
    cfg: Config = Depends(get_cfg),
):
    if status is not None and status not in ALLOWED_STATUS:
        raise ApiError(422, "VALIDATION_ERROR", f"invalid status: {status!r}")
    limit, offset = page
    return repository.list_attendance(
        cfg,
        limit=limit,
        offset=offset,
        date_from=_parse_dt(date_from),
        date_to=_parse_dt(date_to),
        employee_id=employee_id,
        device_user_pk=device_user_pk,
        status=status,
    )


@router.get("/api/v1/attendance/{attendance_id}", response_model=AttendanceDetail)
def get_attendance(attendance_id: int, cfg: Config = Depends(get_cfg)):
    row = repository.get_attendance(cfg, attendance_id)
    if row is None:
        raise not_found("attendance", attendance_id)
    return row


@router.get(
    "/api/v1/attendance/{attendance_id}/raw-payload",
    response_model=AttendanceRawPayload,
    description="Explicit diagnostics endpoint for raw attendance payload.",
)
def get_attendance_raw_payload(attendance_id: int, cfg: Config = Depends(get_cfg)):
    row = repository.get_attendance_raw_payload(cfg, attendance_id)
    if row is None:
        raise not_found("attendance", attendance_id)
    return row
