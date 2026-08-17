# ADMS-Checkpoint-PostServerRebuild-001

**PromptID**: ADMS-Checkpoint-PostServerRebuild-001
**Type**: Post-Rebuild Checkpoint (READ-ONLY validation + documentation write only)
**Date**: 2026-08-11
**Authority**: AGENTS.md §3 (Default READ-ONLY), §20 (Checkpoints), §25 (Reporting)

---

## 1. Purpose

Establish a formal authoritative checkpoint validating the reconstructed ADMS deployment after `ADMS-Server-DatabaseRebuild-001`. This checkpoint is READ-ONLY: no schema changes, no code changes, no Docker rebuilds, no mapping writes, no terminal mutations.

---

## 2. TELEPHONE Git Baseline

| Property | Value |
|----------|-------|
| Branch | `main` |
| HEAD | `d590d6a57146c216545b62b23e0ae3a33da2362d` |
| origin/main | `d590d6a57146c216545b62b23e0ae3a33da2362d` |
| Working tree | Clean (only untracked `.agent/` and this report) |

**Status**: PASS — TELEPHONE synchronized with origin.

---

## 3. ai-brain Identity

| Property | Value |
|----------|-------|
| Hostname | `ai-brain` |
| User | `kanfullbuster` |
| Working directory | `/home/kanfullbuster` |
| IP addresses | `192.168.1.248`, `100.68.88.63`, multiple Docker bridges |

**Status**: PASS

---

## 4. ai-brain Git Synchronization

| Property | Value |
|----------|-------|
| Branch | `main` |
| server HEAD | `d590d6a57146c216545b62b23e0ae3a33da2362d` |
| origin/main | `d590d6a57146c216545b62b23e0ae3a33da2362d` |
| Remote | `https://github.com/kankrittapon/adms-server.git` |

**Status**: PASS — ai-brain = origin = TELEPHONE (all `d590d6a`).

---

## 5. Docker Compose State

| Project | Status | Containers |
|---------|--------|------------|
| adms-server | running(3) | adms_postgres, adms_mqtt, adms_zkteco_listener |
| backend | running(2) | (unrelated) |
| mcp-brpg | running(1) | (unrelated) |
| minecraft-console | running(1) | (unrelated) |
| n8n-zort | running(10) | (unrelated) |
| notebooklm-mcp-deploy | running(2) | (unrelated) |
| speechybykrittapon | running(1) | (unrelated) |

**ADMS containers**:

| Container | Image | Status | Ports |
|-----------|-------|--------|-------|
| adms_postgres | postgres:16-alpine | Up ~1h (healthy) | 5432/tcp |
| adms_mqtt | eclipse-mosquitto:2 | Up 29m | 127.0.0.1:1883->1883/tcp |
| adms_zkteco_listener | adms-server-listener | Up 9m (healthy) | — |

**Restart counts**: All 3 containers = 0 restarts.

**Unrelated workloads**: 17 containers unchanged (private_postgres, adminer, n8n_zort, paddle_ocr, sailfish_collector, etc.)

**Status**: PASS — All ADMS containers running, 0 restarts, no port collisions, unrelated workloads untouched.

---

## 6. Port Bindings

| Port | Binding | Status |
|------|---------|--------|
| 1883 (MQTT) | `127.0.0.1:1883` | Loopback only — no public exposure |
| 5432 (PostgreSQL) | Internal only | No host binding |
| 4370 (ZKTeco) | Outbound to 192.168.1.201 | No host binding |

**Status**: PASS — No public network exposure.

---

## 7. Docker Volumes & Networks

**Volumes**:
- `adms-server_adms_postgres_data`
- `adms-server_adms_mqtt_data`
- `adms-server_adms_mqtt_log`

**Status**: PASS

---

## 8. Database Identity

| Property | Value |
|----------|-------|
| Database | `adms` |
| Version | PostgreSQL 16.14 (Alpine, x86_64) |

**Status**: PASS

---

## 9. Row Counts

