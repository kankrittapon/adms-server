# ADMS-Data-DeviceUserLifecycle-002

**PromptID:** ADMS-Data-DeviceUserLifecycle-002
**Date:** 2026-08-12
**Mode:** WRITE (limited application lifecycle)
**Status:** LIVE VERIFIED
**Commit:** 973d97901200c2db151583cd589fc08bcf4d4786

---

## 1. Objective

Implement Device User roster lifecycle detection so ADMS can observe terminal roster state and maintain lifecycle metadata (`roster_last_seen_at`, `inactive_at`) without deleting historical identity.

## 2. Implementation

### Files Modified

| File | Change |
|------|--------|
| `app/db.py` | Added `reconcile_roster_lifecycle()` function |
| `app/config.py` | Added `roster_poll_interval_seconds` config field (default 300s) |
| `app/collector.py` | Added `perform_roster_lifecycle_check()` method, roster snapshot in BACKFILLING, periodic polling in LIVE |
| `tests/test_device_user_lifecycle.py` | New: 18 tests covering all lifecycle scenarios |

### `reconcile_roster_lifecycle(cfg, device_id, observed_users)`

- **Input:** List of dicts with `user_id` (str), `uid` (int|None), `name` (str|None)
- **Behavior:**
  - Loads known `device_users` for the specified `device_id`
  - For observed users: ensure/resolve device_user, update `roster_last_seen_at = now()`, clear `inactive_at` (REAPPEARED if was inactive)
  - For missing users: set `inactive_at = now()` if currently NULL (preserve original if already inactive)
  - Detect UID changes (log warning, no auto-mapping)
  - Atomic transaction per device
- **Returns:** Dict with `observed`, `new_users`, `marked_inactive`, `reappeared`, `uid_anomalies`
- **Safety:** No human_employees created, no mappings created, no attendance modified, no deletions

### Collector Integration

- **BACKFILLING state:** After backfill completes, before transition to LIVE, calls `perform_roster_lifecycle_check()`
- **LIVE state:** Periodic polling — when `time.time() - last_roster_poll_monotonic >= cfg.roster_poll_interval_seconds`, calls `perform_roster_lifecycle_check()` during idle ping (attendance is None)
- **Failure handling:** If `get_users()` raises an exception or returns None, NO lifecycle updates are made — UNKNOWN state is NOT the same as an empty roster
- **Empty roster:** A successful read returning 0 users IS a valid empty roster — all known active users are marked inactive

### Health File

Added roster lifecycle telemetry fields:
- `last_roster_poll_at`
- `last_roster_poll_success`
- `last_roster_user_count`
- `last_roster_marked_inactive`
- `last_roster_reappeared`
- `last_roster_uid_anomalies`

## 3. Tests

| Test Class | Test | Description |
|------------|------|-------------|
| TestRosterLifecycle | test_successful_roster_with_known_user | Known user present → roster_last_seen_at updated |
| | test_new_user_observed | New user → ensure_device_user called |
| | test_user_missing_from_successful_roster | Active user absent → inactive_at set |
| | test_already_inactive_user_remains_inactive | Already inactive → inactive_at NOT re-updated |
| | test_inactive_user_reappears | Inactive user returns → inactive_at cleared |
| | test_empty_successful_roster | Empty roster → all active users marked inactive |
| | test_multiple_devices_isolation | Device A users not affected by device B roster |
| | test_uid_change_detected | UID change → anomaly logged, no auto-mapping |
| | test_uid_same_no_anomaly | Same UID → no anomaly |
| | test_identity_safety_no_human_employees | No human_employees/mappings/attendance/deletions |
| | test_commit_called | Transaction committed |
| | test_mixed_scenario | Mixed: known+missing+inactive+new |
| TestCollectorRosterLifecycle | test_successful_roster_check | Collector performs check successfully |
| | test_roster_read_failure_no_update | Exception → reconcile NOT called |
| | test_roster_returns_none_no_update | None → treated as FAILED |
| | test_empty_roster_success | Empty list → reconcile IS called |
| | test_no_connection_skips_check | No ZK connection → skip gracefully |

**Result:** 105/105 PASS (87 existing + 18 new), 0 failures

## 4. Deployment

### Pre-write Backup
- **File:** `backups/adms_pre_device_user_lifecycle_20260812_111700.dump`
- **Size:** 45,049 bytes
- **SHA256:** `a7890981cf1631dc87585cbe05eddaafdfb83cdd1d01b87505fbd86e7be2bf2d`
- **Verified:** pg_restore -l confirmed 79 TOC entries, CUSTOM format, pg_dump 16.14

