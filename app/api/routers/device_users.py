"""Device user read endpoints.

PromptID: ADMS-Frontend-F1-API-001

Exposes lifecycle state safely. Never exposes biometric data.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api import repository
from app.api.dependencies import get_cfg, pagination
from app.api.errors import not_found
from app.api.schemas import DeviceUser, Page
from app.config import Config

router = APIRouter(tags=["device-users"])


@router.get("/api/v1/device-users", response_model=Page[DeviceUser])
def list_device_users(
    device_id: Optional[int] = Query(None),
    active: Optional[bool] = Query(None),
    page: tuple = Depends(pagination),
    cfg: Config = Depends(get_cfg),
):
    limit, offset = page
    return repository.list_device_users(
        cfg, limit=limit, offset=offset, device_id=device_id, active=active
    )


@router.get("/api/v1/device-users/{device_user_pk}", response_model=DeviceUser)
def get_device_user(device_user_pk: int, cfg: Config = Depends(get_cfg)):
    row = repository.get_device_user(cfg, device_user_pk)
    if row is None:
        raise not_found("device-user", device_user_pk)
    return row
