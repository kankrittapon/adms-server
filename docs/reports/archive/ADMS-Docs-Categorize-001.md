# ADMS DOCUMENTATION CATEGORIZATION PLAN

## Prompt

* PromptID: `ADMS-Docs-Categorize-001`
* mode: READ-ONLY DOCUMENT INVENTORY + DOCUMENTATION ORGANIZATION PLAN ONLY
* timestamp: 2026-08-11T11:54:00+07:00
* files moved: NO
* files renamed: NO
* application modified: NO
* database modified: NO
* device modified: NO

## Current Inventory

- total docs: 55 files
- canonical root docs: 20 files
- reports/checkpoints: 34 files
- report index: 1 file (`docs/reports/README.md`)
- duplicate/overlap candidates: Low (Each document covers a distinct canonical domain or execution stage)
- root docs clutter assessment: High (20 flat markdown files in `docs/` makes top-level navigation difficult)

## Proposed Categories

| Category | Folder Path | Purpose | Document Count |
| -------- | ----------- | ------- | -------------- |
| Architecture | `docs/architecture/` | System-wide topology, data flows, and trust boundaries | 4 |
| Device | `docs/device/` | Hardware profile, firmware findings, and capability specifications | 2 |
| Collector | `docs/collector/` | Collector FSM state engine, backfill, healthcheck, and reliability | 5 |
| Data & Identity | `docs/data/` | Identity mapping, Human Master schema, Excel profiling and import | 4 |
| Database | `docs/database/` | SQL migration design and DDL constraint transition specs | 2 |
| Operations | `docs/operations/` | Operational policies, security rules, and response style guidelines | 3 |
| Reports | `docs/reports/` | Historical PromptID execution reports and checkpoints | 35 |

## Proposed Tree Structure

```text
docs/
├── README.md                                    # Top-Level Navigation Index
├── architecture/
│   ├── ADMS_ARCHITECTURE.md
│   ├── AI_BRAIN_ARCHITECTURE.md
│   ├── AI_BRAIN_INFRASTRUCTURE.md
│   └── SOURCE_AI_BRAIN_DOCKER_AUDIT_2026-08-10.md
├── device/
│   ├── ZEM560_CAPABILITY_SPEC.md
│   └── ZEM560_DEVICE_PROFILE.md
├── collector/
│   ├── COLLECTOR_HEALTHCHECK.md
│   ├── COLLECTOR_HYBRID_BACKFILL.md
│   ├── COLLECTOR_IDENTITY_TRANSITION.md
│   ├── COLLECTOR_RELIABILITY.md
│   └── COLLECTOR_STATE_ENGINE.md
├── data/
│   ├── EMPLOYEE_IDENTITY_MAPPING.md
│   ├── EXCEL_EMPLOYEE_PROFILE.md
│   ├── EXCEL_HUMAN_MASTER_IMPORT.md
│   └── HUMAN_MASTER_SCHEMA.md
├── database/
│   ├── IDENTITY_SCHEMA_MIGRATION.md
│   └── LEGACY_IDENTITY_CONSTRAINT_MIGRATION.md
├── operations/
│   ├── CHANGE_POLICY.md
│   ├── GEM_RESPONSE_STYLE.md
│   └── SECURITY_RULES.md
└── reports/                                     # Retained flat for instant PromptID lookup
    ├── README.md
    ├── ADMS-Bootstrap-ZEM560-001.md
    ├── ADMS-Checkpoint-CollectorFoundation-001.md
    ├── ADMS-Checkpoint-PostIdentityTransition-001.md
    ├── ADMS-Checkpoint-PreIdentitySchema-001.md
    ├── ... (30 execution & audit reports)
```

## File Move Map

