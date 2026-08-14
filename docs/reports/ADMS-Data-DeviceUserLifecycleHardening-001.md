# ADMS — DEVICE-USER LIFECYCLE HARDENING — FINAL REPORT

**PromptID:** `ADMS-Data-DeviceUserLifecycleHardening-001`
**Mode:** AUDIT → OWNER FEEDBACK (v2 redesign) → APPROVED → MIGRATE → IMPLEMENT → TEST → DEPLOY → LIVE VERIFY → DOCUMENT
**Date:** 2026-08-13/14

---

## 1. AGENT / TOOLING

- **agent/model:** Freebuff (Buffy) — deepseek-v4-flash
- **IDE:** Freebuff chat (TELEPHONE control workstation)
- **pty-mcp:** USED (stateful SSH to ai-brain)
- **temporary SSH transport scripts:** 0 (file-based python drivers piped over SSH)

## 2. MOTIVATION (OWNER FEEDBACK)

The initial plan proposed `account_incarnation` visibility only. **Owner rejected v1**: visibility alone does NOT close the identity-reuse risk. An inactive device_user that reappears with the same `(device_id, device_user_id)` must NOT inherit an old open-ended VERIFIED Human mapping. The revised plan (v2) was approved with the following semantics:

1. **Confirmed disappearance** → preserve row/history, set `inactive_at` once, **close any open VERIFIED mapping** for that device_user at the lifecycle boundary (`valid_to = now()`, canonical timestamp semantics), log explicit audit events, never delete mapping/history.
2. **Reappearance/recreation** → increment `account_incarnation`, reactivate, **never reopen/inherit the previous mapping**; new-incarnation attendance stays unmapped until a fresh controlled enrollment → VERIFIED mapping.
3. **Resolver safety** → attendance before `valid_to` still resolves to the historical Human; at/after the boundary does NOT; a new mapping can begin later without altering historical attribution (leveraged existing `[valid_from, valid_to)` model — **no parallel identity system**).
4. **Tests** for all boundary behaviors (fixture-only).
5. **Audit events**: `DEVICE_USER_INACTIVE`, `DEVICE_USER_REAPPEARED`, `MAPPING_CLOSED_BY_DEVICE_USER_LIFECYCLE`.
6. Migration 009 adds only `account_incarnation`.
7. Pre-migration: verify mapping 1 / user 1001 will NOT be accidentally closed (they are active), verified backup, no production lifecycle simulation, fixture-only reincarnation tests.

## 3. GIT

- starting HEAD: `6a6a08e`
- implementation commit: `a017d36`
- TELEPHONE == origin == ai-brain = **`a017d36`** · synchronized: YES · working trees clean

## 4. PRE-MIGRATION LIVE CHECK + BACKUP (owner requirement 7)

Verified live BEFORE any migration:

- **user 1001 (pk 7)**: `active=true`, `inactive_at NULL`, roster-seen → **will NOT be closed**
- **mapping 1**: VERIFIED, `valid_to NULL` → stays open
- Legacy users pk 1 / pk 2 already inactive (`inactive_at` set, `active=false`)
- **Pre-migration backup VERIFIED**: `adms_pre_lifecycle_hardening_20260813_233954.dump` — 66,957 bytes, SHA256 `61671ac6…`, `pg_restore -l` PASS (124 TOC lines)

## 5. MIGRATION 009 — ADDITIVE, REVERSIBLE

```sql
ALTER TABLE device_users ADD COLUMN IF NOT EXISTS account_incarnation INTEGER NOT NULL DEFAULT 1;
```

- **One field only.** Assessment: no other schema field required — the existing temporal `[valid_from, valid_to)` mapping model is the identity boundary; `inactive_at` already covers lifecycle state. **No parallel identity system.**
- Applied on ai-brain; verified `account_incarnation:integer` column live.

## 6. IMPLEMENTATION (`app/db.py`, `app/collector.py`)

### Confirmed disappearance (`reconcile_roster_lifecycle`, fires exactly once via `AND inactive_at IS NULL`)
1. Existing `UPDATE device_users SET inactive_at = now(), active = false ...` (unchanged)
2. **NEW** — close any open mapping in the same transaction with the same canonical `now()` boundary:
   `UPDATE employee_device_mappings SET valid_to = now(), updated_at = now() WHERE device_user_pk=%s AND mapping_status='VERIFIED' AND valid_to IS NULL`
3. **NEW** audit events: `DEVICE_USER_INACTIVE` (pk, user_id) + `MAPPING_CLOSED_BY_DEVICE_USER_LIFECYCLE` (pk, user_id, mapping_id, valid_to)
4. Row/history/mapping **preserved** — never deleted

