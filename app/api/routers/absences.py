"""Absence (leave / official duty / secondment) and daily roster endpoints.

Record-only — leave is approved on paper before entry, so recording is an
OPERATOR-or-ADMIN data-entry action with no approval step, gated by
API_WRITE_ENABLED only (not the Work Session, which guards scanner work). Reads (list, types, daily roster) are open to every
read-capable role. Holidays are ADMIN-managed.
"""

from datetime import date, datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app import absences
from app.api.auth import ROLES_ADMIN_ONLY, ROLES_GENERAL_READ, ROLES_OPERATOR_PLUS
from app.api.dependencies import (
    OperatorContext,
    get_cfg,
    pagination,
    require_roles,
    require_writes,
)
from app.api.errors import ApiError
from app.config import Config

router = APIRouter(tags=["absences"])

read_roles = require_roles(ROLES_GENERAL_READ)
recorder = require_roles(ROLES_OPERATOR_PLUS)
admin_only = require_roles(ROLES_ADMIN_ONLY)
WRITE_GATES = [Depends(require_writes)]


class AbsenceType(BaseModel):
    code: str
    name_th: str
    name_en: str
    counts_as: str = Field(description="'LEAVE' or 'DUTY' (official duty / secondment count as working)")
    requires_order_ref: bool


class Absence(BaseModel):
    absence_id: int
    employee_id: str
    employee_name: str
    rank: Optional[str] = None
    branch: Optional[str] = None
    type_code: str
    type_name_th: str
    type_name_en: str
    counts_as: str
    start_date: date
    end_date: date
    days: int
    order_ref: Optional[str] = None
    destination: Optional[str] = None
    note: Optional[str] = None
    status: str
    recorded_by: str
    recorded_at: datetime
    cancelled_by: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None


class AbsencePage(BaseModel):
    items: List[Absence]
    total: int
    limit: int
    offset: int


class CreateAbsenceRequest(BaseModel):
    employee_id: str
    type_code: str
    start_date: date
    end_date: date
    order_ref: Optional[str] = Field(None, max_length=200)
    destination: Optional[str] = Field(None, max_length=200)
    note: Optional[str] = Field(None, max_length=500)


class CancelAbsenceRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class Holiday(BaseModel):
    holiday_date: date
    name_th: str


class RosterPerson(BaseModel):
    employee_id: str
    display_name: str
    rank: Optional[str] = None
    branch: Optional[str] = None
    category: Optional[str] = None
    scan_exempt: bool
    status: str = Field(description="PRESENT | LATE | LEAVE | DUTY | EXEMPT | NOT_YET | ABSENT | OFF")
    type_code: Optional[str] = None
    absence_name_th: Optional[str] = None
    order_ref: Optional[str] = None
    absence_start: Optional[date] = None
    absence_end: Optional[date] = None
    first_scan: Optional[datetime] = Field(None, description="first scan inside the scan window")
    tracked_from: Optional[date] = Field(None, description="first day held to scanning (day after enrollment); null = not enrolled")
    scans_outside_window: int = 0


class MonthlyDay(BaseModel):
    date: date
    is_workday: bool
    holiday_name: Optional[str] = None


class MonthlyPerson(BaseModel):
    employee_id: str
    display_name: str
    rank: Optional[str] = None
    branch: Optional[str] = None
    scan_exempt: bool
    days: List[str] = Field(description="one roster status per day of the month")
    counts: dict


class RosterBranch(BaseModel):
    branch: str
    counts: dict


class DailyRoster(BaseModel):
    live: bool = Field(True, description="false = before go-live: absences are trial, not real")
    date: date
    is_workday: bool
    holiday_name: Optional[str] = None
    late_after: str
    scan_window: str = "06:30–11:00"
    total: int
    totals: dict
    by_branch: List[RosterBranch]
    people: List[RosterPerson]