| Current Path | Proposed Path | Type | Reason |
| ------------ | ------------- | ---- | ------ |
| `docs/ADMS_ARCHITECTURE.md` | `docs/architecture/ADMS_ARCHITECTURE.md` | CANONICAL | System architecture specification |
| `docs/AI_BRAIN_ARCHITECTURE.md` | `docs/architecture/AI_BRAIN_ARCHITECTURE.md` | CANONICAL | AI-Brain host architecture |
| `docs/AI_BRAIN_INFRASTRUCTURE.md` | `docs/architecture/AI_BRAIN_INFRASTRUCTURE.md` | CANONICAL | AI-Brain infrastructure setup |
| `docs/SOURCE_AI_BRAIN_DOCKER_AUDIT_2026-08-10.md` | `docs/architecture/SOURCE_AI_BRAIN_DOCKER_AUDIT_2026-08-10.md` | SUPPORTING | Baseline audit snapshot |
| `docs/ZEM560_DEVICE_PROFILE.md` | `docs/device/ZEM560_DEVICE_PROFILE.md` | CANONICAL | Physical hardware profile |
| `docs/ZEM560_CAPABILITY_SPEC.md` | `docs/device/ZEM560_CAPABILITY_SPEC.md` | CANONICAL | Device capability matrix |
| `docs/COLLECTOR_RELIABILITY.md` | `docs/collector/COLLECTOR_RELIABILITY.md` | CANONICAL | Reliability model |
| `docs/COLLECTOR_STATE_ENGINE.md` | `docs/collector/COLLECTOR_STATE_ENGINE.md` | CANONICAL | FSM state engine design |
| `docs/COLLECTOR_HYBRID_BACKFILL.md` | `docs/collector/COLLECTOR_HYBRID_BACKFILL.md` | CANONICAL | Hybrid backfill design |
| `docs/COLLECTOR_HEALTHCHECK.md` | `docs/collector/COLLECTOR_HEALTHCHECK.md` | CANONICAL | Ephemeral healthcheck design |
| `docs/COLLECTOR_IDENTITY_TRANSITION.md` | `docs/collector/COLLECTOR_IDENTITY_TRANSITION.md` | CANONICAL | Identity transition design |
| `docs/EMPLOYEE_IDENTITY_MAPPING.md` | `docs/data/EMPLOYEE_IDENTITY_MAPPING.md` | CANONICAL | Identity domain mapping architecture |
| `docs/EXCEL_EMPLOYEE_PROFILE.md` | `docs/data/EXCEL_EMPLOYEE_PROFILE.md` | SUPPORTING | Excel profiling reference |
| `docs/EXCEL_HUMAN_MASTER_IMPORT.md` | `docs/data/EXCEL_HUMAN_MASTER_IMPORT.md` | CANONICAL | Excel import contract |
| `docs/HUMAN_MASTER_SCHEMA.md` | `docs/data/HUMAN_MASTER_SCHEMA.md` | CANONICAL | Human Master schema architecture |
| `docs/IDENTITY_SCHEMA_MIGRATION.md` | `docs/database/IDENTITY_SCHEMA_MIGRATION.md` | CANONICAL | Additive DDL migration spec |
| `docs/LEGACY_IDENTITY_CONSTRAINT_MIGRATION.md` | `docs/database/LEGACY_IDENTITY_CONSTRAINT_MIGRATION.md` | CANONICAL | Legacy constraint drop spec |
| `docs/CHANGE_POLICY.md` | `docs/operations/CHANGE_POLICY.md` | POLICY | Change management policy |
| `docs/GEM_RESPONSE_STYLE.md` | `docs/operations/GEM_RESPONSE_STYLE.md` | POLICY | Response style guidelines |
| `docs/SECURITY_RULES.md` | `docs/operations/SECURITY_RULES.md` | POLICY | Security redaction rules |

## Reports Strategy

- current count: 35 files (34 PromptID reports/checkpoints + `README.md`)
- flat or categorized: **Flat under `docs/reports/`**
- proposed structure: Keep reports in `docs/reports/` without subfolders to allow instant PromptID string search (e.g. `ADMS-Collector-HybridBackfill-002`).
- PromptID lookup preserved: **100% YES**
- reports README role: Master index mapping PromptIDs to dates, types, modes, and summaries.

## Root `docs/` Strategy

- files remaining directly under `docs/`: `docs/README.md` (Top-level navigation map).
- reason: Keeps `docs/` clean and navigable with depth $\le 2$ levels.

## Cross-Reference Impact

