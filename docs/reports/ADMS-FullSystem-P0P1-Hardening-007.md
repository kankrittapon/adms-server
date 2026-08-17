# ADMS-FullSystem-P0P1-Hardening-007

**Type:** Engineering report — security hardening + usability hardening implementation
**Depends on:** `ADMS-FullSystem-UsabilityReview-006` (read-only findings review)
**Status:** Phases A–E **COMPLETE IN SOURCE**. Phase F (production deployment) **PENDING a separate Owner Gate — not yet executed.**
**Production impact of this report:** none yet. `API_WRITE_ENABLED` unchanged (`false`), migration 012 not applied, Collector/MQTT/device untouched, no real enrollment performed.

---

## 1. Origin: Review-006 Findings

A full-system usability review (`ADMS-FullSystem-UsabilityReview-006`) audited backend, API, frontend, RBAC, enrollment workflow, and Thai/English localization end-to-end. Verified findings carried into this implementation phase:

| Finding | Severity | Verified against source? |
|---|---|---|
| `POST /operators`, `/operators/{id}/toggle-active` bypass `require_writes` entirely | CRITICAL | Yes — confirmed no `Depends(require_writes)` on either route |
| `API_WRITE_ENABLED` is SSH/`.env`-only, requiring a container recreate for every session; the enrollment runbook framed this as a routine per-session operator action, which it cannot be | HIGH | Yes |
| `ENROLLMENT_ACTIONS["*"]["requires_role"]` hand-typed as `"OPERATOR"`, silently omitting `ENROLLMENT_OPERATOR` despite the router actually permitting it via `ROLES_ENROLLMENT_MUTATE` | HIGH (metadata drift, not an auth bug) | Yes |
| Frontend `auth.tsx`'s `canWrite` also hardcoded `role === "OPERATOR" \|\| role === "ADMIN"`, omitting `ENROLLMENT_OPERATOR` | HIGH — new finding surfaced during re-verification, not in Review-006 | Yes |
| `errors.py` centralizes the response envelope but not `EnrollmentError`/`MappingError` → HTTP translation (duplicated 8× in `enrollments.py`, 1× in `mappings.py`) | MEDIUM | Yes |
| Three `alert()`/`window.confirm()` call sites, including the identity-sensitive VERIFIED-mapping confirmation | MEDIUM | Yes |
| `System.tsx`'s "API Gateway Service" card actually rendered `health.data.database` | MEDIUM | Yes |
| No route-level role guard — `/audit` and other admin routes render a partial page for the wrong role instead of a clear denial | MEDIUM | Yes |
| Raw backend enums (`RESERVED`, `NO_MAPPING`, …), raw UUIDs, jargon (`API_WRITE_ENABLED=false`, "MUTATION ENABLED", "SSE", "Human Master", "ASCII", `[valid_from, valid_to)`) leaking into user-facing copy | LOW–MEDIUM (usability) | Yes |
| Attendance timestamps shown in raw UTC only | LOW–MEDIUM (usability) | Yes |

Nothing from Review-006 was found to be materially wrong on re-verification.

---

## 2. Owner-Approved Scope

Owner decision: **B — APPROVE P0 + P1 UX HARDENING**, followed by a detailed architecture/implementation plan (`ADMS-FullSystem-P0P1-Hardening-007` planning pass), then **A — APPROVE FULL P0 + P1 IMPLEMENTATION** with explicit revisions:

1. Runtime write-session duration: **30 minutes**, approved.
2. Error-code strategy: keep `WRITE_DISABLED` unchanged for Layer 1; add `WRITE_SESSION_REQUIRED`, `WRITE_SESSION_EXPIRED`, `WRITE_SESSION_ALREADY_ACTIVE` for Layer 2 — approved.
3. Production `API_WRITE_ENABLED` transition: **conditionally approved**, only at final Phase F deployment, after migration 012, backend write-session verification, closed operator-management bypass, and full test pass — **explicitly not before**.
4. **Required revision**: the write-session concurrency design must not use a naive partial-unique-index-only approach that could let an expired-but-unclosed session block a new open; a transactionally safe reap-then-check-then-insert strategy was required, with specific tests for expiry-doesn't-block, concurrent-open-safety, restart-safety, and Layer-1-overrides-Layer-2.

