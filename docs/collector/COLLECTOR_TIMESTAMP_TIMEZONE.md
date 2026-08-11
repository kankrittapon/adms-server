# ADMS Collector — Timestamp / Timezone Design

**Status:** PLANNED (NOT IMPLEMENTED)
**PromptID:** ADMS-Collector-TimestampTimezone-001
**Date:** 2026-08-11
**Classification:** PLAN ONLY — Documentation Write Only

---

## 1. Problem Statement

ZKTeco ZEM560 terminal returns attendance timestamps via pyzk as **naive Python datetime objects** (`tzinfo=None`). These timestamps represent **Asia/Bangkok local wall-clock time** (UTC+7).

The ADMS collector passes these naive datetime values directly to psycopg2, which inserts them into PostgreSQL `TIMESTAMPTZ` columns. Because PostgreSQL's `timezone` is set to `UTC`, psycopg2 interprets the naive datetime as **UTC**, producing a **+7 hour semantic offset**.

**Example:**
- Device wall time: `2026-08-11 15:30:54` (Bangkok local)
- pyzk returns: `datetime(2026, 8, 11, 15, 30, 54)` with `tzinfo=None`
- Stored in DB: `2026-08-11 15:30:54+00` (interpreted as UTC)
- Correct UTC instant: `2026-08-11 08:30:54+00`
- **Offset: +7 hours**

This makes temporal comparisons between `scan_time` and `valid_from`/`valid_to` incorrect, blocking Temporal Identity implementation.

---

## 2. Verified Evidence

### 2.1 Server Timezone

| Property | Value |
|----------|-------|
| ai-brain timezone | `Asia/Bangkok (+07, +0700)` |
| UTC offset | +07:00 |
| NTP | active, synchronized |
| RTC | UTC (not local TZ) |
| Server local time | `2026-08-11 18:14:10 +07` |
| Server UTC time | `2026-08-11 11:14:10 UTC` |

### 2.2 Container Timezone

| Property | Value |
|----------|-------|
| Collector container timezone | **UTC** (`/etc/localtime → /usr/share/zoneinfo/Etc/UTC`) |
| `TZ` env var | NOT SET |
| PostgreSQL container timezone | **UTC** |
| `TZ` env var (Postgres) | NOT SET |

### 2.3 PostgreSQL Configuration

| Property | Value |
|----------|-------|
| `timezone` | `UTC` |
| `now()` | `2026-08-11 11:15:37.650774+00` |
| `attendance_logs.scan_time` | `timestamp with time zone` (TIMESTAMPTZ) |
| `employee_device_mappings.valid_from` | `timestamp with time zone` (TIMESTAMPTZ) |
| `employee_device_mappings.valid_to` | `timestamp with time zone` (TIMESTAMPTZ) |

### 2.4 Python Environment

| Property | Value |
|----------|-------|
| Python version | 3.12.13 |
| `zoneinfo.ZoneInfo("Asia/Bangkok")` | **AVAILABLE** (system tz database present) |
| `tzdata` package | Not required (system zoneinfo sufficient) |
| Container base image | `python:3.12-slim` |

### 2.5 pyzk Timestamp Semantics

| Property | Value |
|----------|-------|
| Source field | `Attendance.timestamp` |
| Python type | `datetime.datetime` |
| `tzinfo` | `None` (naive) |
| Device clock interpretation | **LOCAL_BANGKOK** |
| Evidence | Terminal clock shows 18:14 while actual UTC is 11:14; all 7 terminal records have `tzinfo=None` |

### 2.6 Live Offset Verification

All 7 attendance rows verified:

