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

from app.api.auth import authenticate_operator, hash_password, issue_token, verify_password
from app.api.dependencies import OperatorContext, get_cfg, rate_limit, require_auth
from app.api.errors import ApiError
from app.api.schemas import WriteSessionStatus
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
    write_enabled: bool = False
    write_session: Optional[WriteSessionStatus] = None


@router.post(
    "/api/v1/auth/login",
    response_model=LoginResponse,
    dependencies=[Depends(rate_limit("login"))],
)
def login(payload: LoginRequest, cfg: Config = Depends(get_cfg), settings: ApiSettings = Depends(get_settings)):
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            operator = authenticate_operator(cur, payload.username, payload.password)
            if operator is None:
                # Audit the failure (username only — never the password).
                log_sync_event(
                    cfg,
                    "AUTH_LOGIN_FAILED",
                    "username=%s (failed login)" % payload.username,
                )
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
def me(
    cfg: Config = Depends(get_cfg),
    ctx: OperatorContext = Depends(require_auth),
    settings: ApiSettings = Depends(get_settings),
):
    from app.write_session import get_write_session_status

    write_session = get_write_session_status(cfg)
    return MeResponse(
        operator_id=ctx.operator_id,
        username=ctx.username,
        display_name=ctx.display_name,
        role=ctx.role,
        write_enabled=settings.write_enabled,
        write_session=WriteSessionStatus(**write_session),
    )


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class ChangePasswordResponse(BaseModel):
    changed: bool
    other_tokens_revoked: int


@router.post("/api/v1/auth/change-password", response_model=ChangePasswordResponse)
def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    cfg: Config = Depends(get_cfg),
    ctx: OperatorContext = Depends(require_auth),
):
    """Operator changes their own password; all OTHER sessions are revoked.

    The presenting token stays valid (its hash differs from the revoked set
    only if it belongs to this operator — we revoke tokens of this operator
    except the presented one). Logged as AUTH_PASSWORD_CHANGE.
    """
    auth_header = request.headers.get("authorization", "")
    parts = auth_header.split(" ", 1)
    import hashlib

    current_token_hash = None
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        current_token_hash = hashlib.sha256(parts[1].strip().encode("utf-8")).hexdigest()
    new_hash = hash_password(payload.new_password)
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM operators WHERE operator_id = %s AND active = true;",
                (ctx.operator_id,),
            )
            row = cur.fetchone()
            if row is None or not verify_password(payload.current_password, row[0]):
                raise ApiError(401, "UNAUTHORIZED", "current password is incorrect")
            cur.execute(
                "UPDATE operators SET password_hash = %s, updated_at = now() "
                "WHERE operator_id = %s;",
                (new_hash, ctx.operator_id),
            )
            if current_token_hash is not None:
                cur.execute(
                    "UPDATE api_tokens SET revoked_at = now() "
                    "WHERE operator_id = %s AND token_hash <> %s AND revoked_at IS NULL;",
                    (ctx.operator_id, current_token_hash),
                )
            else:
                cur.execute(
                    "UPDATE api_tokens SET revoked_at = now() "
                    "WHERE operator_id = %s AND revoked_at IS NULL;",
                    (ctx.operator_id,),
                )
            revoked = cur.rowcount
            conn.commit()
    log_sync_event(
        cfg,
        "AUTH_PASSWORD_CHANGE",
        "operator=%s other_tokens_revoked=%d" % (ctx.username, revoked),
    )
    return ChangePasswordResponse(changed=True, other_tokens_revoked=revoked)
