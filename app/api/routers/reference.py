"""Reference metadata endpoints.

PromptID: ADMS-Frontend-F1-API-001

GET /api/v1/reference/ranks returns the canonical RTN rank table directly
from app/rtn_ranks.py — rank data is never duplicated in the API layer.
"""

from typing import List

from fastapi import APIRouter

from app.api.schemas import RankReference
from app.rtn_ranks import all_canonical_ranks

router = APIRouter(tags=["reference"])


@router.get("/api/v1/reference/ranks", response_model=List[RankReference])
def list_ranks() -> List[RankReference]:
    return [RankReference(**r) for r in all_canonical_ranks()]
