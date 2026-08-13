"""Authentication endpoints (F5).

PromptID: ADMS-Frontend-F5-Auth-001

POST /api/v1/auth/login    -> {token, token_type, role, expires_at, operator}
POST /api/v1/auth/logout   -> revokes the presented token (idempotent)
GET  /api/v1/auth/me       -> current operator context

Tokens are opaque, stored only as SHA-256 hashes, and expire after
API_TOKEN_TTL_HOURS (default 12h). Revocation is reversible (revoked_at).
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.auth import authenticate_operator, issue_token
from app.api.dependencies import OperatorContext, get_cfg, require_auth
from app.api.errors import ApiError
from app.api.settings import ApiSettings, get_settings
from app.config import Config
from app.db import get_db_connection, log_sync_event

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    role: str
    expires_at: datetime
    operator_id: int
    username: str
    display_name: str


class LogoutResponse(BaseModel):
    revoked: bool


class MeResponse(BaseModel):
    operator_id: int
    username: str
    display_name: str
    role: str


@router.post("/api/v1/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, cfg: Config = Depends(get_cfg), settings: ApiSettings = Depends(get_settings)):
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            operator = authenticate_operator(cur, payload.username, payload.password)
            if operator is None:
                raise ApiError(401, "UNAUTHORIZED", "invalid username or password")

            token, expires_at = issue_token(operator["operator_id"], operator["role"], settings.token_ttl_hours)
            import hashlib

            cur.execute(
                "INSERT INTO api_tokens (operator_id, token_hash, role, expires_at) "
                "VALUES (%s, %s, %s, %s);",
                (operator["operator_id"], hashlib.sha256(token.encode()).hexdigest(),
                 operator["role"], expires_at),
            )
            conn.commit()

    log_sync_event(cfg, "AUTH_LOGIN", "operator=%s role=%s" % (operator["username"], operator["role"]))
    return LoginResponse(
        token=token,
        role=operator["role"],
        expires_at=expires_at,
        operator_id=operator["operator_id"],
        username=operator["username"],
        display_name=operator["display_name"],
    )


@router.post("/api/v1/auth/logout", response_model=LogoutResponse)
def logout(request: Request, cfg: Config = Depends(get_cfg), ctx: OperatorContext = Depends(require_auth)):
    auth_header = request.headers.get("authorization", "")
    token = auth_header.split(" ", 1)[1].strip()
    import hashlib

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE api_tokens SET revoked_at = now() "
                "WHERE token_hash = %s AND revoked_at IS NULL;",
                (token_hash,),
            )
            conn.commit()
    log_sync_event(cfg, "AUTH_LOGOUT", "operator=%s" % ctx.username)
    return LogoutResponse(revoked=True)


@router.get("/api/v1/auth/me", response_model=MeResponse)
def me(ctx: OperatorContext = Depends(require_auth)):
    return MeResponse(
        operator_id=ctx.operator_id,
        username=ctx.username,
        display_name=ctx.display_name,
        role=ctx.role,
    )
