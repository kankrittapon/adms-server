# AI-Brain & ADMS Audit & Infrastructure Reports

This index records all historical and active audit, infrastructure, architecture, and planning reports for the AI-Brain and ADMS Server systems.

## Report Index

| PromptID | Date | Type | Mode | Status | Supersedes / Context |
| -------- | ---- | ---- | ---- | ------ | -------------------- |
| `AIBRAIN-Audit-LiveBaseline-001` | 2026-08-11 | Audit | READ-ONLY | COMPLETE | Establishes verified live runtime baseline for AI-Brain host, Docker containers, databases, and network bindings. |
| `AIBRAIN-Infra-HardenNetwork-001` | 2026-08-11 | Hardening Plan | READ-ONLY / PLAN ONLY | COMPLETE | Dependency analysis and network hardening plan for restricting `n8n_zort_postgres` (5432) and `adminer` (8080) host bindings. |
| `AIBRAIN-Infra-HardenNetwork-002` | 2026-08-11 | Execution Report | WRITE — LIMITED AUTHORIZATION | COMPLETE | Execution report for removing host port publishing of `n8n_zort_postgres` (5432) and restricting `adminer` (8080) to loopback `127.0.0.1`. |
| `AIBRAIN-Architecture-MapCurrentState-001` | 2026-08-11 | Architecture Map | READ-ONLY INFRA + DOC WRITE ONLY | COMPLETE | Canonical architecture mapping of AI-Brain components, data flows, network layers, storage persistence, trust boundaries, and Adminer SSH access documentation. |
| `AIBRAIN-Infra-AddHealthchecks-001` | 2026-08-11 | Healthcheck Plan | READ-ONLY / PLAN ONLY | COMPLETE | Analysis and healthcheck improvement plan for `private_postgres`, `adminer`, and `n8n_zort_cloudflared`. |
| `AIBRAIN-Infra-AddHealthchecks-002` | 2026-08-11 | Execution Report | WRITE — LIMITED AUTHORIZATION | COMPLETE | Execution report for adding explicit Docker healthchecks to `private_postgres` (`pg_isready`) and `adminer` (`wget spider`). |
| `ADMS-Bootstrap-ZEM560-001` | 2026-08-11 | Device Bootstrap | READ-ONLY / DOC ONLY | COMPLETE | Project baseline and technical profile reconstruction for ZKTeco ZEM560 series biometric device and ADMS Server collector. |
| `ADMS-Device-LiveFingerprint-001` | 2026-08-11 | Device Fingerprint | READ-ONLY DEVICE / DOC ONLY | COMPLETE | Verified live hardware profile for SONIC / ZEM560_TFT terminal (MIPS CPU, Linux 2.6.24 Treckle, Firmware Ver 6.60 Aug 26 2011, Telnet TCP/23, ZK Protocol TCP/4370). |
| `ADMS-Collector-Reliability-001` | 2026-08-11 | Reliability Plan | READ-ONLY PLAN / DOC ONLY | COMPLETE | Production-grade reliability model, hybrid event capture & backfill architecture, state machine, and deduplication plan for ZEM560 Python collector. |
| `ADMS-Device-AttendanceBehavior-001` | 2026-08-11 | Attendance Behavior | READ-ONLY DEVICE / DOC ONLY | COMPLETE | Verified live device test of `get_attendance()` (0.18s for 6 records), clock drift (-25.39s), `pyzk` `live_capture` 10s timeout yield behavior, and client-side watermark filtering. |
| `ADMS-Device-CapabilityProfile-001` | 2026-08-11 | Capability Spec | READ-ONLY DEVICE / DOC ONLY | COMPLETE | Verified capacity spec for SONIC ZEM560_TFT (30k users, 3k templates, 100k logs), pyzk API capability matrix, 5-tier project usability framework, and UID/deduplication analysis. |
| `ADMS-Collector-StateEngine-001` | 2026-08-11 | State Engine Plan | READ-ONLY PLAN / DOC ONLY | COMPLETE | Modular state engine architecture design for `app/main.py` (`STARTING`, `CONNECTING`, `BACKFILLING`, `LIVE`, `DEGRADED`, `BACKOFF`, `STOPPING`), bounded exponential backoff ($2\text{s}\to 60\text{s}$ with $\pm 20\%$ jitter), interruptible sleep, and failure domain isolation. |
| `ADMS-Data-ExcelProfile-001` | 2026-08-11 | Data Profiling | READ-ONLY DATA / DOC ONLY | COMPLETE | Analysis and normalization profile for employee master workbook `รายละเอียด กพ.พัน.สอล.ฯ ก.พ.69.xlsx` (120 unique records across 4 rank categories), PostgreSQL schema mapping, and idempotent upsert plan. |
| `ADMS-Collector-StateEngine-002` | 2026-08-11 | Execution Report | WRITE — LIMITED APPLICATION AUTHORIZATION | COMPLETE | Modular State Engine implementation (`app/main.py`, `app/config.py`, `app/collector.py`, `app/db.py`, `app/mqtt_client.py`), unit tests (5/5 passed), live verification against SONIC ZEM560_TFT terminal (`LIVE` state reached, graceful shutdown verified). |
| `ADMS-Collector-HybridBackfill-001` | 2026-08-11 | Hybrid Backfill Plan | READ-ONLY PLAN / DOC ONLY | COMPLETE | Detailed design for historical `get_attendance()` log backfill, client-side watermark filtering ($\text{MAX(scan\_time)} - 5\text{ mins}$), 500-record batch chunk persistence, MQTT suppression for historical scans, and 15-minute periodic reconciliation cadence. |
| `ADMS-Collector-HybridBackfill-002` | 2026-08-11 | Execution Report | WRITE — LIMITED APPLICATION AUTHORIZATION | COMPLETE | Implemented historical attendance log backfill (`app/collector.py`, `app/db.py`, `app/config.py`), unit test suite & 100k synthetic benchmark (9/9 passed, 0.0040s filtering), live verification against SONIC ZEM560_TFT terminal (6 records backfilled in 0.2008s, MQTT suppressed, 100% idempotent). |
| `ADMS-Checkpoint-CollectorFoundation-001` | 2026-08-11 | Foundation Checkpoint | DOC ONLY | COMPLETE | Established verified collector foundation baseline after State Engine and Hybrid Backfill implementation. |
| `ADMS-Device-RemoteEnrollmentCapability-001` | 2026-08-11 | Capability Test | CONTROLLED DEVICE TEST | COMPLETE | Controlled live test of `enroll_user()`: Command times out without activating on-screen UI on standalone firmware `Ver 6.60`. Classified as **DO NOT USE / NOT RECOMMENDED FOR PRODUCTION**. |
| `ADMS-Device-FirmwareFilesystemAudit-001` | 2026-08-11 | Filesystem Audit | READ-ONLY DEVICE / DOC ONLY | COMPLETE | Read-only Telnet inspection of MTD partitions, `/mnt/mtdblock/options.cfg`, `AttState=0` (default Check-In punch state key, unrelated to remote enrollment), driver nodes (`/dev/tft_lcd`), and generic config vs physical hardware matrix. |
| `ADMS-Device-NativePushVerification-001` | 2026-08-11 | Protocol Verification | READ-ONLY PROTOCOL / DOC ONLY | COMPLETE | Protocol & socket inspection of native Push config (`AuthServerIP=192.168.1.248:8000`, `libhttppush.so`), embedded HTTP web server (TCP Port 80, `ZK Web Server`), and evaluation. Reconfirmed Python Collector over TCP 4370 as the primary production architecture. |
| `ADMS-Collector-Healthcheck-001` | 2026-08-11 | Healthcheck Plan | READ-ONLY PLAN / DOC ONLY | COMPLETE | Detailed design for atomic ephemeral health status file (`/tmp/collector_health.json`), state-aware liveness thresholds (LIVE/BACKOFF 120s, BACKFILLING 600s), non-invasive `app/healthcheck.py` CLI module, and Docker Compose parameters. |
| `ADMS-Collector-Healthcheck-002` | 2026-08-11 | Healthcheck Execution | WRITE — LIMITED APPLICATION AUTHORIZATION | COMPLETE | Implemented atomic health status updates (`app/collector.py`), non-invasive CLI health evaluation module (`app/healthcheck.py`), Docker Compose healthcheck block (`docker-compose.yml`), test suite (22/22 passed), live verification against physical terminal (Exit Code 0 verified during LIVE state). |
| `ADMS-Data-IdentityMapping-001` | 2026-08-11 | Identity Mapping Plan | READ-ONLY PLAN / DOC ONLY | COMPLETE | Detailed design for strict separation of Human Master Data (`employees`) and Device-Local Identity (`device_users`), multi-device mapping schema (`devices`, `device_users`, `employee_device_mappings`), rejection of Excel row-number mapping assumption, and unmapped attendance ingestion policy. |
| `ADMS-Data-IdentitySchema-001` | 2026-08-11 | Identity Schema Plan | READ-ONLY PLAN / DOC ONLY | COMPLETE | Detailed DDL migration design (`sql/002_identity_foundation.sql`), additive zero-data-loss architecture (`devices`, `device_users`, `human_employees`, `employee_device_mappings`), seed queries for physical terminal (`3392113170057`), and 5-stage migration path. |
| `ADMS-Checkpoint-PreIdentitySchema-001` | 2026-08-11 | Pre-Schema Checkpoint | DOC ONLY | COMPLETE (Latest ADMS Checkpoint) | Established clean, verified repository checkpoint baseline prior to executing the first additive database schema migration (`sql/002_identity_foundation.sql`). |

