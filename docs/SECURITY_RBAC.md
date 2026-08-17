# ADMS Security & Role-Based Access Control (RBAC)

## 1. Security Architecture Principles

1. **Fail-Closed Write Safety**: Production mutations require both valid authenticated role authorization and active server write enablement (`API_WRITE_ENABLED=true`).
2. **Capability-Based Isolation**: Roles are defined by explicit endpoint capabilities rather than simple numeric rank inheritance.
3. **Defense-in-Depth**: Password hashing (PBKDF2-SHA256, 260,000 iterations), ephemeral token hashing (SHA-256 stored in DB), IP rate limiting, and CORS allowlisting are enforced at all entry points.
4. **Zero Automatic Attribution**: Unverified attendance scans remain `employee_id = NULL`. Attributions only occur across explicit `[valid_from, valid_to)` temporal boundaries.

---

## 2. Roles & Capability Matrix

| Endpoint / Area | VIEWER | ENROLLMENT_OPERATOR | OPERATOR | ADMIN |
| --------------- | :----: | :-----------------: | :------: | :---: |
| **Public**: `/api/v1/healthz`, `/api/v1/auth/login` | Allowed | Allowed | Allowed | Allowed |
| **Auth Context**: `/api/v1/auth/me`, `/auth/logout`, `/auth/change-password` | Allowed | Allowed | Allowed | Allowed |
| **Operational Dashboard**: `/api/v1/dashboard/summary` | Allowed | **403 Forbidden** | Allowed | Allowed |
| **Attendance Events**: `GET /api/v1/attendance` | Allowed | **403 Forbidden** | Allowed | Allowed |
| **Realtime SSE Stream**: `GET /api/v1/stream/attendance` | Allowed | Allowed | Allowed | Allowed |
| **Personnel Lookup**: `GET /api/v1/humans` | Allowed | Allowed | Allowed | Allowed |
| **Personnel English Name Edit**: `PATCH /api/v1/humans/{id}` | 403 | 403 | 403 | **Allowed (Write Gated)** |
| **Hardware Registry**: `GET /api/v1/devices` | Allowed | Allowed | Allowed | Allowed |
| **Discovered Terminal Users**: `GET /api/v1/device-users` | Allowed | **403 Forbidden** | Allowed | Allowed |
| **Enrollment Query**: `GET /api/v1/enrollments` | Allowed | Allowed | Allowed | Allowed |
| **Enrollment Workflow Actions**: `POST /api/v1/enrollments/*` | 403 | **Allowed (Write Gated)** | **Allowed (Write Gated)** | **Allowed (Write Gated)** |
| **Terminal Account Creation**: `POST /.../create-terminal-account` | 403 | **Allowed (Write Gated)** | **Allowed (Write Gated)** | **Allowed (Write Gated)** |
| **Identity Mappings**: `GET /api/v1/mappings` | Allowed | **403 Forbidden** | Allowed | Allowed |
| **Mapping Creation**: `POST /api/v1/mappings` | 403 | 403 | 403 | **Allowed (Write Gated)** |
| **Reconciliation Diagnostics**: `GET /api/v1/attendance/unattributed` | 403 | 403 | 403 | **Allowed (Admin Only)** |
| **Operator Management**: `GET/POST /api/v1/operators`, `PATCH toggle-active` | 403 | 403 | 403 | **Allowed (Admin Only)** |
| **Audit Log Trail**: `GET /api/v1/audit/events` | 403 | 403 | 403 | **Allowed (Admin Only)** |

---

## 3. Role Invariants & Specifics

### `ENROLLMENT_OPERATOR`
- **Purpose**: A capability-limited operational role for staff conducting on-site fingerprint enrollment at the physical terminal.
- **Access Scope**: Limited strictly to authenticated identity endpoints, lookup of eligible personnel (`GET /humans`), terminal listing (`GET /devices`), enrollment workflow driver endpoints (`/enrollments/*`), and the realtime attendance SSE stream (`/stream/attendance`).
- **Security Boundary**: Strictly blocked (403 `FORBIDDEN`) from viewing general historical attendance logs, system audit trails, discovered device account tables, temporal identity mappings, operator accounts, and the operational executive dashboard.

### `VIEWER`
- **Purpose**: General audit and monitoring access across all read-only views.
- **Access Scope**: Can inspect attendance, personnel, devices, device users, mappings, and dashboard telemetry. Cannot execute any state mutations.

### `OPERATOR`
- **Purpose**: Standard operational role for personnel enrollment and workflow management.
- **Access Scope**: Inherits `VIEWER` visibility and can execute enrollment reservations, terminal account creations, and controlled scan confirmations when `API_WRITE_ENABLED=true`.

### `ADMIN`
- **Purpose**: System administrator and identity authority.
- **Access Scope**: Full system access including creating `VERIFIED` temporal mappings, modifying personnel English names, creating/deactivating operator accounts, viewing unattributed attendance diagnostics, and inspecting the append-only `sync_events` audit trail.

---

## 4. Authentication & Rate Limiting

1. **Password Policy**: Minimum 12 characters. Stored as `pbkdf2_sha256$260000$<salt>$<hash>`.
2. **Tokens**: High-entropy 32-byte opaque strings prefixed with `adms_`. Stored as SHA-256 hashes in `api_tokens`. Valid for 12 hours by default (`API_TOKEN_TTL_HOURS=12`).
3. **Session Revocation**: Changing an account password immediately revokes all other active session tokens for that operator.
4. **Rate Limiting**:
   - `POST /api/v1/auth/login`: Maximum 5 attempts per minute per IP address. Exceeding triggers HTTP 429 and logs `AUTH_LOGIN_FAILED` / `RATE_LIMITED` audit records.
   - Global `/api/v1/*`: Default backstop of 600 requests per minute per IP address.
