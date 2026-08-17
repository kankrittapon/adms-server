# ADMS-Collector-TemporalIdentity-002 — Temporal Identity Implementation Report

**PromptID**: ADMS-Collector-TemporalIdentity-002
**Date**: 2026-08-11
**Mode**: WRITE — LIMITED APPLICATION IMPLEMENTATION + TESTS + LIVE DEPLOYMENT
**Production Target**: ai-brain (192.168.1.248)
**Source Workstation**: TELEPHONE

---

## BASELINE

| Property | Value |
|----------|-------|
| branch | main |
| starting HEAD | 261e3ee238d848b0f6093e194e098984e97e95d5 |
| checkpoint 261e3ee verified | YES |
| TELEPHONE Docker Desktop started | NO |
| origin synchronized | YES |
| ai-brain synchronized before deployment | YES |

---

## PRE-DEPLOY DATABASE

| Table | Count |
|-------|-------|
| human_employees | 120 |
| human_employee_sources | 120 |
| devices | 1 |
| device_users | 2 |
| attendance_logs | 7 |
| employee_device_mappings | 0 |
| employees | 0 |
| sync_events | 2 |

**timestamp checkpoint valid**: YES

---

## IMPLEMENTATION

| Property | Value |
|----------|-------|
| resolver implemented | YES |
| file | `app/db.py` |
| function | `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)` |
| arguments | `cur` (DB cursor), `device_user_pk` (int), `scan_time` (aware datetime) |
| return | `employee_id` UUID string, or `None` |
| mapping_status | VERIFIED ONLY |
| interval | `[valid_from, valid_to)` |
| valid_from inclusive | YES |
| valid_to exclusive | YES |
| scan_time canonical before resolver | YES |

### Resolver SQL

```sql
SELECT employee_id
FROM employee_device_mappings
WHERE device_user_pk = %s
  AND mapping_status = 'VERIFIED'
  AND valid_from <= %s
  AND (valid_to IS NULL OR %s < valid_to)
LIMIT 2;
```

### Call-Site Changes

| Path | File | Function | Change |
|------|------|----------|-------|
| Realtime | `app/db.py` | `save_attendance_log()` | Pass `scan_time` to resolver |
| Backfill | `app/db.py` | `save_attendance_batch()` | Moved resolution inside per-record loop (scan_time varies per record) |

---

## RESOLUTION BEHAVIOR

| Condition | Result |
|-----------|--------|
| zero matches | `None` (employee_id = NULL) |
| one match | `employee_id` UUID string |
| multiple matches | `None` (ambiguity fail-safe, error logged) |
| ambiguity fails safe | YES |
| automatic mapping | NO |
| Human auto-creation | NO |

---

## INGESTION

| Property | Value |
|----------|-------|
| Realtime uses temporal resolver | YES |
| Hybrid Backfill uses temporal resolver | YES |
| shared resolver | YES (`resolve_verified_employee_mapping()`) |
| attendance employee_id persistence | VERIFIED |
| MQTT consistency | MQTT does not include `employee_id` in payload — no schema change needed. MQTT publishes `user_id`, `scan_time`, `status`, `punch_type`. Database is authoritative for `employee_id`. |

---

## DEDUPE

| Property | Value |
|----------|-------|
| constraint | `UNIQUE (user_id, device_ip, scan_time)` |
| changed | NO |
| regression | PASS |

---

## TESTS

| Property | Value |
|----------|-------|
| previous baseline | 54/54 |
| total | 87 |
| passed | 87 |
| failed | 0 |
| skipped | 0 |

### Test Breakdown

| Suite | Tests | Passed |
|-------|-------|--------|
| test_collector.py | 5 | 5 |
| test_excel_human_master_import.py | 5 | 5 |
| test_healthcheck.py | 13 | 13 |
| test_hybrid_backfill.py | 4 | 4 |
| test_identity_transition.py | 6 | 6 |
| test_temporal_identity.py | 33 | 33 |
| test_timestamp_timezone.py | 21 | 21 |

### Temporal Identity Test Coverage

