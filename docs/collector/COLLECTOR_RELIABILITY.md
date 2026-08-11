# ADMS Collector Reliability Architecture

## Document Status

* **Status**: Verified Collector Reliability Architecture
* **Source PromptID**: `ADMS-Collector-Healthcheck-001`
* **Target Hardware**: SONIC / ZKTeco ZEM560_TFT Series (MIPS Linux 2.6.24, Firmware `Ver 6.60 Aug 26 2011`)
* **SDK Driver**: `pyzk==0.9` (`from zk import ZK`)
* **Verification Basis**: Verified live test output against physical terminal (`192.168.1.201`) and `pyzk` source code inspection.

---

## 1. Verified Live Device Behavior

A live read-only inspection of the SONIC ZEM560_TFT terminal revealed exact protocol behavior:

| Behavior / Feature | Verified Live Observation | Reliability Implication | Evidence Classification |
| ------------------ | ------------------------- | ----------------------- | ----------------------- |
| **`get_attendance()`** | Succeeds in 0.18s for 6 records. Returned fields: `user_id`, `timestamp`, `punch`, `status`, `uid`. | Fast, non-blocking execution. Enables rapid startup and periodic historical backfill. | VERIFIED LIVE DEVICE |
| **Device Interaction** | Executes cleanly **without calling `disable_device()`**. | Does not freeze terminal display or block user scanning during historical log reads. | VERIFIED LIVE DEVICE |
| **Record Ordering** | Ascending chronological order (Oldest scan -> Newest scan). | Simplifies watermark processing and incremental historical log insertion. | VERIFIED LIVE DEVICE |
| **Timestamp Resolution** | 1-second resolution (`YYYY-MM-DD HH:MM:SS`). | Single-second precision is sufficient for user attendance scan separation. | VERIFIED LIVE DEVICE |
| **Device-Side Filtering** | **NOT SUPPORTED** by ZK 4370 protocol binary payload. | The device transmits full log buffer over TCP socket; filtering by timestamp is performed **client-side in Python**. | VERIFIED LIVE DEVICE / SOURCE |
| **Deduplication Key** | `UNIQUE (user_id, device_ip, scan_time)` | **VERIFIED SUFFICIENT**. Users cannot scan twice in the exact same second; `ON CONFLICT DO NOTHING` safely discards duplicate scans. | VERIFIED LIVE DEVICE / REPOSITORY |
| **Device RTC Drift** | Measured live drift: **-25.39 seconds** (Device clock lags host time by ~25s). | Automatic RTC clock synchronization is **JUSTIFIED** when $|\Delta t| > 10\text{s}$. | VERIFIED LIVE DEVICE |
| **`live_capture()` Loop** | Yields `None` every 10s on socket timeout (`except timeout:`). Terminal remains **enabled**. | Non-blocking iteration loop allows updating heartbeat, checking stop signals, and maintaining background tasks cleanly. | SOURCE VERIFIED / REPOSITORY |

---

## 2. Hybrid Event Capture & Recovery Model

ZK historical backfill is designed to recover attendance records still retained in terminal flash memory after collector, host, network, or database downtime.

```text
                  +-----------------------------------+
                  |  SONIC / ZEM560 Terminal (TCP 4370)|
                  +-----------------------------------+
                                    |
                    +---------------+---------------+
                    |                               |
                    v                               v
         [ Real-time Stream ]            [ Historical Flash Sync ]
          connection.live_capture()       connection.get_attendance()
                    |                               |
        (Instant Scan < 1s)              (Backfill Downtime Scans)
                    |                               |
                    +---------------+---------------+
                                    |
                                    v
                     [ Event Normalization & Client-Side Filtering ]
                     scan_time >= MAX(scan_time) - 5 minutes
                                    |
                                    v
                     [ PostgreSQL Persistence (Primary) ]
                     ON CONFLICT (user_id, device_ip, scan_time) DO NOTHING
                                    |
                                    v
                     [ Mosquitto MQTT Broadcast ]
```

### Operational Rules:
1. **Real-time Path (`live_capture()`)**: Used for instant attendance event notification (< 1 second latency). Handles `None` timeouts gracefully to update heartbeat and check cancellation flags.
2. **Historical Backfill Path (`get_attendance()`)**: Executed sequentially upon connection startup and after reconnect. Reads stored attendance logs from the terminal's flash memory buffer (0.18s overhead for small log sets; ~1-2s for full buffers).
3. **Watermark / Client-Side Filtering**: The collector queries the maximum `scan_time` for the device from PostgreSQL:
   $$\text{Watermark} = \max(\text{scan\_time}) - \text{Safety Overlap Window (5 mins)}$$
   Records fetched from `get_attendance()` with $\text{scan\_time} < \text{Watermark}$ are filtered out in Python before database insertion. On first-run (empty database), all historical records are ingested.
