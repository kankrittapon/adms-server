# ADMS-DeviceCommandBus-TimeoutMargin-010

**Scope**: Fix the timeout-margin race between the API-side `DeviceCommandBus` outer wait and the Collector's real terminal-account-creation operation budget; add a distinct pre-mutation error category (`DEVICE_UNAVAILABLE` / `TerminalRosterUnavailable`); correct the record on the cause of User 1002's disappearance.

---

## 1. Owner-Issued Correction (authoritative, supersedes PromptID-009)

**WRONG (prior working hypothesis, PromptID-009, never committed to a permanent document)**: User 1002's disappearance from the terminal roster was attributed to a possible ZEM560 firmware persistence failure, `refresh_data()` behavior, Collector reconciliation, or another automatic/software-driven cause.

**CORRECT (owner's explicit, authoritative statement, this PromptID)**: Terminal User 1002 did **not** disappear spontaneously and no firmware/software/persistence bug caused it. The **OWNER manually deleted User 1002** from the physical ZEM560 terminal after an earlier browser operation reported an error. This is a manual action, not a device or software defect.

This correction:
- Supersedes the persistence interpretation carried informally from `ADMS-ZEM560-UserPersistence-HardwareAudit-009` (that investigation's report was delivered as a chat response only and was never written into a permanent file, so no file required amendment).
- Is recorded here as the permanent, authoritative account of the incident.
- Does **not** invalidate the separately-verified, code-level finding (§2) that pyzk's `set_user()` has no return statement — that remains true and remains the reason the *original erroneous browser error message* was shown in the first place. The two facts are independent: the browser's false failure report was a real software bug (fixed in commit `21ec113`); the owner's reaction to that false report — manually deleting the user — is what actually removed User 1002. Neither the ZEM560 firmware nor the Collector nor pyzk's persistence behavior deleted anything.

No hardware persistence experiment was performed for this incident, per explicit instruction.

## 2. Root Cause Recap (unchanged from prior work, restated for context)

`pyzk 0.9`'s `ZK.set_user()` has no `return` statement and therefore always evaluates as `None` (falsy) on success — a call that the ZEM560 correctly committed could still report failure to the caller. This was the origin of the original browser-visible error. The architectural fix (bounded roster read-back as the sole authority over `set_user()`'s return value) was implemented and deployed in `ADMS-ZEM560-TerminalAccount-Idempotency-Recovery-008` and is unchanged by this PromptID.

## 3. Problem Addressed in This PromptID

A live re-verification pass found that the API-side `DeviceCommandBus.execute()` outer wait (`timeout=10.0`, hardcoded) could fire *before* the Collector's own realistic worst-case operation budget for `CREATE_TERMINAL_ACCOUNT` had elapsed. The Collector's budget includes: an initial roster read, the `set_user()` call (which pyzk internally follows with a second device round-trip, `refresh_data()`), and a bounded, multi-attempt roster read-back with inter-attempt delays. Cross-referencing actual API/Collector logs from the most recent live attempt showed the outer 10s timeout raced ahead of a genuine Collector-side result — the caller saw a generic timeout instead of the Collector's actual (more specific and more useful) outcome.

Additionally, that same log cross-reference revealed the outer timeout can fire during **two different Collector-side phases** that the system did not previously distinguish:

- **Phase A — pre-mutation**: the initial roster read itself times out. `set_user()` is never called. No device state was touched.
- **Phase B — post-mutation**: `set_user()` was called (and possibly committed) but the bounded read-back could not confirm it within its own attempts.

Conflating these two under one generic timeout/error message meant the frontend could not tell an operator "nothing was attempted, safe to retry" (Phase A) from "something may have been written, verify before retrying" (Phase B) — a materially different, safety-relevant distinction.

## 4. Fix — Derived (Non-Arbitrary) Timeout Budget

`app/enrollment.py` now derives the outer timeout from the Collector's own real per-call socket timeout and retry/delay constants, rather than using an arbitrary number:

```
ZK_TIMEOUT (per-socket-call, pyzk)         = 5.0s
ZK_ROUNDTRIPS_PER_ROSTER_READ              = 2   (packet send/recv pairs for get_users())
ZK_ROUNDTRIPS_PER_SET_USER                 = 2   (set_user() + pyzk's internal refresh_data())
READBACK_RETRIES                           = 3
READBACK_DELAY_SECONDS                     = 2.0

initial_roster_read   = ZK_ROUNDTRIPS_PER_ROSTER_READ * ZK_TIMEOUT       = 10.0s
mutation               = ZK_ROUNDTRIPS_PER_SET_USER * ZK_TIMEOUT         = 10.0s
bounded_readback        = READBACK_RETRIES * ZK_ROUNDTRIPS_PER_ROSTER_READ * ZK_TIMEOUT = 30.0s
readback_delays          = (READBACK_RETRIES - 1) * READBACK_DELAY_SECONDS = 4.0s

collector_budget  = initial_roster_read + mutation + bounded_readback + readback_delays = 54.0s
transport_margin  = DEVICE_COMMAND_TRANSPORT_MARGIN_SECONDS                              = 3.0s

CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS = collector_budget + transport_margin      = 57.0s
```

The invariant `outer_command_timeout > maximum_collector_operation_budget + transport_margin` holds by construction and will re-derive automatically if `READBACK_RETRIES`, `READBACK_DELAY_SECONDS`, or the ZK socket timeout ever change — no second number to keep in sync by hand.

`app/api/routers/enrollments.py`'s MQTT/`DeviceCommandBus` branch of `create_terminal_account()` now passes `timeout=CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS` instead of the prior literal `10.0`.

## 5. Fix — Structured Pre-Mutation Error Category

New exception `TerminalRosterUnavailable(EnrollmentError)` in `app/enrollment.py`, raised when the *initial* pre-mutation roster read fails or times out — before `set_user()` is ever attempted. Distinct from `TerminalAccountUnconfirmed` (mutation was attempted, outcome unconfirmed) so callers can correctly say "no write was attempted" rather than implying a possibly-successful write.

Propagation path, each layer adding the next hop:

1. `app/enrollment.py`: `create_or_reconcile_terminal_account()` raises `TerminalRosterUnavailable` from the initial `device.get_users()` call's except clause.
2. `app/collector.py`: `handle_device_command()` catches `TerminalRosterUnavailable` **before** the generic `EnrollmentError` branch (required, since it's a subclass) and reports `error_code="DEVICE_UNAVAILABLE"` over MQTT.
3. `app/device_command_bus.py`: `DeviceCommandError.error_code` carries `"DEVICE_UNAVAILABLE"` back to the API process.
4. `app/api/routers/enrollments.py`: both the `device_executor` test-injection branch and the real MQTT branch map `DEVICE_UNAVAILABLE` explicitly to `HTTP 503`, distinct from `TERMINAL_ACCOUNT_UNCONFIRMED`'s own 503 (same status code, different `code` field — the frontend branches on `code`, not status).
5. `frontend/src/pages/Enrollments.tsx`: new `terminalUnavailableTitle`/`terminalUnavailableBody` copy (TH/EN, `frontend/src/i18n/{types,en,th}.ts`), shown only for this code, explicitly stating no account was created or changed.

## 6. Fix — DeviceCommandBus Hardening (Late-Response / Overlapping-Retry Safety)

Reviewed and hardened during this phase (self-identified during implementation, not from an owner-reported bug):

- **Dedupe key is not released on the caller's own timeout.** If the outer wait times out, the Collector may still genuinely be executing the command; releasing the busy-lock immediately would let a subsequent click dispatch a second `set_user()`-class command while the first is still in flight on the physical device. `_inflight_keys` now stores `{"command_id", "expires_at"}` and is released only when the real response arrives (on time or late, via `_on_message` → `_release_dedupe_key_for_command`) or when a bounded safety-net `expires_at` (derived from the caller's own `timeout`) has passed with no response ever received.
- **Atomic check-and-reserve.** The busy-check and the new registration happen inside a single `with self._lock:` critical section, preventing a TOCTOU race where two concurrent callers could both observe "available" and both dispatch.
- **Late responses are logged, not silently dropped**, and still release the dedupe key — valuable diagnostic evidence that a prior timeout was "late completion," not a true failure.

Proven by tests, not just by design review — see §8.

## 7. What Was Deliberately Not Investigated

Per the owner's explicit instruction: no hardware persistence experiment was performed; the OWNER's manual deletion of User 1002 was not investigated as a device bug; no re-attribution to firmware/software was attempted. Enrollment #2 was not touched, edited, or recovered as part of this PromptID.

## 8. Test Coverage

`tests/test_timeout_margin.py` (new, 20 tests) plus the existing `tests/test_device_command_bus.py` dedupe/late-response tests (updated for the new `_inflight_keys` dict shape) cover the required matrix:

- Pre-mutation roster-read failure raises `TerminalRosterUnavailable`; `set_user()` is provably never called.
- `TerminalRosterUnavailable` is a distinct `EnrollmentError` subclass, not conflated with `TerminalAccountConflict`/`TerminalAccountUnconfirmed`.
- The derived timing-budget formula matches the actual computed constants (54.0s collector budget, 57.0s outer timeout, positive 3.0s margin).
- Collector's except-chain orders `TerminalRosterUnavailable` before the generic `EnrollmentError` catch and maps it to `DEVICE_UNAVAILABLE`.
- Both API router branches map `DEVICE_UNAVAILABLE` explicitly and distinctly from `TERMINAL_ACCOUNT_UNCONFIRMED`; the MQTT branch uses the derived timeout constant, not a literal.
- A dedupe key with an expired safety-net window auto-recovers (new dispatch allowed); a non-expired key still rejects with `DEVICE_COMMAND_IN_PROGRESS`; `expires_at` is correctly derived from the caller's own `timeout`.
- RBAC/write-session/`API_WRITE_ENABLED` gating is unaffected by this phase's changes (regression checks).
- Frontend i18n TH/EN parity for the new `terminalUnavailable*` keys.

Full suite: **467 passed, 0 failed** (447 pre-existing + 20 new), OpenAPI drift guard PASS (no schema changes — the new timeout constant is backend-internal only), `tsc --noEmit` PASS, `vite build` PASS.

## 9. Deployment

`api`, `web`, and `listener` containers rebuilt/recreated. No database migration — this phase is pure code (error semantics + timeout derivation), consistent with the pre-implementation audit's expectation that none would be needed.

## 10. Owner Gate — Enrollment #2 Canonical Recovery

Not executed. Presented separately per the required format; no real terminal write (`set_user()`/`delete_user()`) has occurred on production hardware as part of this PromptID beyond what this document itself describes as already-deployed code changes.