| Table | Count | Expected | Match |
|------|-------|----------|-------|
| human_employees | 120 | 120 | ✓ |
| human_employee_sources | 120 | 120 | ✓ |
| devices | 1 | 1 | ✓ |
| device_users | 2 | 2 | ✓ |
| attendance_logs | 7 | 7 | ✓ |
| employee_device_mappings | 0 | 0 | ✓ |
| employees (legacy stubs) | 0 | 0 | ✓ |
| sync_events | 1 | 1+ | ✓ |

**Status**: PASS — All row counts match expected baseline.

---

## 10. Human Master Integrity

| Check | Result |
|-------|--------|
| Unique UUIDs | 120 / 120 (100%) |
| Orphan sources | 0 |
| Duplicate source_record_keys | 0 |

**Status**: PASS — Human Master data integrity verified.

---

## 11. Device Identity

| Field | Value |
|------|-------|
| device_id | 1 |
| serial_number | 3392113170057 |
| device_name | SONIC ZEM560 #1 |
| device_ip | 192.168.1.201 |
| platform | ZEM560_TFT |
| firmware_version | Ver 6.60 Aug 26 2011 |
| active | true |
| last_seen_at | 2026-08-11 08:34:07 UTC |

**Device users**:

| device_user_pk | device_user_id | device_display_name |
|----------------|----------------|---------------------|
| 2 | 1 | Device User 1 |
| 1 | 2 | Device User 2 |

**Status**: PASS — Device identity matches physical terminal.

---

## 12. Attendance Logs

7 records, all `employee_id = NULL` (unmapped), all `status = UNKNOWN`.

| user_id | scan_time | punch_type | device_user_pk |
|---------|-----------|------------|----------------|
| 1 | 2021-03-03 03:14:58 | 4 | 2 |
| 1 | 2021-03-03 03:15:01 | 4 | 2 |
| 1 | 2021-03-03 03:16:40 | 0 | 2 |
| 1 | 2021-03-03 07:46:03 | 0 | 2 |
| 1 | 2026-08-10 19:47:39 | 0 | 2 |
| 2 | 2026-08-10 20:07:27 | 0 | 1 |
| 1 | 2026-08-11 15:30:54 | 0 | 2 |

**Known pre-existing bug**: `parse_time()` in `app/db.py` unpacks 2 values from `val.split(":")` but `ON_TIME_START`/`ON_TIME_END` are `HH:MM:SS` (3 parts) → "too many values to unpack (expected 2)" → all attendance gets `status=UNKNOWN`. This predates the reconstruction and is outside this checkpoint's scope.

**Status**: PASS — Attendance preserved, unmapped storage working as designed.

---

## 13. Schema 005 Verification

**device_users columns**:
- `roster_last_seen_at` (timestamptz, nullable) ✓
- `inactive_at` (timestamptz, nullable) ✓

**employee_device_mappings columns**:
- `valid_from` (timestamptz, NOT NULL) ✓
- `valid_to` (timestamptz, nullable) ✓
- `verified_by` (text, NOT NULL) ✓
- `verification_method` (text, NOT NULL) ✓
- `verification_note` (text, nullable) ✓

**Constraints**:
- `chk_temporal_validity` ✓
- `chk_verified_metadata` ✓
- `chk_verification_method` ✓

**Partial unique index**:
- `idx_active_verified_device_user` — UNIQUE on `device_user_pk` WHERE `mapping_status = 'VERIFIED' AND valid_to IS NULL` ✓

**Legacy FK** (`attendance_logs_user_id_fkey`): ABSENT ✓

**Status**: PASS — Schema 005 fully applied and verified.

---

## 14. Collector Runtime

**FSM trajectory** (from logs):
```
STARTING → CONNECTING → BACKFILLING → LIVE
```

**Backfill summary**: 7 seen, 7 candidates, 7 inserted, 0 duplicates skipped (0.23s).

**Current state**: LIVE (attendance stream monitoring).

**Healthcheck**: Exit code 0, "HEALTHY - State: LIVE, Device: Connected, DB: HEALTHY".

