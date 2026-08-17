# ADMS Collector Temporal Identity — Live Verification Checkpoint

**PromptID:** `ADMS-Collector-TemporalIdentity-003`  
**Mode:** `CHECKPOINT — READ-ONLY LIVE VERIFICATION + DOCUMENTATION WRITE ONLY`  
**Date:** 2026-08-11  
**Production Target:** `ai-brain` (`192.168.1.248`)  
**Source Workstation:** `TELEPHONE`

---

## 1. Purpose

Verify and checkpoint the Temporal Identity implementation completed by `ADMS-Collector-TemporalIdentity-002`.

This checkpoint proves that Temporal Human resolution is correctly implemented and production-safe before any Human ↔ Device Mapping WRITE is authorized.

**No writes performed:**
- No mappings created or modified
- No attendance rows modified
- No Human Master modified
- No schema modified
- No application code modified
- No Collector rebuild
- No service restart
- No ZKTeco modification
- No roster lifecycle implemented
- No parse_time fix
- No Native ADMS Push

---

## 2. Git Checkpoint

### TELEPHONE

```
branch: main
HEAD: ea80fb4eef490f73e92ccf9d74948efa1c025ed5
origin/main: ea80fb4eef490f73e92ccf9d74948efa1c025ed5
```

Ancestry includes:
- `f9f1a67` (implementation commit)
- `ea80fb4` (documentation commit)

No tracked drift. Untracked: `.agent/`, `docs/reports/ADMS-Server-DeploymentDiscovery-001.md`.

### ai-brain

```
hostname: ai-brain
branch: main
HEAD: ea80fb4eef490f73e92ccf9d74948efa1c025ed5
origin/main: ea80fb4eef490f73e92ccf9d74948efa1c025ed5
```

All three nodes synchronized at `ea80fb4`.

---

## 3. Live Database Baseline

| Metric | Value |
|--------|-------|
| human_employees | 120 |
| human_employee_sources | 120 |
| devices | 1 |
| device_users | 2 |
| attendance_logs | 7 |
| employee_device_mappings | 0 |
| employees | 0 |
| sync_events | 3 |

### Attendance employee_id

| Metric | Value |
|--------|-------|
| employee_id NULL | 7 |
| employee_id non-NULL | 0 |

All 7 attendance rows have `employee_id = NULL` — expected with 0 mappings.

### Sync Events

```
3 | HISTORICAL_BACKFILL | Backfill complete: 7 seen, 1 candidates, 0 inserted, 1 duplicates skipped
2 | HISTORICAL_BACKFILL | Backfill complete: 7 seen, 1 candidates, 0 inserted, 1 duplicates skipped
1 | HISTORICAL_BACKFILL | Backfill complete: 7 seen, 7 candidates, 7 inserted, 0 duplicates skipped
```

---

## 4. Temporal Resolver Source Verification

### File

`app/db.py` (line 82)

### Function

```python
def resolve_verified_employee_mapping(
    cur: Any,
    device_user_pk: int,
    scan_time: datetime,
) -> Optional[str]:
```

### Arguments

- `cur` — database cursor
- `device_user_pk` — integer device user primary key
- `scan_time` — timezone-aware datetime (canonical, post-normalization)

### Return Behavior

- 0 matches → `None` (unmapped)
- 1 match → `str(employee_id)` (UUID string)
- >1 matches → `None` + error log (ambiguity fail-safe)

### SQL Query (VERIFIED LIVE — verified from deployed source on ai-brain)

```sql
SELECT employee_id
FROM employee_device_mappings
WHERE device_user_pk = %s
  AND mapping_status = 'VERIFIED'
  AND valid_from <= %s
  AND (valid_to IS NULL OR %s < valid_to)
LIMIT 2;
```

### Key Design Elements

- **VERIFIED-only**: `mapping_status = 'VERIFIED'` — no other status produces identity
- **Temporal interval**: `[valid_from, valid_to)` — valid_from inclusive, valid_to exclusive
- **Ambiguity defense**: `LIMIT 2` + `fetchall()` + length check — never uses `LIMIT 1` or `ORDER BY` to silently select
- **Canonical scan_time**: Resolver receives timestamp AFTER `normalize_device_timestamp()`

---

## 5. VERIFIED-Only Check

**VERIFIED LIVE** — Source code explicitly requires:

```sql
AND mapping_status = 'VERIFIED'
```

No other mapping status (PROBABLE, LEGACY, CANDIDATE, REVOKED) can produce a Human identity.

Verified from deployed source on ai-brain, not solely from tests.

---

## 6. Temporal Boundary Check

### Source SQL Semantics

```sql
valid_from <= %s          -- valid_from inclusive
AND (valid_to IS NULL OR %s < valid_to)  -- valid_to exclusive, NULL = open-ended
```

### Boundary Verification

| Condition | Expected | Source Matches |
|-----------|----------|---------------|
| scan_time < valid_from | NO MATCH | PASS |
| scan_time == valid_from | MATCH | PASS |
| valid_from < scan_time < valid_to | MATCH | PASS |
| scan_time == valid_to | NO MATCH | PASS |
| scan_time > valid_to | NO MATCH | PASS |
| valid_to IS NULL AND scan_time >= valid_from | MATCH | PASS |

All boundaries verified from source and automated tests.

---

## 7. Canonical Timestamp Check

### `normalize_device_timestamp()` (app/timestamp_utils.py, line 24)

```python
def normalize_device_timestamp(value: datetime) -> datetime:
    if value is None:
        raise ValueError("device timestamp is None")
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value).__name__}")
    if value.tzinfo is None:
        return value.replace(tzinfo=BANGKOK_TZ)
    return value.astimezone(BANGKOK_TZ)
```

### Call Path Verification

**Realtime path** (`save_attendance_log`, line 149):
```python
scan_time = normalize_device_timestamp(attendance.timestamp)
...
employee_id = resolve_verified_employee_mapping(cur, device_user_pk, scan_time)
```

**Backfill path** (`save_attendance_batch`, line 226):
```python
scan_time = normalize_device_timestamp(rec.timestamp)
...
emp_id = resolve_verified_employee_mapping(cur, dpk, scan_time)
```

Both paths normalize BEFORE calling resolver. Resolver never receives raw naive timestamp.

---

## 8. Zero Match Behavior

Production state: `employee_device_mappings = 0`

**VERIFIED LIVE:**
- Attendance ingestion succeeds (7 rows in DB)
- All `employee_id = NULL` (7/7)
- No Human creation (human_employees = 120, unchanged)
- No mapping creation (employee_device_mappings = 0)
- No legacy stub creation (employees = 0)

---

## 9. Ambiguity Fail-Safe Source Check

### Implementation

```python
cur.execute(sql, (device_user_pk, scan_time, scan_time))
rows = cur.fetchall()
if len(rows) == 0:
    return None
if len(rows) == 1:
    return str(rows[0][0])
# Ambiguity: >1 matching VERIFIED temporal intervals
log.error(...)
return None
```

**Does NOT use:**
- `LIMIT 1`
- `ORDER BY ... choose first`
- `fetchone()`

Uses `LIMIT 2` + `fetchall()` + explicit length check. Multiple matches → `None` + error log.

**Ambiguity fails safe: YES**

---

## 10. Realtime Path Check

### Call Path (VERIFIED LIVE from deployed source)

```
terminal attendance
→ collector.py: normalize_device_timestamp(rec.timestamp)
→ db.py: save_attendance_log(cfg, attendance)
  → normalize_device_timestamp(attendance.timestamp) → scan_time (aware)
  → get_or_create_device(cur, device_ip)
  → ensure_device_user(cur, device_id, user_id_str) → device_user_pk
  → resolve_verified_employee_mapping(cur, device_user_pk, scan_time) → employee_id
  → INSERT INTO attendance_logs (... employee_id ...) ON CONFLICT DO NOTHING
```

**Realtime temporal resolution: VERIFIED**

---

## 11. Hybrid Backfill Path Check

### Call Path (VERIFIED LIVE from deployed source)

```
collector.py: backfill state
→ db.py: save_attendance_batch(cfg, attendance_records)
  → get_or_create_device(cur, device_ip)
  → ensure_device_user for all unique users → user_pk_map
  → per-record loop:
    → normalize_device_timestamp(rec.timestamp) → scan_time (aware)
    → dpk = user_pk_map.get(user_id_str)
    → resolve_verified_employee_mapping(cur, dpk, scan_time) → emp_id
    → INSERT INTO attendance_logs (... employee_id ...) ON CONFLICT DO NOTHING
```

