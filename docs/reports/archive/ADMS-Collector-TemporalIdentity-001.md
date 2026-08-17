# ADMS-Collector-TemporalIdentity-001 — Audit & Plan Report

**PromptID:** ADMS-Collector-TemporalIdentity-001
**Mode:** READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY
**Date:** 2026-08-11

---

## BASELINE

| Property | Value |
|----------|-------|
| branch | `main` |
| starting HEAD | `a24006156160376adf43e4d70d6282e85b619df5` |
| checkpoint a240061 verified | YES |
| origin synchronized | YES |
| ai-brain synchronized | YES |
| runtime healthy | YES |

---

## DATABASE

| Table | Count |
|-------|-------|
| human_employees | 120 |
| human_employee_sources | 120 |
| devices | 1 |
| device_users | 2 |
| attendance_logs | 7 |
| employee_device_mappings | 0 |
| employees | 0 |
| sync_events | 1 |

Human mappings created by this Prompt: **0**

---

## CURRENT RESOLVER

| Property | Value |
|----------|-------|
| file | `app/db.py` |
| function | `resolve_verified_employee_mapping(cur, device_user_pk)` |
| current arguments | `cur: Any, device_user_pk: int` |
| current behavior | **TIMELESS** |
| current SQL | `SELECT employee_id FROM employee_device_mappings WHERE device_user_pk = %s AND mapping_status = 'VERIFIED'` |
| call sites | `save_attendance_log()` (realtime), `save_attendance_batch()` (backfill) |

---

## INGESTION PATH

**Realtime path:**
```
live_capture() → handle_live() → save_attendance_log() → get_or_create_device → ensure_device_user → resolve_verified_employee_mapping → INSERT → commit → MQTT publish
```

**Backfill path:**
```
get_attendance() → handle_backfilling() → watermark filter → save_attendance_batch() → get_or_create_device → ensure_device_user (per unique user) → resolve_verified_employee_mapping (per unique user) → INSERT per record → commit per chunk
```

| Property | Value |
|----------|-------|
| shared persistence path | YES (same resolver function) |
| scan_time available before Human resolution | YES |

---

## TEMPORAL CONTRACT

| Property | Value |
|----------|-------|
| proposed resolver | `resolve_verified_employee_mapping(cur, device_user_pk, scan_time)` |
| mapping status requirement | VERIFIED ONLY |
| interval | `[valid_from, valid_to)` |
| valid_from inclusive | YES |
| valid_to exclusive | YES |
| zero matches | UNMAPPED (return None) |
| one match | RESOLVE (return employee_id) |
| multiple matches | AMBIGUOUS / FAIL SAFE (log + return None + sync_event) |

---

## HISTORICAL RECONCILIATION

| Property | Value |
|----------|-------|
| designed | YES |
| automatic overwrite of existing employee_id | NO |
| unmapped-only default | YES |

---

## DEVICE USER RECYCLING

| Property | Value |
|----------|-------|
| risk confirmed | YES |
| temporal mapping mitigates risk | PARTIAL |
| remaining risk | Requires manual accuracy of valid_from/valid_to boundaries; no automatic detection of account recreation; device_uid changes not monitored |

---

## LIFECYCLE

| Property | Value |
|----------|-------|
| roster_last_seen_at schema | PRESENT |
| inactive_at schema | PRESENT |
| automatic lifecycle detection | NOT IMPLEMENTED |
| recommended future behavior | Roster sync via get_users(); update roster_last_seen_at on presence; set inactive_at on absence; flag admin review on device_uid change; do NOT create new device_user_pk |

---

## DEVICE_UID

| Property | Value |
|----------|-------|
| observed semantics | INT column, NULL for attendance-discovered users, not in any uniqueness constraint, not populated by ensure_device_user() |
| recommended role | DIAGNOSTIC ONLY |
| reason | ZKTeco firmware can reuse uid values; not globally stable; current ingestion does not track uid changes; using as canonical would require roster sync infrastructure |

---

## TRANSACTION

