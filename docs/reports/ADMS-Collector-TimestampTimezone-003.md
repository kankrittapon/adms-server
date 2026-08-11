# ADMS-Collector-TimestampTimezone-003 — Live Verification Checkpoint

**PromptID**: ADMS-Collector-TimestampTimezone-003
**Date**: 2026-08-11
**Mode**: READ-ONLY CHECKPOINT
**Authority**: AGENTS.md §20 (Checkpoints), §25 (Reporting)

---

## 1. Objective

Verify that the timestamp/timezone correction implemented in `ADMS-Collector-TimestampTimezone-002` is operationally correct, that all 7 historical attendance rows have been properly corrected, that `normalize_device_timestamp()` is present in all code paths, that runtime deduplication is functional, and that the system is safe to proceed to `ADMS-Collector-TemporalIdentity-002`.

---

## 2. Git Synchronization

| Node | HEAD | Status |
|------|------|--------|
| TELEPHONE (local) | `5adae55ecac30b7729173798d3660385c5665b44` | CLEAN |
| origin/main | `5adae55ecac30b7729173798d3660385c5665b44` | SYNCED |
| ai-brain | `5adae55ecac30b7729173798d3660385c5665b44` | SYNCED, CLEAN |

**Verdict**: PASS — all 3 nodes synchronized.

---

## 3. Runtime Health

| Container | Status | Uptime |
|-----------|--------|--------|
| adms-postgres | Up (healthy) | ~5h |
| mqtt | Up | ~5h |
| listener (collector) | Up (healthy) | ~1h |

**Collector Logs**:
- Connected to ZKTeco terminal at `192.168.1.201:4370` — VERIFIED
- MQTT connected — VERIFIED
- Backfill cycle: 7 seen, 1 candidate, 0 inserted, 1 duplicate skipped — VERIFIED
- FSM transition: BACKFILLING → LIVE — VERIFIED

**Verdict**: PASS — all containers healthy, collector operational.

---

## 4. Database Integrity

| Table | Count | Expected | Match |
|-------|-------|----------|-------|
| attendance_logs | 7 | 7 | YES |
| device_users | 2 | 2 | YES |
| devices | 1 | 1 | YES |
| employee_device_mappings | 0 | 0 | YES |
| employees | 0 | 0 | YES |
| human_employee_sources | 120 | 120 | YES |
| human_employees | 120 | 120 | YES |
| sync_events | 2 | 2 | YES |

**Verdict**: PASS — all counts match expected baseline.

---

## 5. Timestamp Round-Trip Verification

All 7 attendance rows verified: `bangkok_display = scan_time AT TIME ZONE 'Asia/Bangkok'` matches `raw_payload->>'timestamp'` exactly.

| ID | user_id | scan_time (UTC) | bangkok_display | raw_payload timestamp | Round-Trip |
|----|---------|-----------------|-----------------|----------------------|------------|
| 1 | 1 | 2021-03-02 20:14:58+00 | 2021-03-03 03:14:58 | 2021-03-03T03:14:58 | PASS |
| 2 | 1 | 2021-03-02 20:15:01+00 | 2021-03-03 03:15:01 | 2021-03-03T03:15:01 | PASS |
| 3 | 1 | 2021-03-02 20:16:40+00 | 2021-03-03 03:16:40 | 2021-03-03T03:16:40 | PASS |
| 4 | 1 | 2021-03-03 00:46:03+00 | 2021-03-03 07:46:03 | 2021-03-03T07:46:03 | PASS |
| 5 | 1 | 2026-08-10 12:47:39+00 | 2026-08-10 19:47:39 | 2026-08-10T19:47:39 | PASS |
| 6 | 2 | 2026-08-10 13:07:27+00 | 2026-08-10 20:07:27 | 2026-08-10T20:07:27 | PASS |
| 7 | 1 | 2026-08-11 08:30:54+00 | 2026-08-11 15:30:54 | 2026-08-11T15:30:54 | PASS |

**Remaining +7h errors**: 0
**Verdict**: PASS — all 7 rows round-trip correct.

---

## 6. Deduplication Verification

- UNIQUE constraint `attendance_logs_user_id_device_ip_scan_time_key`: PRESENT
- Duplicate rows (same user_id + device_ip + scan_time): 0
- Post-correction backfill: 7 seen, 1 candidate, 0 inserted, 1 duplicate skipped

**Verdict**: PASS — deduplication functional, no duplicates.

---

## 7. Source Code Normalization Verification

`normalize_device_timestamp()` is defined in `app/timestamp_utils.py` using `ZoneInfo("Asia/Bangkok")` and is imported and called in all 4 code paths:

| Path | File | Line | Function | Status |
|------|------|------|----------|--------|
| Definition | `app/timestamp_utils.py` | 24 | `normalize_device_timestamp()` | PRESENT |
| Realtime persistence | `app/db.py` | 117 | `save_attendance_log()` | PRESENT |
| Backfill persistence | `app/db.py` | 196 | `save_attendance_batch()` | PRESENT |
| Watermark comparison | `app/collector.py` | 214 | `handle_backfilling()` | PRESENT |
| MQTT payload | `app/mqtt_client.py` | 55 | `publish_attendance()` | PRESENT |

**Host-timezone independence**: The normalization uses explicit `ZoneInfo("Asia/Bangkok")` at the application level. PostgreSQL `timezone=UTC`, container timezone=UTC, device RTC unchanged. Correctness does NOT depend on host/container/DB timezone.

