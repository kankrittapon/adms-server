"""Shared FastAPI dependencies.

PromptID: ADMS-Frontend-F1-API-001 / ADMS-Frontend-F5-Auth-001
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Query, Request

from app.api.auth import role_required
from app.api.errors import ApiError
from app.api.settings import ApiSettings, get_settings
from app.config import Config
from app.db import get_db_connection

# Fixed upper bound for list endpoints — never unbounded.
MAX_PAGE_LIMIT = 200
DEFAULT_PAGE_LIMIT = 50


class OperatorContext:
    """Authenticated operator bound to the request."""

    def __init__(self, operator_id: int, username: str, display_name: str, role: str):
        self.operator_id = operator_id
        self.username = username
        self.display_name = display_name
        self.role = role


def get_cfg() -> Config:
    return Config.from_env()


def _load_token_context(request: Request) -> Optional[OperatorContext]:
    """Resolves the Authorization: Bearer token to an OperatorContext, or None."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    import hashlib

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cfg = request.app.state.cfg if hasattr(request.app.state, "cfg") else get_cfg()
    try:
        with get_db_connection(cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT t.token_hash, t.role, t.expires_at, t.revoked_at, "
                    "o.operator_id, o.username, o.display_name, o.active "
                    "FROM api_tokens t JOIN operators o ON o.operator_id = t.operator_id "
                    "WHERE t.token_hash = %s;",
                    (token_hash,),
                )
                row = cur.fetchone()
                # Update last_used_at opportunistically (non-fatal).
                try:
                    cur.execute(
                        "UPDATE api_tokens SET last_used_at = now() "
                        "WHERE token_hash = %s AND revoked_at IS NULL;",
                        (token_hash,),
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
    except Exception:
        return None

    from app.api.auth import verify_token_row

    ctx = verify_token_row(row)
    if ctx is None:
        return None
    return OperatorContext(**ctx)


def require_auth(request: Request) -> OperatorContext:
    """Requires a valid Bearer token (any role). Raises 401 when absent/invalid."""
    ctx = _load_token_context(request)
    if ctx is None:
        raise ApiError(401, "UNAUTHORIZED", "missing or invalid bearer token")
    return ctx


def require_role(min_role: str):
    """Dependency factory: requires an authenticated operator with role >= min_role."""

    def dependency(request: Request, ctx: OperatorContext = Depends(require_auth)) -> OperatorContext:
        if not role_required(ctx.role, min_role):
            raise ApiError(403, "FORBIDDEN", "requires role %s or higher" % min_role)
        return ctx

    return dependency


def require_writes(request: Request) -> None:
    """Interim write guard (defense in depth on top of role auth).

    F1 ships writes OFF by default. Enabling writes is a deliberate operator
    decision (API_WRITE_ENABLED=true) — separate from role authorization.
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
