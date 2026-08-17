# ADMS Database Schema & Migration Catalog

## 1. Schema Overview

The ADMS PostgreSQL database (`adms`) is designed with strict additive schema principles and foreign key constraints enforcing the separation between Human Master records and physical biometric hardware identities.

---

## 2. Migration History

| Migration File | Description | Core Tables / Changes Affected |
| -------------- | ----------- | ------------------------------ |
| `001_initial_schema.sql` | Baseline attendance and sync tables. | `attendance_logs`, `sync_events`, `sync_watermarks` |
| `002_identity_foundation.sql` | Introduces hardware and human tables. | `devices`, `device_users`, `human_employees`, `employee_device_mappings` |
| `003_legacy_identity_constraint.sql` | Drops legacy user FK constraint on attendance logs to allow unmapped raw scans. | `attendance_logs_user_id_fkey` dropped; raw `user_id` preserved. |
| `004_human_master_schema.sql` | Extends Human Master with RTN divisions and provenance tracking. | Adds `branch`, `category` to `human_employees`; creates `human_employee_sources`. |
| `005_human_device_mapping_schema.sql` | Adds temporal interval semantics and lifecycle tracking. | Adds `valid_from`, `valid_to`, `verified_by`, `verification_method` to mappings; `roster_last_seen_at`, `inactive_at` to `device_users`. |
| `006_enrollment_sessions.sql` | Implements 9-state guided enrollment state machine. | Creates `enrollment_sessions` table with state check constraints. |
| `007_plothan_production_scope.sql` | Introduces production eligibility filter flag. | Adds `production_scope BOOLEAN NOT NULL DEFAULT true` to `human_employees`. |
| `008_operator_auth_schema.sql` | Adds database-backed operator authentication and sessions. | Creates `operators` and `api_tokens` tables with role check constraints. |
| `009_device_user_lifecycle_hardening.sql` | Adds account incarnation counter for recycled terminal IDs. | Adds `account_incarnation INTEGER NOT NULL DEFAULT 1` to `device_users`. |
| `010_enrollment_operator_role.sql` | Adds `ENROLLMENT_OPERATOR` role constraint. | Updates check constraints on `operators` and `api_tokens` to allow `'ENROLLMENT_OPERATOR'`. |
| `011_human_english_name.sql` | Adds optional English full name for personnel. | Adds `english_name TEXT` column to `human_employees`. |
| `012_write_session_schema.sql` | Runtime write-session (Layer 2 write control). **APPLIED TO PRODUCTION** — see note below. | Creates `write_sessions` table. |

---

### Migration 012 — Runtime Write Session (`012_write_session_schema.sql`)

**Status: APPLIED TO PRODUCTION** (`ADMS-FullSystem-P0P1-Hardening-007-PhaseF`). This migration was implemented in Phase B, validated against the mocked test suite, and applied to the production database during Phase F deployment, following a verified pre-migration `pg_dump` backup (SHA256 + `pg_restore -l` sanity check) and confirmed with a verified post-migration backup. See [docs/reports/ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md](reports/ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md) for the full deployment record.

- **Additive only.** Creates one new table, `write_sessions`; no existing table is altered, no column added/removed elsewhere, no backfill of any kind.
- **Schema:**
  ```sql
  CREATE TABLE write_sessions (
    session_id    BIGSERIAL PRIMARY KEY,
    opened_by     BIGINT NOT NULL REFERENCES operators(operator_id),
    opened_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    reason        TEXT NOT NULL,
    closed_by     BIGINT REFERENCES operators(operator_id),
    closed_at     TIMESTAMPTZ,
    close_reason  TEXT CHECK (close_reason IN ('ADMIN_CLOSED', 'EXPIRED'))
  );
  ```
  Plus a partial unique index guaranteeing at most one row with `closed_at IS NULL` at any time, and a supporting index on `opened_by`.
- **Concurrency protection**: the "at most one active session" invariant is primarily enforced at the application layer via a **PostgreSQL transaction-scoped advisory lock** (`pg_advisory_xact_lock`, `app/write_session.py`) held for the duration of every open/close/status-read transaction — this is what makes reap-then-check-then-insert atomic and prevents two concurrent open attempts from both succeeding. The partial unique index is a database-level backstop behind that, not the primary mechanism (it only guarantees uniqueness of unclosed rows, independent of expiry — expiry is evaluated at read time via `expires_at > now()`, which cannot itself be encoded in a static partial-index predicate).
- **Rollback**: dropping the `write_sessions` table is sufficient and safe in isolation — no other table has a foreign key into it, and no other migration depends on it. If Phase F's code deployment is also rolled back, any production `.env` change to `API_WRITE_ENABLED` made as part of that deployment must be reverted together with the code, not independently (see the Hardening-007 report's rollback plan).
- **Applied**: run against `adms_postgres` during Phase F, preceded by a verified `pg_dump` backup per the pre-migration backup procedure in the Enrollment Session Runbook, and followed by a verified post-migration backup.

---

## 3. Core Tables Reference

### `human_employees`
Authoritative master record of personnel imported from official rosters.
- `employee_id`: UUID (Primary Key, immutable).
- `personnel_id`: Official RTN 10-digit ID (unique when present).
- `display_name`: Canonical Thai full name with rank prefix.
- `english_name`: Optional English full name (editable by Admin).
- `rank`: Thai rank string.
- `branch`: RTN division/branch.
- `category`: Officer / NCO / Enlisted category.
- `production_scope`: `true` for regular personnel, `false` for excluded conscripts (พลทหาร).
- `active`: Boolean active status.

### `device_users`
Discovered hardware user records populated via ZKTeco roster synchronization.
- `device_user_pk`: Serial Primary Key.
- `device_id`: FK referencing `devices(device_id)`.
- `device_user_id`: Terminal string User ID (e.g., `"1001"`).
- `device_uid`: Internal terminal numeric index (diagnostic).
- `device_display_name`: ASCII string name stored on terminal.
- `privilege`: Terminal role (`0` = Normal User).
- `active`: Account presence on terminal.
- `account_incarnation`: Counter incremented upon account recycling.
- `roster_last_seen_at`: Timestamp of latest confirmed roster sync.
- `inactive_at`: Timestamp when account disappeared from terminal roster.

### `employee_device_mappings`
Authoritative temporal identity bindings.
- `mapping_id`: Serial Primary Key.
- `employee_id`: FK referencing `human_employees(employee_id)`.
- `device_user_pk`: FK referencing `device_users(device_user_pk)`.
- `mapping_status`: `VERIFIED`, `PROVISIONAL`, `SUPERSEDED`, or `REVOKED`.
- `valid_from`: UTC timestamp (inclusive start of validity interval).
- `valid_to`: Optional UTC timestamp (exclusive end of validity interval; `NULL` = active).
- `verification_method`: Method of verification (e.g. `CONTROLLED_SCAN`).
- `verified_by`: Username of authorizing administrator.
- `verification_note`: Audit justification text.

### `attendance_logs`
Append-only immutable record of biometric scans.
- `id`: Serial Primary Key.
- `user_id`: Raw terminal User ID string.
- `device_ip`: Originating terminal IP address.
- `scan_time`: Normalized UTC timestamp.
- `status`: Attendance status (`ON_TIME`, `LATE`, `UNKNOWN`).
- `employee_id`: Nullable UUID populated by temporal resolver.
- `device_user_pk`: FK referencing discovered `device_users`.
- `raw_payload`: Raw device JSON payload.
