"""Read-side DB access for the ADMS F1 API.

PromptID: ADMS-Frontend-F1-API-001

All queries are parameterized — no user-provided SQL, no SQL injection.
Reuses the existing app.config.Config + app.db.get_db_connection conventions.
Does NOT rewrite any Collector persistence logic.

Write-side operations are delegated to the canonical modules
(app/enrollment.py, app/mapping.py) — never reimplemented here.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import Config
from app.db import get_db_connection
from app.rtn_ranks import normalize_rtn_rank


def _connect(cfg: Config):
    return get_db_connection(cfg)


def _fetch_all(cfg: Config, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_one(cfg: Config, sql: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
    rows = _fetch_all(cfg, sql, params)
    return rows[0] if rows else None


def _fetch_scalar(cfg: Config, sql: str, params: Tuple[Any, ...] = ()) -> Any:
    row = _fetch_one(cfg, sql, params)
    if row is None:
        return None
    return next(iter(row.values()))


# --- Health ---------------------------------------------------------------


def check_database(cfg: Config) -> bool:
    try:
        _fetch_scalar(cfg, "SELECT 1")
        return True
    except Exception:
        return False


def check_mqtt(cfg: Config) -> Optional[str]:
    """Best-effort MQTT reachability. Returns 'HEALTHY'/'UNREACHABLE'/None."""
    try:
        import socket

        s = socket.create_connection((cfg.mqtt_host, cfg.mqtt_port), timeout=2)
        s.close()
        return "HEALTHY"
    except Exception:
        return "UNREACHABLE"


# --- Dashboard ------------------------------------------------------------


def dashboard_summary(cfg: Config) -> Dict[str, Any]:
    row = _fetch_one(
        cfg,
        """
        SELECT
          (SELECT COUNT(*) FROM human_employees)                          AS humans_total,
          (SELECT COUNT(*) FROM human_employees WHERE production_scope)   AS humans_production_eligible,
          (SELECT COUNT(*) FROM human_employees WHERE NOT production_scope) AS humans_excluded,
          (SELECT COUNT(*) FROM devices)                                  AS devices_total,
          (SELECT COUNT(*) FROM devices WHERE active)                     AS devices_active,
          (SELECT COUNT(*) FROM device_users)                             AS device_users_total,
          (SELECT COUNT(*) FROM device_users WHERE active)                AS device_users_active,
          (SELECT COUNT(*) FROM device_users WHERE active
             AND device_user_pk NOT IN (
               SELECT device_user_pk FROM employee_device_mappings
               WHERE mapping_status = 'VERIFIED'
             ))                                                           AS device_users_unmapped,
          (SELECT COUNT(*) FROM attendance_logs)                          AS attendance_total,
          (SELECT COUNT(*) FROM attendance_logs
             WHERE scan_time >= date_trunc('day', now()))                 AS attendance_today,
          (SELECT COUNT(*) FROM attendance_logs WHERE employee_id IS NULL) AS attendance_unattributed,
          (SELECT COUNT(*) FROM employee_device_mappings)                 AS mappings_total,
          (SELECT COUNT(*) FROM employee_device_mappings
             WHERE mapping_status = 'VERIFIED' AND valid_to IS NULL)      AS mappings_verified_active
        """,
    )
    if row is None:
        return {}

    enroll_rows = _fetch_all(
        cfg,
        "SELECT status, COUNT(*) AS cnt FROM device_user_enrollments GROUP BY status",
    )
    enrollments_by_status = {r["status"]: r["cnt"] for r in enroll_rows}
    row["enrollments_by_status"] = enrollments_by_status
    return row


# --- Human Master ---------------------------------------------------------


HUMAN_COLUMNS = (
    "employee_id, personnel_id, display_name, rank, position, branch, category, "
    "notes, active, production_scope, source, created_at, updated_at"
)


def list_humans(
    cfg: Config,
    limit: int,
    offset: int,
    production_scope: Optional[bool] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if production_scope is not None:
        where.append("production_scope = %s")
        params.append(production_scope)
    if search:
        where.append("(display_name ILIKE %s OR personnel_id ILIKE %s OR rank ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like, like])
    if category:
        where.append("category = %s")
        params.append(category)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = _fetch_scalar(cfg, f"SELECT COUNT(*) FROM human_employees{where_sql}", tuple(params))

    rows = _fetch_all(
        cfg,
        f"SELECT {HUMAN_COLUMNS} FROM human_employees{where_sql} "
        "ORDER BY display_name LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    for r in rows:
        meta = normalize_rtn_rank(r.get("rank") or "")
        r["rank_metadata"] = meta
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_human(cfg: Config, employee_id: str) -> Optional[Dict[str, Any]]:
    row = _fetch_one(
        cfg,
        f"SELECT {HUMAN_COLUMNS} FROM human_employees WHERE employee_id = %s",
        (employee_id,),
    )
    if row:
        meta = normalize_rtn_rank(row.get("rank") or "")
        row["rank_metadata"] = meta
    return row


# --- Devices --------------------------------------------------------------


def list_devices(cfg: Config, limit: int, offset: int) -> Dict[str, Any]:
    total = _fetch_scalar(cfg, "SELECT COUNT(*) FROM devices")
    rows = _fetch_all(
        cfg,
        "SELECT device_id, serial_number, device_name, device_ip, platform, "
        "firmware_version, active, first_seen_at, last_seen_at, created_at, updated_at "
        "FROM devices ORDER BY device_id LIMIT %s OFFSET %s",
        (limit, offset),
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_device(cfg: Config, device_id: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(
        cfg,
        "SELECT device_id, serial_number, device_name, device_ip, platform, "
        "firmware_version, active, first_seen_at, last_seen_at, created_at, updated_at "
        "FROM devices WHERE device_id = %s",
        (device_id,),
    )


# --- Device users ---------------------------------------------------------


def list_device_users(
    cfg: Config,
    limit: int,
    offset: int,
    device_id: Optional[int] = None,
    active: Optional[bool] = None,
) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if device_id is not None:
        where.append("device_id = %s")
        params.append(device_id)
    if active is not None:
        where.append("active = %s")
        params.append(active)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = _fetch_scalar(cfg, f"SELECT COUNT(*) FROM device_users{where_sql}", tuple(params))
    rows = _fetch_all(
        cfg,
        "SELECT device_user_pk, device_id, device_user_id, device_uid, "
        "device_display_name, privilege, active, first_seen_at, last_seen_at, "
        "roster_last_seen_at, inactive_at, created_at, updated_at "
        f"FROM device_users{where_sql} ORDER BY device_user_pk LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_device_user(cfg: Config, device_user_pk: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(
        cfg,
        "SELECT device_user_pk, device_id, device_user_id, device_uid, "
        "device_display_name, privilege, active, first_seen_at, last_seen_at, "
        "roster_last_seen_at, inactive_at, created_at, updated_at "
        "FROM device_users WHERE device_user_pk = %s",
        (device_user_pk,),
    )


# --- Attendance -----------------------------------------------------------


def list_attendance(
    cfg: Config,
    limit: int,
    offset: int,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    employee_id: Optional[str] = None,
    device_user_pk: Optional[int] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if date_from is not None:
        where.append("scan_time >= %s")
        params.append(date_from)
    if date_to is not None:
        where.append("scan_time <= %s")
        params.append(date_to)
    if employee_id is not None:
        where.append("employee_id = %s")
        params.append(employee_id)
    if device_user_pk is not None:
        where.append("device_user_pk = %s")
        params.append(device_user_pk)
    if status is not None:
        where.append("status = %s")
        params.append(status)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = _fetch_scalar(cfg, f"SELECT COUNT(*) FROM attendance_logs{where_sql}", tuple(params))
    rows = _fetch_all(
        cfg,
        "SELECT id, user_id, device_ip, scan_time, punch_type, status, device_id, "
        "device_user_pk, employee_id, created_at "
        f"FROM attendance_logs{where_sql} ORDER BY scan_time DESC, id DESC "
        "LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_attendance(cfg: Config, attendance_id: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(
        cfg,
        "SELECT a.id, a.user_id, a.device_ip, a.scan_time, a.punch_type, a.status, "
        "a.device_id, a.device_user_pk, a.employee_id, a.created_at, "
        "d.device_name, du.device_user_id, h.display_name AS employee_name "
        "FROM attendance_logs a "
        "LEFT JOIN devices d ON d.device_id = a.device_id "
        "LEFT JOIN device_users du ON du.device_user_pk = a.device_user_pk "
        "LEFT JOIN human_employees h ON h.employee_id = a.employee_id "
        "WHERE a.id = %s",
        (attendance_id,),
    )


def get_attendance_raw_payload(cfg: Config, attendance_id: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(
        cfg,
        "SELECT id, raw_payload FROM attendance_logs WHERE id = %s",
        (attendance_id,),
    )


# --- Mappings -------------------------------------------------------------


def list_mappings(
    cfg: Config,
    limit: int,
    offset: int,
    employee_id: Optional[str] = None,
    device_user_pk: Optional[int] = None,
    mapping_status: Optional[str] = None,
) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if employee_id is not None:
        where.append("m.employee_id = %s")
        params.append(employee_id)
    if device_user_pk is not None:
        where.append("m.device_user_pk = %s")
        params.append(device_user_pk)
    if mapping_status is not None:
        where.append("m.mapping_status = %s")
        params.append(mapping_status)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = _fetch_scalar(
        cfg,
        f"SELECT COUNT(*) FROM employee_device_mappings m{where_sql}",
        tuple(params),
    )
    rows = _fetch_all(
        cfg,
        "SELECT m.mapping_id, m.employee_id, m.device_user_pk, m.mapping_status, "
        "m.mapping_source, m.verified_by, m.verification_method, m.verification_note, "
        "m.valid_from, m.valid_to, m.verified_at, m.created_at, m.updated_at, "
        "h.display_name AS employee_name, du.device_user_id "
        "FROM employee_device_mappings m "
        "LEFT JOIN human_employees h ON h.employee_id = m.employee_id "
        "LEFT JOIN device_users du ON du.device_user_pk = m.device_user_pk "
        f"{where_sql} ORDER BY m.mapping_id LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_mapping(cfg: Config, mapping_id: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(
        cfg,
        "SELECT m.mapping_id, m.employee_id, m.device_user_pk, m.mapping_status, "
        "m.mapping_source, m.verified_by, m.verification_method, m.verification_note, "
        "m.valid_from, m.valid_to, m.verified_at, m.created_at, m.updated_at, "
        "h.display_name AS employee_name, du.device_user_id "
        "FROM employee_device_mappings m "
        "LEFT JOIN human_employees h ON h.employee_id = m.employee_id "
        "LEFT JOIN device_users du ON du.device_user_pk = m.device_user_pk "
        "WHERE m.mapping_id = %s",
        (mapping_id,),
    )


# --- Enrollments ----------------------------------------------------------


def list_enrollments(
    cfg: Config,
    limit: int,
    offset: int,
    status: Optional[str] = None,
    employee_id: Optional[str] = None,
    device_id: Optional[int] = None,
) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if status is not None:
        where.append("e.status = %s")
        params.append(status)
    if employee_id is not None:
        where.append("e.employee_id = %s")
        params.append(employee_id)
    if device_id is not None:
        where.append("e.device_id = %s")
        params.append(device_id)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = _fetch_scalar(
        cfg,
        f"SELECT COUNT(*) FROM device_user_enrollments e{where_sql}",
        tuple(params),
    )
    rows = _fetch_all(
        cfg,
        "SELECT e.enrollment_id, e.employee_id, e.device_id, e.reserved_device_user_id, "
        "e.status, e.reserved_by, e.reserved_at, e.terminal_created_at, e.device_uid, "
        "e.fingerprint_confirmed_at, e.controlled_scan_window_until, "
        "e.controlled_scan_time, e.confirmed_by, e.confirmed_at, e.notes, "
        "e.created_at, e.updated_at, "
        "h.display_name AS employee_name, d.device_name "
        "FROM device_user_enrollments e "
        "LEFT JOIN human_employees h ON h.employee_id = e.employee_id "
        "LEFT JOIN devices d ON d.device_id = e.device_id "
        f"{where_sql} ORDER BY e.enrollment_id LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_enrollment_row(cfg: Config, enrollment_id: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(
        cfg,
        "SELECT e.enrollment_id, e.employee_id, e.device_id, e.reserved_device_user_id, "
        "e.status, e.reserved_by, e.reserved_at, e.terminal_created_at, e.device_uid, "
        "e.fingerprint_confirmed_at, e.controlled_scan_window_until, "
        "e.controlled_scan_time, e.confirmed_by, e.confirmed_at, e.notes, "
        "e.created_at, e.updated_at, "
        "h.display_name AS employee_name, d.device_name "
        "FROM device_user_enrollments e "
        "LEFT JOIN human_employees h ON h.employee_id = e.employee_id "
        "LEFT JOIN devices d ON d.device_id = e.device_id "
        "WHERE e.enrollment_id = %s",
        (enrollment_id,),
    )
