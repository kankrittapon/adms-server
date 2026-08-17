# NATIVE ADMS PUSH VERIFICATION REPORT

## Prompt

* PromptID: `ADMS-Device-NativePushVerification-001`
* mode: CONTROLLED READ-ONLY / NON-DESTRUCTIVE PROTOCOL VERIFICATION + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T10:49:00+07:00
* target host: `192.168.1.201` (Telnet TCP/23, ZK Protocol TCP/4370, Embedded HTTP TCP/80)
* modifications performed: NO (Read-only protocol & filesystem inspection)

---

## Configuration Audit

- push enabled: `IclockSvrFun=1`, `AuthServerEnabled=1`
- destination configured: `AuthServerIP=192.168.1.248`
- destination port: `AuthServerPort=8000`
- relevant protocol settings: `AuthServerCheckMode=0`, `~AuthServer=0`, `AuthFromHttpServer`
- secrets exposed: NO (All passwords, Comm Keys, and security secrets redacted)

---

## Firmware Implementation Evidence

- push library: `/mnt/mtdblock/lib/libhttppush.so` present in filesystem.
- main binary integration: Linked via `nand` startup script (`ln -s $DEST/lib/libhttppush.so /lib/libhttppush.so`).
- protocol strings: Strings present in `libhttppush.so` include `AuthFromHttpServer`, `pstrAuthType`, `call_main_update_data`, `pushsdk_cnt_log_by_time`, `pushsdk_options`, `pushsdk_clear_data`.
- expected endpoints: Proprietary ZK Push HTTP endpoints (`/iclock/cdata`, `/iclock/getrequest`).
- implementation confidence: HIGH (Firmware binary implementation present)

---

## Embedded HTTP Server Inspection

- server present: YES (`ZK Web Server`)
- listening: YES
- port: TCP Port 80 (Redirects to `/csl/login`)
- purpose: On-device administrative web management UI.
- live verified: VERIFIED (`HTTP/1.1 200 OK`, `Server: ZK Web Server`, `Set-Cookie: SessionID=...`)

---

## Outbound Push Observation

- connection attempt observed: NO (No active TCP connection established to `192.168.1.248:8000` in `/proc/net/tcp` socket table)
- HTTP request observed: NOT OBSERVED (No native Push receiver currently running on `192.168.1.248:8000`)
- method: UNVERIFIED
- path: UNVERIFIED
- destination: `192.168.1.248:8000` (Configured in `options.cfg`)
- payload classification: UNVERIFIED
- retry behavior: UNVERIFIED

---

## Protocol Capabilities Matrix

| Capability | Firmware Evidence | Live Observed | End-to-End Verified |
| ---------- | ----------------- | ------------- | ------------------- |
| **Registration / Handshake** | `AuthFromHttpServer` in `libhttppush.so` | NO | NOT VERIFIED |
| **Heartbeat / Ping** | `pushsdk_cnt_log_by_time` in `libhttppush.so` | NO | NOT VERIFIED |
| **Attendance Push** | `call_main_update_data` in `libhttppush.so` | NO | NOT VERIFIED |
| **Command Polling** | `pipe_write_to_parent_cmd` in `libhttppush.so` | NO | NOT VERIFIED |
| **User Roster Sync** | `pushsdk_options` in `libhttppush.so` | NO | NOT VERIFIED |

---

## Architecture Comparison

- **Python Collector (`pyzk==0.9` over TCP 4370)**:
  - REALTIME LATENCY: $< 1.0\text{s}$ via `live_capture()`.
  - HISTORICAL BACKFILL: Robust startup/reconnect `get_attendance()` log recovery.
  - RELIABILITY: Production-grade state engine FSM (`STARTING` $\to$ `CONNECTING` $\to$ `BACKFILLING` $\to$ `LIVE`).
  - STATUS: Fully implemented, tested, and verified live.
- **Native ADMS Push**:
  - REALTIME LATENCY: Unknown (Depends on Push client post interval).
  - HISTORICAL BACKFILL: Unverified. Potential scan loss if Push server is down during transmission.
  - RELIABILITY: Unverified end-to-end.
  - STATUS: Firmware evidence present; end-to-end functionality **NOT VERIFIED**.
- **Recommended Direction**:
  - Retain the **Python Collector Architecture** as the primary authoritative ingestion engine.
  - Do NOT replace the Python Collector with Native Push.

---

## Reliability & Outage Recovery

- push outage recovery: UNVERIFIED
- historical resend: UNVERIFIED
- ZK backfill still useful: **CRITICAL**. Python collector `get_attendance()` backfill guarantees recovery of offline terminal scans.
- unknowns: Whether `libhttppush.so` retries unacknowledged HTTP POST requests after server downtime.

---

## Security Analysis

- transport: Plaintext HTTP (`http://192.168.1.248:8000`)
- authentication: Unencrypted session header
- public exposure recommended: **STRICTLY NO**. Legacy ADMS HTTP push endpoints must never be published to the public Internet.
- preferred network boundary: Isolated private LAN / Docker-internal network / Tailscale.

---

## Documentation Corrections

- ADMS Push previous classification: `FIRMWARE IMPLEMENTATION EVIDENCE — STRONG` / `CONFIGURED — YES` / `END-TO-END FUNCTIONALITY — NOT VERIFIED`.
- corrected classification: Native Push firmware libraries exist (`libhttppush.so`), but end-to-end Push transmission is **NOT VERIFIED**. Python collector over TCP 4370 remains the primary production architecture.
- Remote Enrollment wording corrected: `CMD_STARTENROLL` sent over TCP 4370; timed out after 60s without on-screen UI activation or event response packets from standalone firmware `Ver 6.60`.

---

## Proposed Next PromptID

Recommended Next PromptID:
- `# PromptID: ADMS-Collector-Healthcheck-001` (Plan ONLY): Design Docker healthcheck definition and application heartbeat state file (`/tmp/collector_heartbeat`) for `adms_zkteco_listener`.

---

## FINAL

- native Push implementation present: YES (`libhttppush.so` present in `/mnt/mtdblock/lib/`)
- outbound Push attempt verified: NO (No active socket connection to `192.168.1.248:8000`)
- attendance Push end-to-end verified: NO
- suitable to replace Python collector: NO (Python collector remains the authoritative ingestion path)
- hybrid architecture worth considering: YES (Future auxiliary evaluation only)
- device modified: NO
- server modified: NO
- blockers: NONE

STOP.