| Row | raw_payload timestamp | stored scan_time (UTC) | corrected UTC (-7h) | corrected Bangkok |
|-----|----------------------|------------------------|---------------------|-------------------|
| 1 | `2021-03-03T03:14:58` | `2021-03-03 03:14:58+00` | `2021-03-02 20:14:58+00` | `2021-03-03 03:14:58+07` |
| 2 | `2021-03-03T03:15:01` | `2021-03-03 03:15:01+00` | `2021-03-02 20:15:01+00` | `2021-03-03 03:15:01+07` |
| 3 | `2021-03-03T03:16:40` | `2021-03-03 03:16:40+00` | `2021-03-02 20:16:40+00` | `2021-03-03 03:16:40+07` |
| 4 | `2021-03-03T07:46:03` | `2021-03-03 07:46:03+00` | `2021-03-03 00:46:03+00` | `2021-03-03 07:46:03+07` |
| 5 | `2026-08-10T19:47:39` | `2026-08-10 19:47:39+00` | `2026-08-10 12:47:39+00` | `2026-08-10 19:47:39+07` |
| 6 | `2026-08-10T20:07:27` | `2026-08-10 20:07:27+00` | `2026-08-10 13:07:27+00` | `2026-08-10 20:07:27+07` |
| 7 | `2026-08-11T15:30:54` | `2026-08-11 15:30:54+00` | `2026-08-11 08:30:54+00` | `2026-08-11 15:30:54+07` |

**Verified offset: +7 hours** (stored value is 7 hours ahead of correct UTC instant).
**Corrected Bangkok display matches raw_payload timestamp exactly** for all 7 rows.

---

## 3. Current Timestamp Path

### 3.1 Realtime Path

```
pyzk Attendance.timestamp (naive datetime, tzinfo=None)
  → collector.py handle_live(): attendance.timestamp
  → db.py save_attendance_log(): scan_time = attendance.timestamp
  → psycopg2 cur.execute(sql, (..., scan_time, ...))
  → PostgreSQL TIMESTAMPTZ (interpreted as UTC)
```

**Timezone attached before DB: NO**

### 3.2 Backfill Path

```
pyzk get_attendance() → list[Attendance] (naive datetime, tzinfo=None)
  → collector.py handle_backfilling(): rec.timestamp
  → db.py save_attendance_batch(): scan_time = rec.timestamp
  → psycopg2 cur.execute(sql, (..., scan_time, ...))
  → PostgreSQL TIMESTAMPTZ (interpreted as UTC)
```

**Timezone attached before DB: NO**

### 3.3 MQTT Path

```
attendance.timestamp.isoformat() → MQTT payload "scan_time"
```

MQTT payload contains the naive ISO string (e.g., `"2026-08-11T15:30:54"` with no timezone offset).

### 3.4 Watermark Path

```
db.py get_device_watermark(): SELECT MAX(scan_time) FROM attendance_logs
  → Returns timezone-aware datetime (TIMESTAMPTZ → Python aware datetime)
  → collector.py: boundary = watermark - timedelta(minutes=overlap)
  → Compared against rec.timestamp (naive datetime from pyzk)
```

**Watermark comparison bug:** The watermark from DB is timezone-aware (UTC), but `rec.timestamp` from pyzk is naive. Python 3.12 raises `TypeError` when comparing aware and naive datetimes. This is an **additional latent bug** — currently masked because the backfill completed on first run with no watermark (boundary=None).

---

## 4. Canonical Timezone Contract

| Property | Value |
|----------|-------|
| Device timezone | Asia/Bangkok (UTC+7, no DST) |
| Application input | Naive local device time (from pyzk) |
| Normalization output | Timezone-aware datetime with `ZoneInfo("Asia/Bangkok")` |
| Database storage | TIMESTAMPTZ (stores canonical instant) |
| Display timezone | Asia/Bangkok (for reports/UI) |
| PostgreSQL global timezone change required | **NO** |
| Collector container TZ change required | **NO** |

**Principle:** The application explicitly interprets ZKTeco wall-clock time at the ingestion boundary. Neither PostgreSQL timezone nor container timezone needs to change. TIMESTAMPTZ stores the correct absolute instant once the application attaches the correct timezone.

---

## 5. Normalization Function Design

### 5.1 Proposed Function

```python
from zoneinfo import ZoneInfo
from datetime import datetime

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

def normalize_device_timestamp(value: datetime) -> datetime:
    """
    Attaches Asia/Bangkok timezone to naive ZKTeco device timestamps.
    If already timezone-aware, converts to Asia/Bangkok.
    Raises TypeError for non-datetime input.
    Raises ValueError for None input.
    """
    if value is None:
        raise ValueError("device timestamp is None")
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value)}")
    if value.tzinfo is None:
        # Naive datetime from ZKTeco — interpret as Bangkok local
        return value.replace(tzinfo=BANGKOK_TZ)
    # Already aware — convert to Bangkok for consistency
    return value.astimezone(BANGKOK_TZ)
```

