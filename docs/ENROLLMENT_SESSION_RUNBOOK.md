# ADMS — Production Enrollment Session Runbook

**Audience**: ADMS System Administrators & Operators conducting physical fingerprint enrollment at the ZKTeco ZEM560 terminal.

This runbook defines the authoritative end-to-end procedure for enrolling a real person at the terminal and generating an active **`VERIFIED` Temporal Identity Mapping**.

---

> ## ⚠ PRODUCTION STATE NOTICE — READ BEFORE STARTING A REAL SESSION
>
> `ADMS-FullSystem-P0P1-Hardening-007` (Phases A–E) added a browser-controlled
> runtime write-session feature so an ADMIN can open/close write access for an
> enrollment session without SSH — **this feature exists in source only.**
> **Phase F (production deployment) has NOT occurred.** Production today still
> runs the pre-Hardening-007 model: **§3 (Temporary Write Gate Enablement,
> server-owner SSH step) is still required for every real enrollment session**
> until Phase F is deployed and this notice is removed.
>
> Do not skip §3 based on the "Normal Procedure" framing below — that section
> describes the **target end-state**, not what production currently supports.

---

## 1. Prerequisites & Planning

- **Physical Presence**: The individual to be enrolled is physically present in front of the terminal `ADMS-ZEM560` (`192.168.1.201`).
- **Personnel Eligibility**: The individual exists in `human_employees` with `active=true` and `production_scope=true`. (Conscripts/พลทหาร are excluded).
- **Collector Status**: Collector state is `LIVE` and `device_connected=true` on the dashboard.
- **Identity Invariant**: Never infer identity from name similarity or sequential order. Enrollment relies strictly on controlled scan evidence.

---

## 2. Pre-Session Mandatory Backup

On `ai-brain` (`192.168.1.248`), generate and verify a fresh custom database dump:

```bash
docker exec adms_postgres pg_dump -U adms -d adms -Fc -f /tmp/adms_pre_enroll_$(date +%Y%m%d_%H%M%S).dump
docker exec adms_postgres sh -c 'ls -lh /tmp/adms_pre_enroll_*.dump'
docker exec adms_postgres pg_restore -l /tmp/adms_pre_enroll_<TIMESTAMP>.dump | head -20
```

This step is required regardless of which write-gate procedure below applies.

---

## 3. Opening Write Access for the Session

### 3a. Normal Procedure (target end-state — active only after Phase F is deployed)

Once Phase F ships, opening write access for a session is a browser action, not an SSH action:

1. An **ADMIN** signs in to the console and opens **System** (`/system`).
2. In the **Production Changes** panel, enter a reason (e.g. "Enrollment session — Bldg 3") and click **Open work session**.
3. The session is active for **30 minutes**, auto-expiring with no automatic renewal. The header badge shows the remaining time to every signed-in role.
4. If more time is needed, the ADMIN opens a fresh session — there is no "leave it on" option by design.
5. The ADMIN (or any ADMIN) can close the session early from the same panel once the session's work is done.

This still requires the server-owner-controlled infrastructure master gate (`API_WRITE_ENABLED`) to be `true` — see §3b's role once Phase F ships: it becomes a rarely-touched emergency lock, not a per-session toggle.

### 3b. Current Interim Procedure (use this today — production has not deployed Phase F)

Enable the master production write flag on `ai-brain`:

```bash
cd /home/kanfullbuster/adms-server
# Update .env or pass environment variable:
# API_WRITE_ENABLED=true
docker compose up -d api
```

Verify that the dashboard shows the write-enabled indicator (amber badge).

---

## 4. Guided Enrollment Workflow (Primary Browser Path)

This section is unchanged by Hardening-007 — the guided workflow itself was already browser-driven; only the write-gate step above changes once Phase F ships.

### Step 1: Reserve Terminal ID (Browser)
1. Navigate to **Enrollment Workspace** (`http://192.168.1.248:8082/enrollments`).
2. Under **Step 1: Reserve Terminal ID**, select the eligible Human, target device, and enter your operator identity.
3. Click **Reserve Terminal ID**. The system allocates the next safe terminal User ID (e.g. `1002`) and moves the session to `RESERVED`.

