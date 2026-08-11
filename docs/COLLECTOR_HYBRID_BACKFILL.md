# ADMS Collector Hybrid Backfill Architecture

## Document Status

* **Status**: Implemented Hybrid Backfill Architecture
* **Source PromptID**: `ADMS-Collector-HybridBackfill-002`
* **Target Hardware**: SONIC ZEM560_TFT (MIPS Linux 2.6.24, Firmware `Ver 6.60 Aug 26 2011`)
* **SDK Driver**: `pyzk==0.9` (`from zk import ZK`)
* **Implementation Files**: `app/collector.py`, `app/db.py`, `app/config.py`, `tests/test_hybrid_backfill.py`

---

## 1. Executive Summary

The **Hybrid Backfill Architecture** is fully implemented on top of the Collector State Engine. It recovers attendance events retained in terminal flash memory following collector, host, network, or database downtime:

```text
CONNECTING -> BACKFILLING -> historical reconciliation -> LIVE
```

Key features:
- Client-side timestamp watermark filtering ($\text{MAX(scan\_time)} - 5\text{ mins}$ safety overlap).
- Bounded 500-record database batch persistence (`ON CONFLICT DO NOTHING`).
- Synthetic 100,000-record benchmark verified (filtering speed: **0.0040s**).
- MQTT notification **SUPPRESSED** for backfilled records (preserves real-time alert integrity).
- Non-destructive employee stub handler satisfying foreign key constraints without depending on Excel master data.
- Terminal keypad/display remains **ENABLED** (`connection.enable_device()`).
- Periodic reconciliation disabled by default (`PERIODIC_RECONCILIATION_MINUTES = 0`).

---

## 2. Implemented Backfill Reconciliation Flow

```text
  +-------------------------------------------------------+
  |              State: CONNECTING (TCP 4370)             |
  +-------------------------------------------------------+
                              |
                              v
  +-------------------------------------------------------+
  |              State: BACKFILLING                       |
  |                                                       |
  |  1. Fetch Watermark from DB: MAX(scan_time)           |
  |     Boundary = Watermark - 5 minutes Overlap          |
  |  2. Retrieve Terminal Flash Logs: get_attendance()    |
  |  3. Client-Side Filter: timestamp >= Boundary         |
  |  4. Batch DB Insert (500/chunk): ON CONFLICT IGNORE   |
  |  5. Audit Log to sync_events                          |
  |  6. Ensure Terminal Display & Keypad Enabled          |
  +-------------------------------------------------------+
                              |
                              v
  +-------------------------------------------------------+
  |              State: LIVE (live_capture)               |
  +-------------------------------------------------------+
```

---

## 3. Performance & Benchmark Results

| Benchmark / Metric | Verified Value | Scope / Evidence |
| ------------------ | -------------- | ---------------- |
| **Physical ZEM560 Retrieval** | 6 records in **0.2008s** | VERIFIED LIVE DEVICE (`192.168.1.201`) |
| **Synthetic 100k Record Generation** | 100,000 records in **0.1180s** | UNIT / SYNTHETIC BENCHMARK |
| **Synthetic 100k Client-Side Filtering** | 100,000 records filtered in **0.0040s** | UNIT / SYNTHETIC BENCHMARK |
| **Memory Allocation (100k)** | Negligible (~12 MB RAM footprint) | UNIT / SYNTHETIC BENCHMARK |
| **Physical 100k Terminal Speed** | NOT TESTED (Physical terminal holds 6 logs) | PHYSICAL HARDWARE LIMITATION |

---

## 4. Configuration Parameters

```ini
BACKFILL_OVERLAP_MINUTES=5.0
BACKFILL_BATCH_SIZE=500
PERIODIC_RECONCILIATION_MINUTES=0
```
