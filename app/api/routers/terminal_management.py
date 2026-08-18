"""Terminal Management endpoints — physical ZEM560 account/fingerprint
lifecycle, strictly separate from Personnel Lifecycle and Enrollment.

PromptID: ADMS-TerminalManagement-020

Read (inventory) is available to any authenticated read-capable role.
Destructive operations (fingerprint/account removal) are ADMIN-only,
require API_WRITE_ENABLED and an active Runtime Write Session, and are
dispatched over the same DeviceCommandBus/Collector single-owner
architecture used since PromptID 014 — this router never touches pyzk.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth import ROLES_ADMIN_ONLY, ROLES_ENROLLMENT_READ
from app.api.dependencies import get_cfg, require_roles, require_write_session, require_writes
from app.api.errors import ApiError
from app.config import Config
from app.enrollment import CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS

router = APIRouter(tags=["terminal-management"])

# Reuses the terminal-account-creation timeout budget as a conservative,
# already-derived upper bound (see app.enrollment's timing-budget
# constants) rather than deriving a separate formula for these simpler,
# typically-faster single-mutation operations — deliberately generous, not
# tight, so it never causes a spurious timeout.
TERMINAL_MANAGEMENT_DEVICE_TIMEOUT_SECONDS = CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS


class TerminalInventoryItem(BaseModel):
    device_user_id: str
    uid: Optional[int] = None
    name: Optional[str] = None
    privilege: Optional[int] = None
    fingerprint_count: Optional[int] = Field(
        None, description="Number of fingerprint templates on the device for this account. "
        "null means the device could not be read (unknown, never assumed zero)."
    )


class TerminalInventoryResponse(BaseModel):
    items: List[TerminalInventoryItem]
    device_reachable: bool


class RemoveFingerprintRequest(BaseModel):
    device_id: int
    device_user_id: str
    operator: str = Field(description="explicit ADMIN identity performing the removal")
    finger_id: Optional[int] = Field(None, description="specific finger slot to remove; omit to remove all")


class RemoveAccountRequest(BaseModel):
    device_id: int
    device_user_id: str
    operator: str = Field(description="explicit ADMIN identity performing the removal")
    acknowledge_active_human: bool = Field(
        False,
        description="must be explicitly true to remove an account still linked to an ACTIVE "
        "Human's open VERIFIED mapping",
    )


class TerminalMutationResponse(BaseModel):
    device_user_id: str
    already_absent: bool


def _dispatch(action: str, params: Dict[str, Any], cfg: Config) -> Dict[str, Any]:
    from app.device_command_bus import DeviceCommandBusy, DeviceCommandError, get_command_bus

    bus = get_command_bus(cfg)
    try:
        return bus.execute(
            action,
            params,
            timeout=TERMINAL_MANAGEMENT_DEVICE_TIMEOUT_SECONDS,
            dedupe_key="terminal-mgmt:%s:%s" % (params.get("device_id"), params.get("device_user_id")),
        )
    except DeviceCommandBusy as e:
        raise ApiError(409, "DEVICE_COMMAND_IN_PROGRESS", str(e))
    except DeviceCommandError as e:
        err_str = str(e)
        code = getattr(e, "error_code", None)
        if code:
            status = 409 if code in ("ACTIVE_HUMAN_PROTECTION", "TERMINAL_IDENTITY_CONFLICT") else 503
            if code == "TERMINAL_ACCOUNT_NOT_FOUND":
                status = 404
            raise ApiError(status, code, err_str)
        if getattr(e, "timed_out", False):
            raise ApiError(503, "DEVICE_COMMAND_TIMEOUT", err_str)
        raise ApiError(503, "DEVICE_UNAVAILABLE", err_str)


@router.get(
    "/api/v1/terminal-management/inventory",
    response_model=TerminalInventoryResponse,
    dependencies=[Depends(require_roles(ROLES_ENROLLMENT_READ))],
)
def get_terminal_inventory(cfg: Config = Depends(get_cfg)):
    """Read-only — no write session required. If the device cannot be
    read, device_reachable=false and items is empty; callers must never
    interpret that as 'no accounts exist'."""
    try:
        result = _dispatch("TERMINAL_INVENTORY", {"device_id": 1, "device_user_id": ""}, cfg)
    except ApiError:
        return {"items": [], "device_reachable": False}
    return {"items": result.get("items", []), "device_reachable": True}


@router.post(
    "/api/v1/terminal-management/fingerprint/remove",
    response_model=TerminalMutationResponse,
    dependencies=[
        Depends(require_roles(ROLES_ADMIN_ONLY)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def remove_fingerprint(payload: RemoveFingerprintRequest, cfg: Config = Depends(get_cfg)):
    result = _dispatch(
        "REMOVE_TERMINAL_FINGERPRINT",
        {
            "device_id": payload.device_id,
            "device_user_id": payload.device_user_id,
            "operator": payload.operator,
            "finger_id": payload.finger_id,
        },
        cfg,
    )
    return {
        "device_user_id": result["device_user_id"],
        "already_absent": result.get("already_absent", False),
    }


@router.post(
    "/api/v1/terminal-management/account/remove",
    response_model=TerminalMutationResponse,
    dependencies=[
        Depends(require_roles(ROLES_ADMIN_ONLY)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def remove_account(payload: RemoveAccountRequest, cfg: Config = Depends(get_cfg)):
    result = _dispatch(
        "REMOVE_TERMINAL_ACCOUNT",
        {
            "device_id": payload.device_id,
            "device_user_id": payload.device_user_id,
            "operator": payload.operator,
            "acknowledge_active_human": payload.acknowledge_active_human,
        },
        cfg,
    )
    return {
        "device_user_id": result["device_user_id"],
        "already_absent": result.get("already_absent", False),
    }
