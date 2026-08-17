"""Dashboard summary endpoint.

PromptID: ADMS-Frontend-F1-API-001 / ADMS-Frontend-I18n-RBAC-Personnel-004

One efficient aggregation query for F2/F3 dashboard views.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from app.api import repository
from app.api.auth import ROLES_GENERAL_READ
from app.api.dependencies import get_cfg, require_roles
from app.api.routers.health import _read_collector_health
from app.api.schemas import CollectorSummary, DashboardSummary
from app.config import Config

router = APIRouter(tags=["dashboard"])


@router.get(
    "/api/v1/dashboard/summary",
    response_model=DashboardSummary,
    dependencies=[Depends(require_roles(ROLES_GENERAL_READ))],
)
def dashboard_summary(cfg: Config = Depends(get_cfg)) -> DashboardSummary:
    data = repository.dashboard_summary(cfg)
    collector_raw = _read_collector_health()
    collector = None
    if collector_raw:
        collector = CollectorSummary(
            state=collector_raw.get("state"),
            device_connected=collector_raw.get("device_connected"),
            db_status=collector_raw.get("db_status"),
            mqtt_status=collector_raw.get("mqtt_status"),
            loop_alive=collector_raw.get("loop_alive"),
            updated_at=collector_raw.get("updated_at"),
        )
    data["collector"] = collector
    return DashboardSummary(**data)
