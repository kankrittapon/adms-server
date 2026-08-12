# ADMS — BACKEND PRODUCTION BASELINE

**Established:** `ADMS-Backend-Finalization-001` (2026-08-12) — AUTHORITATIVE BACKEND FINAL BASELINE
**Recovery point:** `backups/adms_backend_final_20260812_140826.dump` (SHA256 `08169e66…`, 105 TOC, pg_restore -l PASS)
**Git baseline:** `fe247e7` (implementation) — all nodes synchronized

---

## 1. Scope & Status

The backend/data/identity foundation is **100% COMPLETE** for the current project scope:

- Attendance capture, timestamp normalization, status classification, hybrid backfill
- Human Master (120 records) + provenance (120 source links)
- RTN rank normalization (reference layer only — rank is metadata, never identity)
- Production scope / พลทหาร exclusion (36 excluded reversibly, `production_scope` flag)
- Device User lifecycle (roster-driven active/inactive)
- Controlled enrollment infrastructure (ID allocator 1001+, reservation, state machine, terminal account creation, physical fingerprint workflow, controlled scan)
- Temporal identity resolver + VERIFIED mapping creation + deterministic attendance reconciliation
- Multi-fingerprint (same-Human) validated
- Backups, tests (224/224), runtime health, Git/deployment sync

## 2. Production Topology

| Component | Detail |
|---|---|
| Server | ai-brain (192.168.1.248) |
| Containers | `adms_postgres` · `adms_mqtt` · `adms_zkteco_listener` |
| ZKTeco device | SONIC ZEM560 #1, 192.168.1.201:4370 (Ver 6.60 Aug 26 2011) |
| Timezone | Asia/Bangkok — `normalize_device_timestamp()` (canonical, UTC storage) |
| Attendance time window | `ON_TIME_START=05:00:00` · `ON_TIME_END=10:00:00` (HH:MM:SS) |
| MQTT | `attendance/events` (real-time notification only) |

## 3. Identity State

| Item | Value |
|---|---|
| Human | กฤตพล หมาดเส็น — `039c4486-b30f-4ce1-b780-783cd268858d` |
| Terminal account | 1001 / uid 1 / privilege 0 (NORMAL) |
| device_user_pk | 7 |
| VERIFIED mapping | mapping_id 1, valid_from `2026-08-12 08:47:37+00`, valid_to NULL, CONTROLLED_SCAN |
| Legacy IDs | 1, 2 — RETIRED / inactive, never auto-reused |
| Mappings | exactly 1 VERIFIED · automatic mappings 0 |
| Attendance | 10 rows: 3 attributed (ids 12/15/16), 7 legacy NULL; statuses 8 LATE + 2 ON_TIME |

## 4. DB Baseline (authoritative)

```
human_employees            120   (production_scope: 84 true / 36 false พลทหาร)
human_employee_sources     120
devices                      1
device_users                 3   (pk1 "2" inactive, pk2 "1" inactive, pk7 "1001" active)
device_user_enrollments      1   (#1 READY_FOR_MAPPING → mapped)
employee_device_mappings     1   (mapping_id 1 VERIFIED)
attendance_logs             10   (duplicates 0)
```

## 5. Attendance Status Contract

`parse_time()` accepts `HH:MM` and `HH:MM:SS`; invalid → `ValueError` → `determine_status()` → `UNKNOWN` (fail-safe). Time-of-day only. Timezone owned by `normalize_device_timestamp()`.

## 6. Enrollment Contract

- Production namespace **1001+**; legacy 1/2 blocked; monotonic, no recycling
- `reserve_next_device_user_id()` requires Human exists, device exists, `production_scope=true`, ID free on terminal + not reserved + not retired
- `create_reserved_terminal_account()` — NORMAL privilege, fail-safe on existing ID
- Physical fingerprint enrollment at terminal only; ADMS never stores templates
- Controlled scan → READY_FOR_MAPPING → explicit VERIFIED mapping (never automatic)

## 7. Frontend Handoff

Backend data foundation READY. **API GAP:** no UI-facing REST/HTTP layer yet (MQTT `attendance/events` + internal functions only). Frontend phases will define API contracts before/with implementation.

## 8. Deferred / Experimental

- Multi-person physical validation — DEFERRED until personnel available
- Native ADMS Push — EXPERIMENTAL / DEFERRED (not part of backend acceptance)
- Frontend — NOT IMPLEMENTED (next)

## 9. Known Non-Blocking Notes

- Attendance `punch`/event semantics: ZEM560 `status=1` in raw_payload is the terminal's verify/event code; `UNKNOWN`-status defect resolved; further punch-type semantics are out of current scope.
