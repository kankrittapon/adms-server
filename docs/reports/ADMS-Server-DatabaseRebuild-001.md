# ADMS Server Database Rebuild — Collector Docker Package Fix + Full Reconstruction

**PromptID:** `ADMS-Server-DatabaseRebuild-001`

**Continuation:** `Collector Docker Package Fix`

**Date:** 2026-08-11

**Status:** COMPLETE

---

## Summary

Controlled reconstruction of the ADMS database on ai-brain (192.168.1.248) from canonical sources:
Git SQL migrations (001-005), Excel Human Master workbook (120 personnel), and live ZKTeco terminal
read-only data (device identity + attendance backfill).

Three Docker build defects were discovered and fixed during Collector startup:
1. **Dockerfile package layout** — only `app/main.py` was copied, but `main.py` uses `from app.config` / `from app.collector` package imports
2. **Missing `iputils-ping`** — `python:3.12-slim` lacks `ping`, which pyzk requires for its connectivity check
3. **Missing DB env vars** — `docker-compose.yml` set `DATABASE_URL` but `config.py` reads `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`

All three were fixed with minimal changes, committed, pushed, and synced to ai-brain.

---

## Fixes Applied

### Fix 1: Dockerfile Package Layout (Option A)

**Commit:** `0ee48049d1a0b47700e21854a31178bcd655dc7a`

**Files:** `docker/Dockerfile`, `app/requirements.txt`

**Dockerfile change:**
```dockerfile
# Before
COPY app/main.py ./main.py
CMD ["python", "main.py"]

# After
COPY app/ ./app/
CMD ["python", "-m", "app.main"]
```

**requirements.txt change:** Added `python-dotenv==1.0.1` (required by `app/config.py` `from dotenv import load_dotenv`).

### Fix 2: iputils-ping

**Commit:** `0918ea8cd73a676167e148ca4099c9cc5c149d3c`

**File:** `docker/Dockerfile`

Added `apt-get install iputils-ping` to the image. pyzk's `test_ping()` uses `subprocess.call("ping -c 1 -W 5 <ip>", shell=True)`, which fails if `ping` is not installed.

### Fix 3: DB Environment Variables

**Commit:** `cf4b0f5aba5ea0dfae62693dcc7c1bdf0614aada`

**File:** `docker-compose.yml`

Added `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` environment variables to the `listener` service. `app/config.py` reads these individual vars (not `DATABASE_URL`), defaulting to `localhost` which fails inside the container.

---

## Reconstruction Results

### Database State (LIVE VERIFIED)

| Table | Count | Source |
|-------|-------|--------|
| `devices` | 1 | Migration 002 seed (serial 3392113170057) |
| `device_users` | 2 | Collector from live terminal (user_id '1', '2') |
| `human_employees` | 120 | Excel Human Master import |
| `human_employee_sources` | 120 | Excel Human Master import |
| `employee_device_mappings` | 0 | NOT created (no automatic mapping) |
| `attendance_logs` | 7 | Collector Hybrid Backfill from live terminal |
| `employees` (legacy) | 0 | NOT reconstructed (legacy stubs disabled) |
| `sync_events` | 1 | HISTORICAL_BACKFILL event |

### Attendance Records (LIVE terminal data)

7 records retrieved from terminal flash memory via `get_attendance()`:

| user_id | scan_time | punch_type | status | employee_id |
|---------|-----------|------------|--------|-------------|
| 1 | 2021-03-03 03:14:58 | 4 | UNKNOWN | NULL |
| 1 | 2021-03-03 03:15:01 | 4 | UNKNOWN | NULL |
| 1 | 2021-03-03 03:16:40 | 0 | UNKNOWN | NULL |
| 1 | 2021-03-03 07:46:03 | 0 | UNKNOWN | NULL |
| 1 | 2026-08-10 19:47:39 | 0 | UNKNOWN | NULL |
| 2 | 2026-08-10 20:07:27 | 0 | UNKNOWN | NULL |
| 1 | 2026-08-11 15:30:54 | 0 | UNKNOWN | NULL |