All of the above were implemented as specified — see §5.

---

## 3. Phase A — Security Correctness

**Closed the operator-management write-gate bypass.** `app/api/routers/operators.py`: both `create_operator` and `toggle_active` now carry `Depends(require_writes)` alongside the existing `Depends(admin_only)`, matching every other domain-mutating route. Two new regression tests (`tests/test_api_auth.py::test_operator_create_blocked_when_writes_disabled`, `test_operator_toggle_blocked_when_writes_disabled`) assert 403 `WRITE_DISABLED` when writes are off; the existing `TestOperatorManagement` class's `setUp` was switched from `write_enabled=False` to `write_enabled=True` since its create/toggle tests now require the gate open, exactly the behavior the fix introduces.

**Fixed the `ENROLLMENT_ACTIONS` role-metadata drift.** Rather than maintaining a second, parallel role declaration (the source of the original drift), the per-action `"requires_role"` field was removed from `app/enrollment.py`'s `ENROLLMENT_ACTIONS` dict entirely, with a comment explaining why. The router (`app/api/routers/enrollments.py`, `get_next_actions`) now computes the value returned to the frontend directly from `ROLES_ENROLLMENT_MUTATE` (the actual enforcement set), so there is exactly one source of truth and no way for the two to diverge again.

**Centralized `EnrollmentError`/`MappingError` → HTTP mapping.** Two new exception handlers were added to `app/api/errors.py::register_exception_handlers` (409 `ENROLLMENT_CONFLICT` / `MAPPING_CONFLICT`, identical behavior to before), and the 8 duplicated `try/except EnrollmentError` blocks in `enrollments.py` plus the 1 in `mappings.py` were deleted — the domain exceptions now simply propagate. Behavior is unchanged; the duplication that made future error-model work risky is gone. The `create_terminal_account` route's separate `DeviceCommandError` handling (unrelated exception type, MQTT dispatch failures) was left untouched.

**Files changed:** `app/api/routers/operators.py`, `app/enrollment.py`, `app/api/routers/enrollments.py`, `app/api/routers/mappings.py`, `app/api/errors.py`, `tests/test_api_auth.py`.

---

## 4. Phase B — Runtime Write-Session Backend

### 4.1 Two-layer model

```
allow_write = API_WRITE_ENABLED (Layer 1)  AND  write_session_active (Layer 2)  AND  role_permits_action
```

Layer 1 (`app/api/dependencies.py::require_writes`) is unchanged — env-controlled, fail-closed, server-owner only. Layer 2 is new: `app/api/dependencies.py::require_write_session`, added *alongside* (never replacing) `require_writes` on every domain-mutating route: `enrollments.py` (7 routes), `mappings.py` (1), `humans.py` (1), `operators.py` (2, per the Phase A fix).

### 4.2 Concurrency-safe implementation (`app/write_session.py`)

Per the owner's required revision, open/close/status-read all execute inside a single DB transaction holding a **Postgres transaction-scoped advisory lock** (`pg_advisory_xact_lock`, fixed key `7_931_004_215_678`):

1. Acquire the advisory lock.
2. Reap: `UPDATE write_sessions SET closed_at=now(), closed_by=NULL, close_reason='EXPIRED' WHERE closed_at IS NULL AND expires_at <= now() RETURNING ...` — idempotent by construction, since once a row is closed this WHERE clause never matches it again. This is what makes `WRITE_SESSION_EXPIRED` audit at most once regardless of how many concurrent GET/write requests raced to discover the expiry.
3. Fetch the (now-genuinely-current) unclosed row, if any.
4. For `open`: if a row exists, roll back and raise `WriteSessionAlreadyActive`; otherwise insert the new session and commit.
5. For `close`: if no row exists, commit and return `{active: false, closed_at: null}` (idempotent, not an error); otherwise close it and commit.
6. Commit releases the advisory lock automatically (transaction-scoped, not session-scoped — a crashed connection can never leak a permanent lock).