**Backfill temporal resolution: VERIFIED**

### Shared Resolution Semantics

Both realtime and backfill call the same `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)` function.

Invariant: same `device_user_pk` + same `scan_time` = same `employee_id` regardless of path.

**Shared resolution semantics: YES**

---

## 12. Attendance Persistence Check

### DB Write Path

Both `save_attendance_log` and `save_attendance_batch` INSERT `employee_id` into `attendance_logs.employee_id` column.

### Current Production State

All 7 attendance rows have `employee_id = NULL` (0 mappings).

**employee_id persisted consistently: YES**

---

## 13. Dedupe Check

### Live Constraint

```
attendance_logs_user_id_device_ip_scan_time_key
UNIQUE (user_id, device_ip, scan_time)
```

### Verification

- Temporal Identity does NOT participate in dedupe key
- Dedupe key remains `(user_id, device_ip, scan_time)` — unchanged
- Duplicate attendance rows: 0

**Dedupe: PASS**

---

## 14. Timestamp Regression Check

### Live Timestamp Values

| ID | scan_time (UTC) | Bangkok time |
|----|-----------------|-------------|
| 1 | 2021-03-02 20:14:58+00 | 2021-03-03 03:14:58 |
| 2 | 2021-03-02 20:15:01+00 | 2021-03-03 03:15:01 |
| 3 | 2021-03-02 20:16:40+00 | 2021-03-03 03:16:40 |
| 4 | 2021-03-03 00:46:03+00 | 2021-03-03 07:46:03 |
| 5 | 2026-08-10 12:47:39+00 | 2026-08-10 19:47:39 |
| 6 | 2026-08-10 13:07:27+00 | 2026-08-10 20:07:27 |
| 7 | 2026-08-11 08:30:54+00 | 2026-08-11 15:30:54 |

All timestamps correctly stored as UTC, display as Bangkok (+7). No +7h semantic errors.

**Timestamp regression: PASS**

---

## 15. Runtime Check

| Component | Status |
|-----------|--------|
| PostgreSQL | Up 6 hours (healthy) |
| MQTT | Up 5 hours |
| Collector | Up 14 minutes (healthy) |
| ZKTeco | Connected |
| FSM | LIVE |
| Hybrid Backfill | Operational (7 seen, 1 candidate, 0 inserted, 1 duplicate skipped) |
| Healthcheck | HEALTHY |
| Restart count | 0 (no restarts since deploy) |

No services restarted for this checkpoint.

---

## 16. Log Check

### Collector Logs (last 80 lines)

- FSM transitions: STARTING → CONNECTING → BACKFILLING → LIVE
- ZKTeco connected successfully
- MQTT connected successfully
- Backfill completed: 7 seen, 1 candidate, 0 inserted, 1 duplicate skipped
- Known `parse_time` warning: `failed to determine attendance status: too many values to unpack (expected 2)` — NON-BLOCKING, documented in ADMS-Collector-AttendanceParseTime-001

### Absence Verification

- No temporal resolver exceptions
- No SQL errors
- No timezone errors
- No naive-vs-aware TypeError
- No mapping ambiguity errors (expected under zero-mapping state)
- No restart-loop errors

---

## 17. Test Checkpoint

```
87 passed in 13.55s
```

| Metric | Value |
|--------|-------|
| Total | 87 |
| Passed | 87 |
| Failed | 0 |
| Skipped | 0 |

### Temporal Identity Coverage

| Test | Status |
|------|--------|
| No mapping → None | PASS |
| VERIFIED mapping → employee_id | PASS |
| Non-VERIFIED mapping ignored | PASS |
| Future mapping → no match | PASS |
| Expired mapping → no match | PASS |
| valid_from boundary (inclusive) | PASS |
| valid_to boundary (exclusive) | PASS |
| Open-ended interval (valid_to NULL) | PASS |
| Historical interval | PASS |
| Multiple-match ambiguity → None | PASS |
| Ambiguity logs error | PASS |
| Realtime path uses temporal resolver | PASS |
| Backfill path uses temporal resolver | PASS |
| Same event → same identity both paths | PASS |
| Identity safety regressions (9 tests) | PASS |
| Canonical scan_time before resolver (2 tests) | PASS |

**Temporal Identity coverage: PASS**

---

