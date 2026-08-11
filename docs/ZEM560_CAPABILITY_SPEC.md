# SONIC / ZKTeco ZEM560_TFT Capability Specification

## Document Status

* **Status**: Canonical Device Capability Specification
* **Source PromptID**: `ADMS-Device-RemoteEnrollmentCapability-001`
* **Target Device Hardware**: SONIC (ZKTeco ZEM560_TFT Platform, MIPS CPU, Linux 2.6.24 Treckle, Firmware `Ver 6.60 Aug 26 2011`)
* **Verification Basis**: Verified live read-only SDK queries (`pyzk==0.9`), controlled remote enrollment test, Telnet CLI inspection, and protocol analysis.

---

## 1. Device Identity

* **OEM Brand**: SONIC (Physical terminal chassis branding)
* **Underlying Platform**: ZEM560_TFT
* **Firmware Release**: `Ver 6.60 Aug 26 2011`
* **Kernel**: Linux 2.6.24 Treckle
* **CPU Architecture**: MIPS (Verified via Telnet banner: `Welcome to Linux (ZEM560) for MIPS`)
* **Serial Number**: `3392113170057`
* **MAC Address**: `00:17:61:11:18:D9`

---

## 2. Verified Hardware & Resource Specification

| Property | Verified Value | Evidence Classification | Confidence |
| -------- | -------------- | ----------------------- | ---------- |
| **CPU Architecture** | MIPS (Ingenic/ZKTeco custom MIPS SoC) | VERIFIED LIVE READ-ONLY (Telnet Banner) | HIGH |
| **OS Kernel** | Linux 2.6.24 Treckle | VERIFIED LIVE READ-ONLY (Telnet Banner) | HIGH |
| **Network Interface** | Ethernet 10/100M RJ45 (`192.168.1.201`, Mask: `255.255.255.0`, GW: `192.168.1.1`) | VERIFIED LIVE READ-ONLY (SDK `get_network_params()`) | HIGH |
| **Management Port** | Telnet TCP/23 (Unencrypted Root Linux Shell) | VERIFIED LIVE READ-ONLY | HIGH |
| **ZK Protocol Port** | TCP / UDP 4370 (Comm Key: `600`) | VERIFIED LIVE READ-ONLY | HIGH |
| **HTTP Web Service** | Closed / Not Present (Port 80/8080 unpopulated) | VERIFIED LIVE READ-ONLY | HIGH |
| **Fingerprint Engine** | ZKFinger v10.0 (`FP Version: 10`) | VERIFIED LIVE READ-ONLY (SDK `get_fp_version()`) | HIGH |
| **PIN Width** | 9 digits | VERIFIED LIVE READ-ONLY (SDK `get_pin_width()`) | HIGH |

---

## 3. Capacity Specification

| Metric | Currently Enrolled / Used | Maximum Reported Capacity | Evidence / Source |
| ------ | ------------------------- | ------------------------- | ----------------- |
| **User Accounts** | 2 enrolled users | 30,000 max users | VERIFIED LIVE READ-ONLY (SDK `read_sizes()`) |
| **Fingerprint Templates** | 2 templates | 3,000 max templates | VERIFIED LIVE READ-ONLY (SDK `read_sizes()`) |
| **Attendance Records** | 6 stored logs | 100,000 max logs | VERIFIED LIVE READ-ONLY (SDK `read_sizes()`) |
| **Face Templates** | 0 | 0 (Unsupported by hardware) | VERIFIED LIVE READ-ONLY (SDK `read_sizes()`) |

---

## 4. Communication & Protocol Interfaces

1. **Management Plane — Telnet (TCP Port 23)**:
   - **Status**: Active (`Welcome to Linux (ZEM560) for MIPS`).
   - **Classification**: ADMIN ONLY / LEGACY MANAGEMENT.
   - **Usage**: Emergency system maintenance and low-level kernel diagnostics by human operators. Must be strictly isolated to trusted internal LAN.
