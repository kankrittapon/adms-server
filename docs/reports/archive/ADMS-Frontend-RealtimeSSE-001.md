# ADMS — REALTIME ATTENDANCE SSE BRIDGE — FINAL REPORT

**PromptID:** `ADMS-Frontend-RealtimeSSE-001`
**Mode:** PLAN (owner-approved) → IMPLEMENT → TEST → DEPLOY → LIVE VERIFY → BROWSER VERIFY → DOCUMENT
**Date:** 2026-08-14

---

## 1. AGENT / TOOLING
- **agent/model:** Freebuff (Buffy) — deepseek-v4-flash
- **IDE:** Freebuff chat (TELEPHONE control workstation)
- **pty-mcp:** USED (stateful SSH to ai-brain)
- **temporary SSH transport scripts:** 0 (file-based python drivers)

## 2. GIT
- starting HEAD: `8e66735` · implementation commit: `1ed9f6a`
- TELEPHONE == origin == ai-brain = **`1ed9f6a`** · synchronized: YES · working trees clean

## 3. WHAT WAS BUILT

### Backend
- **`app/api/mqtt_stream.py`** — `MqttStream`: process-local singleton (single uvicorn worker) bridging the Collector's MQTT `attendance/events` topic to connected SSE clients.
  - Lazy `ensure_started()` on first SSE request (never touches the broker on app import — tests stay hermetic)
  - Thread-safe fan-out: paho callbacks (network thread) → `loop.call_soon_threadsafe(queue.put_nowait)`; bounded per-client queue (max 100) so a slow consumer never blocks the loop
  - `register()` / `unregister()` client registry with idempotent `stop()` + `reset_stream()` test hook
  - Malformed/non-JSON MQTT payloads ignored safely
- **`app/api/routers/stream.py`** — `GET /api/v1/stream/attendance` (**VIEWER+**, authenticated via the standard VIEWER dependency)
  - SSE `text/event-stream` with `Cache-Control: no-cache` + `X-Accel-Buffering: no`
  - Heartbeat `: ping` every 15s; clean disconnect via `request.is_disconnected()` + `finally` unregister
  - Extracted `attendance_event_generator()` for deterministic unit testing
  - Live-only channel: no replay/backfill (that stays with the attendance GET endpoints)
- **`app/requirements-api.txt`** — added `paho-mqtt==2.1.0` (exact version match with the listener); `api` compose service already had `MQTT_HOST=mqtt`/`MQTT_PORT` (mosquitto binds 0.0.0.0 internally → reachable)

### Frontend
- **`frontend/src/hooks/useAttendanceStream.ts`** — SSE consumer using `fetch` + `ReadableStream` so the Bearer token stays in the **Authorization header** (EventSource can't set headers; no token-in-URL leak). Auto-reconnect with 3s delay; exposes `status` + `lastEvent`.
- **`frontend/src/pages/Attendance.tsx`** — LIVE/CONNECTING/OFFLINE badge in the header + transient "New scan detected" banner with auto-refresh on `ATTENDANCE_SCAN` events (banner auto-dismisses after 6s).

## 4. TESTS — **383 passed + 18 subtests / 0 failed** (baseline 375)
- 8 new stream tests (`tests/test_api_stream.py`): auth gate 401, SSE response contract (media type, headers, heartbeat→event→disconnect via asyncio), fan-out registry semantics, malformed-payload safety, bounded-queue slow-consumer safety
- **Bonus fix — two pre-existing patch leaks in `tests/test_api_auth.py`**: `_client_with()` and `_admin_client()` called `patch.start()` AND tests used `with p:` — the double-activation meant the single context-manager `stop()` left `_load_token_context` patched **forever**, silently authenticating every later test in the process with a leaked role. (Masked until now because no earlier test asserted 401 *after* these classes ran; the SSE endpoint exposed it as an infinite stream.) Both helpers now defer to `with p:` for start/stop.

## 5. DEPLOYMENT (ai-brain)
- `adms_api` rebuilt only (`docker compose up -d --build --no-deps api` — paho-mqtt installs inside the container) → healthy, restarts 0
- `adms_web` rebuilt (frontend bundle changed) → healthy, restarts 0
- PostgreSQL/MQTT/Collector untouched (10–26h up, restarts 0)

## 6. LIVE VERIFICATION (temp admin token, revoked after — 0 active tokens remain)
- **E2E PASS**: token issued (canonical INSERT) → SSE stream opened → **one synthetic non-biometric `ATTENDANCE_SCAN` published on MQTT → streamed back over SSE as `event: attendance` with the exact payload** → token revoked → 0 active → no-token request → **401**
- No DB writes (SSE is read-only fan-out), no device access, no real scan

## 7. BROWSER VERIFICATION (headless Chrome, fresh profile)
- Attendance page renders with **LIVE badge visible** (SSE connected) · console clean · token revoked after

## 8. SAFETY / BOUNDARY
- Live-only channel — no replay, no DB writes, GET side-effect free
- No schema change · no identity change · Collector untouched (it already publishes to MQTT; it does not consume the stream)
- Backend Foundation **REMAINS 100% COMPLETE** · write gate intact (`API_WRITE_ENABLED=false`)

## 9. USAGE
```text
SSE endpoint: GET http://192.168.1.248:8081/api/v1/stream/attendance  (Bearer, VIEWER+)
Console:      http://192.168.1.248:8082/attendance  — LIVE badge + new-scan banner
```

## 10. FINAL
- repository verified: **YES** · database modified: NO · schema modified: NO · device modified: NO
- **Realtime SSE bridge: 100% COMPLETE** · tests: **383/383** (+18 subtests) · runtime: HEALTHY · safe to proceed: **YES** · blockers: NONE
