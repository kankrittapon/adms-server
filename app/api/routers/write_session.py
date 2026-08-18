"""Runtime write session endpoints (Layer 2 of the two-layer write model).

PromptID: ADMS-FullSystem-P0P1-Hardening-007

GET  /api/v1/write-session        -> status, any authenticated role
POST /api/v1/write-session/open   -> OPERATOR or ADMIN, gated by Layer 1 (require_writes)
                                      (ADMS-RBAC-OperationalRoles-023: OPERATOR is the
                                      operational supervisor role and controls WHEN
                                      operational writes may happen — this grants
                                      opening the write gate, never any ADMIN-only
                                      action once it's open. ENROLLMENT_OPERATOR
                                      deliberately cannot open/close a session, only
                                      act within one already opened by OPERATOR/ADMIN.)
POST /api/v1/write-session/close  -> OPERATOR or ADMIN, NOT gated by Layer 1 — closing
                                      is a de-escalation action and must always
                                      be available, even if the infrastructure
                                      master gate is already off

Neither route is gated by require_write_session itself — opening a session
can't require an already-open session, and closing must not require one
either. Layer 1 (API_WRITE_ENABLED) still applies to open: if the
infrastructure master gate is closed, no one (not even ADMIN) can open a
runtime session, which is the intended "Layer 1 unconditionally overrides
Layer 2" invariant.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth import ROLES_ALL_AUTHENTICATED, ROLES_OPERATOR_PLUS
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
# ADMS-RBAC-OperationalRoles-023: opening/closing the Work Session is an
# OPERATOR-or-ADMIN capability — the Work Session gate is only one of two
# independent checks (allow_write = API_WRITE_ENABLED AND active_write_session
# AND role_permits_action); granting OPERATOR the ability to open/close it
# does NOT grant OPERATOR any ADMIN-only endpoint, each of which still
# requires its own require_roles(ROLES_ADMIN_ONLY) dependency.
operator_or_admin = require_roles(ROLES_OPERATOR_PLUS)


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
    dependencies=[Depends(operator_or_admin), Depends(require_writes), Depends(rate_limit("login"))],
)
def open_session(
    payload: OpenWriteSessionRequest,
    ctx: OperatorContext = Depends(operator_or_admin),
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
    dependencies=[Depends(operator_or_admin)],
)
def close_session(
    ctx: OperatorContext = Depends(operator_or_admin),
    cfg: Config = Depends(get_cfg),
):
    result = close_write_session(cfg, closed_by_operator_id=ctx.operator_id, closed_by_username=ctx.username)
    return WriteSessionStatus(**result)
