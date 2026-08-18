# ADMS-UX-FinalPolish-021

**Scope**: Close remaining user-facing UX inconsistencies before broader real-world use. No core Enrollment/Personnel/Terminal Management/Mapping/DeviceOwner/temporal-attribution redesign.

## Part A — Auth role flicker

**Root cause** (confirmed by direct source audit, not assumed):

1. `frontend/src/auth.tsx` — `AuthProvider` correctly starts `me=null`, `loading=true`, and fetches `/auth/me` asynchronously in a `useEffect`.
2. `frontend/src/components/Layout.tsx` previously destructured only `me` from `useAuth()` — never `loading`. Its role-badge ternary chain (`me?.role === "ADMIN" ? ... : ... : t.roles.viewer`) had no explicit branch for "identity not yet known" — `me === null` fell through every `===` comparison straight into the final `else`, which was the VIEWER label. This is a genuine one-render (or one full network round-trip, on refresh) flash of "VIEWER" before `/auth/me` resolves.
3. **A second, more serious bug surfaced during manual verification** (the owner reproduced it live): neither `Login.tsx` nor `Layout.tsx`'s `logout()` ever told `AuthProvider` to refetch `/auth/me`. Since `navigate()` is a client-side React Router transition, it never remounts `AuthProvider` — so after login, `me` stayed whatever it was *before* login (stale or `null`) indefinitely, until a hard refresh (`Ctrl+Shift+R`) forced a full remount. This is not a one-frame flicker; it's a persistent stale-identity state.

**Fix**:
- `Layout.tsx` now reads `loading`/`authError` from `useAuth()`. The role badge shows an explicit `t.roles.loadingAccount` ("กำลังโหลดสิทธิ์ผู้ใช้งาน...") while loading, and a distinct session-error state (with a "sign in again" action) if `/auth/me` fails — never collapsing "unknown" into "VIEWER".
- `AuthProvider` now tracks a new `authError` boolean, set only on a genuine `/auth/me` failure (never synthesizing a role).
- `Login.tsx` now calls the context's `reload()` immediately after `setToken()`, before navigating — forcing a fresh `/auth/me` fetch on every login.
- `Layout.tsx`'s `logout()` now also calls `reload()` after `clearToken()`, so identity state is deterministically cleared rather than left stale.
- Admin-only nav/controls remain gated on `me?.role === "ADMIN"` directly, which is false-by-construction while `me` is `null` (loading or errored) — destructive controls were never actually exposed early; only the *label* flickered.

**Invariant preserved**: UNKNOWN/LOADING ≠ VIEWER, everywhere in the UI.

## Part B — Enrollment completion semantics

**Design chosen**: **Option A-lite** — drive the enrollment's *already-existing* `RETIRED` terminal state, rather than inventing a new one. Audit found `RETIRED` already defined in `app/enrollment.py`'s `ALLOWED_TRANSITIONS` (`READY_FOR_MAPPING → RETIRED`) and in the DB `CHECK` constraint (`sql/006`) — it was simply never driven by any code path. This is the smallest possible correct fix.

**Migration required**: **No.** `RETIRED` was already valid in the schema.

**Implementation**: `app/mapping.py::create_verified_mapping()` now, in the *same transaction* as the `employee_device_mappings` INSERT, executes `UPDATE device_user_enrollments SET status='RETIRED' WHERE enrollment_id=%s AND status='READY_FOR_MAPPING'`, guarded so a 0-row update (concurrent state change) fails the entire call — a VERIFIED mapping is never left with its source enrollment still looking like open work, and the reverse can't happen either.

**Idempotency**: A duplicate Step 6 confirmation on an already-`RETIRED` enrollment now returns the existing VERIFIED mapping (`already_completed: true` in the API response) instead of erroring or creating a second mapping.

**Active/history queue behavior**: `frontend/src/pages/Enrollments.tsx` already filtered `TERMINAL_STATUSES = {"CANCELLED", "RETIRED"}` out of the active queue, and already rendered a dedicated completed-state card (`enrollment.status === "RETIRED"` → `t.enrollment.completedTitle`/`completedDesc`) — this UI was already built and dormant, waiting for `RETIRED` to become reachable. **No frontend changes were needed for the completion UX itself.**

**Thai completion UX** (already live, verified against source): "ลงทะเบียนสำเร็จสมบูรณ์" / "กำลังพลนี้สามารถสแกนเวลาเข้า-ออกงานได้ตามปกติแล้ว" — displayed in a green success card once `RETIRED`.

## Part C — Rank source-of-truth / dropdown

**Finding**: `human_employees.rank` is **100% import-owned** — written only by `app/import_excel_human_master.py` (`source='EXCEL_IMPORT'`) from the roster Excel file. `PATCH /api/v1/humans/{employee_id}` accepts exactly one field, `english_name` — there is no rank write path anywhere in the API, and no free-text rank input exists anywhere in the frontend today (confirmed by full-codebase audit).

**Decision**: Per the owner's own explicit instruction for externally-owned data ("if rank is external/read-only: DO NOT violate source ownership... render read-only canonical selector, clearly show source-managed status"), **no rank-editing dropdown or write endpoint was built.** Adding one would either (a) silently create a second, driftable copy of Excel-owned data, or (b) require designing and approving a new write surface — out of scope for a "close remaining UX inconsistencies" pass, and explicitly forbidden ("Do NOT invent a rank write endpoint merely to satisfy UI").

