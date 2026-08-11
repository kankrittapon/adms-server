# COLLECTOR STATE ENGINE PLAN

## Prompt

* PromptID: `ADMS-Collector-StateEngine-001`
* mode: READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T10:16:00+07:00
* target repository: `adms-server`
* modifications performed: NO (Documentation writes only)

## Current Flow

- entrypoint: `run()` function in `app/main.py`.
- connection lifecycle: Monolithic `while True` loop instantiating `ZK.connect()` on every cycle.
- live loop: `for attendance in connection.live_capture():` blocking loop. Calls `connection.disable_device()` continuously.
- DB behavior: `save_log()` called synchronously inside live capture loop; exception aborts loop and triggers 10s sleep.
- MQTT behavior: Synchronous publish after DB insert; warning logged on error.
- reconnect: Rigid `time.sleep(10)` loop without exponential backoff or jitter.
- shutdown: Primitive `finally:` block attempting `connection.enable_device()` and `disconnect()`; `time.sleep(10)` blocks Docker shutdown.

## Proposed States

| State | Responsibility | Exit Conditions |
|---|---|---|
| `STARTING` | Load `.env` config, register signal handlers, init DB/MQTT pools | Config & Signals ready -> `CONNECTING` |
| `CONNECTING` | Create fresh `ZK` object, connect to TCP 4370 using Comm Key | Connected -> `BACKFILLING`, Socket Err -> `BACKOFF` |
| `BACKFILLING` | Read historical logs, check RTC drift, insert missing logs | Complete -> `LIVE`, Exception -> `BACKOFF` |
| `LIVE` | Loop `live_capture()`. Terminal remains enabled. 10s yields update heartbeat | Socket Err -> `BACKOFF`, SIGTERM -> `STOPPING` |
| `DEGRADED` | Operating in `LIVE` mode while MQTT is down. DB & ZK stream active | MQTT recovered -> `LIVE`, Socket Err -> `BACKOFF` |
| `BACKOFF` | Bounded exponential backoff wait ($2\text{s} \to 60\text{s}$ with $\pm 20\%$ jitter) | Timer elapsed -> `CONNECTING`, SIGTERM -> `STOPPING` |
| `STOPPING` | Release ZK socket (`enable_device()`, `disconnect()`), stop MQTT/DB | Cleanup complete -> `STOPPED` |
| `STOPPED` | Process cleanly terminated (Exit code 0) | N/A |

## Transition Table

| Current | Event | Next | Action |
|---|---|---|---|
| `STARTING` | Config ready | `CONNECTING` | Reset backoff counter $n=0$ |
| `CONNECTING` | TCP Connect Success | `BACKFILLING` | Instantiate ZK connection object |
| `CONNECTING` | Socket Error / Auth Fail | `BACKOFF` | Increment $n$, calculate exponential delay |
| `BACKFILLING` | Backfill Complete | `LIVE` | Ensure `enable_device()`, enter `live_capture()` loop |
| `BACKFILLING` | Device / DB Exception | `BACKOFF` | Disconnect ZK, increment $n$ |
| `LIVE` | Attendance event | `LIVE` | Persist to DB, publish to MQTT, update telemetry |
| `LIVE` | 10s Socket Timeout (`None`) | `LIVE` | Update heartbeat timestamp, check `stop_event` |
| `LIVE` | Socket Reset / Disconnect | `BACKOFF` | Disconnect ZK, increment $n$ |
| `LIVE` | MQTT Failure | `DEGRADED` | Log warning, continue DB & ZK stream |
| `DEGRADED` | MQTT Reconnected | `LIVE` | Log recovery, resume normal state |
| `DEGRADED` | Socket Reset / Disconnect | `BACKOFF` | Disconnect ZK, increment $n$ |
| `BACKOFF` | Timer elapsed | `CONNECTING` | Attempt reconnection |
| `ANY` | SIGTERM / SIGINT | `STOPPING` | Set `stop_event`, interrupt sleep |
| `STOPPING` | Cleanup complete | `STOPPED` | Exit 0 |