Because the reap step runs first and is itself lock-guarded, an expired-but-unclosed session **never** permanently blocks a new `open` — it is transparently cleared in the same transaction that then checks for a genuinely active session.

### 4.3 Schema (`sql/012_write_session_schema.sql`, additive-only, not yet applied to production)

New `write_sessions` table with `session_id, opened_by, opened_at, expires_at, reason, closed_by, closed_at, close_reason`. A partial unique index (`WHERE closed_at IS NULL`) is a database-level backstop; the advisory lock is the actual serialization mechanism (Postgres partial-index predicates cannot encode `expires_at > now()`, which is why expiry is checked at read time in application code, not the index). See `docs/DATABASE_MIGRATIONS.md` for full detail.

### 4.4 API (`app/api/routers/write_session.py`)

`GET /api/v1/write-session` (any authenticated role), `POST /api/v1/write-session/open` (ADMIN, gated by Layer 1, rejects with 409 `WRITE_SESSION_ALREADY_ACTIVE`), `POST /api/v1/write-session/close` (ADMIN, **not** gated by Layer 1 — closing must always work so an ADMIN can always de-escalate). New error codes `WRITE_SESSION_REQUIRED`, `WRITE_SESSION_EXPIRED`, `WRITE_SESSION_ALREADY_ACTIVE`; `WRITE_DISABLED` unchanged.

### 4.5 Audit

Reuses the existing `sync_events` table/`log_sync_event()` helper (consistent with every other audit event in the system): `WRITE_SESSION_OPENED`, `WRITE_SESSION_CLOSED`, `WRITE_SESSION_EXPIRED`, `WRITE_SESSION_OPEN_FAILED`.

**Files added:** `app/write_session.py`, `app/api/routers/write_session.py`, `sql/012_write_session_schema.sql`, `tests/test_write_session.py`.
**Files changed:** `app/api/dependencies.py` (new `require_write_session`), `app/api/main.py` (router registration), `app/api/schemas.py` (`WriteSessionStatus`), `app/api/routers/auth.py` (`MeResponse.write_session`), `app/api/routers/{enrollments,mappings,humans,operators}.py` (dependency wiring).

---

## 5. Phase C — Admin/Operator Frontend

- **`auth.tsx`**: now fetches `write_session` from `/auth/me`; fixed the pre-existing `canWrite` bug (`ENROLLMENT_OPERATOR` was missing from the write-capable role set — a client-side UX bug, not a security hole, since the backend always enforced the role correctly regardless of what the button state showed); `canMutate = canWrite && serverWriteEnabled && writeSessionActive`; a 30-second poll keeps the countdown live while a session is active.
- **`WriteSessionControl`/`WriteSessionBadge`** (new, `components/WriteSessionControl.tsx`): a deliberate, non-jargon interaction — locked state shows a reason field + "Open work session" button (ADMIN only); active state shows opener, live countdown, reason, and a "Close session now" button. No duration picker (fixed 30 min, by design — no "leave it on" affordance). The header badge (all roles) shows a compact locked/active+countdown summary, factoring in both Layer 1 and Layer 2 so it never shows "active" if the infra gate is actually closed.
- **Route guard** (`App.tsx`, new `RequireRole`): applied to `/audit`. Explicitly documented as UX-only — a deep link from the wrong role now shows a clear "access denied" screen instead of a partially-empty page; the backend 403 remains the actual authorization boundary.
- **OpenAPI/codegen**: `frontend/openapi.json` and `frontend/src/api/generated.ts` regenerated from the live backend contract (40 paths, 52 schemas); `tests/test_openapi_contract.py`'s shape-sanity check extended to assert the new `/write-session` paths and `WriteSessionStatus` schema are present, so the drift guard actually covers the new surface.

---

## 6. Phase D — Enrollment Hardening