| Test | Result |
|------|--------|
| no mapping | PASS |
| active VERIFIED | PASS |
| non-VERIFIED ignored | PASS |
| future mapping | PASS |
| expired mapping | PASS |
| valid_from boundary (inclusive) | PASS |
| valid_to boundary (exclusive) | PASS |
| open-ended mapping (valid_to NULL) | PASS |
| historical mapping | PASS |
| different device_user_pk | PASS |
| multiple match ambiguity | PASS |
| ambiguity logs error | PASS |
| Realtime uses temporal resolver | PASS |
| Backfill uses temporal resolver | PASS |
| same event → same identity | PASS |
| unmapped → employee_id NULL | PASS |
| no Human auto-creation | PASS |
| no legacy employee stub | PASS |
| dedupe constraint unchanged | PASS |
| no Excel row mapping | PASS |
| no display_name mapping | PASS |
| no numeric user_id mapping | PASS |
| timestamp normalization preserved | PASS |
| scan_time canonical before resolver (realtime) | PASS |
| scan_time canonical before resolver (backfill) | PASS |

---

## GIT / DEPLOYMENT

| Property | Value |
|----------|-------|
| implementation commit | `f9f1a67f195102c85db94381b87cca123bfa9ce7` |
| push | YES |
| ai-brain pull | YES |
| Collector rebuilt | YES |
| PostgreSQL rebuilt | NO |
| MQTT rebuilt | NO |
| unrelated containers modified | NO |

---

## RUNTIME

| Component | Status |
|-----------|--------|
| Collector | Up (healthy), ~1 min |
| restart count | 0 |
| PostgreSQL | Up (healthy), ~6h |
| MQTT | Up, ~5h, connected |
| ZKTeco | Connected |
| FSM | LIVE |
| Hybrid Backfill | OPERATIONAL (7 seen, 1 candidate, 0 inserted, 1 duplicate skipped) |
| Healthcheck | HEALTHY |

### Log Inspection

- No SQL errors
- No timestamp errors
- No naive-vs-aware errors
- No mapping resolver errors
- No unexpected ambiguity
- No restart loop
- parse_time warning present (expected, non-blocking, reserved for ADMS-Collector-AttendanceParseTime-001)

---

## LIVE ZERO-MAPPING RESULT

| Property | Value |
|----------|-------|
| employee_device_mappings | 0 |
| resolver production result | UNMAPPED |
| attendance employee_id NULL | YES (all 7 rows) |
| automatic mappings created | 0 |
| Human records created | 0 |
| legacy stubs created | 0 |

---

## POST-DEPLOY DATABASE

| Table | Count |
|-------|-------|
| human_employees | 120 |
| human_employee_sources | 120 |
| devices | 1 |
| device_users | 2 |
| attendance before | 7 |
| attendance after | 7 |
| legitimate attendance delta | 0 (no new terminal scans) |
| employee_device_mappings | 0 |
| sync_events | 3 (+1 from new backfill cycle) |

---

## TIMESTAMP

| Property | Value |
|----------|-------|
| canonical normalization preserved | YES |
| timezone | Asia/Bangkok |
| timestamp regression | PASS |

---

## OUT-OF-SCOPE FEATURES

| Feature | Status |
|---------|--------|
| historical reconciliation implemented | NO |
| automatic roster lifecycle implemented | NO |
| parse_time fixed | NO |
| Human ↔ Device Mapping WRITE executed | NO |
| Native ADMS Push executed | NO |

---

## DOCUMENTATION

| Property | Value |
|----------|-------|
| report created | YES |
| canonical docs updated | YES |
| STATUS updated | YES |
| documentation commit | (this commit) |
| push | YES |

---

## FINAL GIT

| Node | HEAD |
|------|------|
| TELEPHONE | (after docs commit) |
| origin/main | (after push) |
| ai-brain | (after sync) |
| synchronized | YES |

---

## FINAL

    PromptID: ADMS-Collector-TemporalIdentity-002

    Temporal resolver implemented: YES
    VERIFIED-only resolution: YES
    [valid_from, valid_to) semantics: YES
    canonical scan_time used: YES
    ambiguity fails safe: YES
    Realtime integration: PASS
    Hybrid Backfill integration: PASS
    dedupe: PASS
    timestamp regression: PASS
    tests: 87/87
    Collector: OPERATIONAL
    Healthcheck: HEALTHY
    employee_device_mappings: 0
    automatic mappings created: 0
    Human Master preserved: YES
    device modified: NO
    Temporal Identity positive production mapping tested: NO
    reason: Production has zero mappings; positive behavior verified in automated tests only.
    historical reconciliation: NOT IMPLEMENTED
    automatic roster lifecycle: NOT IMPLEMENTED
    parse_time: NOT FIXED
    Native ADMS Push: NOT EXECUTED
    next required PromptID: ADMS-Collector-TemporalIdentity-003
    safe to proceed to checkpoint: YES
    safe to proceed directly to Human ↔ Device Mapping: NO
    blockers: NONE

    STOP.