2. **Application / Data Plane — ZK Protocol (TCP/UDP Port 4370)**:
   - **Status**: Active (Comm Key `600`).
   - **Classification**: PRIMARY PRODUCTION INTERFACE.
   - **Usage**: Real-time event streaming (`live_capture()`), historical backfill (`get_attendance()`), and parameter inspection (`pyzk==0.9`).

---

## 5. Attendance & Data Flow Capabilities

* **Real-time Event Streaming (`live_capture()`)**:
  - Pushes punch events immediately upon user scanning (< 1s latency).
  - Defaults to 10s socket timeout (`except timeout:`), yielding `None` cleanly to update heartbeat and allow non-blocking iteration.
  - Keeps terminal display and keypad **ENABLED**.
* **Historical Log Sync (`get_attendance()`)**:
  - Retrieves stored attendance logs from internal terminal flash memory buffer (0.18s overhead for small log sets; ~1-2s for large sets).
  - Executed cleanly **without requiring `disable_device()`**.
  - Returns logs in **Ascending Chronological Order**.
* **Record Structure**:
  - `user_id`: string (e.g. `'1'`, `'2'`).
  - `timestamp`: `datetime` object (`YYYY-MM-DD HH:MM:SS`), 1-second resolution.
  - `punch`: integer punch state (e.g. `0` = Check-In, `1` = Check-Out, `4` = Overtime In).
  - `status`: integer verification mode (e.g. `1` = Fingerprint).
  - `uid`: integer internal user index (matches `User.uid`), **NOT** a unique record transaction ID.
* **Filtering & Deduplication**:
  - ZK 4370 binary protocol does not support device-side timestamp filtering; filtering is performed **client-side in Python** (`scan_time >= MAX(scan_time) - 5 mins`).
  - PostgreSQL unique constraint `UNIQUE (user_id, device_ip, scan_time)` is **VERIFIED SUFFICIENT** for single-second timestamp scan separation.

---

## 6. Remote Enrollment UI Evaluation

* **Tested Command**: `conn.enroll_user(uid=1, temp_id=6, user_id='1')` (`CMD_STARTENROLL`).
* **Live Test Result**: **COMMAND ACKNOWLEDGED BUT UI NOT ACTIVATED / TIMEOUT**.
* **Finding**: The installed standalone firmware `Ver 6.60 Aug 26 2011` does not support socket-driven remote enrollment UI activation. Sending `CMD_STARTENROLL` times out without activating on-screen UI or optical sensor.
* **Project Classification**: **DO NOT USE / NOT RECOMMENDED FOR PRODUCTION**. Fingerprint enrollment must be performed locally on the terminal keypad.

---

## 7. pyzk Method Capability Matrix

