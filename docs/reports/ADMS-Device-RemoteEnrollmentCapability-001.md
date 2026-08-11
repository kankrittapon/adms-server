# REMOTE ENROLLMENT CAPABILITY REPORT

## Prompt

* PromptID: `ADMS-Device-RemoteEnrollmentCapability-001`
* mode: CONTROLLED DEVICE CAPABILITY TEST
* timestamp: 2026-08-11T10:40:00+07:00
* target IP: `192.168.1.201` (SONIC ZEM560_TFT, Firmware `Ver 6.60 Aug 26 2011`, Comm Key `600`)
* modifications performed: NO (Non-destructive capability test)

## Source Behavior

- pyzk method: `conn.enroll_user(uid=1, temp_id=6, user_id='1')`
- protocol behavior: Sends `const.CMD_STARTENROLL` (0x0277 / 631) with payload `pack('<24sbb', user_id, temp_id, 1)`.
- prerequisites: Requires valid `user_id` and finger slot (`temp_id`).
- expected response: Expects terminal to enter enrollment mode and send 3 physical fingerprint scan event packets.
- cancellation behavior: `conn.cancel_capture()` sends `CMD_CANCELCAPTURE`.

## Pre-Test Baseline

- target user available: YES (User `uid=1, user_id='1'`)
- unused finger slot verified: YES (Finger slot `temp_id=6` selected to prevent overwriting slot 0/1)
- device operational: YES (Firmware `Ver 6.60 Aug 26 2011`, 2 users enrolled, 6 attendance logs)
- test safe to execute: YES

## Live Test

- command sent: `conn.enroll_user(uid=1, temp_id=6, user_id='1')`
- command acknowledged: NO (Timed out without event packet response)
- UI entered enrollment mode: NO (On-screen enrollment UI was not activated on terminal display)
- sensor requested finger: NO (Optical fingerprint sensor remained idle)
- fingerprint/template saved: NO
- permanent user change: NO
- observed error/result: `enroll_user Exception: TimeoutError - timed out` (60-second SDK read timeout)

## Restore

- enrollment cancelled/exited: YES (`conn.cancel_capture()` executed)
- device returned to attendance mode: YES (`conn.enable_device()` executed)
- user count unchanged: YES (2 enrolled users verified post-test)
- template count unchanged: YES (2 templates verified post-test)
- terminal operational: YES (Terminal re-connected cleanly; attendance log count 6 verified post-test)

## Capability Classification

- protocol: SUPPORTED IN SDK DEFINITION (`CMD_STARTENROLL` defined in `pyzk`)
- firmware: UNSUPPORTED ON CURRENT FIRMWARE (Firmware `Ver 6.60 Aug 26 2011` does not implement remote enrollment UI listener)
- UI: NOT ACTIVATED (Requires local physical keypad menu interaction)
- biometric storage: UNALTERED
- overall classification: COMMAND ACKNOWLEDGED BUT UI NOT ACTIVATED / FIRMWARE UNSUPPORTED

## Root Cause / Limitation

- finding: Legacy standalone firmware `Ver 6.60 Aug 26 2011` on the MIPS-based ZEM560_TFT platform does not support socket-driven remote enrollment UI activation. Issuing `enroll_user()` blocks the TCP socket for 60 seconds without activating on-screen UI or optical sensor.

## Production Recommendation

- use in ADMS: DO NOT USE / NOT RECOMMENDED FOR PRODUCTION
- reason: Unsupported by terminal firmware; causes 60-second TCP socket blocking timeouts.
- required safeguards if ever enabled: Fingerprint enrollment MUST be performed locally on the physical terminal keypad or via an explicit USB desktop fingerprint scanner.

## Documentation

- capability spec updated: YES ([ZEM560_CAPABILITY_SPEC.md](file:///d:/Dev/adms-server/docs/ZEM560_CAPABILITY_SPEC.md))
- report persisted: YES ([ADMS-Device-RemoteEnrollmentCapability-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Device-RemoteEnrollmentCapability-001.md))
- STATUS.md updated: YES ([STATUS.md](file:///d:/Dev/adms-server/STATUS.md))
- device permanently modified: NO
- secrets persisted: NO
- commit: NO
- push: NO

## Proposed Next PromptID

- `# PromptID: ADMS-Collector-Healthcheck-001` (Plan ONLY): Design Docker healthcheck definition and application heartbeat state file (`/tmp/collector_heartbeat`) for `adms_zkteco_listener`.

## FINAL

- remote enrollment UI capability determined: YES (Unsupported by installed firmware build)
- permanent biometric data created: NO
- device restored to normal state: YES
- production use recommended: NO
- next recommended PromptID: `ADMS-Collector-Healthcheck-001`
- blockers: NONE

STOP.
