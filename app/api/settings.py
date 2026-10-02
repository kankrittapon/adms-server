"""API settings.

PromptID: ADMS-Frontend-F1-API-001 / ADMS-Frontend-F5-Auth-001

Environment-driven settings for the UI-facing HTTP API.

Security contract:
  - F5 auth: DB-backed operator accounts (strict posture). The API rejects
    requests without a valid Bearer token (401) and requests with insufficient
    role (403). /healthz remains open for the Docker healthcheck.
  - Write endpoints are feature-flagged OFF by default (API_WRITE_ENABLED)
    as defense-in-depth on top of role authorization.
  - CORS is an explicit environment-driven allowlist. Unrestricted "*" with
    credentials is never used.
"""

import os
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ApiSettings:
    write_enabled: bool = False
    cors_origins: Tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    api_host: str = "0.0.0.0"
    api_port: int = 8081
    token_ttl_hours: int = 12
    rate_limit_enabled: bool = True
    login_rate_per_min: int = 5
    global_rate_per_min: int = 600
    # Layer 2 (Work Session) on/off. Production runs with it off: all edits,
    # fingerprint enrollment included, are allowed any time; attendance is
    # instead limited by the scan window (attendance_policy.scan_window).
    work_session_required: bool = True

    @classmethod
    def from_env(cls) -> "ApiSettings":
        write_enabled = os.getenv("API_WRITE_ENABLED", "false").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        origins = tuple(
            o.strip()
            for o in os.getenv(
                "API_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if o.strip()
        )
        rate_enabled = os.getenv("API_RATE_LIMIT_ENABLED", "true").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        return cls(
            write_enabled=write_enabled,
            cors_origins=origins,
            api_host=os.getenv("API_HOST", "0.0.0.0"),
            api_port=int(os.getenv("API_PORT", "8081")),
            token_ttl_hours=int(os.getenv("API_TOKEN_TTL_HOURS", "12")),
            rate_limit_enabled=rate_enabled,
            login_rate_per_min=int(os.getenv("API_LOGIN_RATE_PER_MIN", "5")),
            global_rate_per_min=int(os.getenv("API_GLOBAL_RATE_PER_MIN", "600")),
            work_session_required=os.getenv("API_WORK_SESSION_REQUIRED", "true").strip().lower()
            in ("1", "true", "yes", "on"),
        )


def get_settings() -> ApiSettings:
    return ApiSettings.from_env()
