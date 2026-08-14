"""Drift guard for the frontend OpenAPI codegen contract.

PromptID: ADMS-Frontend-Codegen-001

The frontend TS types are generated from the committed snapshot at
frontend/openapi.json (via openapi-typescript — `npm run codegen:api`).
This test fails when the backend API contract changes without regenerating
the snapshot, so the generated frontend types can never silently drift.

Regenerate after any backend contract change:
    python scripts/export_openapi.py
    (cd frontend && npm run codegen:api)
"""

import json
from pathlib import Path

from app.api.main import app

SNAPSHOT = Path(__file__).resolve().parent.parent / "frontend" / "openapi.json"


def _normalize(spec: dict) -> dict:
    """Deterministic comparison: sort paths/schemas keys recursively."""
    if isinstance(spec, dict):
        return {k: _normalize(spec[k]) for k in sorted(spec)}
    if isinstance(spec, list):
        return [_normalize(v) for v in spec]
    return spec


def test_openapi_snapshot_is_current() -> None:
    assert SNAPSHOT.exists(), (
        f"missing {SNAPSHOT} — run `python scripts/export_openapi.py` first"
    )
    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    live = app.openapi()
    assert _normalize(committed) == _normalize(live), (
        "frontend/openapi.json is stale: the API contract changed without "
        "regenerating the codegen snapshot. Run "
        "`python scripts/export_openapi.py` then `cd frontend && npm run codegen:api` "
        "and commit both files."
    )


def test_openapi_snapshot_shape() -> None:
    """Sanity: snapshot exposes the expected core contract surface."""
    spec = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    paths = spec["paths"]
    schemas = spec["components"]["schemas"]

    for p in (
        "/api/v1/health",
        "/api/v1/dashboard/summary",
        "/api/v1/humans",
        "/api/v1/devices",
        "/api/v1/device-users",
        "/api/v1/attendance",
        "/api/v1/mappings",
        "/api/v1/enrollments",
        "/api/v1/reference/ranks",
    ):
        assert p in paths, f"missing path {p} in OpenAPI snapshot"

    for s in (
        "Human",
        "Device",
        "DeviceUser",
        "Attendance",
        "Mapping",
        "Enrollment",
        "DashboardSummary",
        "RankReference",
        "Page_Human_",
    ):
        assert s in schemas, f"missing schema {s} in OpenAPI snapshot"