### 5.2 Behavior Matrix

| Input | Behavior |
|-------|----------|
| Naive datetime from ZKTeco | Attach `ZoneInfo("Asia/Bangkok")` |
| Already-aware datetime (Bangkok) | Return as-is |
| Already-aware datetime (UTC) | Convert to Bangkok |
| Already-aware datetime (other TZ) | Convert to Bangkok |
| `None` | Raise `ValueError` |
| Non-datetime type | Raise `TypeError` |
| String timestamp | Raise `TypeError` (caller must parse first) |

### 5.3 Scope Safety

This function must be scoped **specifically to device timestamp input**. It must NOT be applied to:
- `now()` or `current_timestamp` from PostgreSQL (already aware)
- `valid_from` / `valid_to` from mapping operations (administrator-entered, separate path)
- Computed timestamps (e.g., watermark comparisons)

---

## 6. Call Site Design

### 6.1 Realtime Path

In `app/db.py` `save_attendance_log()`:
```python
scan_time = normalize_device_timestamp(attendance.timestamp)
```

**Location:** After `scan_time = attendance.timestamp`, before `determine_status()` and INSERT.

### 6.2 Backfill Path

In `app/db.py` `save_attendance_batch()`:
```python
scan_time = normalize_device_timestamp(rec.timestamp)
```

**Location:** After `scan_time = rec.timestamp`, before `determine_status()` and INSERT.

### 6.3 Shared Normalization

**YES** — both realtime and backfill paths use the same `normalize_device_timestamp()` function, ensuring identical canonical `scan_time` for the same physical scan event.

### 6.4 Watermark Comparison Fix

In `app/collector.py` `handle_backfilling()`:
```python
# Current: boundary is aware (from DB), rec.timestamp is naive → TypeError
# Fix: normalize rec.timestamp before comparison
if boundary is None or normalize_device_timestamp(rec.timestamp) >= boundary:
```

Alternatively, convert boundary to naive Bangkok for comparison. The preferred approach is to normalize `rec.timestamp` to aware Bangkok, then compare against `boundary` (which is already aware from TIMESTAMPTZ).

### 6.5 MQTT Path

In `app/mqtt_client.py` `publish_attendance()`:
```python
"scan_time": normalize_device_timestamp(attendance.timestamp).isoformat()
```

This will produce `"2026-08-11T15:30:54+07:00"` instead of `"2026-08-11T15:30:54"`.

### 6.6 raw_payload

In `app/db.py` `save_attendance_log()` and `save_attendance_batch()`:
```python
"timestamp": scan_time.isoformat()  # scan_time is now aware
```

This will include the timezone offset in the raw_payload JSON.

---

## 7. Existing 7 Attendance Rows

### 7.1 Audit Results

| Property | Value |
|----------|-------|
| Rows inspected | 7 |
| Rows affected | **7 (ALL)** |
| Raw timestamp evidence available | **YES** (raw_payload JSON contains original naive timestamp) |
| Terminal history available | **YES** (all 7 records still on terminal) |
| Correction feasibility | **DETERMINISTIC** |

### 7.2 Correction Feasibility

All 7 rows have:
1. `raw_payload->>'timestamp'` preserving the original naive datetime string
2. Matching records on the ZKTeco terminal flash memory
3. Consistent +7 hour offset pattern (all rows are Bangkok local stored as UTC)

The correction is **DETERMINISTIC** — the correct UTC instant is `stored_scan_time - INTERVAL '7 hours'` for every row.

### 7.3 Recommended Correction Strategy

**Strategy A — Correct Existing Rows (DETERMINISTIC)**

```sql
UPDATE attendance_logs
SET scan_time = scan_time - INTERVAL '7 hours'
WHERE scan_time IS NOT NULL;
```

This shifts all 7 rows by -7 hours, producing the correct UTC instant.

**Verification:**
- Row count unchanged (7 before, 7 after)
- `raw_payload` unchanged (JSON not modified)
- `device_id`, `device_user_pk`, `employee_id` unchanged
- `corrected_bangkok` display matches `raw_payload->>'timestamp'`

