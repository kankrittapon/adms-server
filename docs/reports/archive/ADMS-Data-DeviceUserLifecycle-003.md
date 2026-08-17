# ADMS-Data-DeviceUserLifecycle-003: Device User Lifecycle Live Verification Checkpoint

> **PromptID**: `ADMS-Data-DeviceUserLifecycle-003`
> **Date**: 2026-08-12
> **Type**: READ-ONLY LIVE VERIFICATION CHECKPOINT + DOCUMENTATION WRITE ONLY
> **Mode**: READ-ONLY (no source/database/terminal/device modification)
> **Scope**: Verify and checkpoint the Device User lifecycle implementation from `ADMS-Data-DeviceUserLifecycle-002` (commits `973d979` + `91c7012`)

---

## 1. Executive Summary

**VERDICT: PASS**

All 11 critical properties verified. The Device User Lifecycle implementation (`reconcile_roster_lifecycle()` + `perform_roster_lifecycle_check()`) is LIVE, HEALTHY, and operating correctly. `inactive_at` is stable across 13+ periodic roster polls (300s interval). No terminal writes, no DB mutations by agent, no enrollment, no mappings created. Human Master unchanged. Backups verified. 105/105 tests pass.

---

## 2. Git Baseline

| Node | Branch | Commit | Working Tree |
|------|--------|--------|-------------|
| TELEPHONE (local) | `main` | `91c7012c744b1c8bdac1ba4e604bd0b0a4d7199a` | Clean (only `.agent/` untracked) |
| origin | `main` | `91c7012c744b1c8bdac1ba4e604bd0b0a4d7199a` | N/A |
| ai-brain | `main` | `91c7012c744b1c8bdac1ba4e604bd0b0a4d7199a` | Clean |

**Ancestry**: Contains `973d979` (implementation) and `91c7012` (documentation).

**Evidence Classification**: VERIFIED LIVE (queried via `git rev-parse HEAD` on all 3 nodes)

---

## 3. Runtime Baseline

### Docker Containers

| Container | Image | Status | Uptime | Restart Count |
|-----------|-------|--------|--------|---------------|
| `adms_postgres` | `postgres:16-alpine` | Up (healthy) | 22 hours | 0 |
| `adms_mqtt` | `eclipse-mosquitto:2` | Up | 21 hours | 0 |
| `adms_zkteco_listener` | `adms-server-listener` | Up (healthy) | ~1 hour | 0 |

**Evidence Classification**: VERIFIED LIVE (`docker compose ps` + `docker inspect --format '{{.RestartCount}}'`)

### Collector Health File (`/tmp/collector_health.json`)

```json
{
  "schema_version": "1.0",
  "updated_at": "2026-08-12T05:40:29.265870+00:00",
  "state": "LIVE",
  "loop_alive": true,
  "device_connected": true,
  "db_status": "HEALTHY",
  "mqtt_status": "UNKNOWN",
  "reconnect_attempt": 0,
  "current_backoff_seconds": 0.0,
  "last_connect_success": "2026-08-12T04:31:53.819868",
  "last_connect_failure": null,
  "last_backfill_started_at": "2026-08-12T04:31:53.820639",
  "last_backfill_completed_at": "2026-08-12T04:31:53.998983",
  "last_event_received": null,
  "last_event_persisted": null,
  "last_roster_poll_at": "2026-08-12T05:36:58.946035",
  "last_roster_poll_success": "2026-08-12T05:36:59.009348",
  "last_roster_user_count": 0,
  "last_roster_marked_inactive": 0,
  "last_roster_reappeared": 0,
  "last_roster_uid_anomalies": 0
}
```

**Evidence Classification**: VERIFIED LIVE (`docker exec adms_zkteco_listener cat /tmp/collector_health.json`)

---

## 4. Roster Lifecycle Log Evidence

### First Poll (Initial Transition)

```
2026-08-12 04:31:54,104 [INFO] app.db: Roster lifecycle reconciliation complete for device_id=1: 0 observed, 0 new, 2 marked_inactive, 0 reappeared, 0 uid_anomalies.
```

