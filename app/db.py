import json
import logging
from contextlib import contextmanager
from datetime import datetime, time
from typing import Optional, Dict, Any, List, Tuple
import psycopg2
from app.config import Config
from app.timestamp_utils import normalize_device_timestamp

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
    """
    Parses a time-of-day string into a datetime.time instance.

    Supported formats (production contract):
      - HH:MM        (e.g. "08:30")
      - HH:MM:SS     (e.g. "05:00:00" — production docker-compose default)

    Invalid / empty / None values raise ValueError, which callers such as
    determine_status() catch and translate to "UNKNOWN" (fail-safe).
    Timezone handling is intentionally NOT performed here — time-of-day only;
    timezone normalization is owned by normalize_device_timestamp().
    """
    if not val:
        raise ValueError("empty time value")
    parts = val.split(":")
    if len(parts) == 2:
        hour, minute = map(int, parts)
        return time(hour=hour, minute=minute)
    if len(parts) == 3:
        hour, minute, second = map(int, parts)
        return time(hour=hour, minute=minute, second=second)
    raise ValueError(f"unsupported time format: {val!r}")

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

def resolve_verified_employee_mapping(
    cur: Any,
    device_user_pk: int,
    scan_time: datetime,
) -> Optional[str]:
    """
    Temporally resolves a VERIFIED Human identity for a device user at a
    given canonical scan_time.

    Uses the interval [valid_from, valid_to):
      - valid_from is inclusive
      - valid_to is exclusive (NULL means open-ended)

    Only mapping_status = 'VERIFIED' is considered.

    Returns:
      - employee_id UUID string if exactly one VERIFIED temporal mapping matches
      - None if zero matches (unmapped)
      - None if >1 matches (ambiguous — integrity condition logged, no Human assigned)

    scan_time MUST be an already-normalized timezone-aware datetime from
    normalize_device_timestamp().
    """
    sql = """
        SELECT employee_id
        FROM employee_device_mappings
        WHERE device_user_pk = %s
          AND mapping_status = 'VERIFIED'
          AND valid_from <= %s
          AND (valid_to IS NULL OR %s < valid_to)
        LIMIT 2;
    """
    cur.execute(sql, (device_user_pk, scan_time, scan_time))
    rows = cur.fetchall()
    if len(rows) == 0:
        return None
    if len(rows) == 1:
        return str(rows[0][0])
    # Ambiguity: >1 matching VERIFIED temporal intervals for same device_user_pk + scan_time
    log.error(
        "AMBIGUOUS MAPPING: device_user_pk=%s scan_time=%s matched %d VERIFIED intervals — "
        "employee_id set to NULL for safety. Investigate mapping data integrity.",
        device_user_pk, scan_time.isoformat(), len(rows),
    )
    return None

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
    scan_time = normalize_device_timestamp(attendance.timestamp)
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
            employee_id = resolve_verified_employee_mapping(cur, device_user_pk, scan_time)

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

                    # Step 2: Ensure device_users for all unique users
                    unique_users = {str(rec.user_id) for rec in chunk if hasattr(rec, 'user_id')}
                    user_pk_map = {}
                    for uid in unique_users:
                        dpk = ensure_device_user(cur, device_id, uid)
                        user_pk_map[uid] = dpk

                    # Step 3: Insert attendance records (temporal resolution per-record)
                    for rec in chunk:
                        user_id_str = str(rec.user_id)
                        scan_time = normalize_device_timestamp(rec.timestamp)
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
                        emp_id = resolve_verified_employee_mapping(cur, dpk, scan_time)

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

