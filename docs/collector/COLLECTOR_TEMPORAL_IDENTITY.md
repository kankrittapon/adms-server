# Canonical Architecture: Collector Temporal Identity Resolution

**PromptID:** `ADMS-Collector-TemporalIdentity-001`
**Status:** AUDIT & DESIGN COMPLETE / PLAN ONLY

---

## 1. Overview

This document defines the architecture for transitioning the ADMS Collector from **timeless** Human ↔ Device identity resolution to **time-aware (temporal)** resolution using Schema 005 (`valid_from`, `valid_to`, `mapping_status = 'VERIFIED'`).

**Current state**: The resolver exists but is timeless — it queries `employee_device_mappings` without any temporal filter.

**Planned state**: The resolver will accept `scan_time` and apply interval semantics `[valid_from, valid_to)` to ensure historical attendance is attributed to the correct Human during the correct ownership period.

---

## 2. Current Resolver — VERIFIED LIVE

### File
`app/db.py`

### Function
```python
def resolve_verified_employee_mapping(cur: Any, device_user_pk: int) -> Optional[str]:
```

### Current SQL
```sql
SELECT employee_id
FROM employee_device_mappings
WHERE device_user_pk = %s AND mapping_status = 'VERIFIED';
```

### Current Behavior: **TIMELESS**

The current resolver queries all VERIFIED mappings for a `device_user_pk` without any temporal filter. It returns the first match or `None`.

### Call Sites

| Call Site | File | Function | Context |
|-----------|------|----------|---------|
| 1 | `app/db.py` | `save_attendance_log()` | Realtime ingestion — single record |
| 2 | `app/db.py` | `save_attendance_batch()` | Backfill ingestion — batch records |

Both call sites resolve `employee_id` **before** the attendance INSERT, using the same function.

### Arguments
- `cur`: database cursor (within active transaction)
- `device_user_pk`: integer PK from `device_users`

### Return Value
- `str(employee_id)` UUID string, or `None`

---

## 3. Ingestion Path Trace

### Realtime Path (LIVE state)
```
ZKTeco live_capture()
  → collector.py: handle_live()
    → attendance event (has .user_id, .timestamp, .punch, .uid)
    → db.py: save_attendance_log(cfg, attendance)
      → get_or_create_device(cur, device_ip)
      → ensure_device_user(cur, device_id, user_id_str)
      → resolve_verified_employee_mapping(cur, device_user_pk)  ← TIMELESS
      → INSERT INTO attendance_logs (..., employee_id, ...)
      → conn.commit()
    → mqtt_client.py: publish_attendance(attendance, status_str)
```

### Backfill Path (BACKFILLING state)
```
ZKTeco get_attendance()
  → collector.py: handle_backfilling()
    → client-side watermark filtering (rec.timestamp >= boundary)
    → db.py: save_attendance_batch(cfg, candidates, stop_event)
      → get_or_create_device(cur, device_ip)
      → for each unique user_id:
          → ensure_device_user(cur, device_id, uid)
          → resolve_verified_employee_mapping(cur, dpk)  ← TIMELESS
      → for each rec in chunk:
          → INSERT INTO attendance_logs (..., employee_id, ...)
      → conn.commit()  (per chunk)
```

### Shared Persistence Path: **YES**

Both realtime and backfill use the same `resolve_verified_employee_mapping()` function. Both resolve `employee_id` before INSERT. Both use `ON CONFLICT (user_id, device_ip, scan_time) DO NOTHING` for deduplication.

### scan_time Available Before Human Resolution: **YES**

In both paths, `attendance.timestamp` (or `rec.timestamp`) is available before `resolve_verified_employee_mapping()` is called. In `save_attendance_log()`, `scan_time = attendance.timestamp` is extracted at the top. In `save_attendance_batch()`, `scan_time = rec.timestamp` is available per record.