### Subsequent Periodic Polls (300s interval)

| Poll Time (UTC) | Observed | New | Marked Inactive | Reappeared | UID Anomalies |
|-----------------|----------|-----|-----------------|------------|---------------|
| 04:36:54 | 0 | 0 | **0** | 0 | 0 |
| 04:41:55 | 0 | 0 | **0** | 0 | 0 |
| 04:46:55 | 0 | 0 | **0** | 0 | 0 |
| 04:51:55 | 0 | 0 | **0** | 0 | 0 |
| 04:56:56 | 0 | 0 | **0** | 0 | 0 |
| 05:01:56 | 0 | 0 | **0** | 0 | 0 |
| 05:06:56 | 0 | 0 | **0** | 0 | 0 |
| 05:11:57 | 0 | 0 | **0** | 0 | 0 |
| 05:16:57 | 0 | 0 | **0** | 0 | 0 |
| 05:21:57 | 0 | 0 | **0** | 0 | 0 |
| 05:26:58 | 0 | 0 | **0** | 0 | 0 |
| 05:31:58 | 0 | 0 | **0** | 0 | 0 |
| 05:36:59 | 0 | 0 | **0** | 0 | 0 |

**Critical Finding**: After the initial poll marked 2 users inactive at 04:31:54, ALL 13 subsequent polls show `0 marked_inactive`. This proves `inactive_at` is NOT being rewritten on every poll — the `WHERE inactive_at IS NULL` guard is working correctly.

**Evidence Classification**: VERIFIED LIVE (`docker compose logs --tail=300 listener 2>&1 | grep -i roster`)

---

## 5. Database Baseline

### Row Counts

| Table | Expected | Actual | Match |
|-------|----------|--------|-------|
| `human_employees` | 120 | 120 | YES |
| `human_employee_sources` | 120 | 120 | YES |
| `devices` | 1 | 1 | YES |
| `device_users` | 2 | 2 | YES |
| `employee_device_mappings` | 0 | 0 | YES |
| `attendance_logs` | 7 | 7 | YES |
| `attendance_logs` (employee_id IS NULL) | 7 | 7 | YES |
| `attendance_logs` (employee_id IS NOT NULL) | 0 | 0 | YES |
| `sync_events` | — | 17 | — |

### Duplicate Attendance Check

- Duplicate `(user_id, device_ip, scan_time)` groups: **0**

**Evidence Classification**: VERIFIED LIVE (`docker exec adms_postgres psql -U adms -d adms -t -A -c "..."`)

---

## 6. Human Master Integrity

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| UUID uniqueness (`count(DISTINCT employee_id)`) | 120 | 120 | PASS |
| Orphan provenance (`human_employee_sources` → `human_employees` LEFT JOIN NULL) | 0 | 0 | PASS |
| Duplicate source keys (`(source_system, source_record_key)` duplicates) | 0 | 0 | PASS |

**Evidence Classification**: VERIFIED LIVE

---

## 7. Device Users T1/T2 Comparison (inactive_at Stability)

### T1 Capture (~05:27 UTC)

| device_user_id | active | roster_last_seen_at | inactive_at |
|----------------|--------|---------------------|-------------|
| 1 | f | NULL | `2026-08-12 04:31:54.095625+00` |
| 2 | f | NULL | `2026-08-12 04:31:54.095625+00` |

### T2 Capture (~05:42 UTC, after 3+ additional roster polls)

| device_user_id | active | roster_last_seen_at | inactive_at |
|----------------|--------|---------------------|-------------|
| 1 | f | NULL | `2026-08-12 04:31:54.095625+00` |
| 2 | f | NULL | `2026-08-12 04:31:54.095625+00` |

### Comparison

