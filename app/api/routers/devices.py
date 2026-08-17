"""Devices read endpoints.

PromptID: ADMS-Frontend-F1-API-001 / ADMS-Frontend-I18n-RBAC-Personnel-004

Frontend-safe device registry access. Exposes metadata only — never exposes
Comm Key or administrative device credentials.
"""

from fastapi import APIRouter, Depends

from app.api import repository
from app.api.auth import ROLES_ENROLLMENT_READ
from app.api.dependencies import get_cfg, pagination, require_roles
from app.api.errors import not_found
from app.api.schemas import Device, Page
from app.config import Config

router = APIRouter(tags=["devices"])


@router.get(
    "/api/v1/devices",
    response_model=Page[Device],
    dependencies=[Depends(require_roles(ROLES_ENROLLMENT_READ))],
)
def list_devices(page: tuple = Depends(pagination), cfg: Config = Depends(get_cfg)):
    limit, offset = page
    return repository.list_devices(cfg, limit=limit, offset=offset)


@router.get(
    "/api/v1/devices/{device_id}",
    response_model=Device,
    dependencies=[Depends(require_roles(ROLES_ENROLLMENT_READ))],
)
def get_device(device_id: int, cfg: Config = Depends(get_cfg)):
    row = repository.get_device(cfg, device_id)
    if row is None:
        raise not_found("device", device_id)
    return row
