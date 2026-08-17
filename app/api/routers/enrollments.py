"""Enrollment workflow endpoints.

PromptID: ADMS-Frontend-F1-API-001 / ADMS-Frontend-I18n-RBAC-Personnel-004

Read endpoints expose workflow state for the frontend. Write endpoints are
thin wrappers over the canonical app/enrollment.py functions — the allocator
and state-machine logic is NEVER duplicated here. Writes are gated by the
interim write guard (OFF by default). No remote fingerprint enrollment is
performed by the API (physical enrollment happens at the terminal by the
operator; the API only records operator confirmations).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api import repository
from app.api.auth import ROLES_ENROLLMENT_MUTATE, ROLES_ENROLLMENT_READ
from app.api.dependencies import (
    get_cfg,
    pagination,
    require_roles,
    require_write_session,
    require_writes,
)
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
    CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS,
    TerminalAccountConflict,
    TerminalAccountUnconfirmed,
    TerminalRosterUnavailable,
    cancel_enrollment,
    confirm_controlled_scan,
    confirm_fingerprint_enrolled,
    create_or_reconcile_terminal_account,
    get_enrollment,
    mark_ready_for_mapping,
    reserve_next_device_user_id,
    start_controlled_scan_window,
    start_fingerprint_enrollment,
)

router = APIRouter(tags=["enrollments"])

enrollment_read = require_roles(ROLES_ENROLLMENT_READ)
enrollment_mutate = require_roles(ROLES_ENROLLMENT_MUTATE)


@router.get(
    "/api/v1/enrollments",
    response_model=Page[Enrollment],
    dependencies=[Depends(enrollment_read)],
)
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


@router.get(
    "/api/v1/enrollments/{enrollment_id}",
    response_model=Enrollment,
    dependencies=[Depends(enrollment_read)],
)
def get_enrollment_detail(enrollment_id: int, cfg: Config = Depends(get_cfg)):
    row = repository.get_enrollment_row(cfg, enrollment_id)
    if row is None:
        raise not_found("enrollment", enrollment_id)
    return row


@router.get(
    "/api/v1/enrollments/{enrollment_id}/next-actions",
    response_model=EnrollmentNextActions,
    dependencies=[Depends(enrollment_read)],
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
    # requires_role is computed here from the actual enforcement role set
    # (ROLES_ENROLLMENT_MUTATE), not from ENROLLMENT_ACTIONS' per-action
    # "requires_role" field — that field is informational only and must
    # never drift from the router's real Depends(enrollment_mutate) check.
    requires_role = "+".join(sorted(ROLES_ENROLLMENT_MUTATE, key=lambda r: r))
    actions = [
        {
            "action": action,
            "target_status": spec["target"],
            "requires_role": requires_role,
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
    dependencies=[
        Depends(enrollment_mutate),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def reserve(payload: ReserveRequest, cfg: Config = Depends(get_cfg)):
    return reserve_next_device_user_id(
        cfg,
        employee_id=payload.employee_id,
        device_id=payload.device_id,
        operator=payload.operator,
        roster_user_ids=set(payload.roster_user_ids or []),
    )


class TransitionRequest(BaseModel):
    operator: str = Field(description="explicit operator identity")
    notes: Optional[str] = None


class ScanConfirmationRequest(BaseModel):
    """ADMS-ControlledScan-EvidenceBinding-018: no scan_time field — the
    server resolves and binds the actual attendance evidence itself (see
    app.enrollment.confirm_controlled_scan). The operator/browser never
    supplies or estimates a scan time."""

    operator: str = Field(description="explicit operator identity")


class CreateTerminalAccountRequest(BaseModel):
    display_name: str = Field(description="ASCII terminal display name")
    operator: str = Field(description="explicit operator identity")


@router.post(
    "/api/v1/enrollments/{enrollment_id}/create-terminal-account",
    response_model=EnrollmentTransitionResult,
    dependencies=[
        Depends(enrollment_mutate),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def create_terminal_account(
    enrollment_id: int,
    payload: CreateTerminalAccountRequest,
    request: Request,
    cfg: Config = Depends(get_cfg),
):
    # Check if a direct test device is injected into app state (e.g. unit tests)
    if hasattr(request.app.state, "device_executor") and request.app.state.device_executor is not None:
        try:
            result = create_or_reconcile_terminal_account(
                cfg,
                enrollment_id=enrollment_id,
                display_name=payload.display_name,
                device=request.app.state.device_executor,
            )
        except TerminalRosterUnavailable as e:
            # PRE-MUTATION failure — set_user() was never reached.
            raise ApiError(503, "DEVICE_UNAVAILABLE", str(e))
        except TerminalAccountConflict as e:
            raise ApiError(409, "TERMINAL_ACCOUNT_CONFLICT", str(e))
        except TerminalAccountUnconfirmed as e:
            raise ApiError(503, "TERMINAL_ACCOUNT_UNCONFIRMED", str(e))
        return {
            "enrollment_id": enrollment_id,
            "status": "TERMINAL_ACCOUNT_CREATED",
            "action": "create-terminal-account",
            "operator": payload.operator,
            "reconciled": result.get("reconciled", False),
        }

    # Serialized dispatch over DeviceCommandBus to the live Collector.
    # dedupe_key ties concurrent/duplicate requests for this enrollment
    # together so at most one set_user() reaches the device at a time.
    from app.device_command_bus import get_command_bus, DeviceCommandBusy, DeviceCommandError
    bus = get_command_bus(cfg)
    try:
        res = bus.execute(
            "CREATE_TERMINAL_ACCOUNT",
            {
                "enrollment_id": enrollment_id,
                "display_name": payload.display_name,
                "operator": payload.operator,
            },
            # Derived, not arbitrary — see app.enrollment's timing-budget
            # constants. Must exceed the Collector's own worst-case realistic
            # operation duration (roster read + set_user + bounded read-back)
            # plus transport margin, so a genuine Collector-side result
            # (success OR a specific error) always has time to arrive before
            # this outer timeout fires. When it does fire, it should mean
            # only "no authoritative response arrived at all" — not race
            # against and mask a real Collector answer.
            timeout=CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS,
            dedupe_key="enrollment:%s" % enrollment_id,
        )
    except DeviceCommandBusy as e:
        raise ApiError(409, "DEVICE_COMMAND_IN_PROGRESS", str(e))
    except DeviceCommandError as e:
        err_str = str(e)
        # Prefer the structured error_code from the Collector's response when
        # present — only fall back to substring matching for exceptions that
        # didn't carry one (e.g. a transport-level failure with no Collector
        # response at all).
        code = getattr(e, "error_code", None)
        if code == "TERMINAL_ACCOUNT_CONFLICT":
            raise ApiError(409, code, err_str)
        if code == "TERMINAL_ACCOUNT_UNCONFIRMED":
            raise ApiError(503, code, err_str)
        if code == "ENROLLMENT_CONFLICT":
            raise ApiError(409, code, err_str)
        if code == "DEVICE_UNAVAILABLE":
            # Pre-mutation roster failure reported by the Collector itself
            # (TerminalRosterUnavailable) — set_user() was never reached.
            raise ApiError(503, code, err_str)
        if code == "COLLECTOR_UNAVAILABLE":
            # ADMS-ZEM560-SingleOwnerIO-014, category 4 — the Collector
            # itself is not LIVE (no connection, or reconnecting). Distinct
            # from DEVICE_UNAVAILABLE: that means the Collector IS live but
            # a specific roster read against the device failed; this means
            # the Collector never had a usable connection to attempt
            # anything with in the first place.
            raise ApiError(503, code, err_str)
        if code == "DEVICE_COMMAND_QUEUE_FULL":
            # ADMS-ZEM560-SingleOwnerIO-014, category 1 — the Collector's
            # bounded device-command queue was already full. No write was
            # attempted for this request; safe to retry once the earlier
            # command in the queue has been serviced.
            raise ApiError(503, code, err_str)
        if code == "DEVICE_OWNER_TIMEOUT":
            # ADMS-ZEM560-SingleOwnerIO-014, category 2 — the command was
            # accepted but the single device owner never reached a safe
            # point to execute it within its wait budget. Distinct from a
            # device PROTOCOL timeout (DEVICE_UNAVAILABLE /
            # TERMINAL_ACCOUNT_UNCONFIRMED): no device I/O for this command
            # was ever attempted, so — unlike those — it is always safe to
            # retry without any reconciliation concern.
            raise ApiError(503, code, err_str)
        if code == "DEVICE_COMMAND_CANCELLED":
            # ADMS-ZEM560-SingleOwnerIO-014 — the command was queued but
            # cancelled because the device connection was reconnected (or
            # the Collector is shutting down) before it could execute.
            # Nothing was attempted against the device; safe to retry.
            raise ApiError(503, code, err_str)
        if getattr(e, "timed_out", False):
            # UNKNOWN OUTCOME, not guaranteed failure — the frontend should
            # offer "Verify / Reconcile" (re-issuing this same request is
            # safe and idempotent), not a plain "failed, try again". Because
            # the outer timeout now exceeds the Collector's own worst-case
            # budget, this should only fire when no response arrived at all,
            # not as a race against a real Collector-side answer.
            raise ApiError(503, "DEVICE_COMMAND_TIMEOUT", err_str)
        if "already exists" in err_str or "state" in err_str or "expected RESERVED" in err_str:
            raise ApiError(409, "ENROLLMENT_CONFLICT", err_str)
        raise ApiError(503, "DEVICE_UNAVAILABLE", err_str)

    return {
        "enrollment_id": enrollment_id,
        "status": res.get("status", "TERMINAL_ACCOUNT_CREATED"),
        "action": "create-terminal-account",
        "operator": payload.operator,
        "reconciled": res.get("reconciled", False),
    }


@router.post(
    "/api/v1/enrollments/{enrollment_id}/start-fingerprint-enrollment",
    response_model=EnrollmentTransitionResult,
    dependencies=[
        Depends(enrollment_mutate),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def start_fingerprint(
    enrollment_id: int,
    payload: TransitionRequest,
    cfg: Config = Depends(get_cfg),
):
    return start_fingerprint_enrollment(cfg, enrollment_id, payload.operator, payload.notes)


@router.post(
    "/api/v1/enrollments/{enrollment_id}/confirm-fingerprint",
    response_model=EnrollmentTransitionResult,
    dependencies=[
        Depends(enrollment_mutate),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def confirm_fingerprint(
    enrollment_id: int,
    payload: TransitionRequest,
    cfg: Config = Depends(get_cfg),
):
    return confirm_fingerprint_enrolled(cfg, enrollment_id, payload.operator, payload.notes)


@router.post(
    "/api/v1/enrollments/{enrollment_id}/start-controlled-scan",
    response_model=EnrollmentTransitionResult,
    dependencies=[
        Depends(enrollment_mutate),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def start_scan_window(
    enrollment_id: int,
    payload: TransitionRequest,
    cfg: Config = Depends(get_cfg),
):
    return start_controlled_scan_window(cfg, enrollment_id, payload.operator)


@router.post(
    "/api/v1/enrollments/{enrollment_id}/confirm-controlled-scan",
    response_model=EnrollmentTransitionResult,
    dependencies=[
        Depends(enrollment_mutate),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def confirm_scan(
    enrollment_id: int,
    payload: ScanConfirmationRequest,
    cfg: Config = Depends(get_cfg),
):
    return confirm_controlled_scan(cfg, enrollment_id, payload.operator, None)


@router.post(
    "/api/v1/enrollments/{enrollment_id}/mark-ready-for-mapping",
    response_model=EnrollmentTransitionResult,
    dependencies=[
        Depends(enrollment_mutate),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def mark_ready(
    enrollment_id: int,
    payload: TransitionRequest,
    cfg: Config = Depends(get_cfg),
):
    return mark_ready_for_mapping(cfg, enrollment_id, payload.operator, payload.notes)


@router.post(
    "/api/v1/enrollments/{enrollment_id}/cancel",
    response_model=EnrollmentTransitionResult,
    dependencies=[
        Depends(enrollment_mutate),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def cancel(
    enrollment_id: int,
    payload: TransitionRequest,
    cfg: Config = Depends(get_cfg),
):
    return cancel_enrollment(cfg, enrollment_id, payload.operator, payload.notes)
