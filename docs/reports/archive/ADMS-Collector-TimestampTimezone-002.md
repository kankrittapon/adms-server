# ADMS-Collector-TimestampTimezone-002 — Implementation & Historical Correction

**PromptID**: `ADMS-Collector-TimestampTimezone-002`
**Date**: 2026-08-11
**Type**: Implementation (WRITE)
**Status**: COMPLETE
**Git Commit**: `44202d4` (`fix: normalize ZKTeco attendance timestamps`)

---

## Summary

Implemented `normalize_device_timestamp()` using `ZoneInfo("Asia/Bangkok")` to correctly interpret naive pyzk datetime objects as Bangkok local time before insertion into PostgreSQL TIMESTAMPTZ columns. Corrected 7 existing attendance rows by shifting `scan_time` -7 hours. Verified runtime deduplication, backfill idempotency, and identity safety.

---

## Problem

ZKTeco terminals return naive datetime objects (tzinfo=None) representing the device's local wall-clock time (Asia/Bangkok, UTC+7). When psycopg2 inserts a naive datetime into a TIMESTAMPTZ column, it assumes the value is already UTC, producing a +7 hour offset error on every attendance record.

**Evidence**: All 7 rows had `scan_time` values exactly +7h ahead of the correct UTC instant, confirmed by comparing `raw_payload.timestamp` (Bangkok local) against stored `scan_time` (incorrectly treated as UTC).

---

## Implementation

### New Module: `app/timestamp_utils.py`

```python
from zoneinfo import ZoneInfo
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

def normalize_device_timestamp(value: datetime) -> datetime:
    if value is None:
        raise ValueError("device timestamp is None")
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value).__name__}")
    if value.tzinfo is None:
        return value.replace(tzinfo=BANGKOK_TZ)
    return value.astimezone(BANGKOK_TZ)
```

### Files Modified

| File | Change |
|------|--------|
| `app/timestamp_utils.py` | **NEW** — `normalize_device_timestamp()` + `BANGKOK_TZ` constant |
| `app/db.py` | `save_attendance_log()`: `scan_time = normalize_device_timestamp(attendance.timestamp)` |
| `app/db.py` | `save_attendance_batch()`: `scan_time = normalize_device_timestamp(rec.timestamp)` |
| `app/collector.py` | `handle_backfilling()`: normalize `rec.timestamp` before watermark boundary comparison |
| `app/mqtt_client.py` | `publish_attendance()`: normalize `attendance.timestamp` for MQTT payload ISO string |
| `tests/test_timestamp_timezone.py` | **NEW** — 21 tests covering normalization, round-trip, dedupe, boundary, historical correction |
| `tests/test_hybrid_backfill.py` | Updated mock watermark to aware UTC datetime; updated test records to Bangkok local times |

### Historical Correction

Executed in a single transaction BEFORE collector restart:

```sql
UPDATE attendance_logs SET scan_time = scan_time - INTERVAL '7 hours' WHERE id IN (1,2,3,4,5,6,7);
```

**Pre-check**: 0 collisions with existing UNIQUE(user_id, device_ip, scan_time) constraint.
**Post-check**: 7 rows updated, 0 duplicates, raw_payload unchanged (provenance preserved), employee_id remains NULL.

### Corrected Rows

| ID | user_id | scan_time (corrected UTC) | Bangkok display |
|----|---------|---------------------------|-----------------|
| 1 | 1 | 2021-03-02 20:14:58+00 | 2021-03-03 03:14:58 |
| 2 | 1 | 2021-03-02 20:15:01+00 | 2021-03-03 03:15:01 |
| 3 | 1 | 2021-03-02 20:16:40+00 | 2021-03-03 03:16:40 |
| 4 | 1 | 2021-03-03 00:46:03+00 | 2021-03-03 07:46:03 |
| 5 | 1 | 2026-08-10 12:47:39+00 | 2026-08-10 19:47:39 |
| 6 | 2 | 2026-08-10 13:07:27+00 | 2026-08-10 20:07:27 |
| 7 | 1 | 2026-08-11 08:30:54+00 | 2026-08-11 15:30:54 |

---

## Verification

### Tests

- **New tests**: 21/21 PASSED (normalization, round-trip, realtime/backfill equality, dedupe, boundary, historical correction)
- **Full suite**: 54/54 PASSED (0 failures, 0 skipped)
- **Previous baseline**: 33/33 → now 54/54 (21 new tests added, 0 regressions)

### Runtime Verification (LIVE)

| Check | Result |
|-------|--------|
| Container status | `Up (healthy)` |
| ZKTeco connection | CONNECTED |
| MQTT connection | CONNECTED |
| DB watermark | `2026-08-11T08:30:54+00:00` (corrected UTC) |
| Backfill: records seen | 7 |
| Backfill: candidates | 1 (row 7 within overlap window) |
| Backfill: inserted | 0 |
| Backfill: duplicates skipped | 1 |
| FSM state | LIVE |
| parse_time warning | Expected (NON-BLOCKING, reserved for ADMS-Collector-AttendanceParseTime-001) |

### Post-Runtime DB Verification

| Table | Count | Changed? |
|-------|-------|----------|
| human_employees | 120 | NO |
| human_employee_sources | 120 | NO |
| devices | 1 | NO |
| device_users | 2 | NO |
| attendance_logs | 7 | NO (0 new, 0 duplicates) |
| employee_device_mappings | 0 | NO |
| employees | 0 | NO |
| sync_events | 2 | +1 (new backfill audit event) |

### Backups

| Backup | Size | SHA256 | TOC Entries |
|--------|------|--------|-------------|
| Pre-write (`adms_pre_timestamp_timezone_20260811_183000.dump`) | 44K | `697678c0...` | 79 |
| Post-write (`adms_post_timestamp_timezone_20260811_184500.dump`) | 44K | `f0e64f47...` | 79 |

Both verified via `pg_restore -l` (exit code 0).

### Git Synchronization

| Node | HEAD |
|------|------|
| TELEPHONE (local) | `44202d4` |
| origin/main | `44202d4` |
| ai-brain | `44202d4` |

All three nodes synchronized.

---

## Identity Safety

- **Human Master**: UNCHANGED (120 records, no modifications)
- **Employee mappings**: 0 (no mappings created or modified)
- **Legacy stubs**: 0 (no stubs created)
- **employee_id**: All 7 rows remain NULL (unmapped attendance preserved)
- **raw_payload**: All 7 rows unchanged (provenance preserved)
- **device_id / device_user_pk**: All 7 rows unchanged (device references preserved)

---

## What Was NOT Done

- `parse_time()` bug NOT fixed (reserved for `ADMS-Collector-AttendanceParseTime-001`)
- Temporal identity resolver NOT implemented (reserved for `ADMS-Collector-TemporalIdentity-002`)
- No Human ↔ Device mappings created
- No device configuration changes
- No PostgreSQL timezone setting changes (timezone=UTC remains correct)
- No container TZ environment variable changes

---

FINAL

PromptID: ADMS-Collector-TimestampTimezone-002

repository verified: YES
database modified: YES (7 rows scan_time corrected -7h)
application modified: YES (normalize_device_timestamp() implemented)
device modified: NO
tests: PASS (54/54)
runtime verified: YES
commit created: YES (44202d4)
push completed: YES

next authorized PromptID: ADMS-Collector-TimestampTimezone-003
safe to proceed: YES
blockers: NONE

STOP.