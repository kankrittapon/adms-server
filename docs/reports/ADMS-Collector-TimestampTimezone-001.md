# ADMS Collector Timestamp / Timezone — Audit & Plan Report

**PromptID:** ADMS-Collector-TimestampTimezone-001
**Mode:** READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY
**Date:** 2026-08-11

---

## BASELINE

| Property | Value |
|----------|-------|
| branch | `main` |
| starting HEAD | `de5bb4edb167add7ea032fc1fbece472574fb636` |
| origin/main | `de5bb4edb167add7ea032fc1fbece472574fb636` |
| ai-brain HEAD | `de5bb4edb167add7ea032fc1fbece472574fb636` |
| runtime | PostgreSQL HEALTHY, MQTT OPERATIONAL, Collector LIVE/HEALTHY, ZKTeco CONNECTED |
| employee_device_mappings | 0 |

---

## SERVER TIME

| Property | Value |
|----------|-------|
| ai-brain timezone | `Asia/Bangkok (+07, +0700)` |
| UTC offset | +07:00 |
| NTP | active, synchronized |
| Collector container timezone | UTC (`/etc/localtime → /usr/share/zoneinfo/Etc/UTC`, no `TZ` env) |

---

## POSTGRESQL

| Property | Value |
|----------|-------|
| timezone | `UTC` |
| current timestamp | `2026-08-11 11:15:37.650774+00` |
| attendance_logs.scan_time type | `timestamp with time zone` (TIMESTAMPTZ) |
| valid_from type | `timestamp with time zone` (TIMESTAMPTZ) |
| valid_to type | `timestamp with time zone` (TIMESTAMPTZ) |

---

## PYZK TIMESTAMP

| Property | Value |
|----------|-------|
| source field | `Attendance.timestamp` |
| Python type | `datetime.datetime` |
| tzinfo | `None` (naive) |
| device clock interpretation | LOCAL_BANGKOK |
| evidence | Terminal clock 18:14 vs actual UTC 11:14; all 7 terminal records have `tzinfo=None`; raw_payload preserves naive ISO string |

---

## CURRENT TIMESTAMP PATH

| Property | Value |
|----------|-------|
| source | `pyzk Attendance.timestamp` (naive datetime) |
| normalization | **NONE** — naive datetime passed directly to psycopg2 |
| persistence | `psycopg2 cur.execute(sql, (..., scan_time, ...))` → TIMESTAMPTZ interpreted as UTC |
| timezone attached before DB | **NO** |
| current semantic bug | Naive Bangkok local time (UTC+7) interpreted as UTC → stored instant is +7 hours ahead of correct UTC |

### Realtime path:
```
pyzk Attendance.timestamp → collector.py handle_live() → db.py save_attendance_log() → scan_time = attendance.timestamp → psycopg2 INSERT → TIMESTAMPTZ (as UTC)
```

### Backfill path:
```
pyzk get_attendance() → collector.py handle_backfilling() → db.py save_attendance_batch() → scan_time = rec.timestamp → psycopg2 INSERT → TIMESTAMPTZ (as UTC)
```

### Watermark comparison (latent bug):
```
db.py get_device_watermark() → SELECT MAX(scan_time) → aware datetime (UTC)
collector.py handle_backfilling() → rec.timestamp >= boundary → naive vs aware → TypeError (masked by first-run boundary=None)
```

---

## LIVE OFFSET VERIFICATION

| Row | raw_payload timestamp | stored scan_time (UTC) | corrected UTC (-7h) | corrected Bangkok |
|-----|----------------------|------------------------|---------------------|-------------------|
| 1 | `2021-03-03T03:14:58` | `2021-03-03 03:14:58+00` | `2021-03-02 20:14:58+00` | `2021-03-03 03:14:58+07` |
| 2 | `2021-03-03T03:15:01` | `2021-03-03 03:15:01+00` | `2021-03-02 20:15:01+00` | `2021-03-03 03:15:01+07` |
| 3 | `2021-03-03T03:16:40` | `2021-03-03 03:16:40+00` | `2021-03-02 20:16:40+00` | `2021-03-03 03:16:40+07` |
| 4 | `2021-03-03T07:46:03` | `2021-03-03 07:46:03+00` | `2021-03-03 00:46:03+00` | `2021-03-03 07:46:03+07` |
| 5 | `2026-08-10T19:47:39` | `2026-08-10 19:47:39+00` | `2026-08-10 12:47:39+00` | `2026-08-10 19:47:39+07` |
| 6 | `2026-08-10T20:07:27` | `2026-08-10 20:07:27+00` | `2026-08-10 13:07:27+00` | `2026-08-10 20:07:27+07` |
| 7 | `2026-08-11T15:30:54` | `2026-08-11 15:30:54+00` | `2026-08-11 08:30:54+00` | `2026-08-11 15:30:54+07` |