### Reappearance (observed user with `inactive_at` set)
1. `account_incarnation = account_incarnation + 1` in the reactivation UPDATE (reactivates, clears `inactive_at`, touches `roster_last_seen_at`)
2. **NEW** audit event: `DEVICE_USER_REAPPEARED` (pk, user_id, incarnation=N)
3. **Mapping untouched — stays closed.** No reopening, no inheritance, no automatic mapping. New-incarnation attendance remains unmapped until a fresh controlled VERIFIED mapping.

### Resolver — no code change needed (verified semantics)
- scan `< valid_to` → historical Human · scan `>= valid_to` → `None`
- after a fresh mapping (`valid_from > old valid_to`) → new Human only from its `valid_from`; gap attendance stays `None`
- `create_verified_mapping` conflict check: open mapping blocks re-enrollment; closed mapping permits a fresh VERIFIED mapping

### `ensure_device_user` — behavior unchanged
Attendance never flips lifecycle state. Reactivation + incarnation bump are **roster-poll authoritative only**. Roster failure (None/exception) ≠ confirmed disappearance.

## 7. API EXPOSURE

- `account_incarnation` added to `GET /api/v1/device-users` and `GET /api/v1/device-users/{device_user_pk}` (repository + schema + frontend `DeviceUser` type + Devices page column).

## 8. TESTS

- 12 new hardening tests (`tests/test_device_user_lifecycle_hardening.py`, fixture-only — **no production lifecycle simulation**) + shared helper update in `tests/test_device_user_lifecycle.py` (`rowcount`):
  - active account normal polling: incarnation unchanged
  - confirmed disappearance closes open VERIFIED mapping (valid_to set once)
  - repeated empty-roster polls do not rewrite inactive_at/valid_to
  - reappearance increments incarnation exactly once + audit event
  - reappearance does NOT inherit old mapping
  - old attendance remains historically attributable (resolver `[valid_from, valid_to)` interval semantics)
  - new attendance after reappearance is NULL/unmapped until re-verification
  - same-Human re-enrollment still requires a fresh VERIFIED mapping (open mapping blocks, closed mapping allows)
  - different-Human reuse cannot resolve to previous Human
  - roster failure ≠ confirmed disappearance
- **Full suite: 375 passed + 18 subtests / 0 failed** (baseline 363; +12)
- Frontend: `tsc --noEmit` + `vite build` PASS

## 9. DEPLOYMENT (ai-brain)

- Synced to `a017d36` (ff-only)
- **Migration 009 applied** — `account_incarnation` column live
- Rebuilt **both** `adms_api` and `adms_zkteco_listener` (both import `app/db.py`)
- PostgreSQL/MQTT untouched (23h up, restarts 0)

## 10. LIVE VERIFICATION

- **All 3 device_users at `account_incarnation=1`** — proves no silent reuse so far: pk1 (user 2, inactive), pk2 (user 1, inactive), pk7 (user 1001, active)
- **API exposes `account_incarnation`** on all 3 rows (temp admin token via canonical auth, revoked after — **0 active tokens remain**)
- **Collector HEALTHY** (restarts 0), roster lifecycle operational: `Roster lifecycle: 1 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies, 0 mappings_closed` on the most recent poll
- **Audit trail**: 527 `ROSTER_LIFECYCLE` events; **zero** `DEVICE_USER_INACTIVE` / `DEVICE_USER_REAPPEARED` / `MAPPING_CLOSED_BY_DEVICE_USER_LIFECYCLE` — exactly correct, because user 1001 is active and present (no lifecycle boundary has fired)
- **Mapping 1 unchanged**: VERIFIED, valid_from `2026-08-12 08:47:37+00`, valid_to NULL, device_user_pk 7
- Write guard intact (403), GET side-effect free

## 11. SAFETY SUMMARY

- No production lifecycle simulation against real User 1001 — reincarnation verified via automated fixtures only
- No deletion, no pk changes, no mapping/attendance mutation, no device write
- Backend Foundation **REMAINS 100% COMPLETE**
- Identity authority unchanged: VERIFIED temporal mapping remains the sole identity authority; `account_incarnation` + lifecycle mapping closure make account reuse explicit, auditable, and identity-safe

## 12. FINAL

- repository verified: **YES** · database modified: YES (additive migration 009) · schema modified: YES (additive) · device modified: NO
- Human Master destructive deletion: NO · mapping count: 1 (unchanged) · automatic mappings: 0
- **Device-User Lifecycle Hardening: 100% COMPLETE** · tests: **375/375** (+18 subtests) · runtime: HEALTHY · safe to proceed: **YES** · blockers: NONE
