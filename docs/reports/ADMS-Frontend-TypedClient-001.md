# ADMS — Typed API Client Codegen — Completion Report

**PromptID:** `ADMS-Frontend-Codegen-001` (continuation — typed client phase)
**Status:** COMPLETE (owner approved plan → implemented → deployed → live-verified)
**Date:** 2026-08-14

## AGENT / TOOLING
- agent/model: Freebuff (Buffy) — deepseek-v4-flash · IDE: Freebuff chat (TELEPHONE) · pty-mcp: USED · temporary SSH transport scripts: 0

## GOAL
Extend the schema-level codegen (previous phase) so the **client call signatures**
themselves — query params, request bodies, response types — are derived from the
OpenAPI `operations` types instead of being hand-maintained. After this phase,
`client.ts` cannot drift from the API: any backend contract change fails `tsc` at
the call sites, not just the drift-guard snapshot test.

## WHAT WAS DELIVERED

| Item | Detail |
|---|---|
| **Backend contract completion** | 4 response models added to `app/api/schemas.py` — `EnrollmentNextActions`, `EnrollmentReserveResult`, `EnrollmentTransitionResult`, `EventTypesResponse` — and `response_model=` declared on the previously-inline routes: `next-actions`, `reserve`, the 6 enrollment transitions (`start-fingerprint-enrollment`, `confirm-fingerprint`, `start-controlled-scan`, `confirm-controlled-scan`, `mark-ready-for-mapping`, `cancel`), `audit/event-types`, and `/healthz`. Behavior identical; OpenAPI no longer `unknown` for these routes. |
| **Derivation helpers** | `types.ts` gains `QueryOf<OpId>` (query params), `BodyOf<OpId>` (request body JSON), `JsonResponse<OpId, Code>` (response JSON) over the generated `operations` interface, plus an exported `Operations` type. The 4 local hand-written types (`EnrollmentNextActions`, `EnrollmentReserveResult`, `EnrollmentTransitionResult`, `Healthz`) are deleted and now re-derived from schemas. |
| **client.ts rewrite** | Every method retyped against operation IDs (e.g. `humans` uses `QueryOf<"list_humans_api_v1_humans_get">` and `JsonResponse<"list_humans_api_v1_humans_get">`). Runtime, URL building, filters, token handling, and the error model are unchanged. One contract correction surfaced: `confirmControlledScan` no longer accepts a `notes` arg — the backend `ScanConfirmationRequest` does not declare it (handler hardcodes `None`) and no page passed it. |
| **Test mock fidelity** | Two unit tests (`test_api.py::TestWriteGuard::test_reserve_works_when_enabled`, `test_api_auth.py::TestRoleMatrix::test_operator_can_reserve`) mocked `reserve_next_device_user_id` with an abbreviated 3-field dict. The canonical function always returns 6 fields; mocks updated to the true contract (this surfaced only because the reserve route now has a strict response model). |

## TESTS
- **385 passed + 18 subtests / 0 failed** (baseline 385; drift-guard test extended to assert the new schemas exist and the spec has 49 schemas)
- `tsc --noEmit` PASS · `vite build` PASS
- Full-suite hang investigation: the earlier SSE phase fixed two pre-existing `test_api_auth.py` patch leaks; the suite is deterministic green.

## DEPLOYMENT (ai-brain)
- Implementation commit `274fb06` pushed; ai-brain synced `git pull --ff-only` → `274fb06`
- Rebuilt **`adms_api`** (response-model schema change) + **`adms_web`** (typed client) only; PostgreSQL/MQTT/Collector untouched (40h+ up)
- `docker compose ps`: adms_api + adms_web `Up (healthy)`, restarts `0`

## LIVE VERIFICATION
- `/healthz` → 200 `{"status":"ok"}`
- Live `GET /openapi.json` **matches committed snapshot exactly** (37 paths, 49 schemas) — drift guard holds in production
- Web console `192.168.1.248:8082` → 200
- Authenticated `/api/v1/health` → 200 `healthy` (temp VIEWER token via canonical insert; typed response model serializes) · no-token → 401 · temp token revoked → **0 active tokens**

## KNOWN LIMITATION (pre-existing, not a regression)
The API health endpoint's `collector` field reads a health file (`/tmp/collector_health.json`)
inside the **API** container, but the polling Collector writes that file inside its **own**
container and no volume is shared — so live `/api/v1/health` returns `collector: null`.
This predates both codegen phases (the health router and schema are unchanged in
behavior); the frontend renders `—`/`No collector heartbeat` for null and is unaffected.
Options for a future round: a tiny shared volume or `HEALTH_FILE_PATH` bridge between
`listener` and `api` compose services.

## FINAL
- repository verified: **YES** · database modified: NO · schema modified: NO (no DB migration; schema-file contract improvement only) · application modified: YES (backend response models + frontend typed client) · device modified: NO
- **Typed client codegen: 100% COMPLETE** · tests: **385/385** (+18 subtests) · runtime: HEALTHY · safe to proceed: **YES** · blockers: NONE

## NEXT
The `client.ts` ↔ API contract can no longer silently drift — schema and call-signature
levels are both codegen-derived with a committed snapshot + drift-guard + `tsc` at call
sites. Remaining roadmap: **write UX enablement** (needs real personnel at the
terminal — `API_WRITE_ENABLED=true` + operator login, runbook in F3 report); deferred
external items unchanged (multi-person validation, Native ADMS Push).