| Property | T1 | T2 | Stable? |
|----------|----|----|---------|
| User 1 `inactive_at` | `04:31:54.095625+00` | `04:31:54.095625+00` | **YES** |
| User 2 `inactive_at` | `04:31:54.095625+00` | `04:31:54.095625+00` | **YES** |
| User 1 `active` | f | f | **YES** |
| User 2 `active` | f | f | **YES** |
| User 1 `roster_last_seen_at` | NULL | NULL | **YES** |
| User 2 `roster_last_seen_at` | NULL | NULL | **YES** |

**Critical Finding**: `inactive_at` is identical between T1 and T2. The `WHERE inactive_at IS NULL` guard in `reconcile_roster_lifecycle()` prevents rewriting. `roster_last_seen_at` remains NULL for absent users (only updated for observed users).

**Evidence Classification**: VERIFIED LIVE (two independent DB queries separated by 15+ minutes and 3+ roster poll cycles)

---

## 8. ROSTER_LIFECYCLE Sync Events

10 most recent `ROSTER_LIFECYCLE` sync events (DESC):

| created_at (UTC) | message |
|-------------------|---------|
| 2026-08-12 05:31:58 | Roster lifecycle: 0 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies. |
| 2026-08-12 05:26:58 | Roster lifecycle: 0 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies. |
| 2026-08-12 05:21:57 | Roster lifecycle: 0 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies. |
| 2026-08-12 05:16:57 | Roster lifecycle: 0 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies. |
| 2026-08-12 05:11:57 | Roster lifecycle: 0 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies. |
| 2026-08-12 05:06:56 | Roster lifecycle: 0 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies. |
| 2026-08-12 05:01:56 | Roster lifecycle: 0 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies. |
| 2026-08-12 04:56:56 | Roster lifecycle: 0 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies. |
| 2026-08-12 04:51:55 | Roster lifecycle: 0 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies. |
| 2026-08-12 04:46:55 | Roster lifecycle: 0 observed, 0 new, 0 marked_inactive, 0 reappeared, 0 uid_anomalies. |

**Evidence Classification**: VERIFIED LIVE

---

## 9. Source Verification

### `app/db.py` — `reconcile_roster_lifecycle()` (line 277)

Verified semantics:
- ✅ **Successful roster snapshot**: Takes `observed_users` list of dicts `{user_id, uid, name}` from successful `get_users()`
- ✅ **Atomic per-device reconciliation**: Single transaction, `conn.commit()` at end
- ✅ **Observed users**: Ensure/resolve device_user, update `roster_last_seen_at = now()`, clear `inactive_at = NULL` (REAPPEARED if was inactive), set `active = true`
- ✅ **Missing users**: `SET inactive_at = now(), active = false WHERE inactive_at IS NULL` — preserves original `inactive_at` if already set
- ✅ **UID change detection**: Compares `known["device_uid"]` vs `obs_uid`, logs warning, no auto-mapping
- ✅ **No deletions**: No `DELETE` statements
- ✅ **No mappings**: No `employee_device_mappings` writes
- ✅ **No human_employees changes**: No `human_employees` writes
- ✅ **Device scoping**: `WHERE device_id = %s` — multi-device isolation

### `app/collector.py` — `perform_roster_lifecycle_check()` (line 186)

Verified semantics:
- ✅ **Failure-safe**: Catches ALL exceptions, NO lifecycle updates on failure
- ✅ **None check**: `if raw_users is None: return` — treats None as FAILED
- ✅ **No connection check**: `if not self.connection: return`
- ✅ **Called in BACKFILLING** (line 329): After backfill, before LIVE transition
- ✅ **Called in LIVE** (line 371): Every `roster_poll_interval_seconds` during idle ping when `attendance is None`
- ✅ **Health fields updated**: `last_roster_poll_at`, `last_roster_poll_success`, `last_roster_user_count`, `last_roster_marked_inactive`, `last_roster_reappeared`, `last_roster_uid_anomalies`

### `app/config.py` — `roster_poll_interval_seconds` (line 32, 59)