def _map_error(e: absences.AbsenceError) -> ApiError:
    if isinstance(e, absences.AbsenceOverlapError):
        return ApiError(409, "ABSENCE_OVERLAP", str(e))
    if isinstance(e, absences.AbsenceNotFound):
        return ApiError(404, "NOT_FOUND", str(e))
    return ApiError(422, "VALIDATION_ERROR", str(e))


@router.get("/api/v1/absence-types", response_model=List[AbsenceType], dependencies=[Depends(read_roles)])
def get_types(cfg: Config = Depends(get_cfg)):
    return absences.list_types(cfg)


@router.get("/api/v1/absences", response_model=AbsencePage, dependencies=[Depends(read_roles)])
def get_absences(
    employee_id: Optional[str] = Query(None),
    on_or_after: Optional[date] = Query(None, description="absences ending on/after this date"),
    on_or_before: Optional[date] = Query(None, description="absences starting on/before this date"),
    type_code: Optional[str] = Query(None),
    include_cancelled: bool = Query(False),
    search: Optional[str] = Query(None, max_length=100),
    page: tuple = Depends(pagination),
    cfg: Config = Depends(get_cfg),
):
    limit, offset = page
    return absences.list_absences(
        cfg,
        limit=limit,
        offset=offset,
        employee_id=employee_id,
        on_or_after=on_or_after,
        on_or_before=on_or_before,
        type_code=type_code,
        include_cancelled=include_cancelled,
        search=search,
    )


@router.post(
    "/api/v1/absences",
    response_model=Absence,
    status_code=201,
    dependencies=[Depends(recorder), *WRITE_GATES],
)
def post_absence(payload: CreateAbsenceRequest, ctx: OperatorContext = Depends(recorder), cfg: Config = Depends(get_cfg)):
    try:
        return absences.create_absence(cfg, ctx.username, **payload.model_dump())
    except absences.AbsenceError as e:
        raise _map_error(e)


@router.post(
    "/api/v1/absences/{absence_id}/cancel",
    response_model=Absence,
    dependencies=[Depends(recorder), *WRITE_GATES],
)
def post_cancel(
    absence_id: int,
    payload: CancelAbsenceRequest,
    ctx: OperatorContext = Depends(recorder),
    cfg: Config = Depends(get_cfg),
):
    try:
        return absences.cancel_absence(cfg, ctx.username, absence_id, payload.reason)
    except absences.AbsenceError as e:
        raise _map_error(e)


@router.get("/api/v1/holidays", response_model=List[Holiday], dependencies=[Depends(read_roles)])
def get_holidays(year: Optional[int] = Query(None, ge=2000, le=2100), cfg: Config = Depends(get_cfg)):
    return absences.list_holidays(cfg, year)


@router.post("/api/v1/holidays", response_model=Holiday, dependencies=[Depends(admin_only), *WRITE_GATES])
def post_holiday(payload: Holiday, ctx: OperatorContext = Depends(admin_only), cfg: Config = Depends(get_cfg)):
    try:
        return absences.upsert_holiday(cfg, ctx.username, payload.holiday_date, payload.name_th)
    except absences.AbsenceError as e:
        raise _map_error(e)


@router.delete("/api/v1/holidays/{holiday_date}", status_code=204, dependencies=[Depends(admin_only), *WRITE_GATES])
def remove_holiday(holiday_date: date, ctx: OperatorContext = Depends(admin_only), cfg: Config = Depends(get_cfg)):
    absences.delete_holiday(cfg, ctx.username, holiday_date)


@router.get("/api/v1/attendance/daily", response_model=DailyRoster, dependencies=[Depends(read_roles)])
def get_daily_roster(
    day: Optional[date] = Query(None, alias="date", description="local date; defaults to today (Asia/Bangkok)"),
    cfg: Config = Depends(get_cfg),
):
    return absences.daily_roster(cfg, day or datetime.now(ZoneInfo("Asia/Bangkok")).date())


class MonthlyReport(BaseModel):
    month: str
    late_after: str
    scan_window: str = "06:30–11:00"
    workdays: int
    days: List[MonthlyDay]
    people: List[MonthlyPerson]
    by_branch: List[RosterBranch]


