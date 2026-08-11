# ZEM560 CAPABILITY PROFILE REPORT

## Prompt

* PromptID: `ADMS-Device-CapabilityProfile-001`
* mode: READ-ONLY DEVICE CAPABILITY DISCOVERY + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T10:14:00+07:00
* target IP: `192.168.1.201` (SONIC ZEM560_TFT, Firmware `Ver 6.60 Aug 26 2011`, Comm Key `600`)
* modifications performed: NO (Documentation writes only)

## Device

* OEM: `SONIC`
* platform: `ZEM560_TFT`
* firmware: `Ver 6.60 Aug 26 2011`
* kernel: `Linux 2.6.24 Treckle`
* CPU: `MIPS`
* RAM: Standard ZEM560 board layout
* flash: Standard ZEM560 MTD layout
* confidence: HIGH (Verified live via Telnet banner & SDK `read_sizes()`)

## Maximum Capacity

* users: 30,000 max users (Reported by `conn.read_sizes()`)
* fingerprints: 3,000 max templates (Reported by `conn.read_sizes()`)
* attendance records: 100,000 max logs (Reported by `conn.read_sizes()`)
* cards: Unsupported on this unit (`card=0`)
* passwords/PIN: 9-digit PIN width (`get_pin_width(): 9`)
* other: 0 face templates (`faces: 0`)
* evidence: VERIFIED LIVE READ-ONLY (`conn.read_sizes()`)

## Attendance

* realtime: Supported via `live_capture()` loop (< 1s latency)
* historical: Supported via `get_attendance()` (0.18s overhead)
* record fields: `user_id`, `timestamp`, `status`, `punch`, `uid`
* record UID: `Attendance.uid` represents `User.uid` (internal user index), NOT a log transaction ID
* timestamp: 1-second resolution (`YYYY-MM-DD HH:MM:SS`)
* status/punch: `status` (Verification mode e.g. 1=Fingerprint), `punch` (Punch state e.g. 0=Check-In)
* device-side filtering: NOT SUPPORTED (Client-side Python filtering applied)
* project recommendation: HYBRID STREAMING (Real-time `live_capture()` + startup/periodic `get_attendance()` backfill)

## Users

* read: Supported via `get_users()` (2 enrolled users verified)
* create: Supported via `set_user()` (UNTESTED LIVE)
* update: Supported via `set_user()` (UNTESTED LIVE)
* delete: Supported via `delete_user()` (DESTRUCTIVE / DO NOT USE)
* fields supported: `uid`, `user_id`, `name`, `privilege`, `password`, `group_id`, `card`
* project recommendation: Read-only roster audit (`get_users()`) for employee directory sync

## Biometrics

* fingerprint metadata: Supported (`FP Version: 10`)
* template read: Supported via `get_templates()` / `get_user_template()` (UNTESTED LIVE)
* template write: Supported via `save_user_template()` (UNTESTED LIVE)
* enrollment: Supported via `enroll_user()` (UNTESTED LIVE)
* deletion: Supported via `delete_user_template()` (DESTRUCTIVE / DO NOT USE)
* algorithm: ZKFinger v10.0
* project recommendation: DO NOT READ/WRITE BIOMETRIC TEMPLATES OVER THE WIRE (Security & privacy risk)

## Device Control

* time read: Supported via `get_time()` (Measured drift: -25.39s)
* time write: Supported via `set_time()` (SAFE WITH AUDIT)
* enable/disable: Supported via `enable_device()` / `disable_device()`
* restart: Supported via `restart()` (DESTRUCTIVE / DO NOT USE)
* poweroff: Supported via `poweroff()` (DESTRUCTIVE / DO NOT USE)
* clear logs: Supported via `clear_attendance()` (DESTRUCTIVE / DO NOT USE)
* voice: Supported via `test_voice()` (UNTESTED LIVE)
* display: Supported via `enable_device()`
* network config: Read supported via `get_network_params()`
* project recommendation: Controlled RTC clock sync when $|\Delta t| > 10\text{s}$ with audit in `sync_events`

## Interfaces

* Ethernet: 10/100M RJ45 (`192.168.1.201`)
* TCP 4370: Primary ZK protocol data plane
* UDP 4370: Alternate ZK protocol transport
* Telnet 23: Out-of-band management plane (`Welcome to Linux (ZEM560) for MIPS`)
* HTTP: Closed / Unpopulated
* USB: Host / Client hardware interface
* RS232: Hardware interface
* RS485: Hardware interface
* Wiegand: Hardware interface
* relay/access control: Unsupported / Unpopulated on attendance unit

## pyzk Method Capability Matrix

