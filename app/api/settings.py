"""F1 API settings.

PromptID: ADMS-Frontend-F1-API-001

Environment-driven settings for the UI-facing HTTP API foundation.

Security contract:
  - Write endpoints are feature-flagged OFF by default (API_WRITE_ENABLED).
    F1 ships read-only by default; writes require an explicit internal
    operator flag. This is a TEMPORARY WRITE SAFETY mechanism, NOT final
    authentication (that belongs to F5).
  - CORS is an explicit environment-driven allowlist. Unrestricted "*" with
    credentials is never used.
"""

import os
from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class ApiSettings:
    write_enabled: bool = False
    cors_origins: Tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    api_host: str = "0.0.0.0"
    api_port: int = 8081

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
        return cls(
            write_enabled=write_enabled,
            cors_origins=origins,
            api_host=os.getenv("API_HOST", "0.0.0.0"),
            api_port=int(os.getenv("API_PORT", "8081")),
        )


def get_settings() -> ApiSettings:
    return ApiSettings.from_env()
