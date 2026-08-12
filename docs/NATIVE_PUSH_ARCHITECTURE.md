# ADMS NATIVE PUSH ARCHITECTURE (EXPERIMENTAL / DEFERRED)

**Status: EXPERIMENTAL — DEFERRED** (2026-08-12/13, `ADMS-NativePush-Experimental-001`)

The ZEM560 terminal (`Ver 6.60 Aug 26 2011`, serial `3392113170057`) contains a
native push client library (`/mnt/mtdblock/lib/libhttppush.so`, linked at boot via
the `nand` startup script) and file-level push configuration
(`options.cfg`: `AuthServerEnabled=1`, `IclockSvrFun=1`, `AuthServerIP=192.168.1.248`,
`AuthServerPort=8000`). However, **outbound push traffic has NEVER been observed**
from this device — not during the 2026-08-11 read-only audit, not after terminal
UI configuration, not after a full device reboot.

**Production ingestion remains the polling Collector** (pyzk over TCP 4370, live
stream + backfill), which is LIVE/HEALTHY. Native Push is NOT required for Backend
Foundation acceptance (100% COMPLETE) and is not part of the current Frontend scope.

---

## 1. Why Native Push was explored

- Firmware libraries and configuration exist on the device (`libhttppush.so`,
  `AuthServer*` keys) → potential for realtime push instead of polling.
- The classic iclock protocol is well-documented by the community.

## 2. Experimental outcome

| Component | Result |
|---|---|
| Server-side listener (`app/native_push/`, stdlib HTTP, LAN-only) | Fully working (48 tests + live synthetic E2E) |
| Canonical ingestion reuse | PASS — `save_attendance_log()` shared; no second identity system |
| Dedupe | PASS — `UNIQUE(user_id, device_ip, scan_time)` contract |
| Security | ACCEPTABLE — LAN-only bind, source allowlist, serial validation, payload limits |
| Device transmission | **FAIL — zero traffic from `192.168.1.201` even after config + reboot** |

## 3. Architecture (as implemented, retained for future use)

```
ZKTeco (if it transmitted)
   │  HTTP Native Push (iclock protocol)
   ▼
ADMS Push Listener  (app/native_push/service.py)
   │  parse ATTLOG  (protocol.py)
   ▼
canonical attendance event
   ▼
save_attendance_log()          ← shared with polling Collector
   ├── device resolution
   ├── device_user resolution (ensure_device_user)
   ├── normalize_device_timestamp()   (Asia/Bangkok contract)
   ├── parse_time / determine_status  (HH:MM[:SS])
   ├── resolve_verified_employee_mapping()  (temporal resolver)
   ├── attendance_logs  (dedupe UNIQUE(user_id, device_ip, scan_time))
   └── MQTT publish (optional; default OFF while Collector live)
```

Push transport is **not** an identity authority. The VERIFIED Human↔Device mapping
remains the identity authority, identical to the polling path.

## 4. Protocol notes (classic iclock)

- `GET /iclock/cdata?SN=<serial>` → server replies OPTIONS text block
  (`GET OPTIONS FROM:`, `OpStamp=…|COMMAND=OPTIONS|Stamp=…`, `ErrorDelay=`, `Delay=`,
  `TransTimes=`, `TransInterval=`, `TransFlag=`, `Realtime=`, `Encrypt=`).
- `POST /iclock/cdata?SN=<serial>&table=ATTLOG&Stamp=&OpStamp=` → tab-separated rows
  `ATTLOG<TAB>pin<TAB>YYYY-MM-DD HH:MM:SS<TAB>checktype<TAB>verifycode<TAB>workcode` →
  server replies `OK` (non-200 replies cause the device to retain/retry).
- `GET /iclock/getrequest?SN=<serial>` → command polling; server replies `OK` when no
  commands are queued (experiment returns no commands).
- Sources: `fedotovaleksandr/iclockhelper` (Python), ZK Push C# sample (`ZKPush.cs`,
  newer v3.0.1 protocol — NOT used for ZEM560-era firmware). COMMUNITY-DOCUMENTED.
- ZEM560 UI note: the terminal "Webserver" menu controls the **embedded ZK Web Server**
  (`libweb.so`, `WEBPort=808`) — an admin web UI — and is **distinct** from the ADMS
  push client config which lives in `options.cfg`.

## 5. Security boundary (if ever re-enabled)

- LAN-only bind (e.g. `192.168.1.248:8000`), never public Internet
- Source-IP allowlist (device subnet or single device IP)
- Serial validation against expected device serial
- Body-size limit, malformed-payload rejection (device retries)
- No biometric template handling anywhere in the listener
- No secrets in logs or config

## 6. Deferred rationale

- Device does not transmit → no realtime benefit achievable on current hardware.
- Polling already provides <1s realtime latency (verified 0.10s event stream) plus
  robust backfill on reconnect.
- Keeping the experimental source + tests costs nothing and positions ADMS for a
  future terminal/firmware that actually supports push.

## 7. Reactivation procedure (future)

1. Verify device actually transmits (listener log shows `source=192.168.1.201`).
2. Re-add `native-push` service to `docker-compose.yml` (LAN-only bind, allowlist).
3. Build + deploy isolated listener; verify handshake + controlled scan E2E.
4. Verify dedupe against polling; only then consider hybrid/primary.
5. Re-run full test suite; create backup before any production adoption.

STOP.