| Property | Value |
|----------|-------|
| sample device/pyzk time | `2026-08-11 15:30:54` (naive, row 7) |
| stored scan_time | `2026-08-11 15:30:54+00` |
| stored UTC equivalent | `2026-08-11 15:30:54Z` |
| Bangkok display | `2026-08-11 22:30:54+07` |
| verified offset | **+7 hours** (stored instant is 7 hours ahead of correct UTC) |
| corrected UTC | `2026-08-11 08:30:54+00` |
| corrected Bangkok | `2026-08-11 15:30:54+07` (matches raw_payload) |

---

## CANONICAL CONTRACT

| Property | Value |
|----------|-------|
| device timezone | Asia/Bangkok |
| application input | NAIVE LOCAL DEVICE TIME |
| normalization output | Timezone-aware datetime with `ZoneInfo("Asia/Bangkok")` |
| database storage | TIMESTAMPTZ |
| display timezone | Asia/Bangkok |
| PostgreSQL global timezone change required | **NO** |
| Collector container TZ change required | **NO** |

---

## NORMALIZATION DESIGN

| Property | Value |
|----------|-------|
| proposed function | `normalize_device_timestamp(value: datetime) -> datetime` |
| naive input behavior | Attach `ZoneInfo("Asia/Bangkok")` via `value.replace(tzinfo=BANGKOK_TZ)` |
| aware input behavior | Convert to Bangkok via `value.astimezone(BANGKOK_TZ)` |
| None input behavior | Raise `ValueError` |
| non-datetime input behavior | Raise `TypeError` |
| Realtime call site | `app/db.py save_attendance_log()` — after `scan_time = attendance.timestamp` |
| Backfill call site | `app/db.py save_attendance_batch()` — after `scan_time = rec.timestamp` |
| Watermark comparison call site | `app/collector.py handle_backfilling()` — normalize `rec.timestamp` before comparison with aware boundary |
| MQTT call site | `app/mqtt_client.py publish_attendance()` — normalize before `.isoformat()` |
| shared normalization | **YES** (same function for realtime and backfill) |

### Proposed function:
```python
from zoneinfo import ZoneInfo
from datetime import datetime

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

def normalize_device_timestamp(value: datetime) -> datetime:
    if value is None:
        raise ValueError("device timestamp is None")
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value)}")
    if value.tzinfo is None:
        return value.replace(tzinfo=BANGKOK_TZ)
    return value.astimezone(BANGKOK_TZ)
```

### Python environment verification:
- Python 3.12.13 in collector container
- `zoneinfo.ZoneInfo("Asia/Bangkok")` — **AVAILABLE** (system tz database present)
- `tzdata` package not required

---

## EXISTING ATTENDANCE

| Property | Value |
|----------|-------|
| rows inspected | 7 |
| rows affected | 7 (ALL) |
| raw timestamp evidence available | **YES** (raw_payload JSON contains original naive timestamp) |
| terminal history available | **YES** (all 7 records still on ZKTeco terminal flash memory) |
| correction feasibility | **DETERMINISTIC** |
| recommended correction strategy | **A** (Correct Existing Rows) |
| reason | All 7 rows have deterministic +7h offset; raw_payload preserves original naive timestamp; corrected Bangkok display matches raw_payload exactly for all rows; terminal data confirms same values |

---

## DEDUPE