### Step 2: Create Terminal Account on Device (Browser)
1. In the active enrollment inspector, review the allocated ID and terminal display name (English letters and numbers only).
2. Click **Create Terminal Account**.
3. The API dispatches the command across the internal **Device Command Bus** over MQTT. The Collector safely creates the user with `NORMAL` privilege without restarting or releasing the ZK socket. State transitions to `TERMINAL_ACCOUNT_CREATED`.

### Step 3: Physical Fingerprint Capture (Terminal Hardware)
1. Escort the person to the physical terminal `ADMS-ZEM560`.
2. Press **Menu** → **User Mgt** → **Manage**.
3. Locate the allocated User ID (e.g. `1002`) and press **OK**.
4. Select **Enroll FP** and guide the person to press their finger **3 times** until accepted.
5. Press **ESC** to return the terminal to the home punch screen.
6. In the Web Console, click **Confirm Fingerprint Enrolled** (state transitions to `FINGERPRINT_ENROLLED`).

### Step 4: Controlled Verification Scan (Live Biometric Capture)
1. In the Web Console, click **Start Controlled Scan Window** (state transitions to `CONTROLLED_SCAN_PENDING`).
2. Check the live-connection indicator on this step — it must show connected before asking the person to scan; use the retry action if it shows disconnected.
3. Ask the person to scan their newly enrolled finger on the terminal sensor.
4. The Web Console detects the punch in realtime and displays the **scan detected** banner with the exact timestamp. If the live connection is down, enter the scan timestamp manually as a fallback.
5. Verify the scan timestamp and click **Confirm Controlled Scan** (state transitions to `CONTROLLED_SCAN_CONFIRMED`).

### Step 5: Mark Ready for Mapping (Browser)
1. Click **Mark Ready for Mapping**. State transitions to `READY_FOR_MAPPING`.

### Step 6: Activate VERIFIED Mapping (Admin Authority)
1. An **ADMIN** navigates to **Mappings** (`/mappings`).
2. Under **Create VERIFIED Mapping**, select the `READY_FOR_MAPPING` enrollment session.
3. Enter verification notes and click **Create VERIFIED Mapping**.
4. A confirmation step shows the person's name, terminal, and scan time (no raw IDs) — review it, then confirm.
5. The system creates the permanent temporal mapping (`[valid_from, valid_to = NULL]`), updates historical scan attribution, and retires the enrollment session (`RETIRED`).

---

## 5. CLI Terminal-Account Tooling (Emergency/Fallback Only — Never the Normal Workflow)

If the browser→Collector command path (`DeviceCommandBus`) is genuinely unavailable, use the offline CLI while pausing the listener container. This is an emergency procedure, not a routine alternative — it requires pausing live attendance ingestion:

```bash
# Pause Collector
docker compose stop listener

# Execute terminal account creation CLI
docker exec adms_zkteco_listener python -m app.enrollment_cli status --enrollment-id <ID>
docker exec adms_zkteco_listener python -m app.enrollment_cli create-terminal-account \
    --enrollment-id <ID> --display-name "<NAME>" --confirm-collector-paused

# Resume Collector
docker compose start listener
```

---

## 6. Post-Session Lock Down & Verification

### 6a. Normal Procedure (target end-state, post-Phase F)
1. If not already closed, an ADMIN closes the runtime write session from the System page (or lets it auto-expire — no action is required, it cannot be left open indefinitely).
2. **Verify Telemetry**: Collector is `LIVE` and `device_connected=true`; the new scan on the Attendance page is attributed to the correct person.
3. **Post-Session Backup** (§6c).

### 6b. Current Interim Procedure (use this today)
1. **Restore Write Lock**:
   ```bash
   cd /home/kanfullbuster/adms-server
   # Set API_WRITE_ENABLED=false in .env
   docker compose up -d api
   ```
2. **Verify Telemetry**:
   - Verify Collector is `LIVE` and `device_connected=true`.
   - Verify that the new scan on the Attendance page is attributed to the correct Human.
   - Verify that the write-disabled indicator displays on the dashboard.

### 6c. Post-Session Backup (both procedures)
```bash
docker exec adms_postgres pg_dump -U adms -d adms -Fc -f /tmp/adms_post_enroll_$(date +%Y%m%d_%H%M%S).dump
```
