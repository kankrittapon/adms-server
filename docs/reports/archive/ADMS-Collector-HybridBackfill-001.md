# HYBRID BACKFILL PLAN

## Prompt

* PromptID: `ADMS-Collector-HybridBackfill-001`
* mode: READ-ONLY / PLAN ONLY + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T10:27:00+07:00
* target repository: `adms-server`
* modifications performed: NO (Documentation writes only)

## Current Integration

- BACKFILLING hook: Implemented in `app/collector.py` as a non-destructive state transition hook.
- historical API: `connection.get_attendance()` verified live (0.18s overhead for small log sets).
- full-buffer behavior: ZK 4370 binary protocol transfers full log buffer; device-side filtering is unsupported.
- DB abstraction: PostgreSQL `attendance_logs` table with `UNIQUE (user_id, device_ip, scan_time)` constraint.
- State Engine integration: Sequential execution flow (`CONNECTING` -> `BACKFILLING` -> `LIVE`).

## Algorithm

- startup: On startup/reconnect, enter `BACKFILLING` state immediately after TCP socket connection is established.
- first run: If database contains zero logs for device (`Watermark IS NULL`), process all logs returned by `get_attendance()` in 500-record batch chunks.
- normal reconnect: Query DB for `MAX(scan_time)` for device IP; compute boundary $\text{Watermark} - 5\text{ mins}$.
- filtering: Filter records client-side in Python (`event.timestamp >= boundary`).
- persistence: Batch insert candidate records via `ON CONFLICT (user_id, device_ip, scan_time) DO NOTHING`.
- transition to LIVE: Call `enable_device()` and transition cleanly to `LIVE` streaming state.

## Watermark

- source: `SELECT MAX(scan_time) FROM attendance_logs WHERE device_ip = %s`
- overlap: 5 minutes (`BACKFILL_OVERLAP_MINUTES = 5`) to tolerate terminal RTC drift (-25.39s observed).
- semantics: Client-side Python filtering boundary.
- persistent checkpoint required: NO (Database `MAX(scan_time)` serves as self-healing watermark).
- recommendation: Client-side timestamp filtering with 5-minute safety overlap + database idempotency constraint.

## Deduplication

- current constraint: `UNIQUE (user_id, device_ip, scan_time)`
- backfill/live overlap: Duplicate scans safely discarded via `ON CONFLICT DO NOTHING`.
- device identity: `device_ip` (Single-device baseline).
- classification: ACCEPTABLE FOR CURRENT IMPLEMENTATION
- schema change required: NO

## Performance

- maximum device history: 100,000 attendance logs in terminal flash buffer.
- retrieval behavior: Full binary buffer transfer over TCP 4370 socket (~0.18s for small log sets, ~1-2s for 100k buffer).
- memory considerations: In-memory Python filtering in batch chunks.
- DB batching: 500 records per transaction chunk.
- recommended batch size: 500
- MQTT replay policy: **SUPPRESSED** for backfilled events (No MQTT notifications sent for historical scans).

## Failure Handling

| Failure | State Transition | Data Behavior | Recovery |
| ------- | ---------------- | ------------- | -------- |
| `get_attendance()` Socket Error | Transition to `BACKOFF` | Logs remain in terminal flash | Retried on next reconnect |
| PostgreSQL Mid-Batch Error | Abort backfill, rollback active batch, transition to `BACKOFF` | Uncommitted logs remain in terminal flash | Retried on next reconnect |
| Collector SIGTERM | Rollback active batch, call `enable_device()`, transition to `STOPPED` | No corrupt partial transactions | Preserved safely |
| Malformed Record | Skip record, log warning | Valid records in batch committed | Continued |

## Periodic Reconciliation

- recommended: YES
- cadence: Every 15 minutes (`PERIODIC_RECONCILIATION_MINUTES = 15`)
- implementation approach: Sequential state transition within main FSM loop (`LIVE` -> `BACKFILLING` -> `LIVE`).
- concurrency policy: Single-threaded sequential execution to avoid concurrent ZK socket command collisions.

## Observability

- metrics/state: `last_backfill_started_at`, `last_backfill_completed_at`, `backfill_duration`, `records_recovered`, `records_skipped`. Audit logged to `sync_events`.

## Employee Mapping Boundary

- Excel profile: Profiling complete (`ADMS-Data-ExcelProfile-001`).
- employee import: Pending review (`ADMS-Data-ExcelImport-002`).
- ZKTeco mapping: Independent (`user_id` string stored directly in `attendance_logs`).
- attendance ingestion dependency on employee mapping: **NONE** (Employee stub automatically ensured so attendance ingestion is never blocked by employee roster mapping).

## Proposed Implementation

- files: `app/collector.py`, `app/db.py`, `tests/test_hybrid_backfill.py`
- functions: `get_device_watermark()`, `save_attendance_batch()`, `handle_backfilling()`
- SQL changes: NONE
- Docker changes: NONE
- device changes: NONE

## Test Plan

- unit: Watermark calculation, client-side timestamp filtering, batching, MQTT suppression during backfill.
- integration: Mock ZK attendance retrieval with local PostgreSQL container backfill.
- future live fault tests: Stop collector, scan terminal offline, restart collector, verify scan recovery.

## Documentation

- hybrid-backfill doc: Created ([COLLECTOR_HYBRID_BACKFILL.md](file:///d:/Dev/adms-server/docs/COLLECTOR_HYBRID_BACKFILL.md))
- report: Persisted ([ADMS-Collector-HybridBackfill-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Collector-HybridBackfill-001.md))
- reports index: Updated ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))
- STATUS.md: Updated ([STATUS.md](file:///d:/Dev/adms-server/STATUS.md))
- code modified: NO
- database modified: NO
- device modified: NO

## Proposed WRITE PromptID

- `ADMS-Collector-HybridBackfill-002`
- ready: YES
- blockers: NONE

## FINAL

- hybrid backfill design complete: YES
- first-run policy defined: YES (Ingest all 100k logs in 500-record batch chunks)
- watermark semantics defined: YES (Database `MAX(scan_time)` - 5 minutes overlap)
- deduplication suitable: YES (`UNIQUE (user_id, device_ip, scan_time)` verified suitable)
- MQTT replay policy defined: YES (MQTT broadcast suppressed for backfilled events)
- periodic reconciliation decision made: YES (Sequential 15-minute cadence)
- employee mapping blocks attendance ingestion: NO
- safe to prepare implementation: YES
- blockers: NONE

STOP.
