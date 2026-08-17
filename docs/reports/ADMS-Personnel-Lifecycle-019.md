# ADMS-Personnel-Lifecycle-019

**Scope**: Personnel (Human) lifecycle only — ACTIVE/INACTIVE. Strictly separate from Terminal Management (physical account/credential lifecycle), which is out of scope and becomes PromptID 020.

## Owner Requirement 0 — admin account role

Inspected the real `operators` table on `ai-brain` directly (read-only):

```
operator_id | username | role  | active
1           | admin    | ADMIN | true
```

**Already ADMIN.** Per the explicit instruction ("If account 'admin' already has ADMIN: do nothing and report it"), **no action was taken** — no role change, no password reset, no re-creation, no audit event (nothing changed to audit). Credentials, username, and active state are untouched, confirmed by this same read.

## Phase 1 — Architecture audit findings

1. **Active representation**: `human_employees.active BOOLEAN NOT NULL DEFAULT true` already exists — no migration needed for the core ACTIVE/INACTIVE flag.
2. **No dedicated `departed_at`/`departed_reason` column** — departure timestamp is derived from the deactivation transaction's own `now()` (also used as the mapping `valid_to` boundary); reason is recorded in the audit log (`sync_events`), not a new DB column — avoids a migration entirely.
3. **Deletion**: no DELETE path exists for `human_employees` anywhere in the codebase (confirmed by grep) — historical identity was already un-deletable by construction.
4. **Pre-existing invariants** (confirmed by direct source inspection, not assumed): `reserve_next_device_user_id()` already requires `active = true AND production_scope = true`; `create_verified_mapping()` already requires the Human to be `active`. **Both of Phase 9's core invariants ("cannot create new Enrollment for inactive Human" / "cannot create new VERIFIED mapping for inactive Human") already existed before this PromptID** — confirmed, not newly added.
5. **Historical attendance**: `attendance_logs` has no FK-cascade-delete tied to `human_employees.active`, and no code path writes to it based on Human state — untouched by design.
6. **Personnel UI**: previously showed `active`/`inactive` via generic `t.common.active/inactive` copy, read-only — no lifecycle action existed.
7. **Reporting/temporal resolution**: `resolve_verified_employee_mapping()` resolves purely from `employee_device_mappings.valid_from/valid_to`, independent of `human_employees.active` — a deactivated Human's historical mappings still resolve correctly for scans before `valid_to`.
8. **Accidental identity reuse**: none of the existing constraints prevented a *new* Human record from being created for a returning person — this PromptID does not change that; reactivation of the *same* Human row is the only supported "return" path, which is by construction safe against reuse ambiguity since it's the same UUID.

## Phase 2-5 — Lifecycle model implemented

`app/personnel.py` (new): `deactivate_human()` and `reactivate_human()`.

**Deactivation**: ADMIN-only, requires `API_WRITE_ENABLED` + active Write Session (enforced identically to every other domain-mutating route), requires a non-empty reason. Sets `active = false`; atomically closes (`valid_to = now()`, the same transaction) any currently-open VERIFIED mapping(s) for that Human. Never deletes a mapping row, never touches `attendance_logs`, never touches `device_users`, never touches the terminal. **Idempotent**: deactivating an already-inactive Human is a friendly no-op (`already_inactive: true`), not an error — deliberately different from Enrollment cancellation's strict rejection, per this PromptID's explicit spec.

