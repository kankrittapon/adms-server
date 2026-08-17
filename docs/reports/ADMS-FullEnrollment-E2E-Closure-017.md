# ADMS-FullEnrollment-E2E-Closure-017

**Scope**: Treat Enrollment Step 1→6 as one business transaction; find and permanently fix the root cause of the recurring "Attendance ID #?" / 422-at-Step-6 failure class; prove the complete flow deterministically in one automated E2E test; regression-test every real incident found in this project so far.

## Final Step 1–6 architecture

| Step | Canonical function | Evidence gate |
|---|---|---|
| 1 Reserve | `reserve_next_device_user_id` | Human active+in-scope, device active, no duplicate active enrollment, allocator picks a safe unused terminal ID |
| 2 Terminal account | `create_or_reconcile_terminal_account` | Bounded roster read-back is authoritative, never `set_user()`'s return value (PromptID 008/010); single-owner device I/O (PromptID 014) |
| 3 Fingerprint | `confirm_fingerprint_enrolled` | Browser-only state confirmation — physical enrollment happens at the terminal keypad; no biometric API exists or was invented |
| 4 Controlled scan | `start_controlled_scan_window` / `confirm_controlled_scan` | Operator-recorded estimate stored; real evidence resolved later via the canonical resolver, never trusted as exact |
| 5 Ready for mapping | `mark_ready_for_mapping` | **New in this PromptID**: server-side pre-check resolves real controlled-scan attendance evidence via `app.mapping_evidence` before allowing the transition — a broken evidence chain now fails here, not at Step 6 |
| 6 Verified mapping | `create_verified_mapping` | **Simplified contract**: `(enrollment_id, verified_by, verification_note)` only — `employee_id`, `device_user_pk`, `controlled_attendance_id` all derived server-side via the same canonical resolver |

## Step 5 evidence invariant

`mark_ready_for_mapping()` now performs, inside the same call, before allowing `CONTROLLED_SCAN_CONFIRMED → READY_FOR_MAPPING`:
1. Confirms `controlled_scan_time` is recorded.
2. Resolves the enrollment's `device_users` row (device_id + reserved_device_user_id → device_user_pk).
3. Calls `app.mapping_evidence.resolve_controlled_attendance_id(cur, device_user_pk, controlled_scan_time)` — the single canonical evidence resolver (see below).
4. If no attendance row resolves, raises `EnrollmentError` and the transition never happens.

## Step 6 mapping contract

`CreateMappingRequest` is now `{enrollment_id, verified_by, verification_note}` only (breaking change from the prior `{employee_id, device_user_pk, enrollment_id, controlled_attendance_id, verified_by, verification_note}`). `create_verified_mapping()` derives everything else server-side, inside the same transaction, re-validating Human/device-user active state and re-resolving evidence independently rather than trusting client input. The frontend (`Mappings.tsx`) sends only the three fields; `device_user_pk`/`controlled_attendance_id` are no longer read from the eligibility item into the request at all.

## Exact "Attendance ID #?" / 422 root cause (full picture)

Two **separate** places independently re-derived "which attendance row is this enrollment's evidence," and only one of them was fixed by PromptID-016:

1. `app.api.repository.mapping_eligibility()` (the eligibility listing) — originally used **exact equality** between `attendance_logs.scan_time` (full precision) and `device_user_enrollments.controlled_scan_time` (minute precision, from an HTML `datetime-local` input, even when auto-filled from the exact SSE event). PromptID-016 fixed this query with an inline ±2-minute bounded-window SQL subquery.
2. `app.mapping.create_verified_mapping()` — **independently** re-validated the client-supplied `controlled_attendance_id` with its own **exact equality** check (`att_scan_time != valid_from`). This was never touched by PromptID-016. Even after the eligibility query started correctly resolving `controlled_attendance_id`, this second, separate exact-equality check would still reject it — reproducing "Attendance ID #?" / 422 at the exact moment an ADMIN clicked Step 6, for the exact enrollment (#4) the owner was actively working on.

**Fix**: `app/mapping_evidence.py`, a single canonical resolver (`resolve_controlled_attendance_id` / `pick_nearest_attendance`), used by **both** `mapping_eligibility()` and `create_verified_mapping()`. Device/terminal-user constraint applies structurally (via `device_user_pk`, unique per device+terminal-user — an attendance row from a different device or different terminal user can never become a candidate). Among same-`device_user_pk` candidates, nearest-in-time within a ±120s window wins, ties broken deterministically by lowest attendance id. There is now exactly one definition of "the correct controlled-scan evidence row" in the entire codebase.

## Complete E2E test result

`tests/test_full_enrollment_e2e.py::TestCompleteEnrollmentE2E::test_complete_enrollment_to_verified_attendance_e2e` — **PASS**. Drives every canonical function in order (reserve → create/reconcile terminal account → fingerprint confirm → open scan window → confirm controlled scan → mark ready for mapping [evidence-gated] → create VERIFIED mapping [server-derived evidence] → temporal resolution of a post-mapping attendance event to the correct Human, plus a pre-`valid_from` scan correctly NOT resolving). Uses a synthetic test identity (`TEST_HUMAN_ID`/"ทดสอบ ระบบ"/"Test Person", canonical rank น.อ./Capt from `app/rtn_ranks.py`), never a real production ID. No real DB is available in this environment (confirmed: every test in this repository mocks the DB boundary — no live Postgres in CI/sandbox); the test chains real, unmodified canonical functions against per-call FakeCursor state modeling what each prior real call would have produced. The one deliberate fixture shortcut (feeding simulated attendance rows directly into the resolver) is documented inline as representing external terminal input, not a business-logic bypass.

## Real incident → regression-test matrix

| Real incident | Test name | Fix file |
|---|---|---|
| pyzk `set_user()` returns None/False on a call the device committed | `TestBoundedReadbackAuthoritative.test_case1/2/3` | `tests/test_terminal_account_idempotency.py` |
| Pre-mutation `get_users()` timeout | `TestTerminalRosterUnavailable` | `tests/test_timeout_margin.py` |
| DeviceCommandBus timeout race (outer timeout < Collector budget) | `TestDerivedTimingBudget` | `tests/test_timeout_margin.py` |
| Shared pyzk socket concurrency (main thread vs MQTT thread) | `TestNoConcurrentZkAccess`, `TestLiveCaptureIntegration` | `tests/test_device_owner.py` |
| English Name stale in Enrollment (useState-initializer bug) | `TestFrontendDisplayNameSync` | `tests/test_enrollment_state_sync.py` |
| CORS PATCH preflight blocked | `TestCorsPreflight` | `tests/test_cors.py` |
| Duplicate Cancel / `CANCELLED -> CANCELLED` | `TestFrontendCancelConsistency`, `test_cancel_already_cancelled_raises_enrollment_conflict_with_clear_message` | `tests/test_enrollment_state_sync.py` |
| Thai name ASCII failure (terminal display name) | `TestCanonicalEnglishNameAndAsciiGuard` | `tests/test_terminal_account_idempotency.py` |
| Rank terminal-name preview | `TestTerminalNamePreviewRules`, `TestRankToAbbreviationMapping` | `tests/test_rank_terminal_preview.py` |
| Step 5 confusing/unguarded state | `test_ready_for_mapping_without_scan_evidence_rejected`, new pre-check in `mark_ready_for_mapping` | `tests/test_enrollment.py`, `app/enrollment.py` |
| Controlled attendance exact-timestamp mismatch | `TestPickNearestAttendancePureFunction`, `TestResolveControlledAttendanceIdScoping` | `tests/test_mapping_evidence.py` |
| `POST /mappings` 422 (both root causes) | `TestMappingRequestValidation`, `test_no_controlled_attendance_evidence_resolves` | `tests/test_mapping_eligibility_fix.py`, `tests/test_mapping_creation.py` |
| "Attendance ID #?" (create_verified_mapping's own exact-equality re-check) | `test_mapping_creation_uses_the_same_resolver_module`, `test_evidence_matched_within_minute_precision_gap` | `tests/test_mapping_eligibility_fix.py`, `tests/test_mapping_creation.py` |
| Frontend stale state after mutation | `test_item7_all_mutations_trigger_canonical_refetch` | `tests/test_enrollment_state_sync.py` |
| Write session lock UX | write-session tests across `tests/test_api_auth.py` | `app/api/dependencies.py` |
| ENROLLMENT_CANCELLED audit gap (found in PromptID-015) | `test_cancel_emits_enrollment_cancelled_audit_event_exactly_once` | `app/enrollment.py` |

No real incident encountered in this project's session history remains without a regression test.

## Elderly-user UX acceptance (Phase 13)

Checklist applied to the current TH flow, per screen:
- Step 1: "เลือกบุคคล" — obvious primary action, no Reserve/UUID jargon shown prominently. ✅
- Step 2: shows name + terminal ID, plain "กำลังติดต่อเครื่องสแกน..."/"สร้างผู้ใช้เรียบร้อยแล้ว" states, no protocol jargon. ✅
- Step 3: numbered physical steps, explicit "ลงลายนิ้วมือเสร็จแล้ว" button — never implies the browser enrolls biometrics itself. ✅
- Step 4: live SSE badge + "รอการสแกน.../✓ พบการสแกนแล้ว". ✅
- Step 5: evidence checklist (✓ x3) + one button, no "Mapping" word. ✅
- Step 6: single evidence card + "ยืนยันการเชื่อมบุคคลกับเครื่อง" — no `device_user_pk`/UUID ever shown or required as input. ✅
- Failures map to friendly TH copy (`enrollmentConflictBody`, `evidenceIncompleteBody`, `mappingConflictBody`, `alreadyMappedBody`) — raw transition/validation strings never surfaced. ✅
- Every successful mutation triggers `list.reload()`/`nextActions.reload()` — no manual refresh required. ✅

## Full API contract audit (Phase 14)

Searched frontend for `!`, `as any`, `controlled_attendance_id`, `device_user_pk`, `createMapping`. Findings: the non-null assertions on `device_user_pk!`/`controlled_attendance_id!` in `Mappings.tsx` (the direct cause of the original 422) are now **gone** — the payload no longer references either field. `createMapping()`'s call site uses only `enrollment_id`/`verified_by`/`verification_note`, all typed via the regenerated `BodyOf<"create_mapping_api_v1_mappings_post">`. No `as any` found in either file. `MappingEligibilityItem.device_user_pk`/`controlled_attendance_id` remain in the eligibility response model (still useful for UI display/debugging) but are no longer part of the mutation payload.

## Tests / count

534 passed, 0 failed (529 pre-existing baseline + 25 net new across `tests/test_mapping_evidence.py`, `tests/test_full_enrollment_e2e.py`, and additions to `tests/test_enrollment.py`, `tests/test_mapping_eligibility_fix.py`, minus a small net reduction from restructuring `tests/test_mapping_creation.py` to the new contract).

## OpenAPI / typecheck / build

Drift guard PASS (schema regenerated for the simplified `CreateMappingRequest` and the `Enrollment.rank`/`rank_metadata` fields from PromptID-016). `tsc --noEmit` PASS. `vite build` PASS. `git diff --check` clean.

## DB migration required

**NO.** All changes are code-only (new resolver module, simplified request contract, additive audit-event call). No schema change.

## Remaining known Enrollment defects / constraints

- No real Postgres integration test exists in this environment (documented above) — all backend tests mock the DB boundary, consistent with this entire project's established convention since PromptID 006. A true integration test against a live/ephemeral Postgres remains a legitimate future improvement, not attempted here to avoid the explicitly-prohibited "framework migration derail."
- Phases 11's full A–J incident-variant matrix was covered via a representative subset plus cross-references to existing PromptID 010/012/014 coverage, not 10 newly-written dedicated tests — the underlying invariants (single-owner device I/O, write-session gating, dedupe/cancel) were already regression-tested in those PromptIDs and re-verified green here.
- README.md / API_CONTRACT.md / SECURITY_RBAC.md / ENROLLMENT_SESSION_RUNBOOK.md were not updated this pass beyond this report and STATUS.md, given the scope already delivered — flagged as a follow-up documentation pass, not a functional gap.