def reconcile_roster_lifecycle(
    cfg: Config,
    device_id: int,
    observed_users: List[Dict[str, Any]],
) -> Dict[str, int]:
    """
    Reconciles a successful terminal roster snapshot against the device_users table.

    Atomic per-device snapshot:
      - For observed users: ensure/resolve device_user, update roster_last_seen_at,
        clear inactive_at (REAPPEARED if was inactive).
      - For known users absent from roster: set inactive_at = now() if currently NULL.
      - Detect device_uid changes and log warnings (no auto-mapping).

    IMPORTANT: This function MUST only be called after a successful, complete roster
    read. If the roster read failed (timeout, disconnect, exception), do NOT call this
    function — a failed read is UNKNOWN state, not an empty roster.

    Args:
        cfg: Config instance for DB connection.
        device_id: The device_id to scope reconciliation.
        observed_users: List of dicts with keys: user_id (str), uid (int|None),
                        name (str|None). From a successful get_users() call.

    Returns:
        Dict with counts: observed, new_users, marked_inactive, reappeared, uid_anomalies.
    """
    summary = {
        "observed": 0,
        "new_users": 0,
        "marked_inactive": 0,
        "reappeared": 0,
        "uid_anomalies": 0,
    }

    observed_map: Dict[str, Dict[str, Any]] = {}
    for u in observed_users:
        uid_str = str(u.get("user_id", ""))
        if uid_str:
            observed_map[uid_str] = u

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            # 1. Load all known device_users for this device
            cur.execute(
                "SELECT device_user_pk, device_user_id, device_uid, active, "
                "roster_last_seen_at, inactive_at "
                "FROM device_users WHERE device_id = %s;",
                (device_id,),
            )
            known_rows = cur.fetchall()
            known_map: Dict[str, Dict[str, Any]] = {}
            for row in known_rows:
                known_map[str(row[1])] = {
                    "device_user_pk": row[0],
                    "device_user_id": row[1],
                    "device_uid": row[2],
                    "active": row[3],
                    "roster_last_seen_at": row[4],
                    "inactive_at": row[5],
                }

            # 2. Process observed users (present in roster)
            for uid_str, obs in observed_map.items():
                summary["observed"] += 1
                obs_uid = obs.get("uid")
                obs_name = obs.get("name")

                if uid_str in known_map:
                    known = known_map[uid_str]
                    dpk = known["device_user_pk"]

                    # UID change detection
                    if (
                        known["device_uid"] is not None
                        and obs_uid is not None
                        and known["device_uid"] != obs_uid
                    ):
                        summary["uid_anomalies"] += 1
                        log.warning(
                            "UID ANOMALY: device_id=%s device_user_id=%s "
                            "db_uid=%s terminal_uid=%s — continuity not assumed. "
                            "No Human mapping auto-created.",
                            device_id, uid_str, known["device_uid"], obs_uid,
                        )

                    # Reappearance detection
                    was_inactive = known["inactive_at"] is not None
                    if was_inactive:
                        summary["reappeared"] += 1
                        log.info(
                            "REAPPEARED: device_user_id=%s (pk=%s) reappeared in roster. "
                            "Clearing inactive_at.",
                            uid_str, dpk,
                        )

                    # Update roster_last_seen_at, clear inactive_at, update device_uid
                    cur.execute(
                        "UPDATE device_users "
                        "SET roster_last_seen_at = now(), "
                        "    inactive_at = NULL, "
                        "    device_uid = COALESCE(%s, device_uid), "
                        "    active = true, "
                        "    updated_at = now() "
                        "WHERE device_user_pk = %s;",
                        (obs_uid, dpk),
                    )
                else:
                    # New user observed in roster — ensure device_user
                    dpk = ensure_device_user(cur, device_id, uid_str, obs_name)
                    summary["new_users"] += 1
                    # Set roster_last_seen_at for the new user
                    cur.execute(
                        "UPDATE device_users "
                        "SET roster_last_seen_at = now(), "
                        "    device_uid = %s, "
                        "    updated_at = now() "
                        "WHERE device_user_pk = %s;",
                        (obs_uid, dpk),
                    )
                    log.info(
                        "NEW USER: device_user_id=%s (pk=%s) observed in roster for device_id=%s.",
                        uid_str, dpk, device_id,
                    )

            # 3. Process missing users (known but absent from successful roster)
            for uid_str, known in known_map.items():
                if uid_str in observed_map:
                    continue  # User was observed, skip

                dpk = known["device_user_pk"]
                if known["inactive_at"] is None:
                    # Mark as inactive — first known disappearance boundary
                    cur.execute(
                        "UPDATE device_users "
                        "SET inactive_at = now(), "
                        "    active = false, "
                        "    updated_at = now() "
                        "WHERE device_user_pk = %s AND inactive_at IS NULL;",
                        (dpk,),
                    )
                    summary["marked_inactive"] += 1
                    log.info(
                        "INACTIVE: device_user_id=%s (pk=%s) absent from successful roster. "
                        "Marked inactive_at = now().",
                        uid_str, dpk,
                    )
                # If already inactive, preserve original inactive_at (do nothing)

        conn.commit()

    log.info(
        "Roster lifecycle reconciliation complete for device_id=%s: "
        "%d observed, %d new, %d marked_inactive, %d reappeared, %d uid_anomalies.",
        device_id, summary["observed"], summary["new_users"],
        summary["marked_inactive"], summary["reappeared"], summary["uid_anomalies"],
    )
    return summary


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