**Status**: PASS — Collector fully operational.

---

## 15. MQTT

- Client `adms-zkteco-listener` connected to `mqtt:1883`.
- Mosquitto logs show successful connection, periodic reconnect, and database persistence.

**Status**: PASS — MQTT operational.

---

## 16. ZKTeco Terminal Connectivity

| Check | Result |
|-------|--------|
| TCP 4370 reachability | CONNECTED |
| Serial number | 3392113170057 |
| Platform | ZEM560_TFT |

**Status**: PASS — Physical terminal reachable and responding.

---

## 17. Healthcheck

| Check | Result |
|-------|--------|
| Docker health status | healthy |
| Healthcheck exit code | 0 |
| State reported | LIVE |
| Device | Connected |
| DB | HEALTHY |

**Status**: PASS

---

## 18. Tests

| Metric | Value |
|--------|-------|
| Total | 33 |
| Passed | 33 |
| Failed | 0 |
| Skipped | 0 |
| Duration | 13.13s |
| Platform | win32, Python 3.11.8, pytest 9.1.1 |

**Status**: PASS — 33/33 tests passed.

---

## 19. Backup Verification

| Property | Value |
|----------|-------|
| File | `adms_reconstructed_authoritative_20260811_153725.dump` |
| Location | `/home/kanfullbuster/adms-server/backups/` |
| Size | 44,980 bytes |
| SHA256 | `5386681d0ddcb38c840229f121f8fd207302fd3fbb2b394e675bad784bcfd0bd` |
| Format | pg_dump Custom (PGDMP_V1, gzip) |
| pg_dump version | 16.14 |
| pg_restore -l | 79 TOC entries, exit 0 |
| Classification | AUTHORITATIVE |

**Status**: PASS — Backup integrity verified, archive readable.

---

## 20. Git Ignore Verification

| Pattern | Ignored |
|---------|---------|
| `.env` | ✓ |
| `backups/` | ✓ |
| `.agent/` | ✓ (via `.kob/` and AI agent rules) |

**Status**: PASS — Secrets and backups excluded from Git.

---

## 21. Known Pre-Existing Issues (Out of Scope)

1. **`parse_time()` bug in `app/db.py`**: `hour, minute = map(int, val.split(":"))` fails on `HH:MM:SS` format → all attendance `status=UNKNOWN`. Predates reconstruction. To be addressed in `ADMS-Collector-TemporalIdentity-001`.

2. **0 employee_device_mappings**: No Human ↔ Device mappings exist. Attendance is correctly stored with `employee_id = NULL`. Mapping workflow pending explicit authorization.

---

## 22. Checkpoint Summary

| Domain | Status |
|--------|--------|
| Git synchronization (TELEPHONE / origin / ai-brain) | PASS |
| Docker runtime (3 containers, 0 restarts) | PASS |
| Database (row counts, integrity) | PASS |
| Schema 005 (columns, constraints, index) | PASS |
| Collector runtime (LIVE, HEALTHY) | PASS |
| MQTT | PASS |
| ZKTeco terminal | PASS |
| Healthcheck | PASS |
| Tests (33/33) | PASS |
| Backup (authoritative, verified) | PASS |
| Git ignore (secrets excluded) | PASS |

**Overall checkpoint status**: PASS

---

## 23. Next Authorized Phase

`ADMS-Collector-TemporalIdentity-001` — Collector Temporal Identity Resolver & Lifecycle Integration (READ-ONLY / PLAN ONLY).

This phase will design `scan_time`-aware mapping resolution and roster sync integration, addressing the temporal identity requirements established in schema 005 and the `parse_time()` bug.

---

FINAL

PromptID: ADMS-Checkpoint-PostServerRebuild-001

repository verified: YES
database modified: NO
application modified: NO
device modified: NO
tests: PASS (33/33)
runtime verified: YES
commit created: NO (pending authorization)
push completed: NO (pending authorization)

next authorized PromptID: ADMS-Collector-TemporalIdentity-001
safe to proceed: YES
blockers: NONE

STOP.