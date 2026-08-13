"""Health endpoints.

PromptID: ADMS-Frontend-F1-API-001

GET /healthz               — API process liveness (no dependencies).
GET /api/v1/health         — application dependency health (PostgreSQL,
                             optional MQTT, collector state summary if readable).
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from app.api import repository
from app.api.dependencies import get_cfg
from app.api.schemas import CollectorSummary, HealthCheck
from app.config import Config

router = APIRouter(tags=["health"])

_HEALTH_FILE_DEFAULT = "/tmp/collector_health.json"


def _read_collector_health() -> Optional[Dict[str, Any]]:
    """Best-effort read of the Collector health file (may be a separate container)."""
    path = os.getenv("HEALTH_FILE_PATH", _HEALTH_FILE_DEFAULT)
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@router.get("/api/v1/health", response_model=HealthCheck)
def health(cfg: Config = Depends(get_cfg)) -> HealthCheck:
    db_ok = repository.check_database(cfg)
    mqtt = repository.check_mqtt(cfg) if db_ok else None

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

    return HealthCheck(
        status="healthy" if db_ok else "degraded",
        database="HEALTHY" if db_ok else "UNREACHABLE",
        mqtt=mqtt,
        collector=collector,
        timestamp=datetime.now(timezone.utc),
    )
