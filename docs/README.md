# ADMS System Documentation Index

Welcome to the ADMS Server & AI-Brain documentation library.

## Navigation Map

### 1. Architecture (`docs/architecture/`)
* [ADMS Architecture](architecture/ADMS_ARCHITECTURE.md): System overview, state machine data flows, network topology, and failure domain boundaries.
* [Source AI-Brain Audit Snapshot](architecture/SOURCE_AI_BRAIN_DOCKER_AUDIT_2026-08-10.md): Historical live runtime baseline audit snapshot from 2026-08-10.

### 2. Device (`docs/device/`)
* [ZEM560 Device Profile](device/ZEM560_DEVICE_PROFILE.md): Hardware, MIPS CPU, Linux 2.6.24 kernel, and firmware specifications for SONIC ZEM560_TFT terminal (`192.168.1.201`).
* [ZEM560 Capability Specification](device/ZEM560_CAPABILITY_SPEC.md): Protocol capability matrix, user/log capacity limits, and 5-tier usability framework.

### 3. Collector (`docs/collector/`)
* [Collector Reliability Model](collector/COLLECTOR_RELIABILITY.md): Production-grade reliability model, event capture, deduplication, and failure domain isolation.
* [Collector State Engine](collector/COLLECTOR_STATE_ENGINE.md): Finite State Machine design (`STARTING` -> `CONNECTING` -> `BACKFILLING` -> `LIVE` -> `DEGRADED` / `BACKOFF` / `STOPPING`).
* [Collector Hybrid Backfill](collector/COLLECTOR_HYBRID_BACKFILL.md): Historical attendance reconciliation, watermark filtering, 500-record batch chunk persistence, and MQTT suppression.
* [Collector Healthcheck System](collector/COLLECTOR_HEALTHCHECK.md): Atomic ephemeral status file (`/tmp/collector_health.json`), state-aware liveness thresholds, and non-invasive CLI evaluator (`app/healthcheck.py`).
* [Collector Identity Transition](collector/COLLECTOR_IDENTITY_TRANSITION.md): Collector database layer identity transition (`ensure_device_user()`) away from legacy employee stub auto-creation.

### 4. Data & Identity (`docs/data/`)
* [Employee Identity Mapping](data/EMPLOYEE_IDENTITY_MAPPING.md): Strict separation between Human Master Data (`human_employees`) and Device-Local Identity (`device_users`).
* [Human Master Schema & Provenance Architecture](data/HUMAN_MASTER_SCHEMA.md): Additive schema foundation & provenance tracking architecture (`human_employee_sources`).
* [Excel Employee Profile](data/EXCEL_EMPLOYEE_PROFILE.md): Analysis and normalization profile for employee master workbook (`120` records).
* [Excel Human Master Import Contract](data/EXCEL_HUMAN_MASTER_IMPORT.md): Dry-run import contract and schema mapping specification for `human_employees` and `human_employee_sources`.

### 5. Database (`docs/database/`)
* [Identity Schema Migration](database/IDENTITY_SCHEMA_MIGRATION.md): Additive DDL identity migration specification (`sql/002_identity_foundation.sql`).
* [Legacy Identity Constraint Migration](database/LEGACY_IDENTITY_CONSTRAINT_MIGRATION.md): DDL migration specification dropping legacy constraint `attendance_logs_user_id_fkey` (`sql/003_legacy_identity_constraint.sql`).

### 6. Operations & Policy (`docs/operations/`)
* [Change Management Policy](operations/CHANGE_POLICY.md): Operational change management guidelines and execution safety rules.
* [Gemini Response Style Guide](operations/GEM_RESPONSE_STYLE.md): Style and formatting guidelines for AI-Brain system reports.
* [Security Rules](operations/SECURITY_RULES.md): Security practices and secret redaction rules.

### 7. External / AI-Brain (`docs/external/ai-brain/`)
* [AI-Brain System Architecture](external/ai-brain/AI_BRAIN_ARCHITECTURE.md): Host-level architecture for AI-Brain Docker services and databases.
* [AI-Brain Infrastructure](external/ai-brain/AI_BRAIN_INFRASTRUCTURE.md): Host environment configuration and network bindings.

### 8. Historical Reports & Checkpoints (`docs/reports/`)
* [Reports & Checkpoints Index](reports/README.md): Index of all 35 historical PromptID audit, infrastructure, execution, and checkpoint reports.