**Mapping closure**: `valid_to = departure_effective_time` (the deactivation transaction's own `now()`). Historical semantics preserved exactly: a scan before `valid_to` still resolves to the Human via `resolve_verified_employee_mapping()`; a scan at/after `valid_to` does not resolve through the closed mapping (open-interval boundary, unchanged resolver logic).

**Reactivation**: sets `active = true` only. Does **not** reopen any closed mapping and does **not** restore terminal credential validity — a returning person requires a fresh Enrollment/Terminal-lifecycle pass and a new VERIFIED mapping at a new evidence boundary, exactly as specified. Old employment period stays historical/closed under the same canonical Human UUID; no new Human row is ever created for a return.

**Terminal cleanup**: not executed. The Personnel UI surfaces the exact required Thai notice ("บุคคลถูกปิดการใช้งานแล้ว ยังมีข้อมูลอยู่บนเครื่องสแกน กรุณาดำเนินการลบออกจากเครื่อง") on an inactive Human's detail page — a pending-work indicator only, deferred entirely to PromptID 020.

## Rank/dropdown (Phase 7)

Rank remains **read-only** in this system — `human_employees.source` defaults to `'EXCEL_IMPORT'` and no rank-write endpoint exists anywhere in the codebase (confirmed by grep — only `english_name` has a PATCH path). No new rank-write capability was added; inventing one wasn't requested here and would contradict `rtn_ranks.py`'s own documented principle ("original source rank text is NEVER rewritten"). **Read/display path unchanged and already correct** from PromptID 016/018: `Human.rank_metadata` (canonical, single source — `app/rtn_ranks.py`) is already returned by the API and already displayed on the Personnel detail page. No second rank source was introduced.

## Active-person filtering (Phase 8)

`GET /api/v1/humans` gained an `active: Optional[bool]` query filter (additive, `repository.list_humans()`). Personnel list page gained a third filter dropdown (All / Active only / Departed only, Thai-labeled). `GET /api/v1/humans/{id}` (single lookup) remains unconditional — an inactive person's record, and their name in historical contexts (attendance/mapping/audit views), is never hidden.

## RBAC / write-session behavior

`POST /api/v1/humans/{id}/deactivate` and `.../reactivate` both require `ROLES_ADMIN_ONLY` + `require_writes` (infra master lock) + `require_write_session` (runtime session) — the identical three-dependency pattern used by every other domain-mutating route in this codebase, including `create_verified_mapping`. Infra lock (`API_WRITE_ENABLED=false`) unconditionally overrides an active session, same as everywhere else.

## Tests

574 passed, 0 failed (547 pre-existing baseline + 27 net new, in `tests/test_personnel_lifecycle.py` plus a signature-compat fix in `tests/test_api.py`). Covers the required 20-item matrix: deactivation, reason-required, mapping closure (never DELETE), historical attendance never touched, idempotent duplicate deactivate, exactly-once audit events per action, reactivation semantics, reactivation never reopens mappings, active/inactive list filtering, unconditional single-record lookup, RBAC/write-session gating cross-referenced against the shared `require_writes`/`require_write_session` dependencies, and structural cross-reference proving the pre-existing Enrollment/Mapping active-Human checks are still present.

## OpenAPI / typecheck / build

Drift guard PASS (43 paths, 55 schemas — two new endpoints, two new request schemas, one new list-filter param). `tsc --noEmit` PASS. `vite build` PASS. `git diff --check` clean. No secrets found in the diff.

## Migration required

**NO.** `human_employees.active` already existed. No new column, no schema change.

## Changed files

`app/personnel.py` (new), `app/api/routers/humans.py`, `app/api/schemas.py`, `app/api/repository.py`, `frontend/src/api/client.ts`, `frontend/src/pages/Personnel.tsx`, `frontend/src/i18n/{types,en,th}.ts`, `frontend/openapi.json`, `frontend/src/api/generated.ts`, `tests/test_personnel_lifecycle.py` (new), `tests/test_api.py` (signature fix).

## Remaining work for Terminal Management — PromptID 020

Everything explicitly excluded here: `delete_user()`, `delete_user_template()`, fingerprint deletion/re-enrollment, terminal account deletion, physical ZEM560 mutation, terminal-ID reuse, account-incarnation reset. The Personnel UI's pending-cleanup notice is the only hook into that future work — no code in this PromptID calls or prepares an actual terminal I/O path.
