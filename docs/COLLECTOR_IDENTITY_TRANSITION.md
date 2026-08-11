# ADMS Collector Identity Transition Architecture

## Document Status

* **Status**: Approved Collector Identity Transition Plan
* **Source PromptID**: `ADMS-Collector-IdentityTransition-001`
* **Target Subsystem**: Collector Database Layer (`app/db.py`, `app/collector.py`)
* **Prerequisite**: Schema Migration Stage 2 (`ADMS-Data-IdentitySchema-002`) Applied

---

## 1. Executive Summary & Core Identity Flow

The **Collector Identity Transition** upgrades the Python Collector ingestion path to write directly to the additive identity schema (`devices`, `device_users`, `attendance_logs.device_id`, `attendance_logs.device_user_pk`, `attendance_logs.employee_id`).

### Target Ingestion Sequence

```text
ZEM560 Scan Event
        |
        v
Resolve Physical Device (serial_number = '3392113170057') -> device_id
        |
        v
Ensure Device User (device_id, device_user_id) -> device_user_pk
        |
        v
Query Verified Employee Mapping (employee_device_mappings) -> employee_id (or NULL)
        |
        v
Persist Attendance Record
(device_id, device_user_pk, scan_time, status, punch, employee_id)
```

---

## 2. Legacy FK Constraint Blocker Analysis

### Critical Discovery
In the legacy schema (`sql/001_schema.sql`), `attendance_logs` contains:
```sql
user_id TEXT NOT NULL REFERENCES employees(user_id)
```

If `ensure_employee_stub()` is removed from `app/db.py` **before** dropping or relaxing this foreign key constraint, any scan for an unmapped ZKTeco `user_id` will fail with a PostgreSQL `ForeignKeyViolation` error:
`insert or update on table "attendance_logs" violates foreign key constraint "attendance_logs_user_id_fkey"`

### Required Sequence
1. **`ADMS-Data-LegacyIdentityConstraint-001` (Plan ONLY)**: Design DDL migration to drop `attendance_logs_user_id_fkey` constraint while preserving `user_id` string column.
2. **`ADMS-Data-LegacyIdentityConstraint-002` (WRITE Mode)**: Execute DDL script `sql/003_drop_legacy_employee_fk.sql`.
3. **`ADMS-Collector-IdentityTransition-002` (WRITE Mode)**: Update `app/db.py` to invoke `ensure_device_user()` instead of `ensure_employee_stub()`, populating additive columns directly.

---

## 3. Target Database Functions Specification

### A. `ensure_device_user(cur, device_id, device_user_id, display_name)`
```python
def ensure_device_user(cur: Any, device_id: int, device_user_id: str, display_name: Optional[str] = None) -> int:
    """
    Ensures a device_users record exists for (device_id, device_user_id).
    Returns device_user_pk. Does NOT create human_employees rows.
    """
    sql = """
        INSERT INTO device_users (device_id, device_user_id, device_display_name, last_seen_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (device_id, device_user_id) 
        DO UPDATE SET last_seen_at = now()
        RETURNING device_user_pk;
    """
    cur.execute(sql, (device_id, device_user_id, display_name or f"Device User {device_user_id}"))
    row = cur.fetchone()
    if row:
        return row[0]
    
    # Fallback lookup if RETURNING was empty due to concurrency
    cur.execute("SELECT device_user_pk FROM device_users WHERE device_id = %s AND device_user_id = %s;", (device_id, device_user_id))
    return cur.fetchone()[0]
```

### B. `resolve_employee_mapping(cur, device_user_pk)`
```python
def resolve_employee_mapping(cur: Any, device_user_pk: int) -> Optional[str]:
    """
    Looks up active VERIFIED employee mapping for device_user_pk.
    Returns employee_id UUID string or None if unmapped.
    """
    sql = """
        SELECT employee_id 
        FROM employee_device_mappings 
        WHERE device_user_pk = %s AND mapping_status = 'VERIFIED';
    """
    cur.execute(sql, (device_user_pk,))
    row = cur.fetchone()
    return str(row[0]) if row else None
```

---

## 4. Multi-Device Safety & Failure Behavior

* **Device-Scoped Lookup**: All `device_users` queries scope by `device_id`. User `'1'` on Terminal A and User `'1'` on Terminal B remain isolated.
* **Unmapped Attendance Ingestion**: If `resolve_employee_mapping()` returns `None`, `attendance_logs.employee_id` is set to `NULL`. The scan is persisted cleanly without rejection.
* **Zero Terminal Writes**: `ensure_device_user()` operates exclusively within PostgreSQL and never sends write commands to ZKTeco hardware.