**Strategy B (rebuild from terminal) is also feasible** but unnecessary since Strategy A is deterministic and the terminal data matches exactly.

**Strategy C (leave as-is) is NOT acceptable** because Temporal Identity will compare these `scan_time` values against `valid_from`/`valid_to` intervals.

---

## 8. Dedupe Impact

### 8.1 Current Constraint

```sql
UNIQUE (user_id, device_ip, scan_time)
-- Constraint name: attendance_logs_user_id_device_ip_scan_time_key
```

### 8.2 Timezone Correction Impact

**Timezone correction affects dedupe: YES**

After correcting existing 7 rows (shifting -7 hours), the stored `scan_time` values will change. If the collector is restarted with backfill BEFORE the correction is applied, the backfill would:
1. Read the same 7 records from the terminal
2. Normalize them correctly (with Bangkok timezone)
3. Attempt to INSERT with the correct UTC instant
4. The dedupe constraint would NOT match the old (incorrect) rows
5. **Result: 7 duplicate rows**

**Mitigation:** The correction must be applied BEFORE the collector is restarted with the new normalization code. The implementation sequence in `TimestampTimezone-002` must be:

1. Stop collector
2. Apply code changes (normalization function)
3. Apply historical data correction (UPDATE -7h)
4. Rebuild collector container
5. Start collector
6. Verify backfill does not create duplicates

### 8.3 Post-Correction Dedupe

After correction, new events normalized with `ZoneInfo("Asia/Bangkok")` will produce the same UTC instant as the corrected rows, so dedupe will work correctly for future backfill overlap.

---

## 9. Temporal Identity Impact

**Safe to implement TemporalIdentity-002 before correction: NO**

**Reason:** Temporal Identity compares `scan_time` against `valid_from`/`valid_to` intervals. With the current +7 hour offset:
- `scan_time` values are 7 hours ahead of the correct UTC instant
- `valid_from`/`valid_to` will be entered as Bangkok local time and converted to aware timestamps (correct UTC instant)
- The comparison would match attendance to the wrong temporal interval
- Historical reconciliation would attribute scans to incorrect mapping periods

The timezone correction is a **hard prerequisite** for Temporal Identity.

---

## 10. Mapping Timestamp Contract

| Property | Value |
|----------|-------|
| `valid_from` expected input timezone | Asia/Bangkok (administrator enters local time) |
| `valid_to` expected input timezone | Asia/Bangkok (administrator enters local time) |
| Application conversion | Attach `ZoneInfo("Asia/Bangkok")` before TIMESTAMPTZ persistence |
| Compatible with normalized `scan_time` | **YES** (both use the same canonical instant) |

The mapping workflow must use the same `normalize_device_timestamp()` function (or an equivalent `normalize_admin_timestamp()`) to ensure `valid_from`/`valid_to` are stored as the same canonical instant as `scan_time`.

---

## 11. parse_time() Relationship

| Property | Value |
|----------|-------|
| `parse_time()` function | `hour, minute = map(int, val.split(":"))` |
| Live `ON_TIME_START` | `05:00:00` (3 parts) |
| Live `ON_TIME_END` | `10:00:00` (3 parts) |
| `parse_time()` result | `ValueError: too many values to unpack (expected 2)` |
| `scan_time` affected | **NO** (scan_time comes from `attendance.timestamp`, independent of parse_time) |
| `status` affected | **YES** (all records get `status = "UNKNOWN"`) |
| Temporal Identity blocker | **NO** (status field is not used in temporal resolution) |
| Separate defect PromptID | `ADMS-Collector-AttendanceParseTime-001` |

**parse_time does NOT block timezone correction.** The timezone fix operates on `scan_time` (from `attendance.timestamp`), which is completely independent of `parse_time()` (which only affects `status`).

---

## 12. PostgreSQL Timezone Policy

**PostgreSQL timezone change required: NO**

The database runs `timezone = UTC`. This is correct and standard. TIMESTAMPTZ stores an absolute instant regardless of the display timezone. Once the application supplies timezone-aware timestamps, PostgreSQL will correctly store and compare them.

Changing PostgreSQL's `timezone` setting would only affect display, not storage. It would not fix the naive datetime interpretation bug and could introduce confusion.

---