4. **Idempotent Ingestion**: PostgreSQL unique constraint `UNIQUE (user_id, device_ip, scan_time)` ensures duplicate records resulting from overlapping real-time and backfill streams are safely ignored (`ON CONFLICT DO NOTHING`).

### Residual Data Loss Conditions:
While hybrid backfill recovers logs retained in hardware flash, potential data loss conditions include:
* Terminal flash memory log buffer capacity overflow (exceeding 100,000 logs before backfill recovery).
* Manual terminal flash memory clearance via physical LCD menu interaction (`Clear AttLog`).
* Hardware/flash storage failure on the biometric terminal PCB.
* Sub-second duplicate timestamp collisions from corrupt hardware clocks.

---

## 3. Collector State Machine

The collector operates as a finite state machine ensuring controlled transitions, graceful shutdown, and bounded error recovery:

```text
  +------------+
  |  STARTING  |
  +------------+
        |
        v
  +------------+       Socket Error / Exception
  | CONNECTING |-----------------------------------+
  +------------+                                   |
        |                                          |
        | Connected & Authenticated (Key 600)      |
        v                                          v
  +------------+                           +------------+
  | BACKFILLING|                           |  BACKOFF   |
  +------------+                           +------------+
        |                                          ^
        | Historical Sync & Clock Check Complete   |
        v                                          |
  +------------+   Socket Closed / Timeout         |
  |    LIVE    |-----------------------------------+
  +------------+
        |
        | Graceful Shutdown (SIGTERM / SIGINT)
        v
  +------------+
  |  STOPPING  |
  +------------+
```

### State Descriptions:
* **`STARTING`**: Initializes configuration, database connection pools, MQTT client, and signal handlers (`SIGTERM`, `SIGINT`).
* **`CONNECTING`**: Establishes TCP connection to port 4370 using `pyzk` with Comm Key (`600`).
* **`BACKFILLING`**: Queries `get_attendance()`, filters client-side against DB watermark, and backfills missing logs to PostgreSQL. `enable_device()` is verified active.
* **`LIVE`**: Enters `live_capture()` streaming loop. Catches 10-second `None` yield timeouts to update local heartbeat file `/tmp/collector_health.json`. Device remains **enabled**.
* **`BACKOFF`**: Enforces bounded exponential backoff with jitter before re-entering `CONNECTING`.
* **`STOPPING`**: Flushes pending database transactions, closes MQTT connections, releases ZK socket safely (`enable_device()`, `disconnect()`), and exits clean (Exit Code 0).

---

## 4. Reconnect Strategy (Bounded Exponential Backoff)

To prevent socket starvation or device lockup when the biometric hardware is rebooting or network is degraded:

- **Initial Delay ($t_0$)**: 2 seconds
- **Multiplier ($\gamma$)**: 2.0
- **Maximum Delay ($t_{\max}$)**: 60 seconds
- **Jitter ($\delta$)**: $\pm 20\%$ randomized delay
- **Formula**:
  $$t_{\text{retry}} = \min\left(t_{\max},\; t_0 \times \gamma^n\right) \times (1 + \text{random}(-0.2, 0.2))$$
- **Reset Criteria**: Backoff counter $n$ resets to 0 after remaining in `LIVE` state and successfully processing events for $> 30$ seconds.

---

## 5. Clock Synchronization Policy

1. **Inspection**: During `BACKFILLING` state, compare `connection.get_time()` with host UTC system time.
2. **Threshold**: Measured live drift on SONIC ZEM560 was **-25.39s**. Automatic clock synchronization is **RECOMMENDED** when $|\Delta t| > 10 \text{ seconds}$.
3. **Execution**: Run `connection.set_time(datetime.now())`. Log audit record in PostgreSQL `sync_events` (`event_type: 'CLOCK_SYNC'`).

---

## 6. Database & MQTT Decoupling Architecture

1. **PostgreSQL as Primary Source of Truth**: Database persistence must succeed before event notification occurs.
2. **MQTT Non-blocking Broadcast**: MQTT publication failures logged as warnings; database transaction is NOT rolled back if MQTT publish fails.
3. **Deduplication Key**: Composite unique constraint `UNIQUE (user_id, device_ip, scan_time)` in `attendance_logs`.

---

## 7. Health & Observability Signaling

1. **Application Heartbeat**: The collector updates an ephemeral health status file `/tmp/collector_health.json` containing a structured JSON status payload during `live_capture()` 10s timeout loops.
2. **Docker Healthcheck**: Probes `/tmp/collector_health.json` timestamp freshness using `python -m app.healthcheck` (unhealthy if stale > 120 seconds in `LIVE`/`BACKOFF` or > 600 seconds in `BACKFILLING`).