**However**: In `save_attendance_batch()`, the current code resolves mappings once per unique `user_id` (not per record). This means the same `employee_id` is applied to all records for that user regardless of different `scan_time` values. This is a **structural issue** for temporal resolution — see §5 below.

---

## 4. Temporal Lookup Contract

### Proposed Resolver API
```python
def resolve_verified_employee_mapping(
    cur: Any,
    device_user_pk: int,
    scan_time: datetime,
) -> Optional[str]:
```

### Required SQL
```sql
SELECT employee_id
FROM employee_device_mappings
WHERE device_user_pk = %s
  AND mapping_status = 'VERIFIED'
  AND valid_from <= %s
  AND (valid_to IS NULL OR %s < valid_to)
LIMIT 2;
```

### Why LIMIT 2
Using `LIMIT 2` efficiently detects ambiguity:
- 0 rows → UNMAPPED → return `None`
- 1 row → RESOLVE → return `employee_id`
- 2 rows → AMBIGUOUS → fail safe (see §6)

### Mapping Status Requirement
**VERIFIED ONLY.** Non-VERIFIED statuses (`PROBABLE`, `LEGACY`, `CANDIDATE`, `REVOKED`) are ignored.

### Interval Semantics
```
[valid_from, valid_to)
```
- `valid_from`: **inclusive** (`scan_time >= valid_from`)
- `valid_to`: **exclusive** (`scan_time < valid_to`)
- `valid_to IS NULL`: open-ended (matches all `scan_time >= valid_from`)

---

## 5. Boundary Behavior

| Condition | Result |
|-----------|--------|
| `scan_time < valid_from` | UNMAPPED (no match) |
| `scan_time == valid_from` | MATCH (inclusive start) |
| `valid_from < scan_time < valid_to` | MATCH |
| `scan_time == valid_to` | NO MATCH (exclusive end) |
| `scan_time > valid_to` | NO MATCH |
| `valid_to IS NULL` and `scan_time >= valid_from` | MATCH |

---

## 6. Multiple Match Defense

Schema 005 provides `idx_active_verified_device_user` (partial UNIQUE on `device_user_pk WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL`), which prevents multiple **active** (open-ended) VERIFIED mappings for the same `device_user_pk`.

However, **historical interval overlap** is not fully DB-enforced. Two VERIFIED mappings with different `valid_from`/`valid_to` intervals could theoretically overlap for the same `device_user_pk`.

### Planned Behavior

| Match Count | Action |
|-------------|--------|
| 0 | Return `None` — attendance persists with `employee_id = NULL` |
| 1 | Return `employee_id` |
| >1 | **AMBIGUOUS** — log warning, return `None`, record `sync_event` |

### Recommended Approach: **log + return None + record sync_event**

This matches the current architecture's safe-fail pattern (see `parse_time` bug handling — logs warning, returns `UNKNOWN`). Raising an exception would disrupt the ingestion loop and potentially cause data loss. Recording a `sync_event` provides audit trail for administrators.

---

## 7. Unmapped Attendance

Current reconstructed baseline proves `employee_id = NULL` is valid for unmapped attendance. This behavior is **preserved**.

Temporal resolver failure to find a valid VERIFIED mapping must NOT:
- create Human records
- create mappings
- guess identity
- use Excel order
- use `user_id` numerically
- use display name

**Required result**: attendance persists, `employee_id = NULL`.

---

## 8. Historical Reconciliation Design

### Concept
When an administrator creates a VERIFIED mapping with temporal bounds, existing unmapped attendance within that interval should be eligible for retroactive resolution.

### Planned Operation
```sql
UPDATE attendance_logs a
SET employee_id = m.employee_id
FROM employee_device_mappings m
WHERE a.device_user_pk = m.device_user_pk
  AND m.mapping_status = 'VERIFIED'
  AND a.employee_id IS NULL
  AND a.scan_time >= m.valid_from
  AND (m.valid_to IS NULL OR a.scan_time < m.valid_to);
```