| pyzk Method | Protocol Operation | Verified on Unit | Read / Write | Safe | ADMS Project Use |
| ----------- | ------------------ | ---------------- | ------------ | ---- | ---------------- |
| `connect()` | ZK socket handshake | YES (Key 600) | READ | YES | **PRIMARY** |
| `disconnect()` | Socket release | YES | READ | YES | **PRIMARY** |
| `get_firmware_version()` | Query firmware string | YES (`Ver 6.60 Aug 26 2011`) | READ | YES | **RECOMMENDED** |
| `get_platform()` | Query platform | YES (`ZEM560_TFT`) | READ | YES | **RECOMMENDED** |
| `get_serialnumber()` | Query serial | YES (`3392113170057`) | READ | YES | **RECOMMENDED** |
| `get_mac()` | Query MAC | YES (`00:17:61:11:18:D9`) | READ | YES | **RECOMMENDED** |
| `get_network_params()` | Query IP/Mask/GW | YES | READ | YES | **RECOMMENDED** |
| `get_time()` | Query RTC clock | YES | READ | YES | **RECOMMENDED** |
| `get_users()` | Query user roster | YES (2 users) | READ | YES | **RECOMMENDED** |
| `get_attendance()` | Query attendance logs | YES (6 logs) | READ | YES | **PRIMARY** |
| `live_capture()` | Stream punch events | YES | READ | YES | **PRIMARY** |
| `read_sizes()` | Query memory capacity | YES (30k/3k/100k) | READ | YES | **RECOMMENDED** |
| `set_time()` | Update RTC clock | SUPPORTED | WRITE | SAFE WITH AUDIT | **ADMIN ONLY** |
| `enable_device()` | Enable terminal input | YES | WRITE | YES | **PRIMARY** |
| `disable_device()` | Lock terminal input | YES | WRITE | RISK IN LIVE | **NOT RECOMMENDED IN LIVE** |
| `enroll_user()` | Trigger enrollment UI | UNLESS LOCAL | WRITE | TIMEOUT | **DO NOT USE** |
| `set_user()` | Create/Update user | SUPPORTED | WRITE | SAFE | **FUTURE** |
| `delete_user()` | Delete user | SUPPORTED | WRITE | DESTRUCTIVE | **DO NOT USE** |
| `clear_attendance()` | Purge log memory | SUPPORTED | WRITE | DESTRUCTIVE | **DO NOT USE** |
| `clear_data()` | Factory wipe terminal | SUPPORTED | WRITE | DESTRUCTIVE | **DO NOT USE** |
| `restart()` | Reboot terminal | SUPPORTED | WRITE | DESTRUCTIVE | **DO NOT USE** |
| `poweroff()` | Shutdown terminal | SUPPORTED | WRITE | DESTRUCTIVE | **DO NOT USE** |

---

## 8. Production Capability Tiers

### Tier 1 — Production Core
* ZK Protocol over TCP 4370 using `pyzk==0.9`.
* Hybrid Attendance Ingestion: Real-time `live_capture()` stream + startup/periodic `get_attendance()` historical log backfill.
* Database Deduplication & Persistence: PostgreSQL `UNIQUE (user_id, device_ip, scan_time)` with `ON CONFLICT DO NOTHING`.
* Decoupled Event Broadcast: Mosquitto MQTT broker topic `attendance/events`.

### Tier 2 — Safe Operational Features
* Parameter inspection: `get_firmware_version()`, `get_platform()`, `get_serialnumber()`, `get_mac()`, `get_network_params()`.
* Read-Only Roster Audit: `get_users()`.
* RTC clock drift monitoring: `get_time()`.
* Heartbeat state signaling: `/tmp/collector_heartbeat` probed by Docker healthcheck.

### Tier 3 — Administrative Features
* Controlled RTC clock sync: `set_time(datetime.now())` when $|\Delta t| > 10\text{s}$ with audit in `sync_events`.
* Telnet OS Maintenance: Out-of-band Telnet TCP/23 CLI access for kernel/system diagnostics.

### Tier 4 — Experimental / Future Features
* Multi-Device Dynamic Discovery: Polling device list from PostgreSQL `devices` table rather than single IP environment variable.
* User Roster Synchronization: Pushing user display names to terminal via `set_user()`.

### Tier 5 — Avoid
* **Remote Enrollment UI (`enroll_user()`)**: Times out without activating on-screen UI on standalone firmware `Ver 6.60`.
* **`disable_device()` during Live Capture**: Leaves biometric terminal keypad/display disabled during continuous streaming.
* **`clear_attendance()` / `clear_data()`**: Destroys terminal attendance logs in flash memory (prevents backfill recovery).
* **Biometric Template Read/Write over Wire**: Exposing or writing raw fingerprint template bytes (`get_templates()`, `save_user_template()`).
* **Public Exposure of TCP 4370 or Telnet TCP 23**: Unencrypted network interfaces must never be exposed to the public Internet.
* **Tight 10s Reconnect Loop**: Without exponential backoff/jitter, floods device during reboot.
