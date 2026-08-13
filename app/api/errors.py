"""Consistent API error model.

PromptID: ADMS-Frontend-F1-API-001

Every error response uses the same envelope:

    {"error": {"code": "...", "message": "..."}}

Status codes:
  400  validation / domain error
  403  interim write guard (API_WRITE_ENABLED=false)
  404  missing resource
  409  state conflict / duplicate reservation / mapping conflict
  422  request validation (FastAPI RequestValidationError)
  500  unexpected internal error

Never leak DB passwords, stack traces, raw SQL, or secrets.
"""

from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Domain-level API error with a stable machine-readable code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        super().__init__(message)


def not_found(resource: str, identifier: Any) -> ApiError:
    return ApiError(404, "NOT_FOUND", f"{resource} {identifier!r} not found")


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_body(
                "VALIDATION_ERROR",
                "request validation failed: " + str(exc.errors())[:500],
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log full traceback server-side; return a safe generic envelope.
        import logging

        logging.getLogger("app.api").exception("unhandled API error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_error_body("INTERNAL_ERROR", "internal server error"),
        )
