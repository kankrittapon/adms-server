"""ADMS Frontend API application.

PromptID: ADMS-Frontend-F1-API-001 / ADMS-Frontend-F5-Auth-001

UI-facing HTTP API. F5 auth: DB-backed operator accounts with role-based
access (strict posture — invalid/missing token -> 401, insufficient role ->
403). /healthz stays open for the Docker healthcheck.

Security posture:
  - CORS: explicit environment-driven allowlist, never "*" with credentials.
  - Bind: LAN-only (192.168.1.248:<port>) via compose; not public Internet.
  - No raw_payload by default, no biometric data, no destructive routes.
"""

import logging
from typing import Optional

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import require_role
from app.api.errors import register_exception_handlers
from app.api.settings import ApiSettings, get_settings
from app.api.routers import (
    attendance,
    auth,
    dashboard,
    device_users,
    devices,
    enrollments,
    health,
    humans,
    mappings,
    operators,
    reference,
)

log = logging.getLogger("app.api")

APP_TITLE = "ADMS API"
APP_VERSION = "2.0.0"
APP_DESCRIPTION = (
    "ADMS (Attendance Device Management System) UI-facing API. "
    "Backend/identity foundation is 100% complete; this layer exposes stable "
    "read contracts and gated canonical workflow wrappers for the frontend. "
    "F5 auth: operator accounts with VIEWER/OPERATOR/ADMIN roles."
)

VIEWER = Depends(require_role("VIEWER"))


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

    # Public process liveness for the Docker healthcheck (no auth).
    @app.get("/healthz", tags=["system"])
    def healthz():
        return {"status": "ok"}

    # Auth + operator management (login is public; operators is admin-gated).
    app.include_router(auth.router)
    app.include_router(operators.router)

    # Read API surface — any authenticated role (VIEWER+).
    for router in (
        health.router,
        dashboard.router,
        humans.router,
        devices.router,
        device_users.router,
        attendance.router,
        mappings.router,
        enrollments.router,
        reference.router,
    ):
        app.include_router(router, dependencies=[VIEWER])

    log.info(
        "ADMS API created (write_enabled=%s, cors_origins=%s, token_ttl_hours=%s)",
        settings.write_enabled,
        settings.cors_origins,
        settings.token_ttl_hours,
    )
    return app


app = create_app()