**Verdict**: PASS — normalization present in all paths, host-timezone independent.

---

## 8. ZKTeco Device Safety

- Device `192.168.1.201:4370`: CONNECTED (read-only ZK protocol)
- Device writes performed: NONE
- Device configuration changed: NONE
- Terminal users created/deleted/modified: NONE
- Fingerprints enrolled/deleted: NONE
- Device RTC changed: NONE
- Device restarted/reset: NONE

**Verdict**: PASS — device untouched, read-only.

---

## 9. Test Checkpoint

| Suite | Tests | Passed | Failed | Skipped |
|-------|-------|---------|--------|---------|
| test_collector.py | 5 | 5 | 0 | 0 |
| test_excel_human_master_import.py | 5 | 5 | 0 | 0 |
| test_healthcheck.py | 13 | 13 | 0 | 0 |
| test_hybrid_backfill.py | 4 | 4 | 0 | 0 |
| test_identity_transition.py | 6 | 6 | 0 | 0 |
| test_timestamp_timezone.py | 21 | 21 | 0 | 0 |
| **Total** | **54** | **54** | **0** | **0** |

**Verdict**: PASS — 54/54 tests pass, 0 failures.

---

## 10. Backup Verification

### Pre-Write Backup (Before Historical Correction)

| Property | Value |
|----------|-------|
| Filename | `adms_pre_timestamp_timezone_20260811_183000.dump` |
| Size | 44,980 bytes |
| SHA256 | `697678c0407e18c9fec345952499e45658d81505af9268414be5ec148f040865` |
| TOC Entries | 79 |
| `pg_restore -l` | PASS |
| Classification | PRE-WRITE RECOVERY POINT (timestamp-uncorrected state) |

### Post-Write Backup (After Historical Correction)

| Property | Value |
|----------|-------|
| Filename | `adms_post_timestamp_timezone_20260811_184500.dump` |
| Size | 45,033 bytes |
| SHA256 | `f0e64f477a167712eda16c8670935513b8bf8e38ce18df349d49a276674ec0b1` |
| TOC Entries | 79 |
| `pg_restore -l` | PASS |
| Classification | **AUTHORITATIVE TIMESTAMP-CORRECTED RECOVERY POINT** |

**Full isolated restore tested**: NO (only `pg_restore -l` archive readability verified, not actual restore into a test database).

**Verdict**: PASS — both backups present, hashes match, archives readable.

---

## 11. Parse_Time Defect Assessment

| Property | Value |
|----------|-------|
| Defect | PRESENT |
| Location | `app/db.py:25` — `parse_time()` does `hour, minute = map(int, val.split(":"))` |
| Trigger | `ON_TIME_START=05:00:00`, `ON_TIME_END=10:00:00` (3 parts, "too many values to unpack") |
| Impact | `determine_status()` catches exception, returns `"UNKNOWN"` for all attendance |
| Affects `scan_time` | NO |
| Affects `status` field | YES (all rows get `status=UNKNOWN`) |
| Blocks timestamp correctness | NO |
| Blocks TemporalIdentity-002 | NO |
| Reserved for | `ADMS-Collector-AttendanceParseTime-001` |

---

## 12. TemporalIdentity-002 Unblock Decision

| Criterion | Status |
|-----------|--------|
| All attendance timestamps correct (UTC) | PASS |
| `normalize_device_timestamp()` in all 4 code paths | PASS |
| 54/54 tests pass | PASS |
| 0 duplicates, UNIQUE constraint intact | PASS |
| Pre/post backups verified | PASS |
| Runtime healthy, collector LIVE | PASS |
| No device writes | PASS |
| parse_time defect does NOT block temporal identity | PASS |

**TemporalIdentity-002**: **UNBLOCKED** ✅

---

## 13. Sync Events Log

| # | Type | Seen | Candidates | Inserted | Duplicates Skipped |
|---|------|------|------------|----------|-------------------|
| 1 | Original backfill | 7 | 7 | 7 | 0 |
| 2 | Post-correction backfill | 7 | 1 | 0 | 1 |

---

## 14. Evidence Classification Summary

| Evidence | Classification |
|----------|---------------|
| Git HEAD on all 3 nodes | VERIFIED LIVE |
| Container health status | VERIFIED LIVE |
| Collector logs (backfill, MQTT, FSM) | VERIFIED LIVE |
| DB row counts | VERIFIED LIVE |
| Attendance timestamp round-trip | VERIFIED LIVE |
| Deduplication (0 duplicates) | VERIFIED LIVE |
| `normalize_device_timestamp()` in source | FILE EVIDENCE |
| 54/54 tests pass | VERIFIED LIVE (TELEPHONE) |
| Backup files + SHA256 + pg_restore -l | VERIFIED LIVE (ai-brain) |
| ZKTeco connected, no writes | VERIFIED LIVE |
| parse_time defect | FILE EVIDENCE |
| Full isolated restore | NOT TESTED |

---

## FINAL

    PromptID: ADMS-Collector-TimestampTimezone-003

    repository verified: YES
    database modified: NO
    application modified: NO
    device modified: NO
    tests: PASS (54/54)
    runtime verified: YES
    commit created: YES (this checkpoint)
    push completed: PENDING

    next authorized PromptID: ADMS-Collector-TemporalIdentity-002
    safe to proceed: YES
    blockers: NONE

    STOP.