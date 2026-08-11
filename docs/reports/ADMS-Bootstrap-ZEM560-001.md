# ADMS / ZEM560 BOOTSTRAP REPORT

## Prompt

* PromptID: `ADMS-Bootstrap-ZEM560-001`
* mode: READ-ONLY / DOCUMENTATION ONLY
* timestamp: 2026-08-11T09:59:35+07:00
* target repository: `https://github.com/kankrittapon/adms-server.git`
* modifications performed: NO (Documentation writes only)

## Repository

- repository: `adms-server`
- mode: READ-ONLY / DOCUMENTATION ONLY
- current implementation state: Basic Python `pyzk` live event listener daemon, PostgreSQL database schema with attendance logs, MQTT publisher, Docker Compose stack.
- collector exists: YES (`app/main.py` using `pyzk==0.9`, container `adms_zkteco_listener`)
- API exists: NO (Standalone socket listener daemon exists; REST API HTTP push ingestion layer not present)
- PostgreSQL exists: YES (`adms-postgres` container, database `adms`, tables `devices`, `employees`, `attendance_logs`, `sync_events`)
- Docker configuration exists: YES (`docker-compose.yml`, `docker/Dockerfile`)

## ZEM560

- platform: ZEM560 / ZEM560_TFT
- firmware: Ver 6.60 / Ver 8.0.x Standalone Series (Inferred)
- CPU: 32-bit RISC / ARM9
- OS: Embedded Linux (Linux 2.6.x)
- communication protocol: ZK Binary Protocol (TCP / UDP)
- port: 4370 (Verified in `app/main.py` & `.env.example`)
- native ADMS Push: Unproven / Not Demonstrated (For the currently verified firmware, native outbound ADMS Push has not been demonstrated. The ZK protocol on port 4370 is the currently verified integration path.)
- pyzk compatibility: VERIFIED (`pyzk==0.9` driver used in `app/main.py`)
- real-time capture capability: VERIFIED (`connection.live_capture()`)
- confidence: HIGH (Supported by repository source code, environment variables, and protocol specs)

## Collector Decision

- Python collector recommended: YES
- primary reason: Legacy ZEM560 standalone firmware relies on binary ZK protocol over port 4370. `pyzk==0.9` provides direct TCP socket communication, real-time event streaming (`live_capture()`), historical log retrieval (`get_attendance()`), and RTC clock sync.
- preferred capture mode: HYBRID (Real-time `live_capture()` stream + periodic historical `get_attendance()` backfill)
- backfill required: YES (To recover events scanned while collector container or socket connection was down)
- deduplication required: YES (Handled via PostgreSQL unique constraint `UNIQUE (user_id, device_ip, scan_time)`)
- unresolved technical risks: Socket drops in `live_capture()` loop requiring automatic bounded exponential backoff reconnection; RTC clock drift on biometric device requiring periodic synchronization.

## Architecture

- recommended topology: Separate Python Collector daemon (`adms_zkteco_listener`) communicating over TCP 4370 with device, writing deduplicated records to PostgreSQL (`adms_postgres`) and publishing event notifications to Mosquitto MQTT (`adms_mqtt`).
- component boundaries: ZK protocol communication is strictly isolated within the Collector container. PostgreSQL provides durable relational storage. MQTT provides decoupled event distribution for downstream consumers.
- security boundary: Device port 4370 operates unencrypted over internal LAN / Tailscale segment only and MUST NOT be published to the public Internet. MQTT broker is restricted to host loopback (`127.0.0.1:1883`).
- database path: `adms_postgres` (Container), Database: `adms`, Schema: `sql/001_schema.sql`
- downstream integration: Mosquitto MQTT broker topic `attendance/events` -> n8n automation workflows, Telegram bots, external webhooks.

## Documentation

- ZEM560 profile: Created ([ZEM560_DEVICE_PROFILE.md](file:///d:/Dev/adms-server/docs/ZEM560_DEVICE_PROFILE.md))
- architecture document: Created ([ADMS_ARCHITECTURE.md](file:///d:/Dev/adms-server/docs/ADMS_ARCHITECTURE.md))
- report: Created ([ADMS-Bootstrap-ZEM560-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Bootstrap-ZEM560-001.md))
- reports index: Updated ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))

## Next PromptIDs

1. `# PromptID: ADMS-Collector-Reliability-001` (Plan ONLY): Design bounded exponential backoff, historical log backfill, RTC clock sync, and healthchecks for `adms_zkteco_listener`.
2. `# PromptID: ADMS-Collector-MultiDevice-001` (Plan ONLY): Design dynamic multi-device discovery from `devices` table.

## FINAL

- repository baseline established: YES
- device profile established: YES
- collector architecture justified: YES
- application code modified: NO
- infrastructure modified: NO
- secrets exposed: NO
- commit: NO
- push: NO
- blockers: NONE

STOP.