Verified:
- ✅ `roster_poll_interval_seconds: int` field in frozen dataclass
- ✅ Default 300 from `ROSTER_POLL_INTERVAL_SECONDS` env var

**Evidence Classification**: FILE EVIDENCE (source code inspected, matches deployed runtime behavior confirmed by logs)

---

## 10. Test Suite Execution

```
105 passed in 17.85s
```

### Lifecycle Test Coverage (18 tests in `tests/test_device_user_lifecycle.py`)

| Test Class | Test | Scenario |
|-----------|------|----------|
| `TestRosterLifecycle` | `test_successful_roster_with_known_user` | Known user observed → roster_last_seen_at updated, inactive_at cleared |
| | `test_new_user_observed` | New user in roster → ensure_device_user, new_users count |
| | `test_user_missing_from_successful_roster` | Known user absent → inactive_at set, active=false |
| | `test_already_inactive_user_remains_inactive` | Already inactive → inactive_at NOT rewritten |
| | `test_inactive_user_reappears` | Inactive user reappears → inactive_at cleared, reappeared count |
| | `test_empty_successful_roster` | Empty roster (0 users) → all known marked inactive |
| | `test_multiple_devices_isolation` | Device A roster doesn't affect Device B users |
| | `test_uid_change_detected` | UID change → uid_anomalies count, warning logged |
| | `test_uid_same_no_anomaly` | Same UID → no anomaly |
| | `test_identity_safety_no_human_employees` | No human_employees writes during reconciliation |
| | `test_commit_called` | Transaction committed |
| | `test_mixed_scenario` | Multiple users, mixed states |
| `TestRosterFailureSafety` | `test_roster_failure_no_lifecycle_update` | Roster read failure → NO lifecycle updates |
| `TestCollectorRosterLifecycle` | `test_successful_roster_check` | Full collector check with mocked ZK |
| | `test_roster_read_failure_no_update` | ZK exception → no update |
| | `test_roster_returns_none_no_update` | None return → no update |
| | `test_empty_roster_success` | Empty roster → successful reconciliation |
| | `test_no_connection_skips_check` | No connection → skip |

**Evidence Classification**: VERIFIED LIVE (`python -m pytest tests/ -v`)

---

## 11. Recovery Point Verification

### Post-Lifecycle Backup

| Property | Value |
|----------|-------|
| Filename | `adms_post_device_user_lifecycle_20260812_113502.dump` |
| Size | 45,172 bytes |
| SHA256 | `390832323c56a41e1f4f4340badac653ddccda636edf30b560922660d1b1a4ae` |
| Format | `pg_dump` Custom (PGDMP_V1) |
| TOC Entries | 79 |
| `pg_restore -l` | PASS (archive readable) |
| Database Version | 16.14 |
| Dumped by | pg_dump 16.14 |

### Pre-Lifecycle Backup

| Property | Value |
|----------|-------|
| Filename | `adms_pre_device_user_lifecycle_20260812_111700.dump` |
| Size | 45,049 bytes |
| SHA256 | `a7890981cf1631dc87585cbe05eddaafdfb83cdd1d01b87505fbd86e7be2bf2d` |

### All Backups Preserved (7 archives)

1. `adms_post_device_user_lifecycle_20260812_113502.dump` (45,172 bytes)
2. `adms_post_excel_import_20260811_121449.dump` (7,389 bytes)
3. `adms_post_timestamp_timezone_20260811_184500.dump` (45,033 bytes)
4. `adms_pre_device_user_lifecycle_20260812_111700.dump` (45,049 bytes)
5. `adms_pre_rebuild_20260811_150710.dump` (11,563 bytes)
6. `adms_pre_timestamp_timezone_20260811_183000.dump` (44,980 bytes)
7. `adms_reconstructed_authoritative_20260811_153725.dump` (44,980 bytes)

**Evidence Classification**: VERIFIED LIVE (`ls -la`, `sha256sum`, `pg_restore -l`)

---

## 12. Runtime Observation

### Error Scan (last 100 log lines)