## 13. Server / Container Timezone Policy

**Collector container TZ change required: NO**

The container runs with `/etc/localtime → Etc/UTC` and no `TZ` env var. The application must explicitly interpret ZKTeco device timestamps using `ZoneInfo("Asia/Bangkok")` regardless of container timezone.

Setting `TZ=Asia/Bangkok` in the container would:
- Change Python's `datetime.now()` behavior (not relevant — we don't use `datetime.now()` for scan_time)
- NOT fix the pyzk naive datetime issue (pyzk always returns naive datetime)
- Risk masking the real fix by making `datetime.now()` and device timestamps appear to be in the same timezone by coincidence

**Preferred design: explicit application semantics.**

---

## 14. Test Plan

### 14.1 Normalization Tests

| Test | Description |
|------|-------------|
| `test_normalize_naive_bangkok` | Naive datetime → aware with `+07:00` offset |
| `test_normalize_aware_bangkok` | Already-aware Bangkok → unchanged |
| `test_normalize_aware_utc` | Aware UTC → converted to Bangkok |
| `test_normalize_none_raises` | `None` input → `ValueError` |
| `test_normalize_non_datetime_raises` | String input → `TypeError` |

### 14.2 TIMESTAMPTZ Round-Trip Tests

| Test | Description |
|------|-------------|
| `test_timestamptz_roundtrip` | Naive Bangkok → normalize → INSERT → SELECT → matches correct UTC instant |
| `test_roundtrip_example` | `2026-08-11 08:00:00` Bangkok → stored as `2026-08-11 01:00:00+00` → Bangkok display `2026-08-11 08:00:00+07` |

### 14.3 Realtime / Backfill Equality Tests

| Test | Description |
|------|-------------|
| `test_realtime_normalization` | `save_attendance_log()` with naive timestamp → stored as correct UTC |
| `test_backfill_normalization` | `save_attendance_batch()` with naive timestamp → stored as correct UTC |
| `test_same_scan_realtime_backfill` | Same physical scan via both paths → identical `scan_time` in DB |

### 14.4 Dedupe Tests

| Test | Description |
|------|-------------|
| `test_dedupe_after_normalization` | Same (user_id, device_ip, scan_time) → ON CONFLICT DO NOTHING |
| `test_no_duplicate_after_correction` | After -7h correction, backfill does not create duplicates |

### 14.5 Boundary Tests

| Test | Description |
|------|-------------|
| `test_midnight_boundary` | `23:59:00` Bangkok → `16:59:00+00` UTC (same day in UTC) |
| `test_date_rollover` | `00:01:00` Bangkok → previous day `17:01:00+00` UTC |
| `test_valid_from_boundary` | `scan_time == valid_from` → matches (inclusive) |
| `test_valid_to_boundary` | `scan_time == valid_to` → does NOT match (exclusive) |

### 14.6 Historical Correction Tests

| Test | Description |
|------|-------------|
| `test_correction_row_count_unchanged` | 7 rows before, 7 rows after |
| `test_correction_raw_payload_unchanged` | `raw_payload` JSON not modified |
| `test_correction_device_refs_unchanged` | `device_id`, `device_user_pk` not modified |
| `test_correction_employee_id_unchanged` | `employee_id` not modified |
| `test_correction_bangkok_display_matches_raw` | Corrected Bangkok display = `raw_payload->>'timestamp'` |

### 14.7 Coverage Summary

| Coverage | Value |
|----------|-------|
| Realtime coverage | YES |
| Backfill coverage | YES |
| TIMESTAMPTZ round-trip | YES |
| Dedupe coverage | YES |
| Boundary coverage | YES |
| Historical correction coverage | YES |
| Planned tests | 17 |

---

## 15. Implementation Plan (TimestampTimezone-002)

### 15.1 Write Phase Scope

| Property | Value |
|----------|-------|
| Mode | WRITE — LIMITED APPLICATION TIMESTAMP FIX + CONTROLLED HISTORICAL DATA CORRECTION |
| Application files expected | `app/db.py` (normalization + call sites), `app/collector.py` (watermark comparison), `app/mqtt_client.py` (MQTT payload), possibly `app/timestamp_utils.py` (dedicated utility) |
| Test files expected | `tests/test_timestamp_normalization.py` (new), updates to `tests/test_identity_transition.py`, `tests/test_hybrid_backfill.py` |
| Database rows expected to change | 7 (all `attendance_logs.scan_time` values shifted -7 hours) |
| Schema migration required | NO |
| Docker rebuild required | YES (collector container only) |
| PostgreSQL restart required | NO |
| MQTT restart required | NO |
| Terminal mutation required | NO |

