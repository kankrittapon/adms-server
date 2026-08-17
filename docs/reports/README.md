# ADMS Historical Reports & Checkpoint Archive

## 0. Latest Report

- [**ADMS-FullSystem-P0P1-Hardening-007-PhaseF**](ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md) — **deployment record.** Migration 012 applied to production, `adms_api`/`adms_web` redeployed, `API_WRITE_ENABLED` transitioned to `true`, full two-layer write-control verification matrix (13/13 checks passed) run live against production. Read this together with the implementation report below.
- [ADMS-FullSystem-P0P1-Hardening-007](ADMS-FullSystem-P0P1-Hardening-007.md) — the implementation report: security correctness fixes, runtime write-session architecture, enrollment/UX hardening, i18n cleanup (Phases A–E). Kept alongside this index rather than archived, since the Phase F report actively references and extends it.

## 1. About Historical Reports

The documents in this directory represent immutable verification records, execution checkpoints, and architectural audits conducted throughout the development and operational hardening of the ADMS platform.

### Canonical Documentation
For the active, authoritative documentation of the system, refer to the root `docs/` directory:
- [System Architecture](file:///d:/Dev/adms-server/docs/ARCHITECTURE.md) (`docs/ARCHITECTURE.md`)
- [Deployment & Infrastructure Guide](file:///d:/Dev/adms-server/docs/DEPLOYMENT.md) (`docs/DEPLOYMENT.md`)
- [Security & RBAC Matrix](file:///d:/Dev/adms-server/docs/SECURITY_RBAC.md) (`docs/SECURITY_RBAC.md`)
- [Database Schema & Migrations](file:///d:/Dev/adms-server/docs/DATABASE_MIGRATIONS.md) (`docs/DATABASE_MIGRATIONS.md`)
- [Enrollment Runbook](file:///d:/Dev/adms-server/docs/ENROLLMENT_SESSION_RUNBOOK.md) (`docs/ENROLLMENT_SESSION_RUNBOOK.md`)
- [Operations & Troubleshooting](file:///d:/Dev/adms-server/docs/OPERATIONS.md) (`docs/OPERATIONS.md`)

All completed phase reports have been preserved in the [Archive](file:///d:/Dev/adms-server/docs/reports/archive/) (`docs/reports/archive/`).

---

## 2. Chronological PromptID & Phase Index

| Phase / PromptID | Focus Area | Key Outcome / Deliverables | Archived Report |
| ---------------- | ---------- | -------------------------- | --------------- |
| `ADMS-Bootstrap-ZEM560-001` | Hardware Profile | ZKTeco ZEM560_TFT protocol and socket discovery | [ADMS-Bootstrap-ZEM560-001.md](archive/ADMS-Bootstrap-ZEM560-001.md) |
| `ADMS-Collector-StateEngine-002` | Collector FSM | Modular collector architecture (`app/collector.py`) | [ADMS-Collector-StateEngine-002.md](archive/ADMS-Collector-StateEngine-002.md) |
| `ADMS-Collector-HybridBackfill-002` | Ingestion | Historical log backfill and deduplication | [ADMS-Collector-HybridBackfill-002.md](archive/ADMS-Collector-HybridBackfill-002.md) |
| `ADMS-Collector-Healthcheck-002` | Monitoring | Atomic health status file and CLI evaluator | [ADMS-Collector-Healthcheck-002.md](archive/ADMS-Collector-Healthcheck-002.md) |
| `ADMS-Data-IdentitySchema-002` | Database | Additive identity schema migration (`sql/002`) | [ADMS-Data-IdentitySchema-002.md](archive/ADMS-Data-IdentitySchema-002.md) |
| `ADMS-Data-ExcelImport-002` | Human Master | Ingestion of 120 official personnel roster records | [ADMS-Data-ExcelImport-002.md](archive/ADMS-Data-ExcelImport-002.md) |
| `ADMS-Data-HumanMasterSchema-002` | Schema | Provenance and RTN branch schema (`sql/004`) | [ADMS-Data-HumanMasterSchema-002.md](archive/ADMS-Data-HumanMasterSchema-002.md) |
| `ADMS-Collector-TimestampTimezone-002` | Timezones | UTC timestamp normalization with Bangkok timezone | [ADMS-Collector-TimestampTimezone-002.md](archive/ADMS-Collector-TimestampTimezone-002.md) |
| `ADMS-Collector-TemporalIdentity-002` | Resolver | Temporal interval resolver `[valid_from, valid_to)` | [ADMS-Collector-TemporalIdentity-002.md](archive/ADMS-Collector-TemporalIdentity-002.md) |
| `ADMS-Data-DeviceEnrollmentPilot-001` | Pilot | First controlled pilot enrollment on User ID 1001 | [ADMS-Data-DeviceEnrollmentPilot-001.md](archive/ADMS-Data-DeviceEnrollmentPilot-001.md) |
| `ADMS-Data-HumanDeviceMapping-003` | Mapping | First production `VERIFIED` temporal mapping created | [ADMS-Data-HumanDeviceMapping-003.md](archive/ADMS-Data-HumanDeviceMapping-003.md) |
| `ADMS-Data-PlothanProductionExclusion-001` | Data Guard | Migration 007 (`production_scope` conscript exclusion) | [ADMS-Data-PlothanProductionExclusion-001.md](archive/ADMS-Data-PlothanProductionExclusion-001.md) |
| `ADMS-Data-MultiFingerprintValidation-001` | Biometrics | Verified multi-fingerprint resolution to one Human | [ADMS-Data-MultiFingerprintValidation-001.md](archive/ADMS-Data-MultiFingerprintValidation-001.md) |
| `ADMS-Frontend-F1-API-001` | Backend API | FastAPI REST API layer deployment | [ADMS-Frontend-F1-API-001.md](archive/ADMS-Frontend-F1-API-001.md) |
| `ADMS-Frontend-F5-Auth-001` | Security | DB-backed operator authentication (Migration 008) | [ADMS-Frontend-F5-Auth-001.md](archive/ADMS-Frontend-F5-Auth-001.md) |
| `ADMS-Frontend-F3-EnrollmentWorkflow-001` | Frontend | State machine driven Enrollment Workspace UI | [ADMS-Frontend-F3-EnrollmentWorkflow-001.md](archive/ADMS-Frontend-F3-EnrollmentWorkflow-001.md) |
| `ADMS-Frontend-F6-ProductionServing-001` | Serving | Production Nginx web container serving on 8082 | [ADMS-Frontend-F6-ProductionServing-001.md](archive/ADMS-Frontend-F6-ProductionServing-001.md) |
| `ADMS-Frontend-F5-Hardening-001` | Hardening | Login rate limiting and security audit logs | [ADMS-Frontend-F5-Hardening-001.md](archive/ADMS-Frontend-F5-Hardening-001.md) |
| `ADMS-Data-DeviceUserLifecycleHardening-001` | Lifecycle | Migration 009 (`account_incarnation` counter) | [ADMS-Data-DeviceUserLifecycleHardening-001.md](archive/ADMS-Data-DeviceUserLifecycleHardening-001.md) |
| `ADMS-Frontend-RealtimeSSE-001` | Streaming | Realtime SSE attendance event stream | [ADMS-Frontend-RealtimeSSE-001.md](archive/ADMS-Frontend-RealtimeSSE-001.md) |
| `ADMS-Frontend-Codegen-001` | Codegen | OpenAPI snapshot & typed TypeScript client derivation | [ADMS-Frontend-Codegen-001.md](archive/ADMS-Frontend-Codegen-001.md) |
| `ADMS-Infra-CollectorHealthBridge-001` | Health | Shared volume health bridge between listener and API | [ADMS-Infra-CollectorHealthBridge-001.md](archive/ADMS-Infra-CollectorHealthBridge-001.md) |
| `ADMS-Frontend-WriteEnablement-001` | Runbook | Physical enrollment runbook and operator CLI | (Runbook: `docs/ENROLLMENT_SESSION_RUNBOOK.md`) |
| `ADMS-Frontend-FullControlUX-002` | Hardware UX | Browser-driven terminal account creation via Command Bus | [ADMS-Frontend-FullControlUX-002](archive/) |
| `ADMS-Frontend-DesignSystem-003` | Design System | Enterprise UI design system implementation across all pages | (Integrated into `frontend/`) |
| `ADMS-Frontend-I18n-RBAC-Personnel-004` | I18n & RBAC | TH/EN localization, `ENROLLMENT_OPERATOR`, English name edit | (Integrated across codebase) |
| `ADMS-FullSystem-P0P1-Hardening-007` | Security + UX Hardening | Two-layer write-session model, operator-management write-gate fix, alert/confirm removal, centralized i18n enum labels. | [ADMS-FullSystem-P0P1-Hardening-007.md](ADMS-FullSystem-P0P1-Hardening-007.md) *(kept alongside this index, not archived — see §0)* |
| `ADMS-FullSystem-P0P1-Hardening-007-PhaseF` | Production Deployment | Migration 012 applied, containers redeployed, `API_WRITE_ENABLED=true`, two-layer write control verified live (13/13). | [ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md](ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md) |