- **Live-connection indicator**: `useAttendanceStream` gained a `"connecting"` transition fix (previously the UI could flash "disconnected" before the first fetch resolved) and an exposed `reconnect()` callback. A new shared `StreamStatusBadge` component (moved out of `Attendance.tsx`'s page-local `LiveBadge`) is now used on **both** the Attendance page and the Enrollment controlled-scan step, with a manual retry action and no protocol jargon in the label/tooltip (previously "Realtime stream via MQTT→SSE").
- **Native `alert()`/`window.confirm()` removal**: all three remaining call sites replaced — cancel-reason and scan-timestamp validation in `Enrollments.tsx` now use inline styled validation text (matching the page's existing pattern); the VERIFIED-mapping confirmation in `Mappings.tsx` now uses a new shared `ConfirmModal` component. A fourth `alert()` found during this pass (operator-toggle failure in `System.tsx`, not flagged in Review-006) was fixed the same way.
- **Human-readable mapping confirmation**: the modal shows only person name, terminal, and scan time — no raw UUIDs or primary keys in the confirmation body (those remain visible in the existing eligibility-selection detail panel above it, for anyone who wants to cross-check).

**Files added:** `frontend/src/components/ConfirmModal.tsx`.
**Files changed:** `frontend/src/hooks/useAttendanceStream.ts`, `frontend/src/components/Status.tsx`, `frontend/src/pages/{Attendance,Enrollments,Mappings,System}.tsx`.

---

## 7. Phase E — i18n / UX Cleanup

- **Centralized enum→label mapping** (`frontend/src/i18n/enumLabels.ts`, new): TH/EN label tables for enrollment status, mapping status, verification method, and attendance reasoning codes. `StatusBadge` now consults these instead of printing the raw backend enum — this single change fixed the raw-enum leakage simultaneously across the Dashboard status chips, Enrollment queue cards, Mappings status column, and Attendance reconciliation badges (all four consume the same shared component).
- **System page health-card mislabel fixed**: the "API Gateway Service" card previously rendered `health.data.database`. Fixed per the plan's option (a) — no backend change needed, since a successful response to the health request already proves the Web API is reachable. Cards relabeled to plain language: Web API, Database, Live Event Service (was "MQTT Event Broker"), Fingerprint Terminal Collector, Last Updated.
- **Attendance local time**: primary display now formats `scan_time` in `Asia/Bangkok` (fixed UTC+7, no DST) via `Intl.DateTimeFormat`; raw UTC remains available via a tooltip. Storage and the API contract are unchanged — still canonical UTC.
- **Role descriptions**: added to the operator-creation form using the exact TH/EN copy specified by the owner, verified against the actual `ROLES_*` sets in `app/api/auth.py` with no contradictions.
- **Remaining jargon removed**: the literal `API_WRITE_ENABLED=false` string, "MUTATION ENABLED", "Deterministic terminal account provisioning", "Human Master" (in two places), the raw `[valid_from, valid_to)` interval-notation footer on Mappings, and the "(ASCII)" field suffix (reworded to "English letters and numbers only").

**Files added:** `frontend/src/i18n/enumLabels.ts`.
**Files changed:** `frontend/src/components/Status.tsx`, `frontend/src/i18n/{types,en,th}.ts`, `frontend/src/pages/{System,Attendance,Mappings,Personnel}.tsx`.

---

## 8. Protected-Write Endpoint Matrix (final state)

| Endpoint | Role | Layer 1 (`require_writes`) | Layer 2 (`require_write_session`) |
|---|---|---|---|
| `POST /operators`, `/operators/{id}/toggle-active` | ADMIN | ✅ (was missing — closed in Phase A) | ✅ |
| `PATCH /humans/{id}` | ADMIN | ✅ | ✅ |
| `POST /mappings` | ADMIN | ✅ | ✅ |
| `POST /enrollments/reserve` → `/cancel` (7 routes) | ENROLLMENT_OPERATOR+ | ✅ | ✅ |
| `POST /write-session/open` | ADMIN | ✅ | — (would be circular) |
| `POST /write-session/close` | ADMIN | — (de-escalation must always work) | — |
| `POST /auth/login`, `/logout`, `/change-password` | any/self | — (session-maintenance exemption) | — |

---

## 9. Tests

**429 backend tests passing, 0 failing** (410 pre-existing + 2 Phase A regression tests + 19 Phase B write-session tests: session open/close/idempotent-close/reason-required, expired-row-reaped-and-audited-once, expired-row-does-not-block-open, concurrent-open-second-caller-gets-already-active, infra-master-overrides-active-session, domain-write-blocked-without-session, domain-write-allowed-with-session, expired-session-reports-EXPIRED-not-REQUIRED, close-works-even-when-infra-locked). Frontend: `tsc --noEmit` clean, `vite build` clean. `tests/test_openapi_contract.py` (drift guard) passing, extended to cover the new endpoints/schema.

Test-writing note: existing tests that exercise write routes (`test_api.py`, `test_api_auth.py`) use `app.dependency_overrides[require_write_session] = lambda: None` to bypass Layer 2 where the test is about role/Layer-1 behavior, not the write-session mechanism itself — that mechanism has its own dedicated test file.

---

## 10. Security Invariant Review

No change to: Human Master authority, controlled-scan evidence requirement, `VERIFIED` mapping as the identity boundary, the `[valid_from, valid_to)` temporal model, device-user incarnation/lifecycle protections, Collector's exclusive ownership of the ZKTeco connection, or the `DeviceCommandBus` architecture. No automatic/fuzzy identity assignment was introduced anywhere — the mapping confirmation modal still requires an explicit ADMIN click on the same evidence the old `window.confirm` showed, just formatted for humans. RBAC enforcement remains entirely server-side; the new frontend route guard is explicitly documented as UX-only. Net effect: the two-layer model is strictly *more* fail-closed than the single-flag-with-a-bypass model it replaces.

---

## 11. Production State

- `API_WRITE_ENABLED`: **`false`**, unchanged throughout Phases A–E (confirmed via read-only `docker exec adms_api printenv` at the pre-deploy checkpoint).
- Migration `012_write_session_schema.sql`: **not applied** to production.
- `adms_api` / `adms_web`: still running the pre-Hardening-007 build; **no Phase F deployment has occurred.**
- Collector, MQTT broker, ZKTeco terminal: **not modified** in any way.
- No real enrollment session, database write, or device write occurred as part of this work.

---

## 12. Rollback Plan (for the eventual Phase F deployment)

Revert the deploying commit(s) and redeploy prior container images. `write_sessions` is inert if left in place post-rollback (nothing else references it) — dropping it is optional cleanup. If `API_WRITE_ENABLED` is flipped to `true` in production as part of Phase F, it must be reverted to `false` together with the code rollback, not independently — leaving it `true` after reverting the Layer-2-aware code would remove the daily operational gate entirely (every route would fall back to Layer-1-only enforcement with no Layer-2 check present).

---

## 13. Phase F — Owner Gate (not yet exercised)

Phase F requires a separate owner decision covering: apply migration 012 to production, deploy `adms_api`/`adms_web`, and decide whether to transition `API_WRITE_ENABLED` to `true` as the new steady-state infra baseline (recommended) or keep it `false` and require both flags flipped per session (not recommended — reintroduces the original SSH dependency this work removes). See `STATUS.md` §2 for the current phase table and `docs/ENROLLMENT_SESSION_RUNBOOK.md` for the explicit dual-procedure documentation (target end-state vs. current interim procedure) that stays in place until Phase F ships and that notice is removed.

---

## 14. Related Reports

This is the first and only report filed for `ADMS-FullSystem-P0P1-Hardening-007` — no earlier temporary/intermediate report files were created during Phases A–E (all interim pre-deploy status was communicated inline in conversation, not written to `docs/reports/`), so there is nothing to merge, supersede, or archive alongside this one. The preceding read-only review, `ADMS-FullSystem-UsabilityReview-006`, was conversation-only and produced no report file either. `docs/reports/README.md`'s chronological index has been updated to include this report.
