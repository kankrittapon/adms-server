"""Human <-> Device mapping endpoints.

PromptID: ADMS-Frontend-F1-API-001 / ADMS-Frontend-I18n-RBAC-Personnel-004

Reads expose temporal mapping state. The write route wraps the canonical
app.mapping.create_verified_mapping() — it NEVER reimplements identity logic,
never does fuzzy/rank/numeric matching, and never creates automatic mappings.
The write route is gated by the interim write guard (OFF by default).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api import repository
from app.api.auth import ROLES_ADMIN_ONLY, ROLES_GENERAL_READ
from app.api.dependencies import (
    get_cfg,
    pagination,
    require_roles,
    require_write_session,
    require_writes,
)
from app.api.errors import not_found
from app.api.schemas import Mapping, MappingEligibility, Page
from app.config import Config
from app.mapping import create_verified_mapping

router = APIRouter(tags=["mappings"])


@router.get(
    "/api/v1/mappings",
    response_model=Page[Mapping],
    dependencies=[Depends(require_roles(ROLES_GENERAL_READ))],
)
def list_mappings(
    employee_id: Optional[str] = Query(None),
    device_user_pk: Optional[int] = Query(None),
    mapping_status: Optional[str] = Query(None),
    page: tuple = Depends(pagination),
    cfg: Config = Depends(get_cfg),
):
    limit, offset = page
    return repository.list_mappings(
        cfg,
        limit=limit,
        offset=offset,
        employee_id=employee_id,
        device_user_pk=device_user_pk,
        mapping_status=mapping_status,
    )


@router.get(
    "/api/v1/mappings/eligibility",
    response_model=MappingEligibility,
    dependencies=[Depends(require_roles(ROLES_ADMIN_ONLY))],
)
def mapping_eligibility(cfg: Config = Depends(get_cfg)):
    """READY_FOR_MAPPING enrollments with controlled-scan evidence.

    F4: feeds the ADMIN mapping-creation form (POST /api/v1/mappings).
    Read-only; only enrollments whose device user has no overlapping VERIFIED
    mapping are offered, so a duplicate mapping can never be proposed.
    Registered before /{mapping_id} so FastAPI does not shadow it.
    """
    items = repository.mapping_eligibility(cfg)
    return {"items": items, "count": len(items)}


@router.get(
    "/api/v1/mappings/{mapping_id}",
    response_model=Mapping,
    dependencies=[Depends(require_roles(ROLES_GENERAL_READ))],
)
def get_mapping(mapping_id: int, cfg: Config = Depends(get_cfg)):
    row = repository.get_mapping(cfg, mapping_id)
    if row is None:
        raise not_found("mapping", mapping_id)
    return row


class CreateMappingRequest(BaseModel):
    """ADMS-FullEnrollment-E2E-Closure-017: employee_id, device_user_pk, and
    controlled_attendance_id are all derived server-side from the
    enrollment row (see app.mapping.create_verified_mapping) — the ADMIN
    confirming Step 6 supplies only which enrollment and why. This is a
    breaking API change (previously required 4 caller-supplied identity
    fields); every caller in this repository (Mappings.tsx, tests) is
    updated in the same change. It permanently closes the "frontend
    reconstructs security-critical mapping evidence from stale/nullable
    data" bug class that produced 422s at Step 6.
    """

    enrollment_id: int = Field(description="READY_FOR_MAPPING enrollment id")
    verified_by: str = Field(description="explicit operator/owner identity")
    verification_note: str = Field(description="audit note referencing pilot evidence")


class CreateMappingResponse(BaseModel):
    mapping_id: int
    employee_id: str
    device_user_pk: int
    mapping_status: str
    verification_method: str
    valid_from: str
    valid_to: Optional[str] = None
    verified_at: str
    already_completed: bool = Field(
        default=False,
        description="True when this call found the enrollment already RETIRED "
        "with an existing VERIFIED mapping and returned it idempotently, "
        "rather than creating a new one.",
    )


@router.post(
    "/api/v1/mappings",
    response_model=CreateMappingResponse,
    status_code=201,
    dependencies=[
        Depends(require_roles(ROLES_ADMIN_ONLY)),
        Depends(require_writes),
        Depends(require_write_session),
    ],
)
def create_mapping(payload: CreateMappingRequest, cfg: Config = Depends(get_cfg)):
    result = create_verified_mapping(
        cfg,
        enrollment_id=payload.enrollment_id,
        verified_by=payload.verified_by,
        verification_note=payload.verification_note,
    )
    return {
        "mapping_id": result["mapping_id"],
        "employee_id": result["employee_id"],
        "device_user_pk": result["device_user_pk"],
        "mapping_status": result["mapping_status"],
        "verification_method": result["verification_method"],
        "valid_from": result["valid_from"].isoformat(),
        "valid_to": result.get("valid_to").isoformat() if result.get("valid_to") else None,
        "verified_at": result["verified_at"].isoformat(),
        "already_completed": result.get("already_completed", False),
    }