### Automatic Overwrite of Existing employee_id: **NO**

Already-resolved attendance should **NOT** be automatically overwritten. Only `employee_id IS NULL` records are eligible. Conflicts (where a record already has an `employee_id` but a different mapping now claims it) should be flagged for explicit review.

### Unmapped-Only Default: **YES**

### Implementation Phase: NOT THIS PROMPT
Reconciliation is deferred to a future authorized phase after the temporal resolver is operational.

---

## 9. Device User Recycling

### Risk Confirmed: **YES**

Current `ensure_device_user()` uses `ON CONFLICT (device_id, device_user_id) DO UPDATE SET last_seen_at = now()`. If terminal `user_id '1'` is deleted and a new person is enrolled as `user_id '1'`, the same `device_user_pk` is reused.

### Temporal Mapping Mitigates Risk: **PARTIAL**

Temporal mapping (`[valid_from, valid_to)`) allows administrators to record that:
- Person A owned `device_user_pk = 2` from `2026-01-01` to `2026-06-30`
- Person B owned `device_user_pk = 2` from `2026-07-01` onward

Historical attendance before `2026-07-01` resolves to Person A; after resolves to Person B.

### Remaining Risk
- **Requires manual accuracy**: Administrators must correctly record `valid_from`/`valid_to` boundaries. Incorrect boundaries cause silent misattribution.
- **No automatic detection**: The Collector cannot detect when a terminal user is deleted/recreated. `device_uid` changes are not monitored (see §11).
- **Historical gap**: If a `device_user_pk` has no mapping covering a specific `scan_time`, that attendance remains unmapped — which is safe but may require administrative review.

---

## 10. Lifecycle Fields

### Schema Presence
- `device_users.roster_last_seen_at`: **PRESENT** (TIMESTAMPTZ, nullable)
- `device_users.inactive_at`: **PRESENT** (TIMESTAMPTZ, nullable)

### Automatic Lifecycle Detection: **NOT IMPLEMENTED**

### Recommended Future Behavior

| Question | Answer |
|----------|--------|
| What constitutes roster observation? | A successful `get_users()` call that returns the `device_user_id` for this `device_user_pk` |
| When should `roster_last_seen_at` update? | On each successful roster sync where the user is present |
| When should `inactive_at` be set? | When a user present in the previous roster sync is absent in the current sync |
| What indicates reappearance? | User absent (has `inactive_at` set) reappears in a subsequent roster sync → clear `inactive_at`, update `roster_last_seen_at` |
| What happens if `device_uid` changes? | Flag for admin review — potential account recreation. Do NOT automatically create new `device_user_pk` |
| Should lifecycle detection create a new `device_user_pk`? | **NO** — flag for admin review only. Creating new PKs would break historical attendance linkage |
| Should it merely flag admin review? | **YES** — record `sync_event`, set `inactive_at`, but do not mutate identity |

### Implementation Phase: NOT THIS PROMPT
Lifecycle detection requires a roster sync mechanism (`get_users()`) that is not currently in the Collector. Deferred to a future authorized phase.

---

## 11. Device_UID Role

### Observed Semantics
- `device_uid` is an `INT` column in `device_users` (from `sql/002_identity_foundation.sql`)
- Currently **NULL** for both device users (attendance-discovered, not roster-synced)
- `pyzk` attendance records have a `.uid` attribute (integer slot index)
- `device_uid` is NOT part of any uniqueness constraint
- `device_uid` is NOT populated by `ensure_device_user()` — only `device_user_id` (string) is used

### Recommended Role: **DIAGNOSTIC ONLY**

`device_uid` should be treated as diagnostic metadata, not canonical identity. Reasons:
1. ZKTeco firmware can reuse `uid` values after account deletion
2. `uid` is not guaranteed globally stable across firmware resets
3. Current ingestion does not populate or track `device_uid` changes
4. Using `device_uid` as canonical identity would require roster sync infrastructure that does not exist

