# ADMS F1 — API GAP CLOSURE AUDIT

**PromptID origin:** `ADMS-NativePush-Experimental-001` (final gate, owner selected A)
**Status:** PLAN/AUDIT ONLY — no code written in this session
**Reference:** `docs/FRONTEND_ARCHITECTURE_PLAN.md` (§8 API Contract Sketch)
**Backend foundation:** 100% COMPLETE (`docs/BACKEND_PRODUCTION_BASELINE.md`)

---

## 1. Purpose

Identify the exact backend data contracts and functions that must back the planned
read-only API layer, confirm the API gap, and lock the endpoint→function mapping so
F1 implementation (FastAPI layer + OpenAPI) is deterministic when the owner approves
the stack.

**Constraints (inherited, non-negotiable):**
- API is a presentation layer only — identity authority stays in the backend.
- No biometric/template data ever transits the API.
- No endpoint may auto-create mappings, bulk-enroll, or bypass `production_scope`
  enforcement (enforced in `reserve_next_device_user_id()`).
- Every WRITE is audited (`verified_by`/operator identity, `sync_events`).

## 2. Confirmed API Gap

The backend exposes **no UI-facing HTTP layer** today:
- Data: PostgreSQL via `app/db.py`, `app/mapping.py`, `app/enrollment.py`, `app/rtn_ranks.py`
- Realtime: MQTT topic `attendance/events` (publish only, no subscriber API)
- Health: `/tmp/collector_health.json` (file) + `python -m app.healthcheck` (exit code)

→ **GAP CONFIRMED.** A read-only API layer must be added before any UI.

## 3. Read Endpoints → Exact Backend Contract

| Planned endpoint | Backend function / table | Notes |
|---|---|---|
| `GET /api/health` | `/tmp/collector_health.json` + `app/healthcheck.py` | FSM state, restarts (Docker), DB/MQTT/ZK booleans |
| `GET /api/humans?scope=&q=` | `human_employees` + `human_employee_sources` + `app/rtn_ranks.normalize_rtn_rank()` / `classify_rank()` | scope ∈ all/eligible/production; rank is display metadata only |
| `GET /api/humans/{employee_id}` | `human_employees` + `human_employee_sources` (provenance) + `device_user_enrollments` + `employee_device_mappings` | full detail |
| `GET /api/devices` | `devices` (1 row, ZEM560, serial `3392113170057`, IP `192.168.1.201`) | firmware/IP/connected from health |
| `GET /api/device-users?active=` | `device_users` | pk, device_user_id, uid, display_name, privilege, active, inactive_at, roster_last_seen_at |
| `GET /api/attendance?from=&to=&user=&status=&resolved=` | `attendance_logs` | scan_time UTC + Bangkok label; resolved = employee_id IS NOT NULL; raw_payload metadata only |
| `GET /api/enrollments` / `{id}` | `app/enrollment.get_enrollment()` (9-state machine) | RESERVED→…→READY_FOR_MAPPING + CANCELLED/RETIRED |
| `GET /api/mappings` | `employee_device_mappings` (1 VERIFIED row) | temporal [valid_from, valid_to), method CONTROLLED_SCAN, verified_by |
| `GET /api/ranks` | `app/rtn_ranks.all_canonical_ranks()` | canonical RTN catalog (reference data) |
| `GET /api/backups` | filesystem `backups/*.dump` (ai-brain) | name/size/SHA256 from filenames + metadata doc |

## 4. Write Endpoints → Exact Backend Function (gated, audited)

| Planned endpoint | Backend function | Gate / audit |
|---|---|---|
| `POST /api/enrollments/reserve` | `app.enrollment.reserve_next_device_user_id()` | operator role; enforces production_scope=true; operator identity captured |
| `POST /api/enrollments/{id}/create-account` | `app.enrollment.create_reserved_terminal_account()` | operator role; exact reserved ID; NORMAL privilege; fail-safe |
| `POST /api/enrollments/{id}/confirm-account` | `app.enrollment.verify_terminal_account_created()` | operator role |
| `POST /api/enrollments/{id}/fingerprint-confirmed` | `app.enrollment.confirm_fingerprint_enrolled()` | operator confirms physical enrollment |
| `POST /api/enrollments/{id}/scan-window` | `app.enrollment.start_controlled_scan_window()` | 5-min window |
| `POST /api/enrollments/{id}/confirm-scan` | `app.enrollment.confirm_controlled_scan()` | explicit owner/operator confirmation (no inference) |
| `POST /api/enrollments/{id}/ready-for-mapping` | `app.enrollment.mark_ready_for_mapping()` | validated state transition |
| `POST /api/mappings` | `app.mapping.create_verified_mapping()` | admin role; evidence-validated; 1-at-a-time |
| `POST /api/enrollments/{id}/cancel` / `retire` | `app.enrollment.cancel_enrollment()` / `retire_enrollment()` | operator/admin |

All state changes flow through `validate_status_transition()`; no endpoint bypasses it.

## 5. Realtime Design (F1 scope note)

- MQTT `attendance/events` → SSE bridge (read-only fan-out) OR short polling on
  `GET /api/attendance?from=last_id`. Decision deferred to implementation; SSE is
  preferred (no new infra, works with the existing MQTT publish path).

## 6. Auth (F1 scope note)

- Initial phase: single-operator static token or session — **owner must approve**.
- Roles viewer/operator/admin enforced at endpoint level (plan §5).

## 7. Exact Implementation Plan (when approved)

1. Add `fastapi` + `uvicorn` (+ `pydantic`) to `app/requirements.txt` (or new `adms-api` service).
2. New `app/api/` package: `main.py` (FastAPI app), `schemas.py` (pydantic), `routes/` (health, humans, devices, attendance, enrollments, mappings, ranks, backups).
3. Read-only by default; WRITE endpoints call canonical functions with operator identity from the request context.
4. OpenAPI auto-generated at `/docs` + `/openapi.json`; typed TS client via `openapi-typescript` for F2.
5. Tests: API layer tests (read endpoints + WRITE gating + no-bypass assertions), run full suite.
6. Deploy: `adms-api` container on ai-brain (LAN-only), rebuild only affected service.

## 8. Owner Gates Required

- **Stack approval** (FastAPI + React/TS/Vite per plan §3) — required before F1 implementation.
- **Auth model approval** (single-operator token/session) — required before WRITE endpoints ship.
- **F1 scope** (read-only first; WRITE endpoints gated behind role checks).

STOP.
