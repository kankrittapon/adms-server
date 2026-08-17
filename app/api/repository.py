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
    "employee_id, personnel_id, display_name, english_name, rank, position, branch, category, "
    "notes, active, production_scope, source, created_at, updated_at"
)


def list_humans(
    cfg: Config,
    limit: int,
    offset: int,
    production_scope: Optional[bool] = None,
    active: Optional[bool] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if production_scope is not None:
        where.append("production_scope = %s")
        params.append(production_scope)
    if active is not None:
        where.append("active = %s")
        params.append(active)
    if search:
        where.append("(display_name ILIKE %s OR english_name ILIKE %s OR personnel_id ILIKE %s OR rank ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like, like, like])
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


def update_human_english_name(
    cfg: Config,
    employee_id: str,
    english_name: Optional[str],
    operator_username: str,
) -> Optional[Dict[str, Any]]:
    current = get_human(cfg, employee_id)
    if current is None:
        return None
    old_name = current.get("english_name") or ""
    new_name = english_name.strip() if english_name else None

    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE human_employees SET english_name = %s, updated_at = now() "
                f"WHERE employee_id = %s RETURNING {HUMAN_COLUMNS};",
                (new_name, employee_id),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                return None
            cols = [d[0] for d in cur.description]
            updated_dict = dict(zip(cols, row))
            conn.commit()

    from app.db import log_sync_event

    log_sync_event(
        cfg,
        "HUMAN_ENGLISH_NAME_UPDATED",
        f"employee_id={employee_id} old={old_name} new={new_name or ''} by={operator_username}",
    )
    meta = normalize_rtn_rank(updated_dict.get("rank") or "")
    updated_dict["rank_metadata"] = meta
    return updated_dict


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
        "roster_last_seen_at, inactive_at, account_incarnation, created_at, updated_at "
        f"FROM device_users{where_sql} ORDER BY device_user_pk LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_device_user(cfg: Config, device_user_pk: int) -> Optional[Dict[str, Any]]:
    return _fetch_one(
        cfg,
        "SELECT device_user_pk, device_id, device_user_id, device_uid, "
        "device_display_name, privilege, active, first_seen_at, last_seen_at, "
        "roster_last_seen_at, inactive_at, account_incarnation, created_at, updated_at "
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


# --- F5 hardening: audit trail -------------------------------------------


def list_audit_events(
    cfg: Config,
    limit: int,
    offset: int,
    event_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Paginated sync_events audit trail (ADMIN)."""
    where: List[str] = []
    params: List[Any] = []
    if event_type:
        where.append("event_type = %s")
        params.append(event_type)
    if date_from is not None:
        where.append("created_at >= %s")
        params.append(date_from)
    if date_to is not None:
        where.append("created_at <= %s")
        params.append(date_to)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = _fetch_scalar(
        cfg, f"SELECT COUNT(*) FROM sync_events{where_sql}", tuple(params)
    )
    rows = _fetch_all(
        cfg,
        "SELECT id, device_ip, event_type, message, created_at "
        f"FROM sync_events{where_sql} ORDER BY created_at DESC, id DESC "
        "LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def list_audit_event_types(cfg: Config) -> List[str]:
    rows = _fetch_all(
        cfg, "SELECT DISTINCT event_type FROM sync_events ORDER BY event_type;"
    )
    return [r["event_type"] for r in rows]


# --- F4: mapping eligibility / attendance reconciliation diagnostics ------


def mapping_eligibility(cfg: Config) -> List[Dict[str, Any]]:
    """READY_FOR_MAPPING enrollments with the full controlled-scan evidence.

    F4 (ADMS-Frontend-F4-AdminMappingReconciliation-001): the UI drives the
    ADMIN-gated POST /api/v1/mappings from this list. Only enrollments whose
    device user does NOT already carry an overlapping VERIFIED mapping are
    offered (mirrors create_verified_mapping step 5) — no duplicate mapping
    can be proposed.

    ADMS-FullEnrollment-E2E-Closure-017: `controlled_attendance_id` is
    resolved via the single canonical resolver (app.mapping_evidence),
    the same one app.mapping.create_verified_mapping() uses to
    independently re-verify evidence — there is exactly one definition of
    "the correct controlled-scan evidence row" in the system, not two
    drifting SQL implementations. (PromptID-016 first fixed this query's
    own exact-equality bug with an inline bounded-window subquery; 017
    found create_verified_mapping()'s own separate exact-equality re-check
    could still reject the same evidence, reproducing the "Attendance ID
    #?" failure at Step 6 — hence the shared resolver.)
    """
    rows = _fetch_all(
        cfg,
        """
        SELECT e.enrollment_id, e.employee_id, e.device_id, e.reserved_device_user_id,
               e.controlled_scan_time, e.confirmed_by, e.confirmed_at, e.notes,
               h.display_name AS employee_name, d.device_name,
               du.device_user_pk, du.device_user_id, du.active AS device_user_active
        FROM device_user_enrollments e
        LEFT JOIN human_employees h ON h.employee_id = e.employee_id
        LEFT JOIN devices d ON d.device_id = e.device_id
        LEFT JOIN device_users du
          ON du.device_id = e.device_id AND du.device_user_id = e.reserved_device_user_id
        WHERE e.status = 'READY_FOR_MAPPING'
          AND NOT EXISTS (
            SELECT 1 FROM employee_device_mappings m
            WHERE m.device_user_pk = du.device_user_pk
              AND m.mapping_status = 'VERIFIED'
              AND (m.valid_to IS NULL OR m.valid_to > e.controlled_scan_time)
          )
        ORDER BY e.enrollment_id;
        """,
    )
    for row in rows:
        row["controlled_attendance_id"] = None
        if row.get("device_user_pk") is not None and row.get("controlled_scan_time") is not None:
            row["controlled_attendance_id"] = _resolve_controlled_attendance_id(
                cfg, row["device_user_pk"], row["controlled_scan_time"]
            )
    return rows


def _resolve_controlled_attendance_id(cfg: Config, device_user_pk: int, controlled_scan_time: Any) -> Optional[int]:
    """Thin DB-connection wrapper around the canonical resolver — see
    app.mapping_evidence.resolve_controlled_attendance_id for the actual
    matching invariant."""
    from app.mapping_evidence import resolve_controlled_attendance_id

    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            return resolve_controlled_attendance_id(cur, device_user_pk, controlled_scan_time)


LEGACY_TEST_USER_IDS = frozenset({"1", "2"})


def _attribution_reasoning(cur: Any, row: Dict[str, Any]) -> Dict[str, Any]:
    """Classifies why an attendance row is unattributed, using canonical evidence.

    Never attributes anything — this is diagnostics only. Classification uses
    the canonical temporal resolver (resolve_verified_employee_mapping) plus
    device-user / mapping-interval evidence.
    """
    pk = row.get("device_user_pk")
    if pk is None:
        return {"classification": "NO_DEVICE_USER", "detail": "attendance has no device_user_pk"}
    cur.execute(
        "SELECT device_user_id, active FROM device_users WHERE device_user_pk = %s;",
        (pk,),
    )
    du = cur.fetchone()
    if du is None:
        return {
            "classification": "NO_DEVICE_USER",
            "detail": "device_user_pk %s not found" % pk,
        }
    du_id, du_active = du
    if str(du_id) in LEGACY_TEST_USER_IDS:
        return {
            "classification": "LEGACY_USER",
            "detail": "legacy test device user %s — never attributed" % du_id,
        }
    cur.execute(
        "SELECT employee_id, valid_from, valid_to FROM employee_device_mappings "
        "WHERE device_user_pk = %s AND mapping_status = 'VERIFIED' ORDER BY valid_from;",
        (pk,),
    )
    mappings = cur.fetchall()
    if not mappings:
        return {
            "classification": "NO_MAPPING",
            "detail": "no VERIFIED mapping exists for device_user_pk %s" % pk,
        }
    scan = row["scan_time"]
    resolved = resolve_verified_employee_mapping(cur, pk, scan)
    for emp_id, vf, vt in mappings:
        if scan < vf:
            return {
                "classification": "BEFORE_VALID_FROM",
                "detail": "scan %s is before valid_from %s (mapping employee %s)"
                % (scan.isoformat(), vf.isoformat(), emp_id),
                "valid_from": vf,
                "valid_to": vt,
                "resolver_employee_id": resolved,
            }
        if vt is not None and scan >= vt:
            continue
        return {
            "classification": "INSIDE_INTERVAL",
            "detail": "scan is inside a VERIFIED interval but row is unattributed — "
            "resolver returns %s" % (resolved or "None"),
            "valid_from": vf,
            "valid_to": vt,
            "resolver_employee_id": resolved,
        }
    return {
        "classification": "AFTER_VALID_TO",
        "detail": "scan is after the last VERIFIED interval (device user %s)" % du_id,
        "valid_from": None,
        "valid_to": None,
        "resolver_employee_id": resolved,
    }


def unattributed_attendance(cfg: Config, limit: int, offset: int) -> Dict[str, Any]:
    """Unattributed attendance rows (employee_id NULL) with resolver reasoning.

    Read-only reconciliation diagnostics. Never writes — attribution stays
    with the canonical VERIFIED temporal mapping at ingestion time.
    """
    with _connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM attendance_logs WHERE employee_id IS NULL;"
            )
            total = cur.fetchone()[0]
            cur.execute(
                "SELECT id, user_id, device_ip, scan_time, punch_type, status, "
                "device_id, device_user_pk, employee_id, created_at "
                "FROM attendance_logs WHERE employee_id IS NULL "
                "ORDER BY scan_time DESC, id DESC LIMIT %s OFFSET %s;",
                (limit, offset),
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                r["reasoning"] = _attribution_reasoning(cur, r)
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


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
        "h.display_name AS employee_name, h.english_name, h.rank, d.device_name "
        "FROM device_user_enrollments e "
        "LEFT JOIN human_employees h ON h.employee_id = e.employee_id "
        "LEFT JOIN devices d ON d.device_id = e.device_id "
        f"{where_sql} ORDER BY e.enrollment_id LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    )
    for r in rows:
        r["rank_metadata"] = normalize_rtn_rank(r.get("rank") or "")
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_enrollment_row(cfg: Config, enrollment_id: int) -> Optional[Dict[str, Any]]:
    row = _fetch_one(
        cfg,
        "SELECT e.enrollment_id, e.employee_id, e.device_id, e.reserved_device_user_id, "
        "e.status, e.reserved_by, e.reserved_at, e.terminal_created_at, e.device_uid, "
        "e.fingerprint_confirmed_at, e.controlled_scan_window_until, "
        "e.controlled_scan_time, e.confirmed_by, e.confirmed_at, e.notes, "
        "e.created_at, e.updated_at, "
        "h.display_name AS employee_name, h.english_name, h.rank, d.device_name "
        "FROM device_user_enrollments e "
        "LEFT JOIN human_employees h ON h.employee_id = e.employee_id "
        "LEFT JOIN devices d ON d.device_id = e.device_id "
        "WHERE e.enrollment_id = %s",
        (enrollment_id,),
    )
    if row:
        row["rank_metadata"] = normalize_rtn_rank(row.get("rank") or "")
    return row