| Property | Value |
|----------|-------|
| current transaction boundary | Realtime: single transaction (device + user + resolve + INSERT + commit). Backfill: per-chunk transaction (device + users + resolve + INSERTs + commit) |
| recommended resolver location | Within same transaction, after ensure_device_user, before INSERT (already the case) |
| dedupe behavior affected | NO |

---

## MQTT

| Property | Value |
|----------|-------|
| current employee_id behavior | NOT included in MQTT payload |
| temporal resolver payload change required | NO |
| reason | MQTT payload uses attendance object fields, not employee_id. Adding employee_id is recommended but deferred. |

---

## PARSE_TIME AUDIT

| Property | Value |
|----------|-------|
| bug confirmed | YES |
| scan_time affected | NO |
| status affected | YES |
| Temporal Identity blocker | NO |
| recommended PromptID | ADMS-Collector-AttendanceParseTime-001 |

---

## TIMEZONE

| Property | Value |
|----------|-------|
| terminal timestamp | Naive datetime, Bangkok local time (UTC+7) — device clock 18:04 vs actual UTC 11:04 |
| Python datetime | Naive (tzinfo=None) from pyzk |
| attendance_logs.scan_time | TIMESTAMPTZ |
| mapping valid_from | TIMESTAMPTZ |
| mapping valid_to | TIMESTAMPTZ |
| PostgreSQL timezone | UTC |
| comparison safe | **NO** |
| blocker | **TIMEZONE MISMATCH** — naive Bangkok local timestamps inserted as TIMESTAMPTZ interpreted as UTC, causing +7 hour offset. Temporal comparisons between scan_time and valid_from/valid_to will produce incorrect results. |

---

## INDEX REVIEW

| Property | Value |
|----------|-------|
| existing indexes sufficient | YES |
| new migration required | NO |
| recommendation | `idx_employee_device_mappings_temporal` on `(device_user_pk, mapping_status, valid_from, valid_to)` fully supports the temporal resolver query |

---

## TEST PLAN

| Property | Value |
|----------|-------|
| planned tests | 17 |
| boundary tests | YES |
| backfill tests | YES |
| realtime tests | YES |
| ambiguity tests | YES |
| identity safety regressions | YES |

---

## IMPLEMENTATION PLAN

| Property | Value |
|----------|-------|
| next PromptID | ADMS-Collector-TemporalIdentity-002 |
| application files expected to change | `app/db.py`, `tests/test_identity_transition.py`, `tests/test_hybrid_backfill.py` |
| database migration required | NO |
| Docker rebuild required | YES |
| PostgreSQL restart required | NO |
| MQTT restart required | NO |
| terminal mutation required | NO |

---

## CHECKPOINT PLAN

| Property | Value |
|----------|-------|
| verification PromptID | ADMS-Collector-TemporalIdentity-003 |

---

## SAFETY

| Property | Value |
|----------|-------|
| database modified | NO |
| application modified | NO |
| schema modified | NO |
| device modified | NO |
| fingerprints modified | NO |
| mapping rows created | 0 |
| Native ADMS Push executed | NO |

---

## DOCUMENTATION

| Property | Value |
|----------|-------|
| report created | YES |
| canonical docs updated | YES (`docs/collector/COLLECTOR_TEMPORAL_IDENTITY.md`) |
| STATUS updated | YES |
| documentation commit | (pending) |
| push | (pending) |

---

## FINAL

PromptID: ADMS-Collector-TemporalIdentity-001

Temporal Identity architecture audited: YES
current resolver temporal: NO (TIMELESS)
scan_time trustworthy: CONDITIONAL (correct values but wrong timezone interpretation)
timezone comparison safe: NO
parse_time blocker: NO
Schema 005 sufficient: YES
new migration required: NO
implementation plan complete: YES
Human ↔ Device Mapping authorized: NO
automatic mapping authorized: NO
Native ADMS Push authorized: NO

next authorized PromptID: ADMS-Collector-TimestampTimezone-001 (BLOCKER FIX)
safe to proceed: YES (for timezone fix only — NOT for temporal identity implementation)
blockers: TIMEZONE MISMATCH — naive Bangkok local timestamps (UTC+7) from pyzk are stored as TIMESTAMPTZ interpreted as UTC, causing +7 hour offset. Must be fixed before temporal identity implementation.

STOP.