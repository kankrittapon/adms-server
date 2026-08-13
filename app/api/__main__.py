"""Entrypoint: python -m app.api

Runs the ADMS F1 API with uvicorn. Host/port are env-driven
(API_HOST / API_PORT), LAN-only bind is set by docker-compose.
"""

import os

import uvicorn

from app.api.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.api.main:app",
        host=os.getenv("API_HOST", settings.api_host),
        port=settings.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
