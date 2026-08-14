"""Export the ADMS FastAPI OpenAPI schema for openapi-typescript codegen.

PromptID: ADMS-Frontend-Codegen-001

Deterministic, offline source of truth: app.openapi() is generated from the
FastAPI app itself (no DB/network needed at schema time). The committed
snapshot lives at frontend/openapi.json; regenerate + regenerate the TS
types with `npm run codegen:api` (frontend/package.json).

Usage:
    python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.api.main import app  # noqa: E402  (sys.path first)

OUT = ROOT / "frontend" / "openapi.json"


def main() -> None:
    spec = app.openapi()
    OUT.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(spec['paths'])} paths, {len(spec['components']['schemas'])} schemas)")


if __name__ == "__main__":
    main()
