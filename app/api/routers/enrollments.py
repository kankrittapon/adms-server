"""Enrollment workflow endpoints.

PromptID: ADMS-Frontend-F1-API-001

Read endpoints expose workflow state for the frontend. Write endpoints are
thin wrappers over the canonical app/enrollment.py functions — the allocator
and state-machine logic is NEVER duplicated here. Writes are gated by the
interim write guard (OFF by default). No remote fingerprint enrollment is
performed by the API (physical enrollment happens at the terminal by the
operator; the API only records operator confirmations).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api import repository
from app.api.dependencies import get_cfg, pagination, require_role, require_writes
from app.api.errors import ApiError, not_found
from app.api.schemas import (
    Enrollment,
    EnrollmentNextActions,
    EnrollmentReserveResult,
    EnrollmentTransitionResult,
    Page,
)
from app.config import Config
from app.enrollment import (
    ALLOWED_TRANSITIONS,
    ENROLLMENT_ACTIONS,
    EnrollmentError,
    cancel_enrollment,
    confirm_controlled_scan,
    confirm_fingerprint_enrolled,
    get_enrollment,
    mark_ready_for_mapping,
    reserve_next_device_user_id,
    start_controlled_scan_window,
    start_fingerprint_enrollment,
)

router = APIRouter(tags=["enrollments"])


@router.get("/api/v1/enrollments", response_model=Page[Enrollment])
def list_enrollments(
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    device_id: Optional[int] = Query(None),
    page: tuple = Depends(pagination),
    cfg: Config = Depends(get_cfg),
):
    limit, offset = page
    return repository.list_enrollments(
        cfg,
        limit=limit,
        offset=offset,
        status=status,
        employee_id=employee_id,
        device_id=device_id,
    )


@router.get("/api/v1/enrollments/{enrollment_id}", response_model=Enrollment)
def get_enrollment_detail(enrollment_id: int, cfg: Config = Depends(get_cfg)):
    row = repository.get_enrollment_row(cfg, enrollment_id)
    if row is None:
        raise not_found("enrollment", enrollment_id)
    return row


@router.get(
    "/api/v1/enrollments/{enrollment_id}/next-actions",
    response_model=EnrollmentNextActions,
)
def get_next_actions(enrollment_id: int, cfg: Config = Depends(get_cfg)):
    """Returns the valid next operator actions for an enrollment's current state.

    Computed from the canonical state machine (app.enrollment.ALLOWED_TRANSITIONS
    + ENROLLMENT_ACTIONS) so the frontend never duplicates workflow logic.
    Read-only — no state mutation. Physical terminal steps (e.g. terminal
    account creation) are intentionally absent: they happen at the terminal.
    """
    row = repository.get_enrollment_row(cfg, enrollment_id)
    if row is None:
        raise not_found("enrollment", enrollment_id)
    status = row["status"]
    allowed = ALLOWED_TRANSITIONS.get(status, set())
    actions = [
        {
            "action": action,
            "target_status": spec["target"],
            "requires_role": spec["requires_role"],
        }
        for action, spec in sorted(ENROLLMENT_ACTIONS.items())
        if spec["target"] in allowed
    ]
    return {
        "enrollment_id": enrollment_id,
        "status": status,
        "next_actions": actions,
    }


# ---------------------------------------------------------------------------
# Write routes — gated by API_WRITE_ENABLED (OFF by default)
# ---------------------------------------------------------------------------


class ReserveRequest(BaseModel):
    employee_id: str = Field(description="Human UUID")
    device_id: int = Field(description="devices.device_id")
    operator: str = Field(description="explicit operator identity")
    roster_user_ids: Optional[list] = Field(
        None, description="optional live terminal roster IDs (read-only evidence)"
    )


@router.post(
    "/api/v1/enrollments/reserve",
    status_code=201,
    response_model=EnrollmentReserveResult,
    dependencies=[Depends(require_role("OPERATOR")), Depends(require_writes)],
)
def reserve(payload: ReserveRequest, cfg: Config = Depends(get_cfg)):
    try:
        result = reserve_next_device_user_id(
            cfg,
            employee_id=payload.employee_id,
            device_id=payload.device_id,
            operator=payload.operator,
            roster_user_ids=set(payload.roster_user_ids or []),
        )
    except EnrollmentError as e:
        raise ApiError(409, "ENROLLMENT_CONFLICT", str(e))
    return result


class TransitionRequest(BaseModel):
    operator: str = Field(description="explicit operator identity")
    notes: Optional[str] = None


class ScanConfirmationRequest(BaseModel):
    operator: str = Field(description="explicit operator identity")
    scan_time: datetime = Field(description="controlled attendance scan time")


class CreateTerminalAccountRequest(BaseModel):
    display_name: str = Field(description="ASCII terminal display name")
    operator: str = Field(description="explicit operator identity")


@router.post(
    "/api/v1/enrollments/{enrollment_id}/create-terminal-account",
    dependencies=[Depends(require_role("OPERATOR")), Depends(require_writes)],
)
def create_terminal_account(
    enrollment_id: int,
    payload: CreateTerminalAccountRequest,
    cfg: Config = Depends(get_cfg),
):
    # This step requires a live terminal connection and is intentionally NOT
    # performed through the API in F1. The physical account creation is done
    # by the operator at the terminal / collector workflow.
    raise ApiError(
        501,
        "NOT_IMPLEMENTED",
        "terminal account creation requires a live terminal connection and is "
        "not exposed through the F1 API; perform the physical enrollment via "
        "the operator workflow",
    )


@router.post(
    "/api/v1/enrollments/{enrollment_id}/start-fingerprint-enrollment",
    response_model=EnrollmentTransitionResult,
    dependencies=[Depends(require_role("OPERATOR")), Depends(require_writes)],
)
def start_fingerprint(
    enrollment_id: int,
    payload: TransitionRequest,
    cfg: Config = Depends(get_cfg),
):
    try:
        result = start_fingerprint_enrollment(cfg, enrollment_id, payload.operator, payload.notes)
    except EnrollmentError as e:
        raise ApiError(409, "ENROLLMENT_CONFLICT", str(e))
    return result


@router.post(
    "/api/v1/enrollments/{enrollment_id}/confirm-fingerprint",
    response_model=EnrollmentTransitionResult,
    dependencies=[Depends(require_role("OPERATOR")), Depends(require_writes)],
)
def confirm_fingerprint(
    enrollment_id: int,
    payload: TransitionRequest,
    cfg: Config = Depends(get_cfg),
):
    try:
        result = confirm_fingerprint_enrolled(cfg, enrollment_id, payload.operator, payload.notes)
    except EnrollmentError as e:
        raise ApiError(409, "ENROLLMENT_CONFLICT", str(e))
    return result


@router.post(
    "/api/v1/enrollments/{enrollment_id}/start-controlled-scan",
    response_model=EnrollmentTransitionResult,
    dependencies=[Depends(require_role("OPERATOR")), Depends(require_writes)],
)
def start_scan_window(
    enrollment_id: int,
    payload: TransitionRequest,
    cfg: Config = Depends(get_cfg),
):
    try:
        result = start_controlled_scan_window(cfg, enrollment_id, payload.operator)
    except EnrollmentError as e:
        raise ApiError(409, "ENROLLMENT_CONFLICT", str(e))
    return result


@router.post(
    "/api/v1/enrollments/{enrollment_id}/confirm-controlled-scan",
    response_model=EnrollmentTransitionResult,
    dependencies=[Depends(require_role("OPERATOR")), Depends(require_writes)],
)
def confirm_scan(
    enrollment_id: int,
    payload: ScanConfirmationRequest,
    cfg: Config = Depends(get_cfg),
):
    try:
        result = confirm_controlled_scan(
            cfg, enrollment_id, payload.scan_time, payload.operator, None
        )
    except EnrollmentError as e:
        raise ApiError(409, "ENROLLMENT_CONFLICT", str(e))
    return result


@router.post(
    "/api/v1/enrollments/{enrollment_id}/mark-ready-for-mapping",
    response_model=EnrollmentTransitionResult,
    dependencies=[Depends(require_role("OPERATOR")), Depends(require_writes)],
)
def mark_ready(
    enrollment_id: int,
    payload: TransitionRequest,
    cfg: Config = Depends(get_cfg),
):
    try:
        result = mark_ready_for_mapping(cfg, enrollment_id, payload.operator, payload.notes)
    except EnrollmentError as e:
        raise ApiError(409, "ENROLLMENT_CONFLICT", str(e))
    return result


@router.post(
    "/api/v1/enrollments/{enrollment_id}/cancel",
    response_model=EnrollmentTransitionResult,
    dependencies=[Depends(require_role("OPERATOR")), Depends(require_writes)],
)
def cancel(
    enrollment_id: int,
    payload: TransitionRequest,
    cfg: Config = Depends(get_cfg),
):
    try:
        result = cancel_enrollment(cfg, enrollment_id, payload.operator, payload.notes)
    except EnrollmentError as e:
        raise ApiError(409, "ENROLLMENT_CONFLICT", str(e))
    return result
