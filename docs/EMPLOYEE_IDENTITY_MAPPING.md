# ADMS Employee & Device Identity Mapping Architecture

## Document Status

* **Status**: Approved Identity Mapping Architecture Plan
* **Source PromptID**: `ADMS-Data-IdentityMapping-001`
* **Target Environment**: ADMS Server PostgreSQL & SONIC ZEM560_TFT Hardware Roster
* **Implementation Target Phase**: `ADMS-Data-IdentitySchema-001` (Plan) / `ADMS-Data-IdentitySchema-002` (Write)

---

## 1. Executive Summary & Core Identity Principles

The **ADMS Identity Mapping Architecture** enforces a strict separation between **Human Master Data** and **Device-Local Identities**:

1. **Human Master Data (`employees`)**: Represents physical personnel from HR / Excel workbooks.
2. **Device-Local Identity (`device_users`)**: Represents local user slots on physical ZKTeco biometric terminals.
3. **Separation Invariant**: A ZKTeco terminal `user_id` is **NOT** the canonical human employee ID. Excel import must **NEVER** automatically create terminal users or assign fingerprint slots.
4. **Local Enrollment Only**: Fingerprint enrollment is performed physically on terminal keypads (`ADMS-Device-RemoteEnrollmentCapability-001`). Device users enter ADMS only after physical creation on the terminal.

---

## 2. Four Identity Domains

```text
+-----------------------+              +-----------------------+
| Human Master Domain   |              | Device User Domain    |
| (employees)           |              | (device_users)        |
|                       |              |                       |
| - employee_id (UUID)  |              | - device_id (Serial)  |
| - personnel_id        |              | - device_user_id      |
| - display_name        |              | - device_display_name |
+-----------------------+              +-----------------------+
            |                                      |
            +------------------+-------------------+
                               |
                               v
               +-------------------------------+
               | Explicit Identity Mapping     |
               | (employee_device_mappings)    |
               |                               |
               | - employee_id                 |
               | - device_user_pk              |
               | - status ('VERIFIED')         |
               +-------------------------------+
                               |
                               v
               +-------------------------------+
               | Raw Attendance Ingestion      |
               | (attendance_logs)             |
               |                               |
               | - device_user_id (NOT NULL)   |
               | - employee_id (NULLABLE)      |
               +-------------------------------+
```

---

## 3. Recommended Normalized Schema Model

### A. `employees` (Human Master Data)
```sql
CREATE TABLE employees (
  employee_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  personnel_id TEXT UNIQUE, -- Optional official organization ID
  display_name TEXT NOT NULL,
  rank TEXT,
  position TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### B. `devices` (Physical Terminals)
```sql
CREATE TABLE devices (
  device_id BIGSERIAL PRIMARY KEY,
  serial_number TEXT NOT NULL UNIQUE, -- Stable identity e.g. '3392113170057'
  device_name TEXT NOT NULL,
  device_ip INET NOT NULL,
  platform TEXT NOT NULL DEFAULT 'ZEM560_TFT',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### C. `device_users` (Terminal-Local Accounts)
```sql
CREATE TABLE device_users (
  device_user_pk BIGSERIAL PRIMARY KEY,
  device_id BIGINT NOT NULL REFERENCES devices(device_id),
  device_user_id TEXT NOT NULL, -- ZKTeco string user_id e.g. '1', '2'
  device_uid INT,
  device_display_name TEXT,
  privilege INT NOT NULL DEFAULT 0,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (device_id, device_user_id)
);
```

### D. `employee_device_mappings` (Explicit Resolution)
```sql
CREATE TABLE employee_device_mappings (
  mapping_id BIGSERIAL PRIMARY KEY,
  employee_id UUID NOT NULL REFERENCES employees(employee_id),
  device_user_pk BIGINT NOT NULL REFERENCES device_users(device_user_pk) UNIQUE,
  mapping_status TEXT NOT NULL CHECK (mapping_status IN ('VERIFIED', 'PROBABLE', 'LEGACY')),
  verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 4. Attendance Ingestion & Mapping Resolution Flow

```text
ZKTeco Terminal Punch
          |
          v
Attendance Ingested (raw device_user_id stored)
          |
          +----> Matches employee_device_mappings?
          |              |
          |              +-- YES --> employee_id populated
          |              |
          |              +-- NO  --> employee_id remains NULL (UNMAPPED)
          v
Attendance Log Persisted cleanly to PostgreSQL
```

* **Zero Scan Rejection**: Attendance ingestion NEVER fails or drops records because an employee mapping is missing.
* **Multi-Device Isolation**: User `'1'` on Device A (`SONIC-01`) and User `'1'` on Device B (`SONIC-02`) map independently to different employees without key collisions.
* **Stub Compatibility Migration**: `ensure_employee_stub()` will be replaced by automatic `device_users` registration, eliminating auto-generated fake employee rows.