def _parse_month(month: Optional[str]) -> tuple:
    if not month:
        today = datetime.now(ZoneInfo("Asia/Bangkok")).date()
        return today.year, today.month
    try:
        y, m = (int(x) for x in month.split("-"))
        date(y, m, 1)
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", f"invalid month: {month!r} (expected YYYY-MM)")
    return y, m


@router.get("/api/v1/attendance/monthly", response_model=MonthlyReport, dependencies=[Depends(read_roles)])
def get_monthly_report(month: Optional[str] = Query(None, description="YYYY-MM; defaults to this month"), cfg: Config = Depends(get_cfg)):
    return absences.monthly_report(cfg, *_parse_month(month))


@router.get("/api/v1/attendance/monthly.csv", dependencies=[Depends(read_roles)])
def get_monthly_report_csv(month: Optional[str] = Query(None), cfg: Config = Depends(get_cfg)):
    y, m = _parse_month(month)
    report = absences.monthly_report(cfg, y, m)
    return PlainTextResponse(
        content=absences.monthly_report_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="attendance_{y:04d}-{m:02d}.csv"'},
    )


class ReadinessRow(BaseModel):
    branch: str = "ทั้งหมด"
    total: int
    exempt: int
    away: int = Field(0, description="not enrolled but away on official duty / secondment today")
    enrolled: int
    required: int
    missing: int
    percent: int


class Readiness(BaseModel):
    branches: List[ReadinessRow]
    total: ReadinessRow


@router.get("/api/v1/attendance/readiness", response_model=Readiness, dependencies=[Depends(read_roles)])
def get_readiness(cfg: Config = Depends(get_cfg)):
    return absences.readiness(cfg)


class TelegramReportResult(BaseModel):
    sent: bool
    reason: Optional[str] = None
    text: Optional[str] = None


@router.get("/api/v1/reports/telegram/preview", response_model=TelegramReportResult, dependencies=[Depends(admin_only)])
def preview_telegram_report(day: Optional[date] = Query(None, alias="date"), cfg: Config = Depends(get_cfg)):
    """What the daily Telegram message would say (nothing is sent)."""
    from app import telegram_report

    d = day or datetime.now(ZoneInfo("Asia/Bangkok")).date()
    text = telegram_report.build_message(absences.daily_roster(cfg, d))
    return {"sent": False, "reason": None if text else "non-working day", "text": text}


@router.post("/api/v1/reports/telegram/send", response_model=TelegramReportResult, dependencies=[Depends(admin_only)])
def send_telegram_report(day: Optional[date] = Query(None, alias="date"), cfg: Config = Depends(get_cfg)):
    """ADMIN test send of the daily report (same message as the timer)."""
    from app import telegram_report

    try:
        return telegram_report.send_daily_report(cfg, day, force=True)
    except telegram_report.TelegramNotConfigured:
        raise ApiError(409, "TELEGRAM_NOT_CONFIGURED", "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set")
    except telegram_report.TelegramSendError as e:
        raise ApiError(502, "TELEGRAM_SEND_FAILED", str(e))


class TrackingState(BaseModel):
    mode: str = Field(description="auto | on | off")
    live: bool
    live_since: Optional[date] = Field(None, description="auto mode: first day counting became real (latched)")
    readiness: ReadinessRow


class TrackingModeRequest(BaseModel):
    mode: str


@router.get("/api/v1/attendance/tracking", response_model=TrackingState, dependencies=[Depends(read_roles)])
def get_tracking(cfg: Config = Depends(get_cfg)):
    return absences.tracking_state(cfg)


@router.post("/api/v1/attendance/tracking", response_model=TrackingState, dependencies=[Depends(admin_only), *WRITE_GATES])
def post_tracking(payload: TrackingModeRequest, ctx: OperatorContext = Depends(admin_only), cfg: Config = Depends(get_cfg)):
    try:
        return absences.set_tracking_mode(cfg, ctx.username, payload.mode)
    except absences.AbsenceError as e:
        raise _map_error(e)