| Referring File | Current Link / Reference Path | Required New Link |
| -------------- | ----------------------------- | ----------------- |
| `README.md` | `docs/ADMS_ARCHITECTURE.md` | `docs/architecture/ADMS_ARCHITECTURE.md` |
| `STATUS.md` | `docs/EMPLOYEE_IDENTITY_MAPPING.md` | `docs/data/EMPLOYEE_IDENTITY_MAPPING.md` |
| `STATUS.md` | `docs/HUMAN_MASTER_SCHEMA.md` | `docs/data/HUMAN_MASTER_SCHEMA.md` |
| `STATUS.md` | `docs/EXCEL_HUMAN_MASTER_IMPORT.md` | `docs/data/EXCEL_HUMAN_MASTER_IMPORT.md` |
| `docs/reports/README.md` | `docs/*.md` references | Updated category paths in notes section |

## Overlap / Duplication Review

| Documents | Finding | Recommendation |
| --------- | ------- | -------------- |
| `EMPLOYEE_IDENTITY_MAPPING.md` & `HUMAN_MASTER_SCHEMA.md` | Complementary: First defines multi-domain architecture; second defines SQL schema & provenance. | **KEEP SEPARATE** |
| `ZEM560_DEVICE_PROFILE.md` & `ZEM560_CAPABILITY_SPEC.md` | Complementary: First defines physical hardware profile; second defines protocol capability matrix. | **KEEP SEPARATE** |
| `COLLECTOR_STATE_ENGINE.md` & `COLLECTOR_HEALTHCHECK.md` | Complementary: First defines state engine transitions; second defines liveness probing. | **KEEP SEPARATE** |

## Naming Conventions

- canonical docs: `UPPER_SNAKE_CASE.md` (Retained without cosmetic renames)
- reports: `PROMPTID.md` (e.g., `ADMS-Collector-IdentityTransition-002.md`)

## Proposed `docs/README.md` Content

