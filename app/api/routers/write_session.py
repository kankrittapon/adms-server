"""Runtime write session endpoints (Layer 2 of the two-layer write model).

PromptID: ADMS-FullSystem-P0P1-Hardening-007

GET  /api/v1/write-session        -> status, any authenticated role
POST /api/v1/write-session/open   -> ADMIN only, gated by Layer 1 (require_writes)
POST /api/v1/write-session/close  -> ADMIN only, NOT gated by Layer 1 — closing
                                      is a de-escalation action and must always
                                      be available to an ADMIN, even if the
                                      infrastructure master gate is already off

Neither route is gated by require_write_session itself — opening a session
can't require an already-open session, and closing must not require one
either. Layer 1 (API_WRITE_ENABLED) still applies to open: if the
infrastructure master gate is closed, no one (not even ADMIN) can open a
runtime session, which is the intended "Layer 1 unconditionally overrides
Layer 2" invariant.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth import ROLES_ADMIN_ONLY, ROLES_ALL_AUTHENTICATED
from app.api.dependencies import OperatorContext, get_cfg, rate_limit, require_roles, require_writes
from app.api.schemas import WriteSessionStatus
from app.config import Config
from app.write_session import (
    DEFAULT_DURATION_MINUTES,
    WriteSessionAlreadyActive,
    WriteSessionError,
    close_write_session,
    get_write_session_status,
    open_write_session,
)
from app.api.errors import ApiError

router = APIRouter(tags=["write-session"])

read_any = require_roles(ROLES_ALL_AUTHENTICATED)
admin_only = require_roles(ROLES_ADMIN_ONLY)


class OpenWriteSessionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500, description="Why writes are being opened, e.g. 'Enrollment session — Bldg 3'")


@router.get(
    "/api/v1/write-session",
    response_model=WriteSessionStatus,
    dependencies=[Depends(read_any)],
)
def get_status(cfg: Config = Depends(get_cfg)):
    return WriteSessionStatus(**get_write_session_status(cfg))


@router.post(
    "/api/v1/write-session/open",
    response_model=WriteSessionStatus,
    status_code=201,
    dependencies=[Depends(admin_only), Depends(require_writes), Depends(rate_limit("login"))],
)
def open_session(
    payload: OpenWriteSessionRequest,
    ctx: OperatorContext = Depends(admin_only),
    cfg: Config = Depends(get_cfg),
):
    try:
        result = open_write_session(
            cfg,
            opened_by_operator_id=ctx.operator_id,
            opened_by_username=ctx.username,
            reason=payload.reason,
            duration_minutes=DEFAULT_DURATION_MINUTES,
        )
    except WriteSessionAlreadyActive as e:
        raise ApiError(409, "WRITE_SESSION_ALREADY_ACTIVE", str(e))
    except WriteSessionError as e:
        raise ApiError(422, "VALIDATION_ERROR", str(e))
    return WriteSessionStatus(**result)


@router.post(
    "/api/v1/write-session/close",
    response_model=WriteSessionStatus,
    dependencies=[Depends(admin_only)],
)
def close_session(
    ctx: OperatorContext = Depends(admin_only),
    cfg: Config = Depends(get_cfg),
):
    result = close_write_session(cfg, closed_by_operator_id=ctx.operator_id, closed_by_username=ctx.username)
    return WriteSessionStatus(**result)