### Future Potential
If roster sync is implemented, `device_uid` changes could serve as a **continuity evidence** signal for detecting account recreation. But this requires:
- Regular `get_users()` calls
- Comparison of `device_uid` across syncs
- Admin alerting on changes

Until then: **DIAGNOSTIC ONLY**.

---

## 12. Transaction Boundary

### Current Transaction Architecture

**Realtime (`save_attendance_log`)**:
```
get_db_connection() → conn
  cur = conn.cursor()
    get_or_create_device(cur)
    ensure_device_user(cur)
    resolve_verified_employee_mapping(cur)
    INSERT attendance_logs
  conn.commit()
conn.close()
```
All operations within one transaction. ✓

**Backfill (`save_attendance_batch`)**:
```
get_db_connection() → conn
  for each chunk:
    cur = conn.cursor()
      get_or_create_device(cur)
      ensure_device_user(cur) per unique user
      resolve_verified_employee_mapping(cur) per unique user
      INSERT attendance_logs per record
    conn.commit()  ← per chunk
conn.close()
```
Each chunk is one transaction. ✓

### Recommended Resolver Location

The temporal resolver should execute **within the same transaction** as `ensure_device_user()` and the attendance INSERT. This is already the case — `resolve_verified_employee_mapping()` receives `cur` (the active cursor).

**No transaction redesign needed.**

### Structural Issue in Backfill

In `save_attendance_batch()`, mappings are resolved **once per unique `user_id`** before iterating records:
```python
for uid in unique_users:
    dpk = ensure_device_user(cur, device_id, uid)
    user_pk_map[uid] = dpk
    employee_map[uid] = resolve_verified_employee_mapping(cur, dpk)
```

This means the same `employee_id` is applied to all records for that user regardless of different `scan_time` values. For temporal resolution, this must be changed to **resolve per record** (or at minimum, per unique `(device_user_pk, scan_time)` combination).

### Planned Fix for 002
Move the resolver call inside the per-record loop:
```python
for rec in chunk:
    dpk = user_pk_map.get(user_id_str)
    emp_id = resolve_verified_employee_mapping(cur, dpk, rec.timestamp)  # per-record
```

---

## 13. Deduplication Safety

### Current Dedupe Constraint
```sql
UNIQUE (user_id, device_ip, scan_time)
```
Verified live: `attendance_logs_user_id_device_ip_scan_time_key` exists.

### Resolver Interaction
The temporal resolver does NOT alter dedupe semantics. The resolver only determines `employee_id` — the dedupe constraint operates on `(user_id, device_ip, scan_time)` which are unaffected.

### Backfill Interaction
`ON CONFLICT (user_id, device_ip, scan_time) DO NOTHING` — duplicates are silently skipped. The resolver runs before INSERT, so even if a record is a duplicate (skipped), the resolver was called but the result is discarded. This is harmless.

### Dedupe Behavior Affected: **NO**

---

## 14. MQTT Semantics

### Current MQTT Payload
```json
{
  "user_id": "1",
  "device_ip": "192.168.1.201",
  "scan_time": "2026-08-11T15:30:54",
  "punch_type": "0",
  "status": "UNKNOWN",
  "event_type": "ATTENDANCE_SCAN"
}
```

### Current employee_id Behavior
**`employee_id` is NOT included in the MQTT payload.** The MQTT payload is published from `collector.py:handle_live()` using `mqtt_service.publish_attendance(attendance, status_str)`, which only includes `user_id`, `device_ip`, `scan_time`, `punch_type`, `status`, and `event_type`.

### Temporal Resolver Payload Change Required: **NO (but recommended)**

The temporal resolver does not *require* MQTT payload changes. However, it is **recommended** that `employee_id` be added to the MQTT payload in a future phase so downstream consumers know the resolved Human identity.