### 15.2 Implementation Sequence

1. Verify checkpoint (this plan approved)
2. Fresh `pg_dump -Fc` backup + `pg_restore -l` verification + SHA256
3. Implement `normalize_device_timestamp()` function
4. Update `save_attendance_log()` — normalize before INSERT
5. Update `save_attendance_batch()` — normalize before INSERT
6. Update `handle_backfilling()` — normalize for watermark comparison
7. Update `publish_attendance()` — normalize for MQTT payload
8. Write tests (17 planned)
9. Stop collector container
10. Apply historical correction: `UPDATE attendance_logs SET scan_time = scan_time - INTERVAL '7 hours'`
11. Verify correction (row count, raw_payload, device refs, Bangkok display)
12. Rebuild collector container
13. Start collector
14. Verify backfill does not create duplicates
15. Verify healthcheck
16. Commit/push
17. Sync ai-brain
18. STOP

### 15.3 Backup Requirement

Fresh pre-write `pg_dump -Fc` required BEFORE any DB write. Must verify:
- `pg_restore -l` readability
- SHA256 recorded
- File size recorded

---

## 16. Checkpoint Plan (TimestampTimezone-003)

| Property | Value |
|----------|-------|
| Mode | LIVE VERIFICATION / CHECKPOINT |
| Git synchronization | Verify TELEPHONE = origin = ai-brain |
| Timestamp round-trip | Verify new attendance stored with correct UTC instant |
| Existing attendance | Verify 7 rows corrected (Bangkok display matches raw_payload) |
| New attendance | Trigger live scan, verify correct timezone |
| Dedupe | Verify no duplicates after backfill overlap |
| Collector | Verify LIVE/HEALTHY |
| Hybrid Backfill | Verify no duplicate insertion |
| Healthcheck | Verify exit code 0 |
| Tests | Verify all pass |
| Backup/recovery | Verify post-correction backup |

---

## 17. Updated Sequencing Lock

```
ADMS-Collector-TemporalIdentity-001
    COMPLETE
        ↓
ADMS-Collector-TimestampTimezone-001
    PLAN ONLY (THIS DOCUMENT)
        ↓
ADMS-Collector-TimestampTimezone-002
    WRITE (implementation + historical correction)
        ↓
ADMS-Collector-TimestampTimezone-003
    CHECKPOINT (live verification)
        ↓
ADMS-Collector-AttendanceParseTime-001
    OPTIONAL / NON-BLOCKING DEFECT TRACK
        ↓
ADMS-Collector-TemporalIdentity-002
    WRITE (temporal resolver implementation)
        ↓
ADMS-Collector-TemporalIdentity-003
    CHECKPOINT
        ↓
Human ↔ Device Mapping workflow
        ↓
Native ADMS Push experimental track
```

---

## 18. Safety Summary

| Property | Value |
|----------|-------|
| Database modified | NO (this plan only) |
| Application modified | NO (this plan only) |
| Schema modified | NO |
| Device modified | NO |
| Mapping rows created | 0 |
| Native Push executed | NO |
| PostgreSQL timezone change | NO (not required) |
| Container TZ change | NO (not required) |
| Device RTC change | NO (prohibited) |

---

## 19. Documentation Classifications

| Item | Classification |
|------|---------------|
| Timezone bug | VERIFIED LIVE |
| pyzk naive datetime | VERIFIED LIVE |
| +7 hour offset | VERIFIED LIVE (all 7 rows) |
| Terminal history available | VERIFIED LIVE |
| zoneinfo availability | VERIFIED LIVE |
| Normalization function | PLANNED |
| Historical correction | PLANNED (DETERMINISTIC) |
| Watermark comparison bug | INFERENCE (latent, masked by first-run) |
| MQTT payload fix | PLANNED |
| Temporal Identity unblock | PLANNED (after 002 + 003) |