import json
import logging
from contextlib import contextmanager
from datetime import datetime, time
from typing import Optional, Dict, Any, List, Tuple
import psycopg2
from app.config import Config

log = logging.getLogger(__name__)

@contextmanager
def get_db_connection(cfg: Config):
    conn = psycopg2.connect(
        host=cfg.db_host,
        port=cfg.db_port,
        dbname=cfg.db_name,
        user=cfg.db_user,
        password=cfg.db_password,
        connect_timeout=5
    )
    try:
        yield conn
    finally:
        conn.close()

def parse_time(val: str) -> time:
    hour, minute = map(int, val.split(":"))
    return time(hour=hour, minute=minute)

def determine_status(scan_time: datetime, on_time_start: str, on_time_end: str) -> str:
    try:
        t_start = parse_time(on_time_start)
        t_end = parse_time(on_time_end)
        scan_t = scan_time.time()
        if t_start <= scan_t <= t_end:
            return "ON_TIME"
        return "LATE"
    except Exception as e:
        log.warning("failed to determine attendance status: %s", e)
        return "UNKNOWN"

def ensure_employee_stub(cur: Any, user_id: str):
    """
    Ensures a minimal employee stub row exists in 'employees' table for user_id.
    Satisfies foreign key constraint without depending on Excel master data import.
    """
    sql = """
        INSERT INTO employees (user_id, display_name)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO NOTHING;
    """
    cur.execute(sql, (user_id, f"User {user_id}"))

def get_device_watermark(cfg: Config, device_ip: str) -> Optional[datetime]:
    """
    Queries PostgreSQL for MAX(scan_time) for device_ip.
    Returns None if no attendance records exist for device.
    """
    sql = "SELECT MAX(scan_time) FROM attendance_logs WHERE device_ip = %s;"
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (device_ip,))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
            return None

def save_attendance_log(cfg: Config, attendance: Any) -> bool:
    """
    Persists a single real-time attendance record into PostgreSQL.
    Returns True if inserted, False if skipped due to UNIQUE constraint collision.
    """
    user_id_str = str(attendance.user_id)
    scan_time = attendance.timestamp
    status = determine_status(scan_time, cfg.on_time_start, cfg.on_time_end)
    raw_payload = json.dumps({
        "uid": getattr(attendance, "uid", None),
        "user_id": user_id_str,
        "timestamp": scan_time.isoformat(),
        "status": getattr(attendance, "status", None),
        "punch": getattr(attendance, "punch", None),
        "device_ip": cfg.device_ip
    })

    sql = """
        INSERT INTO attendance_logs (user_id, device_ip, scan_time, punch_type, status, raw_payload)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, device_ip, scan_time) DO NOTHING
        RETURNING id;
    """

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            ensure_employee_stub(cur, user_id_str)
            cur.execute(sql, (
                user_id_str,
                cfg.device_ip,
                scan_time,
                str(getattr(attendance, "punch", "")),
                status,
                raw_payload
            ))
            row = cur.fetchone()
            conn.commit()
            return row is not None

def save_attendance_batch(cfg: Config, attendance_records: List[Any], stop_event: Optional[Any] = None) -> Tuple[int, int]:
    """
    Persists a list of historical attendance records into PostgreSQL in chunks of cfg.backfill_batch_size.
    Returns Tuple[inserted_count, skipped_count].
    Rolls back uncommitted active batch if database error or stop signal occurs.
    """
    if not attendance_records:
        return 0, 0

    inserted_total = 0
    skipped_total = 0
    batch_size = max(1, cfg.backfill_batch_size)

    with get_db_connection(cfg) as conn:
        for i in range(0, len(attendance_records), batch_size):
            if stop_event and stop_event.is_set():
                log.info("Stop event detected during backfill DB batch persistence")
                break

            chunk = attendance_records[i:i + batch_size]
            inserted_chunk = 0
            skipped_chunk = 0

            try:
                with conn.cursor() as cur:
                    # Step 1: Ensure employee stubs exist for all unique user_ids in chunk
                    unique_users = {str(rec.user_id) for rec in chunk if hasattr(rec, 'user_id')}
                    for uid in unique_users:
                        ensure_employee_stub(cur, uid)

                    # Step 2: Insert attendance records
                    for rec in chunk:
                        user_id_str = str(rec.user_id)
                        scan_time = rec.timestamp
                        status = determine_status(scan_time, cfg.on_time_start, cfg.on_time_end)
                        raw_payload = json.dumps({
                            "uid": getattr(rec, "uid", None),
                            "user_id": user_id_str,
                            "timestamp": scan_time.isoformat(),
                            "status": getattr(rec, "status", None),
                            "punch": getattr(rec, "punch", None),
                            "device_ip": cfg.device_ip
                        })

                        sql = """
                            INSERT INTO attendance_logs (user_id, device_ip, scan_time, punch_type, status, raw_payload)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (user_id, device_ip, scan_time) DO NOTHING
                            RETURNING id;
                        """
                        cur.execute(sql, (
                            user_id_str,
                            cfg.device_ip,
                            scan_time,
                            str(getattr(rec, "punch", "")),
                            status,
                            raw_payload
                        ))
                        row = cur.fetchone()
                        if row is not None:
                            inserted_chunk += 1
                        else:
                            skipped_chunk += 1

                # Commit batch chunk transaction
                conn.commit()
                inserted_total += inserted_chunk
                skipped_total += skipped_chunk
                log.info("Committed backfill batch chunk %d-%d: %d inserted, %d duplicate skipped",
                         i + 1, min(i + batch_size, len(attendance_records)), inserted_chunk, skipped_chunk)

            except Exception as e:
                conn.rollback()
                log.error("Error in backfill batch chunk %d-%d: %s. Rolled back chunk.", i + 1, i + len(chunk), e)
                raise e

    return inserted_total, skipped_total

def log_sync_event(cfg: Config, event_type: str, message: str):
    """
    Logs an operational audit entry to sync_events table.
    """
    sql = "INSERT INTO sync_events (device_ip, event_type, message) VALUES (%s, %s, %s);"
    try:
        with get_db_connection(cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (cfg.device_ip, event_type, message))
                conn.commit()
    except Exception as e:
        log.warning("Failed to log sync event to DB: %s", e)