### Classification
MQTT payload changes are **SEPARATE / DEFERRED** — not required for temporal identity implementation.

---

## 15. Parse_Time Bug — Audit Only

### Bug Confirmed: **YES**

`app/db.py:parse_time()`:
```python
def parse_time(val: str) -> time:
    hour, minute = map(int, val.split(":"))
    return time(hour=hour, minute=minute)
```

`ON_TIME_START` defaults to `"08:00"` and `ON_TIME_END` defaults to `"08:30"` in `config.py`. The test `test_determine_status` uses `"08:00"` and `"08:30"` (2 parts) and passes.

However, the live deployment has `ON_TIME_START=05:00:00` and `ON_TIME_END=10:00:00` (3 parts, `HH:MM:SS`). `val.split(":")` produces `['05', '00', '00']` → `map(int, ...)` yields 3 values → `hour, minute = ...` fails with "too many values to unpack (expected 2)".

### Impact Analysis

| Question | Answer |
|----------|--------|
| Is `parse_time()` involved in `scan_time` generation? | **NO** — `parse_time()` only processes `ON_TIME_START`/`ON_TIME_END` config strings |
| Could the bug corrupt temporal identity lookup? | **NO** — `scan_time` comes from `attendance.timestamp` (pyzk), not from `parse_time()` |
| Is only `status` affected? | **YES** — the exception is caught in `determine_status()`, which returns `"UNKNOWN"` |
| Does `scan_time` remain correct? | **YES** — `scan_time` is the raw pyzk timestamp, unaffected by `parse_time()` |
| Should this be fixed before Temporal Identity WRITE? | **RECOMMENDED but NOT BLOCKING** |

### Temporal Identity Blocker: **NO**

`parse_time()` only affects the `status` field (`ON_TIME`/`LATE`/`UNKNOWN`). The `scan_time` used for temporal lookup is the raw pyzk `attendance.timestamp`, which is completely independent.

### Classification: **SEPARATE DEFECT / NON-BLOCKING**

### Proposed Separate PromptID
`ADMS-Collector-AttendanceParseTime-001`

---

## 16. Timezone Audit — BLOCKER IDENTIFIED

### Terminal Timestamp Source
ZKTeco device clock: `2026-08-11 18:04:00` (naive datetime, Bangkok local time UTC+7)
Actual UTC at same moment: `2026-08-11 11:04:56 UTC`

**The terminal operates in Bangkok local time (UTC+7).**

### Python Datetime Representation
`pyzk` returns `datetime.datetime` objects with `tzinfo = None` (naive). Example:
```
datetime.datetime(2021, 3, 3, 3, 14, 58)  # tzinfo=None
```

These naive datetimes represent **Bangkok local time** (UTC+7), not UTC.

### Database Types
| Column | Type |
|--------|------|
| `attendance_logs.scan_time` | `TIMESTAMPTZ` (timestamp with time zone) |
| `employee_device_mappings.valid_from` | `TIMESTAMPTZ` |
| `employee_device_mappings.valid_to` | `TIMESTAMPTZ` |

### PostgreSQL Timezone
```
timezone = UTC
```

### Current Insertion Behavior
When psycopg2 inserts a **naive datetime** into a `TIMESTAMPTZ` column, PostgreSQL assumes the naive datetime is in the session's timezone (`UTC`). Therefore:

- pyzk returns `2026-08-11 15:30:54` (Bangkok local)
- psycopg2 inserts it as `2026-08-11 15:30:54+00` (interpreted as UTC)
- Actual UTC should be `2026-08-11 08:30:54+00`
- **Stored value is +7 hours ahead of actual UTC**

### Verification
```
scan_time stored:     2026-08-11 15:30:54+00  (interpreted as UTC)
raw_payload timestamp: 2026-08-11T15:30:54    (naive, Bangkok local)
device clock:          2026-08-11 18:04:00    (Bangkok local)
actual UTC:            2026-08-11 11:04:56Z
```

