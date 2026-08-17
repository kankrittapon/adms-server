# ADMS Current Status

## 1. Production Environment

- **Management Web Console**: `http://192.168.1.248:8082` (Container `adms_web` via Nginx, LAN bind)
- **Backend API**: `http://192.168.1.248:8081` (Container `adms_api` via FastAPI/Uvicorn, LAN bind)
- **Biometric Terminal**: `192.168.1.201:4370` (SONIC / ZKTeco ZEM560_TFT, standalone binary protocol)
- **Container Topology**: All 5 containers `Up (healthy)` with 0 restarts (`adms_web`, `adms_api`, `adms_zkteco_listener`, `adms_postgres`, `adms_mqtt`)
- **Collector Connection State**: `LIVE` / `device_connected = true`
- **Master Production Write Gate**: `API_WRITE_ENABLED = false` (Fail-closed read-only default)

---

## 2. Current Version & Quality Baseline

- **Repository HEAD**: `315a5e6` (`origin/main` synchronized with `ai-brain`)
- **Database Migrations**: Applied through `011_human_english_name.sql` (11 migrations total)
- **Automated Test Baseline**: **408 passed / 0 failed** across 21 test suites (`pytest tests/`)
- **Frontend Typecheck & Build**: `tsc --noEmit` PASS (0 errors), Vite production build PASS

---

## 3. Major Capabilities

1. **Human Master Registry**:
   - 120 official personnel records imported from Royal Thai Navy roster.
   - Immutable UUIDs, RTN rank normalization, branch/division mapping.
   - Conscript exclusion: 36 conscripts (พลทหาร) safely excluded (`production_scope = false`).
2. **Attendance Processing & Reconciliation**:
   - Ingestion over ZKTeco TCP socket with deduplication on `(user_id, device_ip, scan_time)`.
   - UTC timestamp normalization with Bangkok timezone (`Asia/Bangkok`).
   - Unmapped scans stored safely with `employee_id = NULL`.
3. **Temporal Identity Mapping**:
   - Strict `[valid_from, valid_to)` validity interval resolution.
   - Ambiguity fail-safe: Multiple matching mappings fail closed to `NULL`.
   - 1 active production mapping created and verified from pilot evidence (`039c4486...` ↔ User 1001).
4. **Guided Enrollment Workspace**:
   - 9-state formal enrollment state machine (`app/enrollment.py`).
   - Safe automated User ID reservation (namespace `1001+`).
   - 6-step guided visual workspace in the web console with countdown timer and realtime scan capture.
5. **Browser-Driven Hardware Account Creation**:
   - Direct web-driven `set_user()` creation via internal **Device Command Bus** over MQTT.
   - Single-socket exclusive execution inside Collector session without downtime or competing connections.
6. **Realtime Attendance SSE Stream**:
   - High-throughput Server-Sent Events (`/api/v1/stream/attendance`) bridging MQTT scan topics to browsers.
   - Live visual scan notification banner and auto-refreshing tables.
7. **Bilingual Localization (TH / EN)**:
   - Lightweight, typed i18n engine with Thai (`th`) default and English (`en`) switchable in header.
   - Persistent preference stored in `localStorage` key `adms.locale`.
8. **Role-Based Access Control (RBAC)**:
   - Explicit capability sets: `VIEWER`, `ENROLLMENT_OPERATOR`, `OPERATOR`, `ADMIN`.
   - `ENROLLMENT_OPERATOR` is strictly capability-limited to the Enrollment Workspace.
9. **Admin Operator Account Management**:
   - Provisioning, password assignment, role selection, and active toggle from Web Console.
10. **Personnel English Name Support**:
    - Bilingual personnel display and Admin-only inline editing (`PATCH /api/v1/humans/{id}`).
11. **Security & System Audit Trail**:
    - In-process rate limiting (5 login attempts/min/IP), PBKDF2 password hashing, opaque Bearer tokens.
    - Comprehensive audit event logging (`sync_events`) covering auth, rate limits, lifecycle, and enrollment actions.
12. **OpenAPI Snapshot & Typed Client Codegen**:
    - Automated schema snapshot generation and operation-derived TypeScript client.
13. **Collector Health Bridge**:
    - Shared volume bridge delivering real-time Collector socket telemetry to API consumers.

---

## 4. Security & Safety Rules

- **Zero Automatic Mapping**: No assumption that Excel row number equals terminal user ID.
- **Fail-Closed Write Gate**: All state mutations require active `API_WRITE_ENABLED=true`.
- **Lifecycle & Incarnation Protection**: Inactive terminal accounts have open mappings closed automatically. Reappearing IDs increment `account_incarnation` without inheriting prior identity.
- **Biometric Boundary**: No biometric templates are ever extracted, transmitted over HTTP, or stored in application databases.

---

## 5. Roadmap & Operational Readiness

### READY FOR EXECUTION
- **Real Personnel Enrollment**: Ready for on-site physical enrollment following `docs/ENROLLMENT_SESSION_RUNBOOK.md`.

### DEFERRED
- **Multi-Person Enrollment Validation**: Verification across multiple distinct individuals.
- **Native ADMS Push**: Deferred (Device hardware silent; polling Collector remains authoritative primary).