```markdown
# ADMS & AI-Brain System Documentation

Welcome to the ADMS Server & AI-Brain documentation library.

## Navigation Map

### 1. Architecture (`docs/architecture/`)
* [ADMS_ARCHITECTURE.md](file:///d:/Dev/adms-server/docs/architecture/ADMS_ARCHITECTURE.md): System overview, state machine data flows, network topology, and failure domain boundaries.
* [AI_BRAIN_ARCHITECTURE.md](file:///d:/Dev/adms-server/docs/architecture/AI_BRAIN_ARCHITECTURE.md): Host-level architecture for AI-Brain Docker services and databases.
* [AI_BRAIN_INFRASTRUCTURE.md](file:///d:/Dev/adms-server/docs/architecture/AI_BRAIN_INFRASTRUCTURE.md): Host environment configuration and network bindings.
* [SOURCE_AI_BRAIN_DOCKER_AUDIT_2026-08-10.md](file:///d:/Dev/adms-server/docs/architecture/SOURCE_AI_BRAIN_DOCKER_AUDIT_2026-08-10.md): Historical live runtime baseline audit snapshot.

### 2. Device (`docs/device/`)
* [ZEM560_DEVICE_PROFILE.md](file:///d:/Dev/adms-server/docs/device/ZEM560_DEVICE_PROFILE.md): Hardware, MIPS CPU, Linux 2.6.24 kernel, and firmware specifications for SONIC ZEM560_TFT terminal (`192.168.1.201`).
* [ZEM560_CAPABILITY_SPEC.md](file:///d:/Dev/adms-server/docs/device/ZEM560_CAPABILITY_SPEC.md): Protocol capability matrix, user/log capacity limits, and 5-tier usability framework.

### 3. Collector (`docs/collector/`)
* [COLLECTOR_RELIABILITY.md](file:///d:/Dev/adms-server/docs/collector/COLLECTOR_RELIABILITY.md): Production-grade reliability model, event capture, deduplication, and failure domain isolation.
* [COLLECTOR_STATE_ENGINE.md](file:///d:/Dev/adms-server/docs/collector/COLLECTOR_STATE_ENGINE.md): Finite State Machine design (`STARTING` -> `CONNECTING` -> `BACKFILLING` -> `LIVE` -> `DEGRADED` / `BACKOFF` / `STOPPING`).
* [COLLECTOR_HYBRID_BACKFILL.md](file:///d:/Dev/adms-server/docs/collector/COLLECTOR_HYBRID_BACKFILL.md): Historical attendance reconciliation, watermark filtering, 500-record batch chunk persistence, and MQTT suppression.
* [COLLECTOR_HEALTHCHECK.md](file:///d:/Dev/adms-server/docs/collector/COLLECTOR_HEALTHCHECK.md): Atomic ephemeral status file (`/tmp/collector_health.json`), state-aware liveness thresholds, and non-invasive CLI evaluator (`app/healthcheck.py`).
* [COLLECTOR_IDENTITY_TRANSITION.md](file:///d:/Dev/adms-server/docs/collector/COLLECTOR_IDENTITY_TRANSITION.md): Collector database layer identity transition (`ensure_device_user()`) away from legacy employee stub auto-creation.

### 4. Data & Identity (`docs/data/`)
* [EMPLOYEE_IDENTITY_MAPPING.md](file:///d:/Dev/adms-server/docs/data/EMPLOYEE_IDENTITY_MAPPING.md): Strict separation between Human Master Data (`human_employees`) and Device-Local Identity (`device_users`).
* [HUMAN_MASTER_SCHEMA.md](file:///d:/Dev/adms-server/docs/data/HUMAN_MASTER_SCHEMA.md): Additive schema foundation & provenance tracking architecture (`human_employee_sources`).
* [EXCEL_EMPLOYEE_PROFILE.md](file:///d:/Dev/adms-server/docs/data/EXCEL_EMPLOYEE_PROFILE.md): Analysis and normalization profile for employee master workbook (`120` records).
* [EXCEL_HUMAN_MASTER_IMPORT.md](file:///d:/Dev/adms-server/docs/data/EXCEL_HUMAN_MASTER_IMPORT.md): Dry-run import contract and schema mapping specification for `human_employees` and `human_employee_sources`.

### 5. Database (`docs/database/`)
* [IDENTITY_SCHEMA_MIGRATION.md](file:///d:/Dev/adms-server/docs/database/IDENTITY_SCHEMA_MIGRATION.md): Additive DDL identity migration specification (`sql/002_identity_foundation.sql`).
* [LEGACY_IDENTITY_CONSTRAINT_MIGRATION.md](file:///d:/Dev/adms-server/docs/database/LEGACY_IDENTITY_CONSTRAINT_MIGRATION.md): DDL migration specification dropping legacy constraint `attendance_logs_user_id_fkey` (`sql/003_legacy_identity_constraint.sql`).

### 6. Operations & Policy (`docs/operations/`)
* [CHANGE_POLICY.md](file:///d:/Dev/adms-server/docs/operations/CHANGE_POLICY.md): Operational change management guidelines and execution safety rules.
* [GEM_RESPONSE_STYLE.md](file:///d:/Dev/adms-server/docs/operations/GEM_RESPONSE_STYLE.md): Style and formatting guidelines for AI-Brain system reports.
* [SECURITY_RULES.md](file:///d:/Dev/adms-server/docs/operations/SECURITY_RULES.md): Security practices and secret redaction rules.

### 7. Historical Reports & Checkpoints (`docs/reports/`)
* [README.md](file:///d:/Dev/adms-server/docs/reports/README.md): Index of all 34 historical PromptID audit, infrastructure, execution, and checkpoint reports.
```

## Future WRITE Plan (`ADMS-Docs-Categorize-002`)

1. Create target directories: `docs/architecture/`, `docs/device/`, `docs/collector/`, `docs/data/`, `docs/database/`, `docs/operations/`.
2. Move 20 canonical markdown files using `git mv`.
3. Create `docs/README.md` navigation map.
4. Update cross-references in `README.md`, `STATUS.md`, and canonical docs.
5. Verify zero broken markdown links.
6. Commit and push changes.
7. Server restart required: **NO** (0 runtime impact).

## Proposed Next PromptID

Recommended Next PromptID:
- `#NotInfra PromptID: ADMS-Docs-Categorize-002` (DOCUMENTATION REORGANIZATION WRITE)

## FINAL

- inventory complete: YES (55 files inventoried)
- clear category model available: YES (6 domain categories + reports)
- exact move map available: YES (20 canonical moves mapped)
- canonical vs historical separated: YES
- broken-link impact understood: YES
- runtime dependency on docs paths: NO (0 runtime impact)
- safe to reorganize docs: YES
- blockers: NONE

STOP.