The stored `scan_time` values are **Bangkok local time stored as if UTC** — they are offset by +7 hours from true UTC.

### Impact on Temporal Identity

If an administrator creates a VERIFIED mapping with `valid_from = '2026-08-11 00:00:00+00'` (intending Bangkok midnight), but attendance `scan_time` is stored as Bangkok local interpreted as UTC, the comparison would be:

```
stored scan_time:  2026-08-11 15:30:54+00  (actually 08:30:54 Bangkok)
mapping valid_from: 2026-08-11 00:00:00+00  (intending 00:00 Bangkok = 17:00 UTC previous day)
```

The interval check would produce **incorrect results** because the timezone semantics are inconsistent.

### Comparison Safe: **CONDITIONAL → NO (BLOCKER)**

### Blocker: **TIMEZONE MISMATCH**

The naive datetime from pyzk (Bangkok local) is stored as TIMESTAMPTZ interpreted as UTC. Temporal comparisons between `scan_time` and `valid_from`/`valid_to` will produce incorrect results unless timezone semantics are aligned.

### Required Fix Before Temporal Identity WRITE

**Option A (Preferred)**: Attach `Asia/Bangkok` timezone to pyzk timestamps before insertion:
```python
from datetime import timezone, timedelta
BANGKOK_TZ = timezone(timedelta(hours=7))
scan_time = attendance.timestamp.replace(tzinfo=BANGKOK_TZ)
```
This makes psycopg2 correctly convert Bangkok local → UTC for storage. Future `valid_from`/`valid_to` values would also be in Bangkok local (or any timezone), and PostgreSQL would handle the conversion correctly.

**Option B**: Set PostgreSQL session timezone to `Asia/Bangkok` — but this affects all queries and is fragile.

**Option C**: Store as `TIMESTAMP` (without timezone) — but this loses timezone information and is worse for future multi-timezone support.

### Recommended Approach
**Option A** — attach `Asia/Bangkok` timezone to pyzk timestamps at the application layer before DB insertion. This is a minimal, targeted fix.

### Important Note on Existing Data
The 7 existing attendance records are stored with incorrect UTC offset (+7 hours). A data migration would be needed to correct them:
```sql
UPDATE attendance_logs SET scan_time = scan_time - INTERVAL '7 hours';
```
This should be done in the fix phase, not this planning phase.

### Proposed Blocker PromptID
`ADMS-Collector-TimestampTimezone-001` — Fix timezone handling before temporal identity implementation.

---

## 17. Index Review

### Existing Indexes on `employee_device_mappings`

| Index | Definition | Supports Temporal Query? |
|-------|------------|--------------------------|
| `employee_device_mappings_pkey` | UNIQUE btree (`mapping_id`) | No (not used for lookup) |
| `idx_active_verified_device_user` | UNIQUE btree (`device_user_pk`) WHERE `mapping_status = 'VERIFIED' AND valid_to IS NULL` | Partially (active only, no temporal) |
| `idx_employee_device_mappings_temporal` | btree (`device_user_pk, mapping_status, valid_from, valid_to`) | **YES** — covers all columns in the temporal query |

### Analysis
`idx_employee_device_mappings_temporal` is a composite index on `(device_user_pk, mapping_status, valid_from, valid_to)` — exactly the columns used in the planned temporal query. This index efficiently supports the resolver.

### Existing Indexes Sufficient: **YES**

### New Migration Required: **NO**

### Recommendation
No new index needed. The existing `idx_employee_device_mappings_temporal` index is sufficient for the temporal resolver query. With 0 mappings currently, performance is irrelevant, but the index design is correct for future scale.

---

## 18. Test Plan

### Planned Tests: 17