### Git
- **Commit:** `973d97901200c2db151583cd589fc08bcf4d4786`
- **Message:** `feat: add device user roster lifecycle tracking (# PromptID: ADMS-Data-DeviceUserLifecycle-002)`
- **Pushed:** origin/main (b2b2b42..973d979)
- **ai-brain synced:** `git pull --ff-only origin main` → fast-forward to 973d979

### Docker
- **Build:** `docker compose build listener` — successful (cached layers, new app/ code)
- **Deploy:** `docker compose up -d listener` — listener recreated, postgres and mqtt untouched

## 5. Live Verification

### First Roster Poll (BACKFILLING → LIVE transition)

```
2026-08-12 04:31:54,070 [INFO] Roster snapshot: 0 users observed on terminal.
2026-08-12 04:31:54,099 [INFO] INACTIVE: device_user_id=2 (pk=1) absent from successful roster. Marked inactive_at = now().
2026-08-12 04:31:54,100 [INFO] INACTIVE: device_user_id=1 (pk=2) absent from successful roster. Marked inactive_at = now().
2026-08-12 04:31:54,104 [INFO] Roster lifecycle reconciliation complete for device_id=1: 0 observed, 0 new, 2 marked_inactive, 0 reappeared, 0 uid_anomalies.
2026-08-12 04:31:54,104 [INFO] Roster lifecycle: 0 observed, 0 new, 2 marked_inactive, 0 reappeared, 0 uid_anomalies.
2026-08-12 04:31:54,119 [INFO] State transition: BACKFILLING -> LIVE
```

### Database State After First Poll

| device_user_id | device_uid | active | roster_last_seen_at | inactive_at |
|----------------|------------|--------|---------------------|-------------|
| 1 | NULL | false | NULL | 2026-08-12 04:31:54.095625+00 |
| 2 | NULL | false | NULL | 2026-08-12 04:31:54.095625+00 |

### Row Counts (unchanged except sync_events +1)

| Table | Before | After |
|-------|--------|-------|
| device_users | 2 | 2 |
| attendance_logs | 7 | 7 |
| devices | 1 | 1 |
| human_employees | 120 | 120 |
| employee_device_mappings | 0 | 0 |
| sync_events | 4 | 5 (+1 ROSTER_LIFECYCLE) |

### Health File

```json
{
  "state": "LIVE",
  "device_connected": true,
  "db_status": "HEALTHY",
  "last_roster_poll_at": "2026-08-12T04:31:54.020036",
  "last_roster_poll_success": "2026-08-12T04:31:54.070608",
  "last_roster_user_count": 0,
  "last_roster_marked_inactive": 2,
  "last_roster_reappeared": 0,
  "last_roster_uid_anomalies": 0
}
```

### Post-write Backup
- **File:** `backups/adms_post_device_user_lifecycle_20260812_113502.dump`
- **Size:** 45,172 bytes
- **SHA256:** `390832323c56a41e1f4f4340badac653ddccda636edf30b560922660d1b1a4ae`

## 6. Safety Verification

- **No terminal writes:** `get_users()` is READ-ONLY, no `set_user()`, no `enroll_user()`
- **No fingerprint operations:** None
- **No mapping creation:** employee_device_mappings count = 0 (unchanged)
- **No schema migration:** No SQL migration files applied
- **No production enrollment:** None
- **No deletions:** device_users count = 2 (unchanged), attendance_logs count = 7 (unchanged)
- **No human_employees created:** Count = 120 (unchanged)
- **PostgreSQL not rebuilt:** Container remained running
- **MQTT not rebuilt:** Container remained running

## 7. Next Authorized PromptID

`ADMS-Data-DeviceUserLifecycle-003` (READ-ONLY)

---

FINAL

PromptID: ADMS-Data-DeviceUserLifecycle-002

repository verified: YES
database modified: YES (device_users.lifecycle fields updated)
application modified: YES (collector.py, db.py, config.py)
device modified: NO
tests: PASS (105/105)
runtime verified: YES (LIVE, roster lifecycle active)
commit created: YES (973d979)
push completed: YES (origin/main)

next authorized PromptID: ADMS-Data-DeviceUserLifecycle-003
safe to proceed: YES
blockers: NONE

STOP.