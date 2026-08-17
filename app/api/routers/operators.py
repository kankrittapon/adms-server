"""Operator management endpoints (F5, admin-only).

PromptID: ADMS-Frontend-F5-Auth-001

GET  /api/v1/operators          -> list operators (admin)
POST /api/v1/operators          -> create operator (admin; password required)
POST /api/v1/operators/{id}/toggle-active -> activate/deactivate (admin)

Passwords are hashed with PBKDF2-SHA256 (app.api.auth.hash_password) and
never returned by any endpoint.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth import ROLES_ADMIN_ONLY, VALID_ROLES, hash_password
from app.api.dependencies import (
    OperatorContext,
    get_cfg,
    require_roles,
    require_write_session,
    require_writes,
)
from app.api.errors import ApiError, not_found
from app.config import Config
from app.db import get_db_connection, log_sync_event

router = APIRouter(tags=["operators"])

admin_only = require_roles(ROLES_ADMIN_ONLY)


class CreateOperatorRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=256)
    role: str = Field(default="VIEWER")


class OperatorOut(BaseModel):
    operator_id: int
    username: str
    display_name: str
    role: str
    active: bool
    created_at: str
    updated_at: str


class ToggleActiveRequest(BaseModel):
    active: bool


class ToggleActiveResponse(BaseModel):
    operator_id: int
    username: str
    active: bool


@router.get("/api/v1/operators", response_model=list[OperatorOut], dependencies=[Depends(admin_only)])
def list_operators(cfg: Config = Depends(get_cfg)):
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT operator_id, username, display_name, role, active, "
                "created_at, updated_at FROM operators ORDER BY operator_id;"
            )
            rows = cur.fetchall()
    return [
        OperatorOut(
            operator_id=r[0], username=r[1], display_name=r[2], role=r[3],
            active=r[4], created_at=r[5].isoformat(), updated_at=r[6].isoformat(),
        )
        for r in rows
    ]


@router.post(
    "/api/v1/operators",
    response_model=OperatorOut,
    status_code=201,
    dependencies=[Depends(admin_only), Depends(require_writes), Depends(require_write_session)],
)
def create_operator(
    payload: CreateOperatorRequest,
    ctx: OperatorContext = Depends(admin_only),
    cfg: Config = Depends(get_cfg),
):
    role = payload.role.upper()
    if role not in VALID_ROLES:
        raise ApiError(422, "VALIDATION_ERROR", "invalid role: %s" % payload.role)
    if role != "ADMIN" and ctx.role != "ADMIN":
        # Only an ADMIN may create any operator; this branch is defensive.
        raise ApiError(403, "FORBIDDEN", "requires ADMIN")
    password_hash = hash_password(payload.password)
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO operators (username, display_name, role, password_hash) "
                    "VALUES (%s, %s, %s, %s) RETURNING operator_id, created_at, updated_at;",
                    (payload.username, payload.display_name, role, password_hash),
                )
                row = cur.fetchone()
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise ApiError(409, "OPERATOR_CONFLICT", "username already exists or invalid: %s" % payload.username)
    log_sync_event(cfg, "OPERATOR_CREATED",
                   "operator=%s role=%s created_by=%s" % (payload.username, role, ctx.username))
    return OperatorOut(
        operator_id=row[0], username=payload.username, display_name=payload.display_name,
        role=role, active=True, created_at=row[1].isoformat(), updated_at=row[2].isoformat(),
    )


@router.post(
    "/api/v1/operators/{operator_id}/toggle-active",
    response_model=ToggleActiveResponse,
    dependencies=[Depends(admin_only), Depends(require_writes), Depends(require_write_session)],
)
def toggle_active(
    operator_id: int,
    payload: ToggleActiveRequest,
    ctx: OperatorContext = Depends(admin_only),
    cfg: Config = Depends(get_cfg),
):
    if operator_id == ctx.operator_id and not payload.active:
        raise ApiError(422, "VALIDATION_ERROR", "cannot deactivate yourself")
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE operators SET active = %s, updated_at = now() "
                "WHERE operator_id = %s RETURNING username;",
                (payload.active, operator_id),
            )
            row = cur.fetchone()
            if row is None:
                raise not_found("operator", operator_id)
            conn.commit()
    log_sync_event(cfg, "OPERATOR_TOGGLE",
                   "operator=%s active=%s by=%s" % (row[0], payload.active, ctx.username))
    return ToggleActiveResponse(operator_id=operator_id, username=row[0], active=payload.active)
