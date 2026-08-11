# ZKTeco ZEM560 Device Profile

## Verification Status

* **Status**: VERIFIED LIVE HARDWARE PROFILE
* **OEM Brand**: SONIC
* **Underlying Platform**: ZEM560_TFT
* **Verification Timestamp**: 2026-08-11T10:14:00+07:00
* **Source PromptID**: `ADMS-Device-CapabilityProfile-001`
* **Canonical Specification**: [ZEM560_CAPABILITY_SPEC.md](file:///d:/Dev/adms-server/docs/ZEM560_CAPABILITY_SPEC.md)
* **Primary Management Protocol**: Telnet over TCP Port 23
* **Primary Collector Protocol**: ZK Binary Protocol over TCP/UDP Port 4370

---

## Verified Device Specification

| Property | Verified Value | Evidence / Source | Classification | Confidence |
| -------- | -------------- | ----------------- | -------------- | ---------- |
| **OEM Brand** | SONIC | Physical terminal branding | VERIFIED LIVE DEVICE | HIGH |
| **Underlying Platform** | ZEM560 / ZEM560_TFT | Telnet banner & `conn.get_platform()` | VERIFIED LIVE DEVICE | HIGH |
| **CPU Architecture** | MIPS | Telnet Banner: `Welcome to Linux (ZEM560) for MIPS` | VERIFIED LIVE DEVICE | HIGH |
| **OS / Kernel** | Linux 2.6.24 Treckle | Telnet Banner: `Kernel 2.6.24 Treckle on an MIPS` | VERIFIED LIVE DEVICE | HIGH |
| **Firmware Version** | `Ver 6.60 Aug 26 2011` | SDK Query: `conn.get_firmware_version()` | VERIFIED LIVE DEVICE | HIGH |
| **Serial Number** | `3392113170057` | SDK Query: `conn.get_serialnumber()` | VERIFIED LIVE DEVICE | HIGH |
| **MAC Address** | `00:17:61:11:18:D9` | SDK Query: `conn.get_mac()` | VERIFIED LIVE DEVICE | HIGH |
| **Fingerprint Algorithm** | ZKFinger v10.0 (`FP Version: 10`) | SDK Query: `conn.get_fp_version()` | VERIFIED LIVE DEVICE | HIGH |
| **PIN Width** | 9 digits | SDK Query: `conn.get_pin_width()` | VERIFIED LIVE DEVICE | HIGH |
| **Enrolled User Count** | 2 users | SDK Query: `len(conn.get_users())` | VERIFIED LIVE DEVICE | HIGH |
| **Attendance Log Count** | 6 records | SDK Query: `len(conn.get_attendance())` | VERIFIED LIVE DEVICE | HIGH |
| **User Capacity** | 30,000 max users | SDK Query: `conn.read_sizes()` (`users_cap: 30000`) | VERIFIED LIVE DEVICE | HIGH |
| **Fingerprint Capacity** | 3,000 max templates | SDK Query: `conn.read_sizes()` (`fingers_cap: 3000`) | VERIFIED LIVE DEVICE | HIGH |
| **Attendance Log Capacity** | 100,000 max logs | SDK Query: `conn.read_sizes()` (`rec_cap: 100000`) | VERIFIED LIVE DEVICE | HIGH |
| **Ethernet Interface** | 10/100M RJ45 (`192.168.1.201`) | Verified live TCP 23 & 4370 reachability | VERIFIED LIVE DEVICE | HIGH |
| **Management Port** | Telnet TCP/23 | Verified live TCP 23 response | VERIFIED LIVE DEVICE | HIGH |
| **ZK Protocol Port** | TCP/UDP 4370 | Verified live TCP 4370 response | VERIFIED LIVE DEVICE | HIGH |
| **HTTP Service** | Not Present / Unverified | Port 80/8080 closed | VERIFIED LIVE DEVICE | HIGH |
| **ADMS Push Capability** | Unproven for Current Firmware | Stock Ver 6.60 standalone firmware does not run native push daemon | VERIFIED LIVE DEVICE | HIGH |
| **Comm Key Support** | YES (`ZK_DEVICE_PASSWORD=600`) | Verified live SDK authentication with key `600` | VERIFIED LIVE DEVICE | HIGH |

---

## Communication & Management Interfaces

### 1. Management Plane — Telnet (TCP Port 23)
- **Protocol**: Unencrypted Telnet CLI
- **System Banner**: `Welcome to Linux (ZEM560) for MIPS` / `Kernel 2.6.24 Treckle on an MIPS`
- **Role**: System maintenance, low-level OS diagnostic inspection, and firmware status.
- **Security Notice**: Telnet is a legacy plaintext management protocol. Access to TCP port 23 MUST be strictly restricted to trusted administrative LAN/VPN networks and NEVER published to the public Internet. Credentials must never be embedded in scripts, source code, or public reports.

### 2. Application / Data Plane — ZK Protocol (TCP Port 4370)
- **Protocol**: ZKTeco binary protocol over TCP/UDP port 4370.
- **SDK Driver**: `pyzk==0.9` (`from zk import ZK`).
- **Comm Key**: `600` (Authenticated successfully).
- **Supported Operational Modes**:
  1. **Real-time Event Streaming**: `live_capture()` loop receives instant attendance punch events.
  2. **Historical Log Sync / Backfill**: `get_attendance()` fetches all stored logs from flash memory.
  3. **Clock Synchronization**: `set_time(datetime.now())` updates device RTC clock.

---

## ADMS Outbound Push Capability Evaluation

- **Status**: VERIFIED UNSUPPORTED FOR CURRENT FIRMWARE.
- **Evidence**: The terminal runs standalone firmware `Ver 6.60 Aug 26 2011`. No HTTP server or outbound HTTP push client is active on this firmware build.
- **Conclusion**: Native outbound HTTP ADMS Push is not supported by the currently installed firmware. The ZK protocol on TCP port 4370 via a dedicated Python collector is the verified, operational data collection mechanism for this terminal.

---

## Baseline Corrections (Documented vs Live)

| Property | Previous Documented Assumption | Verified Live Evidence | Correction Summary |
| -------- | ------------------------------ | ---------------------- | ------------------ |
| OEM Brand | Unspecified / Generic ZKTeco | `SONIC` | Device carries OEM brand `SONIC`. |
| CPU Architecture | ARM9 / 32-bit RISC | MIPS | Live Telnet banner explicitly identifies CPU as **MIPS**. |
| Kernel | Linux 2.6.x | Linux 2.6.24 Treckle | Exact kernel version identified as **Linux 2.6.24 Treckle**. |
| Firmware | Unverified | `Ver 6.60 Aug 26 2011` | Exact firmware release version verified via SDK. |
| Serial Number | Unverified | `3392113170057` | Device serial number verified. |
| MAC Address | Unverified | `00:17:61:11:18:D9` | Physical MAC address verified. |
| Reported Capacities | 3,000 / 3,000 / 100,000 | 30,000 Users / 3,000 Templates / 100,000 Logs | Max user capacity reported directly as 30,000 by firmware `read_sizes()`. |
| Management Protocol | Unspecified | Telnet TCP/23 | Management plane identified on TCP 23. |
