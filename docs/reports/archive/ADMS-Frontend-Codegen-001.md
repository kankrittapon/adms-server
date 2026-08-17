# ADMS — OpenAPI TypeScript Codegen — Completion Report

**PromptID:** `ADMS-Frontend-Codegen-001`
**Status:** COMPLETE (owner approved plan → implemented → deployed → live-verified)
**Date:** 2026-08-14

## AGENT / TOOLING
- agent/model: Freebuff (Buffy) — deepseek-v4-flash · IDE: Freebuff chat (TELEPHONE) · pty-mcp: USED · temporary SSH transport scripts: 0

## GOAL
Replace the hand-maintained `frontend/src/api/types.ts` model types with types
generated from the FastAPI OpenAPI schema, so the frontend/API contract can
never silently drift.

## WHAT WAS DELIVERED

| Item | Detail |
|---|---|
| **Source of truth** | `scripts/export_openapi.py` dumps `app.openapi()` → committed snapshot `frontend/openapi.json` (37 paths, 44 schemas). Deterministic: generated from the app itself, no DB/network needed. |
| **Codegen** | `openapi-typescript@7.13.0` (devDependency) → `frontend/src/api/generated.ts` with typed `paths` + `components`. |
| **Integration** | `frontend/src/api/types.ts` now re-exports `components["schemas"][…]` under the same stable names (`Human`, `Attendance`, `Mapping`, …). Only types absent from the schema stay local: generic `Page<T>`, `ApiErrorBody`, `Healthz`, inline write/transition dicts (`EnrollmentNextActions`, `EnrollmentReserveResult`, `EnrollmentTransitionResult`). `client.ts` + all pages compile unchanged (one import fix: `auth.tsx` pulls `MeResponse` from `types`). |
| **Drift guard** | New `tests/test_openapi_contract.py` (2 tests): committed snapshot must equal current `app.openapi()`; core path/schema surface sanity. Any backend contract change without regeneration fails the suite. |
| **npm script** | `npm run codegen:api` = export snapshot + regenerate types. Generated file is committed → `npm ci && npm run build` stays hermetic (no python in Docker). |

## BACKEND CONTRACT IMPROVEMENT
`HealthCheck.collector` was declared `Optional[Dict[str, Any]]` (untyped) in
`app/api/schemas.py` while the health router already builds a
`CollectorSummary`. Typed it as `Optional[CollectorSummary]` (class reordered
above `HealthCheck`). This is a strict contract improvement — response shape
unchanged, OpenAPI now precise, and the generated frontend type is
`components["schemas"]["CollectorSummary"] | null` instead of
`{ [key: string]: unknown }`.

## TESTS
- Full suite: **385 passed + 18 subtests / 0 failed** (baseline 383 + 2 new drift-guard tests)
- Frontend: `tsc --noEmit` PASS · `vite build` PASS
- No tests removed or disabled.

## DEPLOYMENT (ai-brain)
- Pushed `dc90125`; synced `git pull --ff-only` (75644ad → dc90125).
- Rebuilt ONLY `adms_api` (schema change) + `adms_web` (frontend + lockfile): `docker compose up -d --build --no-deps api web`.
- PostgreSQL / MQTT / Polling Collector untouched (23–39 h up, healthy).

## LIVE VERIFICATION
- Live `GET /openapi.json` (50,655 B) **matches committed snapshot exactly** (37 paths, 44 schemas).
- `GET /healthz` → `{"status":"ok"}`; web `http://192.168.1.248:8082/` → 200.
- Authenticated `GET /api/v1/health` → `status: healthy`, `database: HEALTHY`, `mqtt: HEALTHY`, typed `collector` serialized (temp VIEWER token issued via canonical insert, **revoked after — 0 active tokens**).
- Containers: `adms_web`/`adms_api` (healthy, restarts 0), `adms_zkteco_listener` (healthy, 23 h), `adms_mqtt`, `adms_postgres` (healthy).

## SAFETY
- No DB/schema migration · no device write · no identity/mapping/scope change · GET side-effect free · write guard intact · Backend Foundation **REMAINS 100% COMPLETE**.

## LIMITATIONS / NOTES
- `openapi-typescript` is a frontend devDependency only; the API container does not need it.
- The snapshot + generated file must both be committed together whenever the API contract changes (drift-guard test enforces the snapshot; `codegen:api` regenerates both).
- SSE stream endpoint (`/api/v1/stream/attendance`) is typed in `paths` as a plain 200 response (SSE payloads are not JSON-typed); the frontend stream hook consumes it untyped by design.

## FINAL
- repository verified: **YES** · database modified: NO · schema modified: NO · device modified: NO · Human Master destructive deletion: NO
- **OpenAPI codegen: 100% COMPLETE** · tests: **385/385** (+18 subtests) · runtime: HEALTHY · safe to proceed: **YES** · blockers: NONE
