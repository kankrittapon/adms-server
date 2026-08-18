# ADMS-UX-CrossLifecycleClosure-021B

**Scope**: verify and fix cross-lifecycle consistency after terminal account removal, using the real historical Pimai / old Terminal ID 1004 incident as the acceptance model.

## 1. Root cause

021's fix (atomically driving `READY_FOR_MAPPING → RETIRED` inside `create_verified_mapping()`) only takes effect for mappings created **after** that code deploys. It does not retroactively fix rows written before it — and more importantly, it never addressed what should happen when a mapping is later **closed** (terminal account removed, roster-lifecycle reconciler sets `valid_to`) well after the enrollment already "finished." The real production Enrollment #4 row is *still* `status='READY_FOR_MAPPING'` in the database (021 hasn't deployed), and its mapping (#2) has since been closed by the terminal-removal cleanup performed this session — so the old raw-status-based Active Queue filter (`status !== 'RETIRED'`) kept showing it as unfinished work indefinitely. No status transition anywhere in the codebase was ever driven by "the mapping got closed" — only by "the mapping got created."

## 2. Canonical derived-state design

Added `_derive_enrollment_lifecycle_state()` in `app/api/repository.py`, computed fresh on every read from a `LEFT JOIN LATERAL` against `device_users` + the most relevant `VERIFIED` `employee_device_mappings` row — never stored, never migrated:

```
CANCELLED                → status == 'CANCELLED'
COMPLETED                → status in ('RETIRED', already-mapped 'READY_FOR_MAPPING')
                            AND device account still active AND mapping still open
REMOVED_FROM_TERMINAL     → same status condition, but account inactive OR mapping closed
IN_PROGRESS               → everything else (genuinely unfinished work)
```

Because this is derived from current joined facts rather than trusted from the stored `status` column alone, it **self-heals** the real Enrollment #4 row (still `READY_FOR_MAPPING` in the DB) into the correct `REMOVED_FROM_TERMINAL` state without any backfill or migration — proven directly by `tests/test_enrollment_lifecycle_state.py::test_pimai_1004_self_heals_even_with_stale_stored_status`.

A parallel Human-level field, `has_active_terminal_account` (in `GET /api/v1/humans`), answers "does this specific Human currently have a working account" using the identical underlying join predicate (`mapping_status='VERIFIED' AND valid_to IS NULL AND device_users.active=true`) — so Personnel and Enrollment/Terminal Management can never disagree about this fact, by construction (one SQL predicate, not two independent reimplementations).

The frontend never combines `enrollment.status` + `device_users.active` + `mapping.valid_to` itself — confirmed by `tests/test_cross_lifecycle_ui.py::test_no_frontend_reimplementation_of_lifecycle_join` (those raw field names don't even appear in `Enrollments.tsx`).

## 3. Backend changes

- `app/api/repository.py`: `_ENROLLMENT_LIFECYCLE_JOIN_SQL`, `_derive_enrollment_lifecycle_state()`, `_attach_lifecycle_state()` — wired into both `list_enrollments()` and `get_enrollment_row()`. `_HAS_ACTIVE_TERMINAL_ACCOUNT_SQL` — wired into `list_humans()` and `get_human()`.
- `app/api/schemas.py`: `Enrollment.lifecycle_state: str` (required), `Human.has_active_terminal_account: Optional[bool]` (nullable only on the one write-response path — `PATCH /humans` — that doesn't recompute it; GET always populates it).
- No changes to `app/enrollment.py`, `app/mapping.py`, `app/terminal_management.py`, `app/collector.py` — this is a read-side derivation layer only.

## 4. Enrollment active/history behavior

`frontend/src/pages/Enrollments.tsx`: the Active Queue now filters on `lifecycle_state === "IN_PROGRESS"` (was: raw `status` against a hardcoded terminal-status set). Auto-selection only ever considers `activeItems`, so a historical enrollment can never become "the selected active workflow" merely by being newest. A new, visually distinct, **non-clickable** "ประวัติการลงทะเบียน" (Enrollment History) section lists everything else, labeled `COMPLETED` / `REMOVED_FROM_TERMINAL` / `CANCELLED` in Thai — no raw enum, no internal ID, in that section.

## 5. Personnel behavior

`frontend/src/pages/Personnel.tsx`'s Human detail page now shows a distinct amber "ยังไม่มีบัญชีบนเครื่องสแกน" card whenever `data.active && data.has_active_terminal_account === false` — with an ADMIN-only "ลงทะเบียนใหม่" button linking to the Enrollment Workspace. Critically, this is a **separate condition from `data.active`** — a removed terminal account is never described as the Human being inactive; the existing ACTIVE/INACTIVE lifecycle card (019) is untouched and still governs that separately.

## 6. Terminal Management behavior

Unchanged. Terminal Management is inherently an inventory-of-currently-discovered-terminal-accounts view (`TERMINAL_INVENTORY` reads the live roster) — a Human with no account simply doesn't appear there, which is already correct; "no account, please re-enroll" is Personnel's/Enrollment's concern, not Terminal Management's.

## 7. Re-enrollment behavior

Unchanged, by design — "ลงทะเบียนใหม่" links to the existing Enrollment Workspace, whose `ReserveCard` already goes through the canonical allocator (`app/enrollment.py::reserve_next_device_user_id()`, including the 020 no-migration reclamation policy). Nothing about this PromptID touches allocation — a fresh enrollment for Pimai would get a **new** enrollment row and, per the existing 1002-vs-1003 policy, terminal ID 1004 stays permanently unreclaimable (it had a real `device_users` row) while a genuinely never-created cancelled ID would be eligible. Enrollment #4, Mapping #2, and `device_user_pk=29` are never touched by re-enrollment.

## 8. Exact Pimai/1004 simulated result

Using fakes only (`tests/test_enrollment_lifecycle_state.py::TestPimai1004AcceptanceSimulation`), reproducing status=`READY_FOR_MAPPING` (real stored value), `device_user_active=False`, `verified_mapping_status='VERIFIED'`, `mapping_valid_to=<closed>`:

```
lifecycle_state == "REMOVED_FROM_TERMINAL"   (never "IN_PROGRESS")
```

Combined with the Personnel-side simulation (`has_active_terminal_account=False`, `active=True`), the operator-facing result is exactly the required shape: Human stays visible and ACTIVE, Enrollment #4 appears only in history (non-actionable, labeled "นำออกจากเครื่องแล้ว"), and Personnel shows "ยังไม่มีบัญชีบนเครื่องสแกน" with a single "ลงทะเบียนใหม่" action — never a Step 5/6 unfinished-workflow appearance.

## 9. Tests before/after

685 passing (662 baseline + 1 updated + 23 new: 12 `test_enrollment_lifecycle_state.py`, 11 `test_cross_lifecycle_ui.py`). 0 failed. One pre-existing test (`test_item10_terminal_statuses_excluded_from_active_queue`) was updated in place — it asserted the now-superseded raw-status filtering mechanism; updated to confirm the old mechanism is gone and the new `lifecycle_state`-based one is present, without weakening the guarantee it checks.

## 10. OpenAPI drift

Regenerated (`frontend/openapi.json` / `generated.ts`) for `Enrollment.lifecycle_state` and `Human.has_active_terminal_account`. Drift guard: PASS.

## 11. `tsc --noEmit`

PASS.

## 12. `vite build`

PASS (`dist/assets/index-DDUUpII8.js`, 320.74 kB / 90.16 kB gzip).

## 13. Migration required?

**No.** Everything is a read-time SQL derivation (`LEFT JOIN LATERAL`, `EXISTS` subquery) over existing tables/columns — no schema change, no backfill.

## 14. Changed files

`app/api/repository.py`, `app/api/schemas.py`, `frontend/openapi.json`, `frontend/src/api/generated.ts`, `frontend/src/i18n/{en,th,types}.ts`, `frontend/src/pages/Enrollments.tsx`, `frontend/src/pages/Personnel.tsx`, `tests/test_api.py`, `tests/test_enrollment_state_sync.py`, `tests/test_cross_lifecycle_ui.py` (new), `tests/test_enrollment_lifecycle_state.py` (new).

## 15. Commit hash

Committed this session — see git log (`ADMS-UX-CrossLifecycleClosure-021B` commit, pushed to `origin/main`). Production mutation count: **0**.

## 16. Remaining known UX inconsistencies

- `ActiveEnrollmentInspector`'s Cancel-button guard (`enrollment.status !== "RETIRED" && !== "CANCELLED"`) still keys off raw `status`, not `lifecycle_state`. This is currently safe in practice because historical items are never selectable through normal navigation (excluded from `activeItems`, excluded from auto-select, history rows aren't clickable) — but if a future change makes history rows selectable for ADMIN inspection, that guard should be updated to `lifecycle_state === "IN_PROGRESS"` at the same time. Flagged, not fixed, to keep this change's blast radius minimal.
- No live-browser click-through performed — structural/source-level tests only, consistent with this repo's no-frontend-runner convention.
- Terminal Management does not currently offer a reverse link ("this Human has no account — go enroll them") — Personnel is the single entry point for that action, which is intentional (Terminal Management stays a pure device-inventory view) but worth knowing if a future UX pass wants a shortcut there too.