## Failure Isolation

- device: Catches `socket.timeout`, `socket.error`, `ZKNetworkError`; releases socket and transitions to `BACKOFF`.
- database: Exception in DB insert logs error and transitions to `BACKOFF`. Scans remain safely buffered in terminal flash memory.
- MQTT: Non-blocking warning logged; state transitions to `DEGRADED`. DB persistence and ZK stream continue.
- malformed event: Logged as warning and skipped; `live_capture()` continues.
- unexpected exception: Caught by FSM top-level error handler; releases ZK socket and transitions to `BACKOFF`.

## Backoff

- initial: 2.0 seconds
- multiplier: 2.0
- max: 60.0 seconds
- jitter: $\pm 20\%$ randomized delay
- reset rule: Counter $n$ resets to 0 after remaining in `LIVE` state for $> 30$ seconds.
- shutdown interruption: Uses `threading.Event().wait(timeout=t)` instead of `time.sleep()`. SIGTERM wakes thread instantly.

## Connection Lifecycle

- ZK object: Fresh `ZK` instance created per reconnection attempt; old instance discarded.
- connect: Explicit socket handshake on TCP port 4370 using Comm Key (`600`).
- disconnect: Safely releases TCP socket via `connection.disconnect()` in `finally:` blocks.
- stale connection handling: Stale sockets closed immediately before creating new connection instance.
- device enable behavior: `connection.enable_device()` called during `live_capture()` so terminal display and keypad function normally.

## Live Capture

- timeout/None: 10s socket timeout yields `None`, updating heartbeat timestamp and checking shutdown flag without exiting loop.
- attendance event: Yields `Attendance` object; persisted to PostgreSQL and published to MQTT.
- socket error: Catches socket exception, releases ZK socket, transitions to `BACKOFF`.
- graceful stop: `stop_event.set()` causes loop exit on next 10s yield or iteration.
- future backfill transition: `BACKFILLING` state runs sequentially after `CONNECTING` before entering `LIVE`.

## Code Structure

- files retained: `app/main.py` (CLI entrypoint & signal registration)
- files added: `app/config.py`, `app/collector.py`, `app/db.py`, `app/mqtt_client.py`
- files split: Split monolithic `app/main.py` into focused modules.
- rationale: Improves unit testability, separates DB/MQTT/ZK concerns, and enables clean state engine transitions.

## Implementation Plan

1. Create `app/config.py` for `.env` config validation.
2. Create `app/db.py` for DB connection pooling and `save_attendance_log()`.
3. Create `app/mqtt_client.py` for Mosquitto MQTT wrapper.
4. Create `app/collector.py` for `CollectorStateEngine` FSM implementation.
5. Update `app/main.py` as entrypoint script.

## Test Plan

- unit: State transition unit tests, exponential backoff formula and jitter tests, mock DB/MQTT failure isolation tests.
- integration: Local PostgreSQL & Mosquitto container integration tests with state engine.
- live fault tests: Controlled network disconnect, container restart, DB restart tests under future authorization.

## Documentation

- state-engine doc: Created ([COLLECTOR_STATE_ENGINE.md](file:///d:/Dev/adms-server/docs/COLLECTOR_STATE_ENGINE.md))
- report: Persisted ([ADMS-Collector-StateEngine-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Collector-StateEngine-001.md))
- reports index: Updated ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))
- code modified: NO
- schema modified: NO
- Docker modified: NO
- device modified: NO

## Proposed WRITE PromptID

- `ADMS-Collector-StateEngine-002`
- ready: YES
- blockers: NONE

## FINAL

- state-engine design complete: YES
- failure boundaries defined: YES
- graceful shutdown design complete: YES
- backoff design complete: YES
- future backfill integration supported: YES
- safe to prepare implementation: YES
- blockers: NONE

STOP.