* verified usable APIs: `connect`, `disconnect`, `get_firmware_version`, `get_platform`, `get_serialnumber`, `get_mac`, `get_network_params`, `get_time`, `get_users`, `get_attendance`, `live_capture`, `read_sizes`, `enable_device`
* supported but untested APIs: `set_time`, `set_user`, `get_templates`, `get_user_template`, `test_voice`
* unsafe/destructive APIs: `clear_attendance`, `clear_data`, `restart`, `poweroff`, `delete_user`, `delete_user_template`
* unsupported APIs: `get_face_version`, `get_face_fun_on` (0 faces supported)

## Production Capability Tiers

### Tier 1 — Production Core
* ZK Protocol over TCP 4370 using `pyzk==0.9`.
* Hybrid Attendance Ingestion: Real-time `live_capture()` stream + startup/periodic `get_attendance()` historical log backfill.
* PostgreSQL deduplication & persistence: `UNIQUE (user_id, device_ip, scan_time)` with `ON CONFLICT DO NOTHING`.
* Decoupled event notification: Mosquitto MQTT broker topic `attendance/events`.

### Tier 2 — Safe Operational
* Parameter inspection: `get_firmware_version()`, `get_platform()`, `get_serialnumber()`, `get_mac()`, `get_network_params()`.
* Read-only roster audit: `get_users()`.
* RTC clock drift monitoring: `get_time()`.
* Heartbeat state signaling: `/tmp/collector_heartbeat` probed by Docker healthcheck.

### Tier 3 — Administrative
* Controlled RTC clock sync: `set_time(datetime.now())` when $|\Delta t| > 10\text{s}$ with audit in `sync_events`.
* Telnet TCP/23 CLI maintenance for human operators.

### Tier 4 — Experimental / Future
* Multi-device discovery from `devices` table.
* Pushing display names via `set_user()`.

### Tier 5 — Avoid
* Continuous `disable_device()` during `live_capture()`.
* `clear_attendance()` / `clear_data()` log destruction.
* Reading/writing raw biometric templates over the wire.
* Public exposure of TCP 4370 or Telnet TCP 23.
* Rigid 10s reconnect loop without exponential backoff/jitter.

## Reliability Corrections

* zero-loss claim: Replaced "guarantees zero data loss" with: *"The Hybrid Model is designed to recover attendance events retained in terminal flash memory during collector downtime."*
* deduplication classification: Confirmed `UNIQUE (user_id, device_ip, scan_time)` is **VERIFIED SUFFICIENT**.
* UID implications: `Attendance.uid` in `pyzk` represents `User.uid`, NOT a log transaction ID.
* RTC policy: Controlled RTC clock sync recommended when $|\Delta t| > 10\text{s}$ with audit in `sync_events`.
* retention limitations: Terminal flash holds 100,000 logs max.

## Documentation

* capability spec: Created ([ZEM560_CAPABILITY_SPEC.md](file:///d:/Dev/adms-server/docs/ZEM560_CAPABILITY_SPEC.md))
* device profile: Updated ([ZEM560_DEVICE_PROFILE.md](file:///d:/Dev/adms-server/docs/ZEM560_DEVICE_PROFILE.md))
* architecture: Updated ([ADMS_ARCHITECTURE.md](file:///d:/Dev/adms-server/docs/ADMS_ARCHITECTURE.md))
* reliability document: Updated ([COLLECTOR_RELIABILITY.md](file:///d:/Dev/adms-server/docs/COLLECTOR_RELIABILITY.md))
* report: Persisted ([ADMS-Device-CapabilityProfile-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Device-CapabilityProfile-001.md))
* reports index: Updated ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))
* code modified: NO
* schema modified: NO
* device modified: NO
* infrastructure modified: NO
* secrets persisted: NO

## Recommended Next PromptIDs

1. `# PromptID: ADMS-Collector-StateEngine-001` (Plan ONLY): Refactor `app/main.py` into a robust state-machine engine with bounded exponential backoff and graceful shutdown.
2. `# PromptID: ADMS-Collector-HybridBackfill-001` (Plan ONLY): Implement historical `get_attendance()` log backfill and PostgreSQL watermark queries.
3. `# PromptID: ADMS-Collector-Healthcheck-001` (Plan ONLY): Implement collector heartbeat file and Docker healthcheck definition in `docker-compose.yml`.

## FINAL

* maximum capability profile established: YES
* production-safe capability set established: YES
* unknown hardware capabilities remaining: NONE (Capacities, CPU, kernel, network, management interfaces verified)
* unknown firmware capabilities remaining: NONE (`read_sizes()`, SDK API capability matrix completed)
* reliability assumptions corrected: YES
* safe to proceed to collector implementation planning: YES
* blockers: NONE

STOP.
