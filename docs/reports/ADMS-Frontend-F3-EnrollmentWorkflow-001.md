# ADMS-Frontend-F3-EnrollmentWorkflow-001 — Enrollment Operator Workflow UI

**Status:** COMPLETE — F3 WORKFLOW UI LIVE, WRITES STAY GATED
**Date:** 2026-08-13
**Owner gate:** F5 gate → owner selected **F3 — Enrollment operator workflow**

---

## 1. Goal

Give an authenticated OPERATOR/ADMIN a role-aware UI to drive the controlled
enrollment state machine through the canonical backend functions:

```
reserve → terminal account (physical) → fingerprint confirm → controlled scan → ready-for-mapping
```

Production writes remain gated: `API_WRITE_ENABLED=false` until a real physical
enrollment session begins. No enrollment was executed during this phase.

## 2. Backend changes

- `app/enrollment.py` — added canonical **`ENROLLMENT_ACTIONS`** catalog
  (action name → target status + required role). The state machine knowledge
  stays in one place; the frontend never duplicates `ALLOWED_TRANSITIONS`.
- `app/api/routers/enrollments.py` — added **`GET /api/v1/enrollments/{id}/next-actions`**
  (read-only): returns the valid next operator actions for the enrollment's
  current state, computed from `ALLOWED_TRANSITIONS` + `ENROLLMENT_ACTIONS`.
  Empty at `READY_FOR_MAPPING` (only `RETIRED` remains, consumed by the
  ADMIN-only VERIFIED mapping creation) and at terminal states.
- No schema change. No new write routes (F1's 9 gated POSTs already wrap the
  canonical functions; `create-terminal-account` remains 501 — physical step).

## 3. Frontend changes (`frontend/`)

- `src/auth.tsx` — new `AuthProvider`/`useAuth` context exposing the signed-in
  operator, `role`, `canWrite` (OPERATOR/ADMIN), `isAdmin`. Layout now consumes
  it (removes the duplicate `/me` fetch).
- `src/api/client.ts` — typed write methods for the workflow:
  `reserveEnrollment`, `startFingerprintEnrollment`, `confirmFingerprintEnrolled`,
  `startControlledScan`, `confirmControlledScan`, `markReadyForMapping`,
  `cancelEnrollment`, plus `enrollmentNextActions`.
- `src/api/types.ts` — `EnrollmentNextActions`, `EnrollmentReserveResult`,
  `EnrollmentTransitionResult`.
- `src/pages/Enrollments.tsx` — interactive workflow page:
  - **Reserve form** (OPERATOR/ADMIN only): eligible Humans fetched live
    (`production_scope=true`), device select, operator (defaults to current
    username). Server 403 surfaces a clear write-disabled message.
  - **Detail panel** per enrollment: status badge, Human/device/terminal,
    timestamps, notes, and the per-state action buttons from `next-actions`.
  - **confirm-controlled-scan**: inline datetime-local input (converted to UTC
    ISO). **cancel**: required reason input. Other transitions: confirm dialog.
  - **Write-disabled banner** when a write returns 403 `WRITE_DISABLED`
    (includes the `API_WRITE_ENABLED=false` hint); 409 conflicts surfaced.
  - VIEWER sees the read-only list/detail without action buttons.

## 4. Tests

- 7 new API tests for `next-actions` (per-state transitions, terminal states,
  404, 422): `tests/test_api.py::TestEnrollmentNextActions`.
- **Full suite: 343 passed + 18 subtests / 0 failed** (baseline 336 + 18).
- Frontend: `tsc --noEmit` (strict) + `vite build` PASS (47 modules).

## 5. Deployment (ai-brain)

- Commit `9d26f5d` pushed; ai-brain `git pull --ff-only` → `9d26f5d`.
- `adms_api` container rebuilt only (`docker compose build api && up -d api`).
  PostgreSQL, MQTT, Collector, and all unrelated ai-brain containers untouched
  (restarts 0). `/healthz` OK.

## 6. Live verification (owner-authorized temp admin token)

- Token issued via canonical `issue_token` (hash-only `api_tokens` row for the
  existing admin operator_id 1, 1h TTL), used, then **revoked**; two orphaned
  tokens from a failed automation attempt were also revoked. Final state:
  **0 active tokens** for operator 1.
- `GET /api/v1/enrollments/1/next-actions` → **200**, status
  `READY_FOR_MAPPING`, `next_actions: []` (correct — awaiting admin mapping).
- Enrollment 1 state intact: terminal 1001, employee
  `039c4486-b30f-4ce1-b780-783cd268858d`, device 1.
- Write guard live: enrollment write AND admin mapping create both → **403
  `WRITE_DISABLED`** (production stays read-only; defense in depth even for
  ADMIN).
- Reads (ranks, enrollments, device-users, dashboard) → 200.
- **GET side-effect free**: DB counts `120|3|1|12|1`
  (humans|device_users|mappings|attendance|enrollments) identical before/after.
- Revoked token reuse → **401**.

## 7. Browser verification (headless Chrome + CDP)

- Workflow page renders against the live API with a temp ADMIN token:
  - Reserve form visible with **84 eligible production-scope Humans** fetched
    live (กฤตพล หมาดเส็น first).
  - Enrollment list + detail panel; at READY_FOR_MAPPING shows
    "No further operator actions … Awaiting admin VERIFIED mapping creation."
  - Reserve-form submit → server 403 → UI shows the write-disabled message.
  - No console errors.

## 8. Safety / regression

- **No real enrollment executed.** No User 1002 created. No terminal write.
- Human Master / mapping 1 VERIFIED / production_scope 84/36 / attendance
  counts unchanged. Backend Foundation **REMAINS 100% COMPLETE**.
- No secrets in repo; parameterized SQL; LAN-only bind unchanged.

## 9. Runbook — enabling real enrollment writes

```bash
# on ai-brain, when a physical enrollment session begins:
#  1) set API_WRITE_ENABLED=true for the api service (compose env)
#  2) docker compose up -d api
#  3) operator/admin logs into the console and drives the workflow
#     (physical terminal steps still happen at the device by the operator)
# After the session, restore API_WRITE_ENABLED=false.
```

## 10. Commits

- `9d26f5d` — feat: enrollment operator workflow UI + next-actions endpoint
  (# ADMS-Frontend-F3-EnrollmentWorkflow-001)

## 11. Next

- **F4 — Mapping/admin views + reconciliation UI** (write-gated; VERIFIED
  mapping creation is ADMIN-only) or enable write UX for a real session.
- Backend/identity foundation unchanged and healthy.