## 18. Positive Mapping Test Classification

Production positive Human mapping is intentionally NOT tested because:

```
employee_device_mappings = 0
```

| Classification | Status |
|----------------|--------|
| Automated tests | PASS (33 temporal tests) |
| Production positive mapping | NOT TESTED |

This is expected and is NOT a checkpoint failure. No temporary production mapping was created.

---

## 19. Human Master Safety

| Metric | Value |
|--------|-------|
| human_employees | 120 |
| human_employee_sources | 120 |
| UUID integrity (employee_id) | 120/120 (all present) |
| Provenance integrity (source_file) | 120/120 (all present) |

Temporal Resolver does not modify Human Master. **Modified: NO**

---

## 20. Device Safety

| Check | Status |
|-------|--------|
| Device modified | NO |
| Fingerprints modified | NO |
| Terminal users modified | NO |
| Attendance cleared | NO |

Read-only Collector operation only.

---

## 21. Out-of-Scope Status

| Item | Status |
|------|--------|
| Historical attendance reconciliation | NOT IMPLEMENTED |
| Automatic roster lifecycle | NOT IMPLEMENTED |
| parse_time defect | NOT FIXED |
| Human ↔ Device Mapping WRITE | NOT EXECUTED |
| Native ADMS Push | NOT EXECUTED |

---

## 22. Recovery Point Check

### Authoritative Backup

```
file: backups/adms_post_timestamp_timezone_20260811_184500.dump
exists: YES
SHA256: f0e64f477a167712eda16c8670935513b8bf8e38ce18df349d49a276674ec0b1
pg_restore -l: VERIFIED (79 TOC entries, archive readable)
```

From `ADMS-Collector-TimestampTimezone-003`. No new backup created (no DB mutation occurred).

---

## 23. Mapping Readiness Decision

### PASS Requirements

| Requirement | Status |
|-------------|--------|
| Temporal Resolver source verified | PASS |
| VERIFIED-only behavior verified | PASS |
| [valid_from, valid_to) verified | PASS |
| Canonical timestamp input verified | PASS |
| Ambiguity fail-safe verified | PASS |
| Realtime verified | PASS |
| Backfill verified | PASS |
| Dedupe preserved | PASS |
| Runtime healthy | PASS |
| Tests pass (87/87) | PASS |
| employee_device_mappings remains 0 | PASS |

**Human ↔ Device Mapping PLAN may be authorized.** NOT WRITE.

---

## 24. Next Phase Sequencing

Recommended next core PromptID:

```
ADMS-Data-HumanDeviceMapping-002
```

Mode: `READ-ONLY / WORKFLOW PLAN ONLY`

Purpose: Design the administrator-controlled mapping workflow using:
- 120 Human Master records
- 2 current device users
- Temporal valid_from / valid_to
- verified_by, verification_method, verification_note
- Device lifecycle evidence
- Controlled scan evidence

No automatic mapping creation.

---

## 25. parse_time Track

Known separate defect: `ADMS-Collector-AttendanceParseTime-001`

Non-blocking for Temporal Identity. Not executed automatically.

---

## 26. Native ADMS Push

Status: `EXPERIMENTAL / DEFERRED`

Not executed.

---

## 27. Checkpoint Summary

| Item | Value |
|------|-------|
| Temporal Resolver | LIVE VERIFIED |
| Production mappings | 0 |
| Positive resolution | Automated-test verified only |
| Historical reconciliation | NOT IMPLEMENTED |
| Roster lifecycle | NOT IMPLEMENTED |
| Mapping WRITE | Still unauthorized |
| Implementation commit | f9f1a67f195102c85db94381b87cca123bfa9ce7 |
| Documentation commit | ea80fb4eef490f73e92ccf9d74948efa1c025ed5 |
| Checkpoint commit | (this commit) |

---

## 28. Checkpoint Principle

This checkpoint does NOT prove that a real Human has already been mapped.

It proves that when an explicitly verified mapping is created later, the Collector has a safe and deterministic mechanism to resolve it by:

```
device_user_pk
+ canonical scan_time
+ VERIFIED status
+ [valid_from, valid_to)
```

Only after PASS may the project move into the Human ↔ Device Mapping PLAN.

---

FINAL

PromptID: ADMS-Collector-TemporalIdentity-003

checkpoint: PASS

STOP.