- **1 WARNING**: `app.db: failed to determine attendance status: too many values to unpack (expected 2)` — this is the known NON-BLOCKING `parse_time()` bug (`ADMS-Collector-AttendanceParseTime-001`), only affects `status` field, does NOT affect `scan_time` or lifecycle.
- **0 ERROR / CRITICAL / TRACEBACK** entries

### Terminal Write Attempts

- `set_user|delete_user|enroll|create_user` in logs: **0 matches** (NONE)

### UID Anomalies

- All polls: `0 uid_anomalies`

### DB Exceptions

- `psycopg|operationalerror|programmingerror` in logs: **0 matches** (NONE)

### Restart Loops

- All 3 containers: `RestartCount = 0`

**Evidence Classification**: VERIFIED LIVE

---

## 13. 11 Critical Properties Summary

| # | Property | Expected | Actual | Result |
|---|----------|----------|--------|--------|
| 1 | Successful empty roster handling | 0 users → all known marked inactive | First poll: 0 observed → 2 marked_inactive | **PASS** |
| 2 | Users 1 & 2 remain INACTIVE | active=false, inactive_at set | active=f, inactive_at=04:31:54.095625+00 | **PASS** |
| 3 | inactive_at NOT rewritten on every poll | T1 == T2 | 04:31:54.095625+00 == 04:31:54.095625+00 | **PASS** |
| 4 | Roster failure ≠ empty roster | Exception → no lifecycle update | Source verified: try/except returns None, no DB writes | **PASS** |
| 5 | Historical device_users preserved | 2 device_users, no deletions | 2 device_users, 0 DELETEs | **PASS** |
| 6 | Attendance preserved | 7 logs, 0 duplicates | 7 logs, 0 duplicates | **PASS** |
| 7 | Human Master unchanged | 120/120, 0 orphans, 0 dup keys | 120/120, 0 orphans, 0 dup keys | **PASS** |
| 8 | Mappings = 0 | employee_device_mappings = 0 | 0 | **PASS** |
| 9 | Collector LIVE/HEALTHY | state=LIVE, db=HEALTHY, 0 restarts | LIVE, HEALTHY, 0 restarts | **PASS** |
| 10 | No terminal mutation | 0 set_user/delete_user/enroll | 0 matches in logs | **PASS** |
| 11 | No enrollment | 0 enroll attempts | 0 matches in logs | **PASS** |

---

## 14. Authorization Boundary Compliance

| Action | Authorized? | Performed? |
|--------|-------------|------------|
| Source code modification | NO | NO |
| Database writes (INSERT/UPDATE/DELETE) | NO | NO (only collector runtime lifecycle activity) |
| Terminal writes (set_user/delete_user/enroll) | NO | NO |
| Schema changes | NO | NO |
| Docker restart/recreate | NO | NO |
| Documentation write | YES | YES (this report + STATUS.md) |
| Git commit/push | YES (documentation only) | YES |

**Note**: Normal collector runtime lifecycle activity (periodic roster polling, `inactive_at` preservation) is expected autonomous behavior and NOT agent-initiated mutation.

---

## 15. Checkpoint Conclusion

The Device User Lifecycle implementation from `ADMS-Data-DeviceUserLifecycle-002` is **LIVE VERIFIED** and operating correctly. All 11 critical properties PASS. The `inactive_at` stability is proven both from logs (13+ polls with 0 marked_inactive) and from direct DB T1/T2 comparison (identical timestamps). No collateral mutations detected. Human Master integrity preserved. Backups verified.

**Next authorized PromptID**: `ADMS-Data-DeviceEnrollmentWorkflow-002`

---

FINAL

PromptID: ADMS-Data-DeviceUserLifecycle-003

repository verified: YES
database modified: NO
application modified: NO
device modified: NO
tests: PASS (105/105)
runtime verified: YES
commit created: YES (documentation only)
push completed: YES

next authorized PromptID: ADMS-Data-DeviceEnrollmentWorkflow-002
safe to proceed: YES
blockers: NONE

STOP.