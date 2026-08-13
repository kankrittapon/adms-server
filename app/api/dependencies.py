"""Shared FastAPI dependencies.

PromptID: ADMS-Frontend-F1-API-001
"""

from typing import Optional

from fastapi import Depends, Query, Request

from app.api.errors import ApiError
from app.api.settings import ApiSettings, get_settings
from app.config import Config

# Fixed upper bound for list endpoints — never unbounded.
MAX_PAGE_LIMIT = 200
DEFAULT_PAGE_LIMIT = 50


def get_cfg() -> Config:
    return Config.from_env()


def require_writes(request: Request) -> None:
    """Interim write guard. F1 ships writes OFF by default.

    Reads the effective settings from app.state so tests can override and so
    the running process honours the env at startup. This is a TEMPORARY WRITE
    SAFETY mechanism, NOT final authentication.
    """
    settings: ApiSettings = request.app.state.settings
    if not settings.write_enabled:
        raise ApiError(
            403,
            "WRITE_DISABLED",
            "API write endpoints are disabled by default "
            "(set API_WRITE_ENABLED=true to enable).",
        )


def pagination(
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
) -> tuple:
    return limit, offset
