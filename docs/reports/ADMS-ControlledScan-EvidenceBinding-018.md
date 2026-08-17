# ADMS-ControlledScan-EvidenceBinding-018

**Scope**: Close the Controlled Scan evidence gap permanently — replace "estimate now, rediscover-by-timestamp-proximity later" with server-side evidence binding at Step 4 itself.

## Why 16:42:00 vs 16:44:18 happened

Traced through `frontend/src/pages/Enrollments.tsx` and `app/enrollment.py::confirm_controlled_scan` (pre-018): the Step 4 `datetime-local` input's `value` was auto-filled from the SSE `lastEvent.scan_time` via `new Date(lastEvent.scan_time).toISOString().slice(0, 16)` — truncating to minute precision even when it *was* pre-filled from a real detected event — and remained freely editable by the operator afterward. The stored `controlled_scan_time` (16:42:00, exactly on the minute — the unmistakable signature of a `datetime-local` value with no seconds) was therefore always an **operator/browser estimate**, never a value read back from `attendance_logs` itself. Enrollment #4's `ENROLLMENT_SCAN_CONFIRMED` audit event fired at 16:42:34.9 — 34 seconds after the recorded estimate — while the actual successful attendance scan landed at 16:44:18, over a minute *after* the confirm click. The most likely sequence: the operator clicked confirm just as (or just before) the person began the physical scan, entering an early estimate, and the terminal's real, successful scan was recorded moments later. This is not provable as the exact human sequence with certainty (no browser-side logs exist), but it is fully consistent with all available evidence and requires no other explanation — critically, it does not matter *why* the estimate was off, because the architectural fix removes the estimate step entirely.

## Final evidence source of truth

`confirm_controlled_scan(cfg, enrollment_id, operator, notes=None)` — **no `scan_time` parameter at all**. It resolves the real attendance evidence itself:
1. Confirms `controlled_scan_window_until` is set.
2. Reads `window_start` = the enrollment row's own `updated_at` at the exact moment `start_controlled_scan_window()` committed the `CONTROLLED_SCAN_PENDING` transition (read before this call's own UPDATE overwrites it — **no schema migration**, the column already existed and was already written by `_transition()`; this PromptID's only DB-adjacent change is adding `updated_at` to the Python-side `_ENROLLMENT_COLUMNS` SELECT list).
3. Resolves `device_user_pk` from `(device_id, reserved_device_user_id)`, requiring `device_users.active = true`.
4. Queries `attendance_logs WHERE device_user_pk = %s AND scan_time BETWEEN window_start AND window_until ORDER BY scan_time ASC LIMIT 1` — device/terminal-user constraint applies structurally via `device_user_pk`; deterministic tie-break is "earliest scan in the window wins."
5. Stores that row's **exact** `scan_time` as `controlled_scan_time` — thereafter always bit-for-bit equal to real terminal evidence, never an estimate.

**Manual scan time removed**: yes — `ScanConfirmationRequest` no longer has a `scan_time` field; the `<input type="datetime-local">` is gone from `Enrollments.tsx`; the confirm button calls the action with an empty payload. The SSE-detected event is now purely a display indicator (`detectedScan`), never sent to the server.

## Step 5 invariant

Unchanged from PromptID 017 (`mark_ready_for_mapping` still resolves evidence via `app.mapping_evidence.resolve_controlled_attendance_id` before allowing the transition) — but now benefits from **exact-match** resolution, since `controlled_scan_time` is always the real attendance row's own value (delta = 0), not an approximation the ±120s window has to bridge.

## Step 6 behavior

Unchanged from PromptID 017: `create_verified_mapping(cfg, enrollment_id, verified_by, verification_note)` — server-derived evidence throughout.

## Enrollment #4 reconciliation eligibility

**Proven eligible**, via read-only production inspection (no mutation performed):
- Device matches: `device_id=1`. ✅
- Terminal user matches: `reserved_device_user_id=1004` → `device_user_pk=29`. ✅
- Scan occurred inside the real window: `controlled_scan_window_until = 16:46:42.29`, so `window_start ≈ 16:41:42.29` (5-minute default window) → real scan at `16:44:18` falls inside `[16:41:42, 16:46:42]`. ✅
- Account incarnation matches: `device_users.account_incarnation = 1`, `created_at = 16:41:27` (matches `TERMINAL_ACCOUNT_CREATED`), unchanged since — single incarnation throughout. ✅
- No competing scan/evidence ambiguity: exactly one `attendance_logs` row exists for `device_user_pk=29` (`id=38`, `scan_time=16:44:18`). ✅

**Proposed canonical one-time reconciliation path** (not executed — requires a separate owner gate): re-run the same resolution `confirm_controlled_scan` would have performed, using the historically-reconstructed window `[16:41:42.29, 16:46:42.29]` instead of the (now-overwritten) enrollment row's `updated_at`, to update `controlled_scan_time` from `16:42:00` to `16:44:18` — a single, audited, evidence-backed correction, not a blind manual edit. This should be implemented as a small, explicit one-time admin/CLI operation (not a general-purpose "edit any enrollment" backdoor), logging a distinct audit event (e.g. `ENROLLMENT_SCAN_EVIDENCE_RECONCILED`) referencing this PromptID and the specific attendance_id, and should only ever be exercised under explicit owner approval per enrollment — not automated.

## Tests

547 passed, 0 failed (534 pre-existing baseline + 13 net new, in `tests/test_controlled_scan_evidence_binding.py` plus updates to `tests/test_enrollment.py` and `tests/test_full_enrollment_e2e.py` for the new `confirm_controlled_scan` signature/semantics). Covers: wrong-user scans never considered (structural device_user_pk scoping), correct scan binds attendance_id, deterministic earliest-wins tie-break, out-of-window rejection, inclusive boundary timestamps, tz-aware throughout, full sub-second precision preserved, no `scan_time` parameter in the signature or frontend payload, no proximity-resolver import on the normal path, SSE event is display-only, inactive/recycled device_user_pk rejected.

## OpenAPI / typecheck / build

Drift guard PASS (schema regenerated: `ScanConfirmationRequest` loses `scan_time`, `EnrollmentTransitionResult` gains `controlled_scan_time`). `tsc --noEmit` PASS. `vite build` PASS. `git diff --check` clean.

## Migration requirement

**NO.** `updated_at` already existed on `device_user_enrollments` (written by every `_transition()` call since the table's original migration) — this PromptID only adds it to the Python-side SELECT column list. No new column, no schema change.

## Commit

Pending — committed after this report, per instruction: implement/test/commit/push, but STOP before production deployment.