All `employee_id = NULL` (unmapped — no automatic Human ↔ Device mapping).

**Note:** `status=UNKNOWN` for all records due to a pre-existing `parse_time` bug in `db.py` ("too many values to unpack (expected 2)") when parsing `ON_TIME_START`/`ON_TIME_END`. This is a non-blocking warning — attendance is still persisted. This bug predates this reconstruction and is outside the scope of the authorized Docker package fix.

### Identity Safety

- `employee_device_mappings = 0` — no VERIFIED/PROBABLE/LEGACY mappings created
- `employees = 0` — no legacy stubs recreated
- No Human ↔ Device automatic mapping
- No terminal writes (Collector read-only)
- No fingerprints modified

---

## Runtime Verification (LIVE VERIFIED)

| Component | Status |
|-----------|--------|
| PostgreSQL | OPERATIONAL (healthy) |
| MQTT | OPERATIONAL (127.0.0.1:1883, 0 restarts) |
| Collector | OPERATIONAL (LIVE state, 0 restarts) |
| State Engine | OPERATIONAL (STARTING → CONNECTING → BACKFILLING → LIVE) |
| Hybrid Backfill | OPERATIONAL (7 retrieved, 7 inserted, 0 duplicates) |
| Healthcheck | HEALTHY (exit 0) |
| ZKTeco Connection | CONNECTED (192.168.1.201:4370) |

---

## Test Results

```
33 passed, 0 failed, 0 skipped (14.79s)
```

Matches historical baseline exactly.

---

## Authoritative Backup

| Field | Value |
|-------|-------|
| Filename | `adms_reconstructed_authoritative_20260811_153725.dump` |
| Absolute path | `/home/kanfullbuster/adms-server/backups/adms_reconstructed_authoritative_20260811_153725.dump` |
| Size | 44980 bytes |
| SHA256 | `5386681d0ddcb38c840229f121f8fd207302fd3fbb2b394e675bad784bcfd0bd` |
| pg_dump version | 16.14 |
| pg_restore version | 16.14 |
| pg_restore -l | VERIFIED (exit 0, 79 TOC entries) |
| Format | PostgreSQL Custom Format (PGDMP_V1, gzip compression) |

---

## Git History

| Step | Commit | Description |
|------|--------|-------------|
| Pre-fix HEAD | `2501035f97e93ec670abbf705de0e4ba894731a8` | Baseline |
| Fix 1 | `0ee48049d1a0b47700e21854a31178bcd655dc7a` | Dockerfile package layout + python-dotenv |
| Fix 2 | `0918ea8cd73a676167e148ca4099c9cc5c149d3c` | iputils-ping |
| Fix 3 | `cf4b0f5aba5ea0dfae62693dcc7c1bdf0614aada` | DB env vars in docker-compose.yml |
| Final HEAD | `cf4b0f5aba5ea0dfae62693dcc7c1bdf0614aada` | = origin/main = ai-brain HEAD |

---

## Known Issues (Pre-existing, out of scope)

1. **`parse_time` bug in `db.py`**: `determine_status()` calls `parse_time(val)` which does `hour, minute = map(int, val.split(":"))`. If `ON_TIME_START`/`ON_TIME_END` contain seconds (e.g. `05:00:00`), `split(":")` returns 3 values but only 2 are unpacked, causing "too many values to unpack (expected 2)". Result: all attendance records get `status=UNKNOWN`. This predates this reconstruction.

2. **Historical backup invalidated**: `adms_post_excel_import_20260811_121449.dump` from the previous session was JSON metadata, not `pg_dump -Fc`. The new authoritative backup supersedes it.

3. **Human UUID continuity**: UUIDs are freshly generated in this reconstruction. They are NOT guaranteed to match any previous database state.

---

## Unrelated Workloads

All 17 unrelated ai-brain containers verified unchanged throughout the operation.