| # | Test Name | Description |
|---|-----------|-------------|
| 1 | `test_no_mapping` | No mappings exist → returns None |
| 2 | `test_active_verified_mapping` | Active VERIFIED mapping, scan_time in range → returns employee_id |
| 3 | `test_non_verified_mapping_ignored` | PROBABLE/CANDIDATE mapping → returns None |
| 4 | `test_future_mapping` | valid_from in future → returns None |
| 5 | `test_expired_mapping` | valid_to in past → returns None |
| 6 | `test_scan_time_equals_valid_from` | Boundary: inclusive start → returns employee_id |
| 7 | `test_scan_time_equals_valid_to` | Boundary: exclusive end → returns None |
| 8 | `test_historical_mapping` | valid_to set, scan_time within range → returns employee_id |
| 9 | `test_open_ended_mapping` | valid_to IS NULL → returns employee_id |
| 10 | `test_multiple_historical_matches` | Two overlapping VERIFIED mappings → AMBIGUOUS → returns None |
| 11 | `test_different_device_user_pk` | Mapping for different device_user_pk → returns None |
| 12 | `test_backfill_temporal_resolution` | Backfill path resolves per-record with scan_time |
| 13 | `test_realtime_temporal_resolution` | Realtime path resolves with scan_time |
| 14 | `test_unmapped_attendance_remains_null` | No mapping → employee_id = NULL in DB |
| 15 | `test_dedupe_unaffected` | Dedupe constraint still works with temporal resolver |
| 16 | `test_human_auto_creation_disabled` | Regression: no human_employees created by resolver |
| 17 | `test_legacy_stub_creation_disabled` | Regression: no employees table stubs created |

### Boundary Tests: **YES**
### Backfill Tests: **YES**
### Realtime Tests: **YES**
### Ambiguity Tests: **YES**
### Identity Safety Regressions: **YES**

---

## 19. Implementation Plan for 002

### Next PromptID
`ADMS-Collector-TemporalIdentity-002`

### Prerequisites
1. **BLOCKER MUST BE RESOLVED FIRST**: `ADMS-Collector-TimestampTimezone-001` — fix timezone handling (attach `Asia/Bangkok` to pyzk timestamps, correct existing 7 records)
2. **RECOMMENDED**: `ADMS-Collector-AttendanceParseTime-001` — fix `parse_time()` to handle `HH:MM:SS` format

### Application Files Expected to Change

| File | Change |
|------|--------|
| `app/db.py` | Modify `resolve_verified_employee_mapping()` to accept `scan_time` and use temporal SQL; modify `save_attendance_batch()` to resolve per-record; add timezone attachment to timestamps |
| `app/collector.py` | No change needed (already passes attendance objects with timestamps) |
| `app/config.py` | No change needed |
| `app/mqtt_client.py` | No change required (optionally add `employee_id` to payload) |
| `tests/test_identity_transition.py` | Update `test_resolve_verified_employee_mapping_*` tests for new `scan_time` argument; add temporal tests |
| `tests/test_hybrid_backfill.py` | Update backfill tests for per-record resolution |

### Database Migration Required: **NO**

Schema 005 already contains all required columns, constraints, and indexes. No new migration needed.

### Docker Rebuild Required: **YES** (application code change)

### PostgreSQL Restart Required: **NO**

### MQTT Restart Required: **NO**

### Terminal Mutation Required: **NO**

### Deployment Steps
```
1. verify checkpoint
2. implement resolver (add scan_time parameter, temporal SQL)
3. update save_attendance_batch (per-record resolution)
4. add timezone attachment to pyzk timestamps
5. add tests
6. run tests
7. review diff
8. commit/push
9. sync ai-brain
10. rebuild Collector only
11. verify runtime
12. verify DB unchanged except legitimate new attendance
13. verify mappings remain 0
14. verify Healthcheck
15. STOP
```

---

## 20. Checkpoint Plan for 003

**PromptID**: `ADMS-Collector-TemporalIdentity-003`

**Scope**: LIVE VERIFICATION + CHECKPOINT