*Latest relevant checkpoint for network-hardening work: `AIBRAIN-Infra-HardenNetwork-002`*  
*Latest relevant checkpoint for architecture mapping: `AIBRAIN-Architecture-MapCurrentState-001`*  
*Latest relevant checkpoint for healthcheck implementation: `AIBRAIN-Infra-AddHealthchecks-002`*  
*Latest relevant checkpoint for ADMS ZEM560 live fingerprint: `ADMS-Device-LiveFingerprint-001`*  
*Latest relevant checkpoint for ADMS device attendance behavior: `ADMS-Device-AttendanceBehavior-001`*  
*Latest relevant checkpoint for ADMS capability specification: `ADMS-Device-CapabilityProfile-001`*  
*Latest relevant checkpoint for ADMS collector state engine design: `ADMS-Collector-StateEngine-001`*  
*Latest relevant checkpoint for ADMS employee master data profile: `ADMS-Data-ExcelProfile-001`*  
*Latest relevant checkpoint for ADMS collector state engine implementation: `ADMS-Collector-StateEngine-002`*  
*Latest relevant checkpoint for ADMS hybrid backfill implementation: `ADMS-Collector-HybridBackfill-002`*  
*Latest relevant checkpoint for ADMS collector foundation baseline: `ADMS-Checkpoint-CollectorFoundation-001`*  
*Latest relevant checkpoint for ADMS remote enrollment test: `ADMS-Device-RemoteEnrollmentCapability-001`*  
*Latest relevant checkpoint for ADMS firmware filesystem audit: `ADMS-Device-FirmwareFilesystemAudit-001`*  
*Latest relevant checkpoint for ADMS native Push verification: `ADMS-Device-NativePushVerification-001`*  
*Latest relevant checkpoint for ADMS collector healthcheck execution: `ADMS-Collector-Healthcheck-002`*  
*Latest relevant checkpoint for ADMS employee identity mapping plan: `ADMS-Data-IdentityMapping-001`*  
*Latest relevant checkpoint for ADMS identity schema migration plan: `ADMS-Data-IdentitySchema-001`*  
*Latest relevant checkpoint for ADMS pre-identity-schema baseline: `ADMS-Checkpoint-PreIdentitySchema-001`*
