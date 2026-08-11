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

def get_or_create_device(cur: Any, serial_number: str = "3392113170057", device_ip: str = "192.168.1.201", device_name: str = "SONIC ZEM560 #1") -> int:
    """
    Resolves device_id from physical serial_number. Upserts device record idempotently.
    """
    sql = """
        INSERT INTO devices (serial_number, device_name, device_ip, platform, firmware_version, last_seen_at)
        VALUES (%s, %s, %s, 'ZEM560_TFT', 'Ver 6.60 Aug 26 2011', now())
        ON CONFLICT (serial_number) 
        DO UPDATE SET device_ip = EXCLUDED.device_ip, last_seen_at = now()
        RETURNING device_id;
    """
    cur.execute(sql, (serial_number, device_name, device_ip))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("SELECT device_id FROM devices WHERE serial_number = %s;", (serial_number,))
    res = cur.fetchone()
    return res[0] if res else 1

def ensure_device_user(cur: Any, device_id: int, device_user_id: str, display_name: Optional[str] = None) -> int:
    """
    Ensures a device_users record exists for (device_id, device_user_id).
    Returns device_user_pk. Does NOT create human_employees rows.
    """
    sql = """
        INSERT INTO device_users (device_id, device_user_id, device_display_name, last_seen_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (device_id, device_user_id) 
        DO UPDATE SET last_seen_at = now()
        RETURNING device_user_pk;
    """
    cur.execute(sql, (device_id, device_user_id, display_name or f"Device User {device_user_id}"))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("SELECT device_user_pk FROM device_users WHERE device_id = %s AND device_user_id = %s;", (device_id, device_user_id))
    res = cur.fetchone()
    return res[0] if res else 1

def resolve_verified_employee_mapping(cur: Any, device_user_pk: int) -> Optional[str]:
    """
    Looks up active VERIFIED employee mapping for device_user_pk.
    Returns employee_id UUID string or None if unmapped.
    """
    sql = """
        SELECT employee_id 
        FROM employee_device_mappings 
        WHERE device_user_pk = %s AND mapping_status = 'VERIFIED';
    """
    cur.execute(sql, (device_user_pk,))
    row = cur.fetchone()
    return str(row[0]) if row else None

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
    Populates device_id, device_user_pk, and optional employee_id.
    Does NOT invoke legacy ensure_employee_stub().
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
        INSERT INTO attendance_logs (user_id, device_ip, scan_time, punch_type, status, raw_payload, device_id, device_user_pk, employee_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, device_ip, scan_time) DO NOTHING
        RETURNING id;
    """

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            device_id = get_or_create_device(cur, device_ip=cfg.device_ip)
            device_user_pk = ensure_device_user(cur, device_id, user_id_str)
            employee_id = resolve_verified_employee_mapping(cur, device_user_pk)

            cur.execute(sql, (
                user_id_str,
                cfg.device_ip,
                scan_time,
                str(getattr(attendance, "punch", "")),
                status,
                raw_payload,
                device_id,
                device_user_pk,
                employee_id
            ))
            row = cur.fetchone()
            conn.commit()
            return row is not None

def save_attendance_batch(cfg: Config, attendance_records: List[Any], stop_event: Optional[Any] = None) -> Tuple[int, int]:
    """
    Persists a list of historical attendance records into PostgreSQL in chunks of cfg.backfill_batch_size.
    Populates device_id, device_user_pk, and optional employee_id.
    Does NOT invoke legacy ensure_employee_stub().
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
                    # Step 1: Resolve physical device
                    device_id = get_or_create_device(cur, device_ip=cfg.device_ip)

                    # Step 2: Ensure device_users and resolve employee mappings
                    unique_users = {str(rec.user_id) for rec in chunk if hasattr(rec, 'user_id')}
                    user_pk_map = {}
                    employee_map = {}
                    for uid in unique_users:
                        dpk = ensure_device_user(cur, device_id, uid)
                        user_pk_map[uid] = dpk
                        employee_map[uid] = resolve_verified_employee_mapping(cur, dpk)

                    # Step 3: Insert attendance records
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

                        dpk = user_pk_map.get(user_id_str)
                        emp_id = employee_map.get(user_id_str)

                        sql = """
                            INSERT INTO attendance_logs (user_id, device_ip, scan_time, punch_type, status, raw_payload, device_id, device_user_pk, employee_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (user_id, device_ip, scan_time) DO NOTHING
                            RETURNING id;
                        """
                        cur.execute(sql, (
                            user_id_str,
                            cfg.device_ip,
                            scan_time,
                            str(getattr(rec, "punch", "")),
                            status,
                            raw_payload,
                            device_id,
                            dpk,
                            emp_id
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
