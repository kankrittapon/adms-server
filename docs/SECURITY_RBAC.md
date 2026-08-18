# ADMS Security & Role-Based Access Control (RBAC)

> **Production state note (`ADMS-FullSystem-P0P1-Hardening-007`)**: this document describes the two-layer write model, **live in production as of Phase F**. `API_WRITE_ENABLED` (Layer 1) is now `true` — the steady-state infrastructure baseline. The runtime write session (Layer 2) is closed by default; production stays write-locked until an ADMIN explicitly opens one. See [STATUS.md](../STATUS.md), [docs/reports/ADMS-FullSystem-P0P1-Hardening-007.md](reports/ADMS-FullSystem-P0P1-Hardening-007.md), and [docs/reports/ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md](reports/ADMS-FullSystem-P0P1-Hardening-007-PhaseF.md).

## 1. Security Architecture Principles

1. **Fail-Closed Write Safety**: Production mutations require valid authenticated role authorization AND active server write enablement. As of Hardening-007, this is formalized as two independent layers (§1a) — both required, neither optional, neither implying the other.
2. **Capability-Based Isolation**: Roles are defined by explicit endpoint capabilities rather than simple numeric rank inheritance.
3. **Defense-in-Depth**: Password hashing (PBKDF2-SHA256, 260,000 iterations), ephemeral token hashing (SHA-256 stored in DB), IP rate limiting, and CORS allowlisting are enforced at all entry points.
4. **Zero Automatic Attribution**: Unverified attendance scans remain `employee_id = NULL`. Attributions only occur across explicit `[valid_from, valid_to)` temporal boundaries.

## 1a. Two-Layer Write Authorization Model

```
allow_write =
    infrastructure_master_enabled   (Layer 1 — API_WRITE_ENABLED)
    AND runtime_write_session_active (Layer 2 — ADMIN-opened work session)
    AND role_permits_action          (RBAC — role-set check)
```

**Layer 1 — Infrastructure master gate** (`API_WRITE_ENABLED`, unchanged from prior design): env-controlled, server-owner-only, fail-closed. Production value: `true` (the steady-state deploy-time baseline as of Phase F — a rarely-touched emergency lock, not a daily toggle). Overrides Layer 2 unconditionally — if Layer 1 is closed, Layer 2 is never even evaluated, and no runtime session can be opened. This override behavior was explicitly verified live during Phase F deployment.

**Layer 2 — Runtime write session** (new in Hardening-007, **live in production as of Phase F**; open/close authorization widened to OPERATOR-or-ADMIN in `ADMS-RBAC-OperationalRoles-023`): a short-lived, auditable permission window (`app/write_session.py`, table `write_sessions`, migration 012 — applied), opened/closed by an OPERATOR or ADMIN; fixed 30-minute duration with no automatic renewal; at most one session active at a time, enforced by a Postgres transaction-scoped advisory lock so concurrent open attempts cannot both succeed and an expired-but-unclosed session is reaped (and audited exactly once) before it can block a new open. Closed by default — no session is open unless an OPERATOR or ADMIN explicitly opens one. **Opening/closing the session is only Layer 2 — it never widens Layer 3 (role-permits-action).** A single global session opened by an OPERATOR does not grant OPERATOR access to any ADMIN-only endpoint (mapping verification, Personnel lifecycle, destructive Terminal Management, operator/role management all remain independently `ROLES_ADMIN_ONLY`-gated); it only lets ENROLLMENT_OPERATOR/OPERATOR/ADMIN perform the writes each was already independently permitted to make.

**Auth/session-maintenance exemption**: `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/change-password` are exempt from **both** write layers — they establish or terminate the caller's own authentication session, not domain state (Human/Device/Enrollment/Mapping/Operator records). An operator must always be able to log in or change a compromised password even while all domain writes are locked. The invariant: *any endpoint that creates, modifies, or invalidates domain state requires both write layers; endpoints that only establish/terminate the caller's own session do not.*

**Operator management is a protected production write, not an exception.** `POST /api/v1/operators` and `POST /api/v1/operators/{id}/toggle-active` previously bypassed Layer 1 entirely (a real gap — an ADMIN token could create or reactivate privileged accounts even while `API_WRITE_ENABLED=false`). This was closed in Hardening-007 Phase A; both routes are now gated exactly like every other domain-mutating endpoint by both layers.

**Closing a write session is never gated by Layer 1.** `POST /write-session/close` is a de-escalation action and must always be available to an ADMIN, even if the infrastructure gate is already off — narrowing permissions should never itself require permissions.

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
| **Operator Management**: `GET /api/v1/operators` (read) | 403 | 403 | 403 | **Allowed (Admin Only)** |
| **Operator Management**: `POST /api/v1/operators`, `POST .../toggle-active` (write) | 403 | 403 | 403 | **Allowed (Admin Only, Write Gated)** — was previously ungated; fixed in Hardening-007 Phase A |
| **Audit Log Trail**: `GET /api/v1/audit/events` | 403 | 403 | 403 | **Allowed (Admin Only)** |
| **Write Session Status**: `GET /api/v1/write-session` | Allowed | Allowed | Allowed | Allowed |
| **Write Session Open/Close**: `POST /api/v1/write-session/*` | 403 | 403 | **Allowed** | **Allowed** |

> Widened from Admin-only to OPERATOR-or-ADMIN in `ADMS-RBAC-OperationalRoles-023`. ENROLLMENT_OPERATOR remains 403 for open/close — it may use a session already opened by OPERATOR/ADMIN but may never open or close one itself.

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
- **Purpose**: Operational supervisor. Controls **when** operational writes may happen, not **what** privileged ADMIN actions become allowed.
- **Access Scope**: Inherits `VIEWER` visibility, can execute the same enrollment reservations/terminal account creation/controlled scan confirmations as `ENROLLMENT_OPERATOR` when writes are open, and — as of `ADMS-RBAC-OperationalRoles-023` — can open and close the runtime write session (`POST /api/v1/write-session/open`, `/close`) itself. Both `API_WRITE_ENABLED=true` and an active runtime write session are still required for any domain write.
- **Explicitly forbidden**: operator/role management, Personnel admin lifecycle (deactivate/reactivate), mapping verification, and destructive Terminal Management (fingerprint delete, terminal account delete) — all remain `ADMIN`-only regardless of who opened the write session.

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
