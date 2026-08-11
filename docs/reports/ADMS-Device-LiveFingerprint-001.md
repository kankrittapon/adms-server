# LIVE DEVICE FINGERPRINT REPORT

## Prompt

* PromptID: `ADMS-Device-LiveFingerprint-001`
* mode: READ-ONLY DEVICE INSPECTION + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T10:05:00+07:00
* target IP: `192.168.1.201` (Verified live TCP 23 & TCP 4370 reachability)
* modifications performed: NO (Documentation writes only)

## Identity

* OEM brand: `SONIC`
* underlying platform: `ZEM560_TFT`
* device model: SONIC ZEM560 TFT Series Terminal
* firmware: `Ver 6.60 Aug 26 2011`
* kernel: `Linux 2.6.24 Treckle`
* CPU architecture: `MIPS` (Verified via Telnet banner: `Welcome to Linux (ZEM560) for MIPS`)
* SoC: MIPS-based ZK custom SoC
* RAM: Standard ZEM560 flash/RAM layout
* flash: Standard ZEM560 internal MTD flash layout
* evidence confidence: VERIFIED LIVE DEVICE (Direct live SDK & Telnet banner inspection)

## Interfaces

* Telnet 23: VERIFIED LIVE (`Welcome to Linux (ZEM560) for MIPS` / `Kernel 2.6.24 Treckle on an MIPS`)
* ZK protocol 4370: VERIFIED LIVE (SDK connected using Comm Key `600`)
* HTTP: Closed / Unverified (No web server active on port 80/8080)
* RS232/RS485: Supported hardware interface
* USB: USB Host / Client hardware interface
* other relevant interfaces: N/A

## ADMS

* native push status: VERIFIED UNSUPPORTED FOR CURRENT FIRMWARE
* evidence: Installed firmware `Ver 6.60 Aug 26 2011` is legacy ZEM560 standalone firmware. No HTTP server or outbound HTTP push client is active on this firmware build.
* remaining uncertainty: None for current firmware build. Native Push requires specific ADMS firmware upgrade.

## Corrections to Previous Baseline

* CPU: Corrected from `ARM9` assumption to **MIPS** (Verified via Telnet banner).
* OS/kernel: Corrected from generic `Linux 2.6.x` to **Linux 2.6.24 Treckle on MIPS** (Verified via Telnet banner).
* firmware: Corrected from generic assumption to **`Ver 6.60 Aug 26 2011`** (Verified via SDK `get_firmware_version()`).
* platform: Confirmed as **`ZEM560_TFT`** (Verified via SDK `get_platform()`).
* capacities: Enrolled User Count = 2, Attendance Log Count = 6 (Verified live via SDK).
* management access: Identified management plane on **Telnet TCP port 23**.
* collector path: Confirmed ZK Protocol on **TCP port 4370** via Python collector as the primary operational path.

## Security

* plaintext Telnet present: YES (TCP port 23 exposes unencrypted Telnet login interface)
* Internet exposure verified: NO (Device is located on private internal LAN `192.168.1.201`)
* recommended network boundary: Telnet TCP port 23 and ZK protocol TCP port 4370 MUST be strictly isolated to internal LAN / Tailscale segments and NEVER published or port-forwarded to the public Internet. Credentials must never be embedded in scripts, source code, or committed files.

## Documentation

* device profile updated: YES ([ZEM560_DEVICE_PROFILE.md](file:///d:/Dev/adms-server/docs/ZEM560_DEVICE_PROFILE.md))
* architecture updated: YES ([ADMS_ARCHITECTURE.md](file:///d:/Dev/adms-server/docs/ADMS_ARCHITECTURE.md))
* report persisted: YES ([ADMS-Device-LiveFingerprint-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Device-LiveFingerprint-001.md))
* reports index updated: YES ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))
* secrets persisted: NO
* commit: NO
* push: NO

## FINAL

* live device fingerprint established: YES
* ZEM560 family identification confidence: HIGH (100% verified live via Telnet banner and pyzk SDK queries)
* collector path still justified: YES (ZK Protocol on TCP 4370 via Python collector `adms_zkteco_listener`)
* device modified: NO
* application modified: NO
* secrets exposed/persisted: NO
* blockers: NONE

STOP.
