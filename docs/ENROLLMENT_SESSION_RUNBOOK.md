# ADMS — Physical Enrollment Session Runbook

**PromptID:** `ADMS-Frontend-WriteEnablement-001`
**Status:** READY (tooling + procedures verified; no real session executed)
**Audience:** the ADMS owner/operator driving a real physical enrollment at the ZEM560 terminal.

This runbook is the single authoritative procedure for turning a **real person at the
terminal** into a **VERIFIED Human ↔ Device mapping**. It closes the one remaining gap in
write enablement: the physical terminal-account step (`set_user`) is deliberately **not**
exposed over HTTP (`create-terminal-account` returns 501), so it is driven by the operator
CLI below while the Collector is briefly paused (the Collector holds the terminal's single
ZK connection).

---

## 0. Session prerequisites

- A real person (the Human being enrolled) is physically present at the terminal.
- Their identity has already been established by the **completed controlled-enrollment
  evidence** process (see `docs/data/DEVICE_ENROLLMENT_WORKFLOW.md` and the
  `HumanDeviceMapping` reports). **Never infer identity from name, rank, numeric ID, or
  timestamp.**
- The Human's record exists in `human_employees` with `active=true` and
  `production_scope=true` (พลทหาร are excluded — they must NOT be enrolled).
- Terminal `192.168.1.201` is reachable and the polling Collector is healthy.

## 1. Pre-session backup (mandatory)

On ai-brain, create a verified custom-format backup and record its identity:

```bash
docker exec adms_postgres pg_dump -U adms -d adms -Fc -f /tmp/adms_pre_enroll_$(date +%Y%m%d_%H%M%S).dump
```

Then verify:
```bash
docker exec adms_postgres sh -c 'ls -la /tmp/adms_pre_enroll_*.dump; sha256sum /tmp/adms_pre_enroll_*.dump'
docker cp <backup> /tmp/ && pg_restore -l <backup> >/dev/null && echo RESTORE_OK
```

Do not proceed until the backup restores cleanly.

## 2. Enable the API write gate

The console's write endpoints are feature-flagged OFF by default. Enable them for the
session (on ai-brain):

```bash
cd /home/kanfullbuster/adms-server
# edit .env: API_WRITE_ENABLED=true   (or docker-compose.yml env override)
docker compose up -d api
```

Verify the gate is open and identity is untouched:
```bash
curl -s http://192.168.1.248:8081/api/v1/health | head
```
The write gate is **temporary**: restore `API_WRITE_ENABLED=false` immediately after the
session (Section 7).

## 3. Reserve the terminal ID (console / API)

1. Log into the console (`http://192.168.1.248:8082`) as an OPERATOR or ADMIN.
2. Enrollments page → **Reserve**: choose the Human (only production-scope eligible humans
   are listed), the device (1), and the operator identity.
3. The reservation allocates the next safe terminal ID (skips legacy/retired/reserved IDs)
   and creates a `RESERVED` enrollment.

Verify:
```bash
curl -s http://192.168.1.248:8081/api/v1/enrollments | python -m json.tool | head -40
```
Expected: one `RESERVED` enrollment with the new `reserved_device_user_id` (e.g. `1002`).

## 4. Create the physical terminal account (operator CLI)

**Why a CLI:** the account creation calls `set_user()` on the terminal and requires the
single live ZK connection that the Collector normally holds. The API route is intentionally
501; the CLI runs inside the listener container with the Collector paused.

```bash
# 4a. Pause the Collector (it holds the terminal's single connection)
docker compose stop listener
docker compose ps            # adms_zkteco_listener Exited

# 4b. Run the CLI (uses the canonical create_reserved_terminal_account())
docker exec adms_zkteco_listener python -m app.enrollment_cli \
    status --enrollment-id <ENROLLMENT_ID>
docker exec adms_zkteco_listener python -m app.enrollment_cli \
    create-terminal-account --enrollment-id <ENROLLMENT_ID> \
    --display-name "<ASCII NAME>" \
    --confirm-collector-paused
```

