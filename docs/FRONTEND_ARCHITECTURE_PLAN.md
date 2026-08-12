# ADMS — FRONTEND ARCHITECTURE & UX PLAN

**PromptID:** `ADMS-Backend-Finalization-001` (owner-selected continuation: option A)
**Status:** PLAN ONLY — no frontend code written
**Backend foundation:** 100% COMPLETE (`docs/BACKEND_PRODUCTION_BASELINE.md`, `cb4701c`)

---

## 1. Goals

Provide an operator-facing web interface over the accepted backend that supports:

- Human Master browsing/search (120 records, production-scope aware)
- Device & device-user status (roster, active/inactive lifecycle)
- Attendance viewing (realtime + historical, status classification)
- Enrollment operator workflow (controlled, evidence-gated, one-person-at-a-time)
- Mapping state (VERIFIED temporal mappings, history)
- Runtime health monitoring (collector FSM, MQTT, DB, ZKTeco)

Non-goals (deferred): Native ADMS Push, bulk enrollment UI, biometric template access.

## 2. Frontend API Gap (authoritative)

The backend today exposes **no UI-facing HTTP/REST layer**. Current interfaces:

- PostgreSQL (internal functions in `app/db.py`, `app/mapping.py`, `app/enrollment.py`, `app/rtn_ranks.py`)
- MQTT topic `attendance/events` (realtime notification)
- Health file `/tmp/collector_health.json` + `python -m app.healthcheck` (exit-code)

**Frontend API GAP = CONFIRMED.** A read-only + controlled-write API layer must be added
before/between frontend phases. It must NOT bypass backend safety invariants (identity
authority, production-scope enforcement, controlled-scan evidence, no automatic mapping).

## 3. Recommended Stack (proposal for owner approval)

| Layer | Proposal | Notes |
|---|---|---|
| Backend API | **FastAPI** (Python 3.12, same container image family) | Same language/stack as collector; async; auto OpenAPI docs; pydantic validation |
| API placement | New `app/api/` inside the listener image (or separate `adms-api` service) | Read-only by default; WRITE endpoints gated by explicit operator + audit |
| Frontend | **React + TypeScript + Vite**, TanStack Query, Tailwind CSS | Fast iteration, typed API client from OpenAPI schema |
| State | TanStack Query server state + minimal client state | Roster/health polling via WebSocket/SSE or short polls |
| Auth | Initial phase: single-operator auth (session or static token) — MUST be owner-approved | Permissions model below |
| Deployment | Same ai-brain host; frontend as static build served by the API or a tiny nginx | No new infrastructure required |

Stack choice requires **owner approval before implementation** (option B gate).

## 4. Information Architecture & Navigation

```
ADMS Console
├── Dashboard            (runtime health, recent attendance, today's status summary)
├── Personnel
│   ├── Human Master     (browse/search 120, production_scope filter, rank/unit, source provenance)
│   └── Eligible        (production_scope=true filter — enrollment candidates)
├── Devices
│   ├── Device List      (ZEM560 #1, IP, firmware, connected)
│   └── Device Users     (roster, pk, uid, display name, privilege, active/inactive, last seen)
├── Attendance
│   ├── Live Feed        (realtime events from MQTT/SSE)
│   ├── History          (filter by date/user/status; employee_id attribution)
│   └── Status Legend    (ON_TIME / LATE / UNKNOWN semantics + window)
├── Enrollment
│   ├── New Enrollment   (operator workflow — see §6)
│   └── Enrollment Log   (state machine history: RESERVED → … → READY_FOR_MAPPING / CANCELLED / RETIRED)
├── Mapping
│   ├── Verified Mappings (temporal [valid_from, valid_to), method, verified_by)
│   └── Mapping History
└── System
    ├── Health           (collector FSM state, restarts, MQTT/DB/ZK, last events)
    └── Backups          (list of verified recovery points)
```

## 5. Permissions Model (proposal)

| Role | Scope |
|---|---|
| viewer | Read-only: dashboard, personnel, devices, attendance, mapping, health |
| operator | viewer + controlled enrollment workflow steps (reserve, account-create confirm, controlled-scan window, READY_FOR_MAPPING) |
| admin | operator + VERIFIED mapping creation, attendance reconciliation, backup actions |

Principle: **no UI action bypasses backend evidence requirements.** Every WRITE is audited
(`verified_by`/operator identity, timestamps, `sync_events`).

## 6. Enrollment Operator Workflow UX (core flow)

```
1. Select eligible Human (production_scope=true)  ── explicit search, no name/rank inference
2. Reserve next production ID (1001+)             ── shows allocator result, confirm
3. Create ONE terminal account                    ── NORMAL privilege, exact ID, fail-safe
4. INSTRUCT operator: physical fingerprint at terminal (User ID shown, no template access)
5. Start controlled scan window (5 min)           ── timer UI
6. Verify controlled event (device_user_pk, window, user 1001)
7. Operator identity confirmation                 ── explicit checkbox/affirm
8. READY_FOR_MAPPING                              ── then admin creates VERIFIED mapping
```

The UI must display the physical-action instructions from the pilot pattern and **never**
auto-advance or auto-map.

## 7. Attendance & Identity Views

- Attendance rows show: scan_time (canonical UTC, Bangkok label), user 1001, device_user_pk,
  employee attribution (employee_id → display name when VERIFIED mapping resolves),
  status (ON_TIME/LATE/UNKNOWN), raw_payload (metadata only — no biometric data).
- Legacy unmapped rows clearly labeled "unmapped (before valid_from)" — never auto-attributed.

## 8. API Contract Sketch (for the API Gap Closure phase)

Read endpoints (all read-only):
- `GET /api/health` — collector FSM, DB/MQTT/ZK status, restarts
- `GET /api/humans?scope=eligible&q=…` — Human Master + rank + production_scope
- `GET /api/humans/{employee_id}` — detail + sources + enrollments + mappings
- `GET /api/devices` · `GET /api/device-users?active=…`
- `GET /api/attendance?from=&to=&user=&status=` (+ `?resolved=`)
- `GET /api/enrollments` · `GET /api/enrollments/{id}`
- `GET /api/mappings` (VERIFIED temporal)
- `GET /api/backups`

Write endpoints (gated, audited, one-at-a-time):
- `POST /api/enrollments/reserve`  → reservation
- `POST /api/enrollments/{id}/create-account` → terminal account creation (operator)
- `POST /api/enrollments/{id}/scan-window` → controlled scan window start
- `POST /api/enrollments/{id}/confirm-scan` → explicit owner/operator confirmation
- `POST /api/enrollments/{id}/advance` → state transitions (validated)
- `POST /api/mappings` → VERIFIED mapping (admin, evidence-validated)

No endpoint may create automatic mappings, bulk-enroll, or touch biometric data.

## 9. Phases (owner-gated)

| Phase | Deliverable | Gate |
|---|---|---|
| F1 | API layer (read-only) + OpenAPI | approve stack + scope |
| F2 | Core read UI (dashboard/personnel/devices/attendance/health) | demo |
| F3 | Enrollment operator workflow UI (write, gated) | approve flow |
| F4 | Mapping/admin views + reconciliation UI | approve |
| F5 | Auth/permissions hardening | approve |

## 10. Risks & Constraints

- Identity authority must remain backend-owned; UI is a presentation layer.
- No biometric/template data may ever transit the API/UI.
- Production-scope enforcement stays in `reserve_next_device_user_id()` — UI cannot bypass.
- Controlled-scan evidence remains the only mapping authority.