- Git synchronization
- Runtime health
- Temporal resolver presence (verify code contains `scan_time` parameter)
- Test results
- DB integrity
- Attendance integrity
- Mapping safety (0 mappings)
- Backup/recovery decision
- Documentation
- Checkpoint commit

No new implementation in 003.

---

## 21. Rollback Design

### Expected Rollback Concept
```
revert application commit
rebuild Collector
restart Collector
database schema unchanged
attendance preserved
mappings preserved
```

### Database Migration Required: **NO**
No schema changes are made during implementation. Rollback is purely application code revert + Docker rebuild.

### Rollback Steps
1. `git revert <implementation-commit>`
2. `git push`
3. Sync ai-brain: `git pull`
4. Rebuild Collector: `docker compose up -d --build listener`
5. Verify runtime

### Data Impact
- Attendance records inserted during the implementation phase remain in the database
- `employee_id` values assigned by the temporal resolver remain in existing records
- No data loss on rollback

---

## 22. Sequencing Lock

```
ADMS-Collector-TemporalIdentity-001  (THIS PROMPT — READ-ONLY / PLAN ONLY)
        ↓
ADMS-Collector-TimestampTimezone-001  (BLOCKER FIX — timezone handling)
        ↓
ADMS-Collector-AttendanceParseTime-001  (RECOMMENDED FIX — parse_time bug)
        ↓
ADMS-Checkpoint-TimestampFix-001  (CHECKPOINT)
        ↓
ADMS-Collector-TemporalIdentity-002  (WRITE / IMPLEMENTATION)
        ↓
ADMS-Collector-TemporalIdentity-003  (LIVE VERIFICATION / CHECKPOINT)
        ↓
Human ↔ Device Mapping workflow
        ↓
Native ADMS Push experimental track
```

**Agent MUST NOT skip phases.**

The timezone blocker MUST be resolved before temporal identity implementation. Implementing temporal resolution with incorrect timezone semantics would produce silently incorrect Human attribution.

---

## 23. Realtime vs Backfill Consistency

### Design Goal
```
same attendance event
+ same device_user_pk
+ same scan_time
= same Human resolution
```
regardless of ingestion path.

### Current Architecture
Both paths call `resolve_verified_employee_mapping(cur, device_user_pk)`. After implementation, both will call `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)`.

### Architectural Obstacle: **YES (backfill batch resolution)**

In `save_attendance_batch()`, mappings are currently resolved **once per unique user_id** before iterating records. This must be changed to **per-record resolution** because different records for the same user may have different `scan_time` values that fall within different temporal mapping intervals.

### Planned Fix
Move resolver call inside the per-record loop in `save_attendance_batch()`. This ensures each record gets its own temporal lookup.

### After Fix
Both realtime and backfill will use the same resolver with the same `(device_user_pk, scan_time)` arguments, producing identical results for the same event.

---

## 24. Safety Summary

| Safety Check | Status |
|--------------|--------|
| Database modified | NO |
| Application modified | NO |
| Schema modified | NO |
| Device modified | NO |
| Fingerprints modified | NO |
| Mapping rows created | 0 |
| Native ADMS Push executed | NO |
| Human ↔ Device Mapping authorized | NO |
| Automatic mapping authorized | NO |

---

## 25. Documentation Classifications

| Item | Classification |
|------|---------------|
| Current resolver (`resolve_verified_employee_mapping`) | IMPLEMENTED (timeless) |
| Temporal resolver with `scan_time` | PLANNED |
| Historical reconciliation | PLANNED |
| Lifecycle detection (roster sync) | NOT IMPLEMENTED |
| `device_uid` as canonical identity | NOT RECOMMENDED (diagnostic only) |
| Timezone fix | BLOCKER — PLANNED |
| `parse_time` fix | SEPARATE DEFECT — PLANNED |
| MQTT `employee_id` in payload | DEFERRED |
| Schema 005 | IMPLEMENTED + LIVE VERIFIED |