**What was already true, and what changed**: The canonical English abbreviation was *already* derived automatically everywhere rank is shown (`Personnel.tsx`, `Enrollments.tsx`) via `rank_metadata` from `GET /api/v1/reference/ranks` — no operator has ever had to type a rank abbreviation. The one concrete gap was that the Personnel detail page didn't say rank was import-managed, which could invite an operator to look for an edit control that doesn't exist. Fixed: added a small source-managed hint next to the rank field ("นำเข้าจากไฟล์บัญชีกำลังพล แก้ไขที่นี่ไม่ได้" / "from personnel roster file — not editable here").

**Proposed future integration path** (not built, for a future PromptID if needed): an ADMIN-gated, audited rank-**correction** endpoint (distinct from bulk import) that validates against `rtn_ranks.RTN_RANK_CATALOG` and writes a clearly-flagged `source='ADMIN_CORRECTION'` row, so a legitimate one-off fix (e.g. a promotion not yet re-imported) doesn't require waiting for the next Excel import, while the audit trail keeps import vs. manual-correction provenance distinct.

**Terminal-name preview**: `frontend/src/lib/terminalName.ts::computeTerminalNamePreview()` already implements exactly the required policy — deterministic, ASCII-safe (validated server-side too, `app/enrollment.py::validate_terminal_display_name`), `MAX_TERMINAL_NAME_LENGTH=20` matching the server-side limit, never silently truncates mid-name (drops the rank prefix entirely and flags `rankOmittedForLength` instead), never asks the operator to type a rank abbreviation. No changes needed.

## Part D — Elderly-UX acceptance checklist

Reviewed Dashboard, Personnel, Enrollment, Mapping, Terminal Management, System against the 10 rules. No visual redesign performed — only the auth/completion/rank fixes above and the rank source-managed hint. Checklist for future changes:

1. ☑ Thai is the default language and reads in plain, non-technical wording.
2. ☑ Each workflow step/card has exactly one primary action button.
3. ☑ No UUIDs surfaced in normal operator-facing text (only in the collapsed "metadata inspector" detail section, clearly optional/technical).
4. ☑ No raw backend enum strings shown to non-ADMIN roles (Terminal Management, Enrollment, Personnel all translate status to Thai labels).
5. ☑ No raw backend error text surfaced for expected error classes (`WRITE_DISABLED`, `MAPPING_CONFLICT`, `ACTIVE_HUMAN_PROTECTION`, etc. are all mapped to friendly copy).
6. ☑ "Mapping" terminology does not appear in Thai operator copy (Thai UI uses "เชื่อมบุคคลกับเครื่อง" / "ยืนยันตัวบุคคล" instead).
7. ☑ No pyzk/MQTT/DeviceOwner/SingleOwnerIO jargon in any user-facing string (verified by `test_no_internal_ids_exposed_in_ui_copy`).
8. ☑ Button labels describe the real-world action (ลบลายนิ้วมือ / ลงลายนิ้วใหม่ / นำผู้ใช้ออกจากเครื่อง, not "Execute"/"Submit").
9. ☑ Success states say the work is finished (completion card, "removed successfully" toasts) rather than just closing silently.
10. ☑ Loading states use a distinct visual/copy from a permission or completion result (this PromptID's Part A fix directly addresses the one place this rule was violated).

## Part E — Incident → regression matrix

| Real incident | Regression test |
|---|---|
| Role VIEWER flicker / stuck before ADMIN | `tests/test_auth_ux.py` (13 tests, incl. login/logout refetch ordering) |
| English name stale | `tests/test_enrollment_state_sync.py`, `tests/test_full_enrollment_e2e.py` (english_name propagation) |
| Duplicate Cancel | `tests/test_enrollment_state_sync.py` (already-cancelled idempotency) |
| CORS PATCH | `tests/test_cors.py` |
| Terminal-account timeout race | `tests/test_timeout_margin.py`, `tests/test_enrollment_state_sync.py` |
| SingleOwnerIO race | `tests/test_device_owner.py`, `tests/test_device_command_bus.py`, `tests/test_timeout_margin.py` |
| Mapping 422 / Attendance ID #? (evidence minute-precision mismatch) | `tests/test_mapping_creation.py::test_evidence_matched_within_minute_precision_gap` |
| Manual controlled-scan time mismatch | `tests/test_mapping_creation.py` precondition suite, PromptID-018 evidence-binding tests |
| Step 6 completed but Enrollment still looked incomplete | `tests/test_mapping_creation.py::TestEnrollmentCompletionSemantics` (5 new tests, this session) |
| Terminal fingerprint pyzk `user_id` bug | `tests/test_terminal_management.py::test_item6b_delete_user_template_never_passes_user_id` (added during the 020 deploy incident) |
| Terminal ID reservation/reclamation behavior | `tests/test_terminal_id_reclamation.py` |

No known real incident is without regression coverage.

## Totals

- **662 tests passing** (632 baseline + 30 new: 13 auth, 5 enrollment-completion, 12 rank-source-of-truth). 0 failed.
- OpenAPI drift guard: PASS. `frontend/openapi.json`/`generated.ts` regenerated (added `CreateMappingResponse.already_completed`).
- `tsc --noEmit`: PASS. `vite build`: PASS.
- `git diff --check`: clean. No secrets in diff.
- **Production mutation count: 0.** All verification was read-only/source-audit; no destructive device operation, no Human deactivation, no mapping/attendance alteration, terminal account 1001 untouched.

## Remaining known UX defects (not addressed this pass, out of scope)

- Rank remains fundamentally import-only; a genuine correction workflow (proposed above) is not built.
- `mqtt_status` in Collector health telemetry shows `UNKNOWN` immediately after a restart until the next real attendance event — cosmetic, pre-existing, not user-facing.
- No live browser end-to-end verification was performed for Parts A/B/C in this session (structural/source-level tests only, consistent with this repo's existing no-frontend-runner convention) — recommend a manual click-through before the deployment gate is exercised.
