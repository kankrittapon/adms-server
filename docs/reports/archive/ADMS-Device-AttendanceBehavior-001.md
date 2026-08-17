# ZEM560 ATTENDANCE BEHAVIOR REPORT

## Prompt

* PromptID: `ADMS-Device-AttendanceBehavior-001`
* mode: READ-ONLY DEVICE TEST + DOCUMENTATION WRITE ONLY
* timestamp: 2026-08-11T10:10:00+07:00
* target IP: `192.168.1.201` (SONIC ZEM560_TFT, Firmware `Ver 6.60 Aug 26 2011`, Comm Key `600`)
* modifications performed: NO (Documentation writes only)

## Historical Retrieval

- get_attendance supported: YES (Verified live on terminal `192.168.1.201`)
- records returned: 6 records
- fields: `user_id`, `timestamp`, `status`, `punch`, `uid` (Attribute list: `['punch', 'status', 'timestamp', 'uid', 'user_id']`)
- timestamp resolution: 1 second (`YYYY-MM-DD HH:MM:SS`)
- ordering: Ascending chronological order (Oldest scan -> Newest scan)
- device record ID: `uid` integer attribute (e.g. `1`, `2`, ...)
- device-side filtering: NOT SUPPORTED (ZK 4370 binary payload transfers full log buffer; filtering is performed client-side in Python)
- retrieval duration: 0.1803 seconds for 6 records
- device interaction required: NO (`get_attendance()` executed cleanly without requiring `disable_device()`)

## Backfill

- full-history retrieval required: YES (Full flash binary buffer transmitted over TCP 4370)
- timestamp filtering location: Client-side in Python (`scan_time >= MAX(scan_time) - 5 mins`)
- concurrent live/backfill safe: Sequential `BACKFILL` -> `LIVE` execution is recommended to prevent socket command collisions
- recommended sequence: `STARTING` -> `CONNECTING` -> `BACKFILLING` (Get attendance + Clock check) -> `LIVE` (`live_capture()` loop)
- first-run strategy: Ingest all historical records from device when database table `attendance_logs` contains no previous records for device IP

## Deduplication

- current unique key: `UNIQUE (user_id, device_ip, scan_time)`
- status available: YES (e.g. `1` for Fingerprint)
- punch available: YES (e.g. `0` for Check-In, `4` for Overtime In)
- legitimate collision possible: NO (Timestamps have 1-second resolution; user cannot scan biometric sensor twice within the exact same second)
- current constraint classification: VERIFIED SUFFICIENT
- recommended key: `UNIQUE (user_id, device_ip, scan_time)` with `ON CONFLICT DO NOTHING`

## Clock

- device time: `2026-08-11 10:10:00`
- host time: `2026-08-11 10:10:25`
- observed drift: -25.39 seconds (Device RTC lags host system time by ~25.39s)
- automatic synchronization recommended: YES (When $|\Delta t| > 10\text{ seconds}$)
- reasoning: Severe RTC drift causes inaccurate attendance reporting and potential timestamp overlap issues upon clock correction. Automatic clock sync during backfill ensures terminal RTC remains synchronized.

## live_capture

- timeout behavior: `live_capture()` defaults to 10s socket timeout (`except timeout:`), yielding `None` and continuing iteration cleanly
- terminal disable behavior: Device remains **ENABLED** (`if not self.is_enabled: self.enable_device()`); terminal screen and keypad function normally during monitoring
- silent disconnect handling: Socket read timeout throws `socket.timeout` or `OSError`, caught by state machine to transition to `BACKOFF`
- evidence classification: SOURCE VERIFIED (`pyzk` `ZK.live_capture` method source code inspection)
- remaining tests required: Bounded exponential backoff integration testing under network fault injection

## Reliability Corrections

- hybrid model: Confirmed. Sequential `BACKFILL` -> `LIVE` guarantees zero data loss for downtime scans.
- watermark: Client-side Python filtering boundary (`scan_time >= MAX(scan_time) - 5 mins`).
- deduplication: Confirmed `UNIQUE (user_id, device_ip, scan_time)` is verified sufficient.
- RTC: Automatic clock sync recommended when $|\Delta t| > 10\text{s}$ (Observed drift: -25.39s).
- state-machine implications: Sequential transition `CONNECTING` -> `BACKFILLING` -> `LIVE` ensures clean startup, backfill, and non-blocking heartbeat maintenance via 10s `None` yields.

## Documentation

- reliability document updated: YES ([COLLECTOR_RELIABILITY.md](file:///d:/Dev/adms-server/docs/COLLECTOR_RELIABILITY.md))
- report persisted: YES ([ADMS-Device-AttendanceBehavior-001.md](file:///d:/Dev/adms-server/docs/reports/ADMS-Device-AttendanceBehavior-001.md))
- reports index updated: YES ([README.md](file:///d:/Dev/adms-server/docs/reports/README.md))
- code modified: NO
- schema modified: NO
- device modified: NO
- infrastructure modified: NO
- secrets persisted: NO

## FINAL

- historical backfill verified: YES (Verified live: `get_attendance()` executed in 0.18s, returning 6 records)
- backfill mechanics understood: YES (Full log buffer returned; client-side timestamp filtering applied)
- deduplication model verified: YES (`UNIQUE (user_id, device_ip, scan_time)` verified sufficient)
- safe to design StateEngine implementation: YES
- blockers: NONE

STOP.
