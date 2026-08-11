# ADMS Collector State Engine Architecture

## Document Status

* **Status**: Implemented State Engine Architecture
* **Source PromptID**: `ADMS-Collector-StateEngine-002`
* **Target Device**: SONIC ZEM560_TFT (MIPS Linux 2.6.24, Firmware `Ver 6.60 Aug 26 2011`)
* **SDK Driver**: `pyzk==0.9` (`from zk import ZK`)
* **Implementation Files**: `app/main.py`, `app/config.py`, `app/collector.py`, `app/db.py`, `app/mqtt_client.py`

---

## 1. Executive Summary

The **Collector State Engine Architecture** replaces the baseline monolithic loop in `app/main.py` with a modular, testable finite state machine (FSM). It provides:
- Controlled ZKTeco connection lifecycle with fresh socket initialization per attempt.
- Bounded exponential backoff ($2\text{s} \to 60\text{s}$ with $\pm 20\%$ randomized jitter).
- Interruptible sleep responsive to Docker `SIGTERM`/`SIGINT` signals (`threading.Event`).
- Database failure isolation (persistence failure aborts stream to prevent silent data loss).
- Non-blocking MQTT notification (MQTT failures transition engine to `DEGRADED`, preserving DB persistence and ZK stream).
- Sequential integration hook (`BACKFILLING` state) for upcoming `ADMS-Collector-HybridBackfill-001`.
- Terminal keypad/display remains **enabled** (`connection.enable_device()`) during live monitoring.

---

## 2. Implemented Modular Architecture

```text
app/
├── main.py            # CLI entrypoint, logging, OS signal registration (SIGTERM/SIGINT)
├── config.py          # Config class loading & validating environment variables
├── collector.py       # CollectorStateEngine FSM class (STARTING -> CONNECTING -> BACKFILLING -> LIVE -> BACKOFF -> STOPPING -> STOPPED)
├── db.py              # PostgreSQL database persistence & attendance status evaluation
└── mqtt_client.py     # Asynchronous Mosquitto MQTT v2 publisher wrapper
```

---

## 3. State Transition Model

```text
  +------------+
  |  STARTING  |
  +------------+
        |
        v
  +------------+       Socket Error / Auth Fail
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
        |  \
        |   \ MQTT Down
        |    v
        |  +------------+
        |  |  DEGRADED  |
        |  +------------+
        |
        | Graceful Shutdown (SIGTERM / SIGINT)
        v
  +------------+
  |  STOPPING  |
  +------------+
        |
        v
  +------------+
  |  STOPPED   |
  +------------+
```

---

## 4. Reconnect & Reset Strategy

- **Initial Delay ($t_0$)**: 2.0 seconds
- **Multiplier ($\gamma$)**: 2.0
- **Maximum Delay ($t_{\max}$)**: 60.0 seconds
- **Jitter ($\delta$)**: $\pm 20\%$ randomized delay
- **Formula**:
  $$t_{\text{retry}} = \min\left(60.0,\; 2.0 \times 2^n\right) \times (1 + \text{uniform}(-0.2, 0.2))$$
- **Interruptible Sleep**: Uses `threading.Event().wait(timeout=t)` so SIGTERM/SIGINT interrupts waiting instantly.
- **Reset Criteria**: Reconnect counter $n$ resets to 0 after remaining in `LIVE` state for $> 30.0$ seconds (`STABLE_LIVE_WINDOW_SECONDS`).
