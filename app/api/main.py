"""ADMS Frontend F1 API application.

PromptID: ADMS-Frontend-F1-API-001

UI-facing HTTP API foundation. Read endpoints are always available; write
endpoints are feature-flagged OFF by default (API_WRITE_ENABLED) as a
TEMPORARY WRITE SAFETY mechanism — not final authentication (F5).

Security posture:
  - CORS: explicit environment-driven allowlist, never "*" with credentials.
  - Bind: LAN-only (192.168.1.248:<port>) via compose; not public Internet.
  - No raw_payload by default, no biometric data, no destructive routes.
"""

import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.settings import ApiSettings, get_settings
from app.api.routers import (
    attendance,
    dashboard,
    device_users,
    devices,
    enrollments,
    health,
    humans,
    mappings,
    reference,
)

log = logging.getLogger("app.api")

APP_TITLE = "ADMS API"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = (
    "ADMS (Attendance Device Management System) UI-facing API foundation (F1). "
    "Backend/identity foundation is 100% complete; this layer exposes stable "
    "read contracts and gated canonical workflow wrappers for the frontend (F2+)."
)


def create_app(settings: Optional[ApiSettings] = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title=APP_TITLE,
        version=APP_VERSION,
        description=APP_DESCRIPTION,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.state.settings = settings

    app.include_router(health.router)
    app.include_router(dashboard.router)
    app.include_router(humans.router)
    app.include_router(devices.router)
    app.include_router(device_users.router)
    app.include_router(attendance.router)
    app.include_router(mappings.router)
    app.include_router(enrollments.router)
    app.include_router(reference.router)

    log.info(
        "ADMS API created (write_enabled=%s, cors_origins=%s)",
        settings.write_enabled,
        settings.cors_origins,
    )
    return app


app = create_app()
