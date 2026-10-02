"""PRM-ADMS-004: Automated Business Hours Write Window — Scheduler Config.

POST /api/v1/write-session/auto-window -> ADMIN only, called by the host systemd timer
GET  /api/v1/admin/schedule-settings  -> ADMIN only, returns enabled/days/start/end/timezone + active_window
POST /api/v1/admin/schedule-settings  -> ADMIN only, toggles enabled bool
"""

import json
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.auth import ROLES_ADMIN_ONLY
from app.api.dependencies import OperatorContext, get_cfg, require_roles
from app.api.errors import ApiError
from app.api.schemas import WriteSessionStatus
from app.config import Config
from app.db import get_db_connection, log_sync_event
from app.write_session import (
    WriteSessionAlreadyActive,
    WriteSessionError,
    close_write_session,
    get_write_session_status,
    open_write_session,
)

router = APIRouter(tags=["schedule"])
admin_only = require_roles(ROLES_ADMIN_ONLY)


class ScheduleSettingsOut(BaseModel):
    enabled: bool
    days: str = Field(description="cron days 1-5 Mon-Fri")
    start_time: str
    end_time: str
    timezone: str
    updated_by: Optional[int] = None
    updated_by_name: Optional[str] = None
    updated_at: Optional[str] = None
    active_window: Optional[dict] = None
    last_run: Optional[dict] = None


class ScheduleToggleRequest(BaseModel):
    enabled: bool


def _fetch_schedule(cur) -> dict:
    cur.execute(
        "SELECT value, updated_by, updated_at FROM system_configurations WHERE key='auto_write_schedule';"
    )
    row = cur.fetchone()
    if row is None:
        # Default safe rollout false if missing (should not happen due to seed)
        return {
            "enabled": False,
            "days": "1-5",
            "start_time": "09:00",
            "end_time": "18:00",
            "timezone": "Asia/Bangkok",
            "updated_by": None,
            "updated_by_name": None,
            "updated_at": None,
        }
    value = row[0]
    updated_by = row[1]
    updated_at = row[2]
    # Resolve updated_by_name
    updated_by_name = None
    if updated_by is not None:
        cur.execute("SELECT username FROM operators WHERE operator_id=%s;", (updated_by,))
        r2 = cur.fetchone()
        if r2:
            updated_by_name = r2[0]
    return {
        "enabled": bool(value.get("enabled", False)),
        "days": value.get("days", "1-5"),
        "start_time": value.get("start_time", "09:00"),
        "end_time": value.get("end_time", "18:00"),
        "timezone": value.get("timezone", "Asia/Bangkok"),
        "updated_by": updated_by,
        "updated_by_name": updated_by_name,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "last_run": value.get("last_run"),
    }


@router.get(
    "/api/v1/admin/schedule-settings",
    response_model=ScheduleSettingsOut,
    dependencies=[Depends(admin_only)],
)
def get_schedule_settings(
    ctx: OperatorContext = Depends(admin_only),
    cfg: Config = Depends(get_cfg),
):
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            data = _fetch_schedule(cur)
    # Attach active_window status (reuses write_session logic, which reaps expired)
    try:
        status = get_write_session_status(cfg)
        data["active_window"] = status
    except Exception:
        data["active_window"] = {"active": False}
    return ScheduleSettingsOut(**data)


