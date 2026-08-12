"""
ADMS — Experimental ZKTeco Native Push Listener (EXPERIMENTAL).

PromptID: ADMS-NativePush-Experimental-001
Status: EXPERIMENTAL SIDE-TRACK — NOT the production ingestion path.

This package implements an isolated LAN-only HTTP listener for the ZKTeco
classic iclock push protocol (/iclock/cdata, /iclock/getrequest, ...).

Design invariants:
  - Push transport is NEVER an identity authority.
  - All attendance payloads are converted into canonical pyzk-like attendance
    objects and persisted through app.db.save_attendance_log(), which reuses:
      device resolution, device_user resolution, normalize_device_timestamp()
      (Asia/Bangkok), parse_time()/determine_status(), the temporal
      resolve_verified_employee_mapping(), and the UNIQUE(user_id, device_ip,
      scan_time) dedupe contract.
  - No Human creation, no automatic mapping, no fingerprint/template handling,
    no biometric payload logging.
  - LAN-only + source-IP allowlist + serial logging. Never public Internet.
"""