The CLI is fail-safe:
- refuses to run without `--confirm-collector-paused`;
- refuses if the enrollment is not exactly `RESERVED`;
- reads the live roster first and **refuses to overwrite** an existing terminal ID;
- creates the account with **NORMAL privilege only** (never ADMIN/ENROLLER/SUPERVISOR);
- records the `device_users` row and moves the enrollment to `TERMINAL_ACCOUNT_CREATED`;
- never reads or writes fingerprint templates.

Expected output: `OK: terminal account created.` with the new status
`TERMINAL_ACCOUNT_CREATED`.

```bash
# 4c. Resume the Collector
docker compose start listener
docker compose ps            # adms_zkteco_listener Up (healthy), restarts 0
```

## 5. Physical fingerprint + controlled scan (person at terminal)

1. **Fingerprint:** the operator enrolls the person's finger at the terminal UI under the
   new terminal ID. Then in the console: Confirm fingerprint (state →
   `FINGERPRINT_ENROLLED`), Start controlled scan (opens the bounded 5-minute window).
2. **Controlled scan:** the person performs **exactly one** attendance scan with the
   enrolled finger inside the window. The polling Collector captures it.
3. In the console: Confirm controlled scan with the exact `scan_time` observed
   (state → `CONTROLLED_SCAN_CONFIRMED`), then Mark ready for mapping
   (state → `READY_FOR_MAPPING`).

Rules:
- The scan time must be inside the active controlled window and resolve to this Human
  via the temporal resolver — never attribute before `valid_from`, never fuzzy/name/rank
  matching.
- If more than one event appears in the window: **stop**, do not pick one arbitrarily.

## 6. VERIFIED mapping (ADMIN)

Only an ADMIN may create the VERIFIED mapping (console → Mappings → Create, or
`POST /api/v1/mappings` with `verification_method=CONTROLLED_SCAN`, `verified_by`,
explicit `valid_from`). This is the identity-authority step — it must use the completed
controlled-enrollment evidence, never inference.

Verify:
- `employee_device_mappings` count increased by exactly 1; the new mapping is
  `VERIFIED` with `valid_to IS NULL`;
- the attendance event is attributed to the Human through the mapping;
- `automatic mappings = 0`.

## 7. Post-session: lock down + verify + backup

```bash
# 7a. Close the write gate
cd /home/kanfullbuster/adms-server
# edit .env: API_WRITE_ENABLED=false
docker compose up -d api

# 7b. Verify identity + counts unchanged elsewhere (sample)
curl -s http://192.168.1.248:8081/api/v1/mappings | python -m json.tool | head -40
curl -s http://192.168.1.248:8081/api/v1/dashboard/summary

# 7c. Post-session backup (mandatory)
docker exec adms_postgres pg_dump -U adms -d adms -Fc -f /tmp/adms_post_enroll_$(date +%Y%m%d_%H%M%S).dump
# verify size / sha256 / pg_restore -l as in Section 1
```

Verify runtime: Collector LIVE/HEALTHY, restarts 0, ZKTeco CONNECTED, mapping
`valid_from` correct, attendance attributed, duplicates 0.

## 8. Rollback

- **Wrong terminal ID / failed set_user:** nothing was committed (the CLI errors before
  the DB transition); restart the Collector and re-reserve.
- **Abort after account created:** cancel the enrollment from the console
  (state → `CANCELLED`, reversible, no mapping). The terminal account remains but is
  never mapped; the next reservation skips the ID.
- **Full restore:** `pg_restore` the Section 1 backup (destructive — confirm before use).

## 9. Known constraints

- The Collector must be paused only for the terminal-account step (Section 4); it must be
  running for the controlled scan so attendance is captured.
- No remote fingerprint enrollment exists — enrollment is always at the terminal UI.
- `API_WRITE_ENABLED` is a temporary write safety mechanism, not final authentication
  (F5 auth governs roles; the write gate is defense-in-depth and always restored to false).
- Native ADMS Push remains deferred; polling is the production transport.