| Property | Value |
|----------|-------|
| current constraint | `UNIQUE (user_id, device_ip, scan_time)` — `attendance_logs_user_id_device_ip_scan_time_key` |
| timezone correction affects dedupe | **YES** |
| duplicate risk | If collector restarts with new normalization BEFORE historical correction, backfill would create 7 duplicate rows (new correct UTC instants won't match old incorrect ones) |
| mitigation | Stop collector → apply code changes → apply historical correction (-7h) → rebuild → start collector. Correction MUST be applied before collector restart with new normalization. |

---

## TEMPORAL IDENTITY IMPACT

| Property | Value |
|----------|-------|
| safe to implement TemporalIdentity-002 before correction | **NO** |
| reason | Temporal Identity compares `scan_time` against `valid_from`/`valid_to`. With +7h offset, `scan_time` values are 7 hours ahead of correct UTC. `valid_from`/`valid_to` will be entered as Bangkok local and converted to correct UTC instants. The comparison would match attendance to the wrong temporal interval. Historical reconciliation would attribute scans to incorrect mapping periods. |

---

## MAPPING TIMESTAMP CONTRACT

| Property | Value |
|----------|-------|
| valid_from expected input timezone | Asia/Bangkok (administrator enters local time) |
| valid_to expected input timezone | Asia/Bangkok (administrator enters local time) |
| compatible with normalized scan_time | **YES** (both use same canonical instant via ZoneInfo("Asia/Bangkok")) |

---

## PARSE_TIME

| Property | Value |
|----------|-------|
| scan_time affected | **NO** |
| status affected | **YES** (all records get `status = "UNKNOWN"` due to `parse_time()` failing on `HH:MM:SS` format) |
| Temporal Identity blocker | **NO** |
| separate defect PromptID | `ADMS-Collector-AttendanceParseTime-001` |

---

## TEST PLAN

| Property | Value |
|----------|-------|
| planned tests | 17 |
| Realtime coverage | YES |
| Backfill coverage | YES |
| TIMESTAMPTZ round-trip | YES |
| Dedupe coverage | YES |
| Boundary coverage | YES |
| Historical correction coverage | YES |

### Test categories:
1. Normalization tests (5): naive, aware Bangkok, aware UTC, None, non-datetime
2. TIMESTAMPTZ round-trip tests (2): general round-trip, specific example
3. Realtime/backfill equality tests (3): realtime, backfill, same-scan equality
4. Dedupe tests (2): after normalization, no duplicate after correction
5. Boundary tests (4): midnight, date rollover, valid_from inclusive, valid_to exclusive
6. Historical correction tests (5): row count, raw_payload, device refs, employee_id, Bangkok display

### Example test case:
```
Device wall time: 2026-08-11 08:00:00 Asia/Bangkok
Expected UTC instant: 2026-08-11 01:00:00Z
Expected Bangkok display: 2026-08-11 08:00:00+07
```

---

## DATABASE WRITE REQUIRED IN 002

| Property | Value |
|----------|-------|
| database write required | **YES** |
| reason | 7 existing attendance_logs rows have incorrect scan_time (+7h offset). Must apply `UPDATE attendance_logs SET scan_time = scan_time - INTERVAL '7 hours'` to correct the stored UTC instant. |
| fresh pre-write pg_dump required | **YES** |

---

## IMPLEMENTATION PLAN

| Property | Value |
|----------|-------|
| next PromptID | `ADMS-Collector-TimestampTimezone-002` |
| application files expected | `app/db.py`, `app/collector.py`, `app/mqtt_client.py`, possibly `app/timestamp_utils.py` |
| database rows expected to change | 7 (all attendance_logs.scan_time shifted -7 hours) |
| schema migration required | **NO** |
| Docker rebuild required | **YES** (collector container only) |
| PostgreSQL restart required | **NO** |
| MQTT restart required | **NO** |
| terminal mutation required | **NO** |

### Implementation sequence:
1. Verify checkpoint
2. Fresh `pg_dump -Fc` backup + verify
3. Implement `normalize_device_timestamp()`
4. Update `save_attendance_log()`, `save_attendance_batch()`, `handle_backfilling()`, `publish_attendance()`
5. Write tests (17)
6. Stop collector
7. Apply historical correction (`UPDATE ... SET scan_time = scan_time - INTERVAL '7 hours'`)
8. Verify correction
9. Rebuild collector container
10. Start collector
11. Verify no duplicates
12. Verify healthcheck
13. Commit/push/sync
14. STOP

---

## CHECKPOINT PLAN

| Property | Value |
|----------|-------|
| PromptID | `ADMS-Collector-TimestampTimezone-003` |
| Mode | LIVE VERIFICATION / CHECKPOINT |
| Verification items | Git sync, timestamp round-trip, existing attendance correctness, new attendance correctness, dedupe, Collector, Hybrid Backfill, Healthcheck, tests, backup/recovery point |

---

## SAFETY

| Property | Value |
|----------|-------|
| database modified | NO |
| application modified | NO |
| schema modified | NO |
| device modified | NO |
| mapping rows created | 0 |
| Native Push executed | NO |

---

## DOCUMENTATION

| Property | Value |
|----------|-------|
| report created | YES |
| canonical docs updated | YES (`docs/collector/COLLECTOR_TIMESTAMP_TIMEZONE.md`) |
| STATUS updated | YES |
| documentation commit | (pending) |
| push | (pending) |

---

## FINAL

PromptID: ADMS-Collector-TimestampTimezone-001

| Property | Value |
|----------|-------|
| timezone bug independently verified | YES |
| pyzk timestamp is naive | YES |
| device clock is Asia/Bangkok local | YES |
| current TIMESTAMPTZ interpretation incorrect | YES |
| verified offset | +7 hours (all 7 rows) |
| existing attendance affected | YES (7/7 rows) |
| historical correction required | YES |
| historical correction safe | YES (DETERMINISTIC — raw_payload + terminal data confirm all values) |
| canonical timezone contract defined | YES |
| PostgreSQL timezone change required | NO |
| device RTC change required | NO |
| Schema migration required | NO |
| application correction required | YES |
| TemporalIdentity-002 remains blocked | YES |
| parse_time blocks timezone correction | NO |
| implementation plan complete | YES |
| next authorized PromptID | ADMS-Collector-TimestampTimezone-002 |
| safe to proceed | YES (for implementation phase) |
| blockers | NONE |

STOP.