@router.post(
    "/api/v1/admin/schedule-settings",
    response_model=ScheduleSettingsOut,
    dependencies=[Depends(admin_only)],
)
def update_schedule_settings(
    payload: ScheduleToggleRequest,
    ctx: OperatorContext = Depends(admin_only),
    cfg: Config = Depends(get_cfg),
):
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            # Use jsonb_set to toggle enabled, keep other fields intact
            cur.execute(
                """
                UPDATE system_configurations
                SET value = jsonb_set(value, '{enabled}', to_jsonb(%s::bool)),
                    updated_by = %s,
                    updated_at = now()
                WHERE key='auto_write_schedule'
                RETURNING value, updated_by, updated_at;
                """,
                (payload.enabled, ctx.operator_id),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                # If missing, insert
                cur.execute(
                    """
                    INSERT INTO system_configurations (key, value, updated_by)
                    VALUES ('auto_write_schedule', jsonb_build_object('enabled', %s::bool, 'days', '1-5', 'start_time', '09:00', 'end_time', '18:00', 'timezone', 'Asia/Bangkok'), %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by=EXCLUDED.updated_by, updated_at=now()
                    RETURNING value, updated_by, updated_at;
                    """,
                    (payload.enabled, ctx.operator_id),
                )
                row = cur.fetchone()
            conn.commit()
            value = row[0]
            updated_by = row[1]
            updated_at = row[2]
            # Resolve name
            cur.execute("SELECT username FROM operators WHERE operator_id=%s;", (updated_by,))
            r2 = cur.fetchone()
            updated_by_name = r2[0] if r2 else None
            data = {
                "enabled": bool(value.get("enabled", False)),
                "days": value.get("days", "1-5"),
                "start_time": value.get("start_time", "09:00"),
                "end_time": value.get("end_time", "18:00"),
                "timezone": value.get("timezone", "Asia/Bangkok"),
                "updated_by": updated_by,
                "updated_by_name": updated_by_name,
                "updated_at": updated_at.isoformat() if updated_at else None,
            }
    # Audit
    try:
        log_sync_event(
            cfg,
            "AUTO_SCHEDULE_TOGGLED",
            "enabled=%s by=%s" % (payload.enabled, ctx.username),
        )
    except Exception:
        pass
    # Attach active_window
    try:
        status = get_write_session_status(cfg)
        data["active_window"] = status
    except Exception:
        data["active_window"] = {"active": False}
    return ScheduleSettingsOut(**data)


class AutoWindowRequest(BaseModel):
    action: str = Field(description="open or close")


@router.post(
    "/api/v1/write-session/auto-window",
    response_model=WriteSessionStatus,
    dependencies=[Depends(admin_only)],
)
def auto_window(
    ctx: OperatorContext = Depends(admin_only),
    cfg: Config = Depends(get_cfg),
    action: Optional[str] = Query(None, description="open or close"),
    payload: Optional[AutoWindowRequest] = None,
):
    # Resolve action from query or body (spec: accepts query or body)
    effective_action = action or (payload.action if payload else None)
    if effective_action not in ("open", "close"):
        raise ApiError(422, "VALIDATION_ERROR", "action must be open or close")
    # Check scheduler enabled flag (read via DB, default false)
    enabled = False
    schedule: dict = {}
    try:
        with get_db_connection(cfg) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM system_configurations WHERE key='auto_write_schedule';")
                row = cur.fetchone()
                if row:
                    schedule = row[0] or {}
                    enabled = schedule.get("enabled") is True
    except Exception:
        enabled = False
    _record_last_run(cfg, effective_action, "skipped_disabled" if not enabled else "ok")

    if not enabled:
        # No-op when disabled — return current status without mutation
        return WriteSessionStatus(**get_write_session_status(cfg))

    # Resolve SYSTEM_SCHEDULER operator_id (active=false, but valid FK)
    scheduler_id = None
    scheduler_name = "SYSTEM_SCHEDULER"
    try:
        with get_db_connection(cfg) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT operator_id FROM operators WHERE username='SYSTEM_SCHEDULER';")
                r = cur.fetchone()
                if r:
                    scheduler_id = r[0]
    except Exception:
        pass
    if scheduler_id is None:
        raise ApiError(500, "SCHEDULER_MISCONFIGURED", "SYSTEM_SCHEDULER operator not found")

    if effective_action == "open":
        # Check if already active — idempotent, extend not needed; just return active
        status = get_write_session_status(cfg)
        if status.get("active"):
            # If already active (any opener), gracefully handle without violating uq
            # If opened by scheduler, return as-is; if by human, also return 200 (do not close human session)
            return WriteSessionStatus(**status)
        try:
            result = open_write_session(
                cfg,
                opened_by_operator_id=scheduler_id,
                opened_by_username=scheduler_name,
                reason="Scheduled Business Hours Window",
                duration_minutes=_minutes_until_end(schedule),
            )
        except WriteSessionAlreadyActive as e:
            raise ApiError(409, "WRITE_SESSION_ALREADY_ACTIVE", str(e))
        except WriteSessionError as e:
            raise ApiError(422, "VALIDATION_ERROR", str(e))
        return WriteSessionStatus(**result)
    else:  # close (effective_action == "close")
        # Only close if active session was opened by SYSTEM_SCHEDULER
        status = get_write_session_status(cfg)
        if not status.get("active"):
            return WriteSessionStatus(**status)
        # Verify opener is scheduler (check DB directly for accuracy)
        try:
            with get_db_connection(cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT opened_by FROM write_sessions WHERE closed_at IS NULL LIMIT 1;")
                    r = cur.fetchone()
                    if r and r[0] != scheduler_id:
                        # Human session active — do not close, return current
                        return WriteSessionStatus(**status)
        except Exception:
            pass
        result = close_write_session(cfg, closed_by_operator_id=ctx.operator_id, closed_by_username=ctx.username)
        # Audit close reason already ADMIN_CLOSED, but add explicit log for scheduler teardown
        try:
            log_sync_event(cfg, "AUTO_WINDOW_CLOSED", "closed_by=%s action=close" % ctx.username)
        except Exception:
            pass
        return WriteSessionStatus(**result)


def _minutes_until_end(schedule: dict) -> int:
    """Window length so the session expires at the configured end_time today
    (local timezone), rather than a fixed span from whenever the timer fired."""
    try:
        tz = ZoneInfo(schedule.get("timezone") or "Asia/Bangkok")
        hh, mm = (int(x) for x in (schedule.get("end_time") or "18:00").split(":"))
        now = datetime.now(tz)
        end = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        minutes = int((end - now).total_seconds() // 60)
        return minutes if minutes > 0 else 1
    except Exception:
        return 540


def _record_last_run(cfg: Config, action: str, result: str) -> None:
    """Stamp last_run into the schedule config so the System page can show
    whether the host timer is actually reaching the API."""
    try:
        with get_db_connection(cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE system_configurations SET value = value || %s::jsonb "
                    "WHERE key='auto_write_schedule';",
                    (json.dumps({"last_run": {"action": action, "result": result,
                                              "at": datetime.now(ZoneInfo("UTC")).isoformat()}}),),
                )
            conn.commit()
    except Exception:
        pass
