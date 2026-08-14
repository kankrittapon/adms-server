# ADMS — Collector Health Bridge — Completion Report

**PromptID:** `ADMS-Infra-CollectorHealthBridge-001`
**Status:** COMPLETE (owner selected from write-enablement gate → implemented → deployed → live-verified)
**Date:** 2026-08-14

## AGENT / TOOLING
- agent/model: Freebuff (Buffy) — deepseek-v4-flash · IDE: Freebuff chat (TELEPHONE) · pty-mcp: USED · temporary SSH transport scripts: 0

## PROBLEM
`GET /api/v1/health` always returned `collector: null` in production, even while the
polling Collector was LIVE/HEALTHY. Root cause: the API health router reads a health file
from `HEALTH_FILE_PATH` (default `/tmp/collector_health.json`) **inside the API container**,
but the Collector writes that file **inside the listener container** — no shared volume
existed, so the API could never see it. (Documented as a known pre-existing limitation in
the typed-client codegen report.)

## FIX
Both `app/collector.py` and `app/healthcheck.py` already honor `HEALTH_FILE_PATH`; only
the compose wiring was missing:

- **`docker-compose.yml`**
  - New named volume `adms_collector_health`
  - `listener`: mounts the volume at `/var/run/adms` (read-write), `HEALTH_FILE_PATH=/var/run/adms/collector_health.json`
  - `api`: mounts the volume at `/var/run/adms` **read-only** (`:ro`), same `HEALTH_FILE_PATH`
  - Both values overridable via `${HEALTH_FILE_PATH:-...}`
- **No application code changed** — the router, collector, and healthcheck were already
  env-driven. The API container sees the Collector's live health file through the shared
  volume.

## TESTS
- **395 passed + 18 subtests / 0 failed** (baseline 394; +1 regression test
  `TestHealth::test_health_surfaces_collector_from_env_file` — writes a real health file
  to a temp dir, points `_HEALTH_FILE_DEFAULT` at it, and asserts
  `/api/v1/health` returns `collector.state=LIVE`, `device_connected`, `db_status`)

## DEPLOYMENT (ai-brain)
- Commit `c7a7607` pushed; ai-brain synced `git pull --ff-only` → `c7a7607`
- `docker compose up -d listener api` (compose config change — no image rebuild needed)
- Containers healthy, **restarts 0**; PostgreSQL/MQTT/web untouched (41h+ up)

## LIVE VERIFICATION
- Listener writes to the shared volume: `/var/run/adms/collector_health.json` exists,
  `state=LIVE`, `device_connected=true`, `db_status=HEALTHY`
- Authenticated `GET /api/v1/health` (temp VIEWER token, revoked after — 0 active):
  ```
  status: healthy
  database: HEALTHY
  mqtt: HEALTHY
  collector.state: LIVE
  collector.device_connected: True
  collector.db_status: HEALTHY
  ```
  (Previously `collector: null`.)
- Write gate intact: OPERATOR token → `POST /api/v1/enrollments/reserve` →
  **403 WRITE_DISABLED**; token revoked → 0 active
- Note: `collector.mqtt_status` reads `UNKNOWN` — that is the value the Collector itself
  writes in its health file (pre-existing collector-side MQTT status detail, unchanged by
  this bridge; the API now faithfully relays it)

## FINAL
- repository verified: **YES** · database modified: NO · schema modified: NO · application
  modified: NO (compose + test only) · device modified: NO
- **Collector health bridge: 100% COMPLETE** · tests: **395/395** (+18 subtests) ·
  runtime: HEALTHY · safe to proceed: **YES** · blockers: NONE
