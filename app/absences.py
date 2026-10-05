"""Absence records (leave / official duty / secondment) and the daily roster.

Record-only by design: the battalion commander signs leave on paper before
it is entered, so there is no approval workflow here. A RECORDED absence
simply means "this person is not expected to scan on these days". Records
are never deleted — a mistake is CANCELLED with a reason, keeping the trail.

The daily roster is computed on read from current facts (roster, absences,
holidays, first scan of the day); nothing derived is stored.
"""

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import psycopg2

from app.config import Config
from app.db import get_db_connection, log_sync_event

# Attendance scans only count inside scan_window (06:30–11:00 local). A scan
# outside it is still stored (raw log) but never makes anyone present; the
# scanner itself stays usable all day for fingerprint enrollment.
DEFAULT_POLICY = {
    "late_after": "10:00",
    "scan_window_start": "06:30",
    "scan_window_end": "11:00",
    "timezone": "Asia/Bangkok",
    "workdays": [1, 2, 3, 4, 5],
}


def _hm(value: Any, default: str) -> time:
    hh, mm = (int(x) for x in str(value or default).split(":"))
    return time(hh, mm)


def policy_times(policy: Dict[str, Any]) -> Dict[str, time]:
    return {
        "late_after": _hm(policy.get("late_after"), "10:00"),
        "start": _hm(policy.get("scan_window_start"), "06:30"),
        "end": _hm(policy.get("scan_window_end"), "11:00"),
    }


def _window_bounds(day: date, tz: ZoneInfo, times: Dict[str, time]) -> tuple:
    """[start, end + 1 minute): a scan stamped 11:00:xx still counts."""
    start = datetime.combine(day, times["start"], tzinfo=tz)
    end = datetime.combine(day, times["end"], tzinfo=tz) + timedelta(minutes=1)
    return start, end

# Daily roster statuses, in display order.
ROSTER_STATUSES = ("PRESENT", "LATE", "LEAVE", "DUTY", "EXEMPT", "NOT_YET", "ABSENT", "NOT_ENROLLED", "OFF")


class AbsenceError(Exception):
    """Validation failure — maps to 422."""


class AbsenceOverlapError(AbsenceError):
    """The person already has a recorded absence covering one of the days — maps to 409."""


class AbsenceNotFound(AbsenceError):
    pass


def _rows(cur) -> List[Dict[str, Any]]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def load_policy(cur) -> Dict[str, Any]:
    cur.execute("SELECT value FROM system_configurations WHERE key = 'attendance_policy';")
    row = cur.fetchone()
    policy = dict(DEFAULT_POLICY)
    if row and row[0]:
        policy.update(row[0])
    return policy


def list_types(cfg: Config) -> List[Dict[str, Any]]:
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT code, name_th, name_en, counts_as, requires_order_ref FROM absence_types "
                "WHERE active ORDER BY sort_order, code;"
            )
            return _rows(cur)


_RECORD_SELECT = (
    "SELECT a.absence_id, a.employee_id::text AS employee_id, h.display_name AS employee_name, h.rank, h.branch, "
    "a.type_code, t.name_th AS type_name_th, t.name_en AS type_name_en, t.counts_as, "
    "a.start_date, a.end_date, (a.end_date - a.start_date + 1) AS days, "
    "a.order_ref, a.destination, a.note, a.status, a.recorded_by, a.recorded_at, "
    "a.cancelled_by, a.cancelled_at, a.cancel_reason "
    "FROM absence_records a "
    "JOIN human_employees h ON h.employee_id = a.employee_id "
    "JOIN absence_types t ON t.code = a.type_code "
)


def list_absences(
    cfg: Config,
    limit: int,
    offset: int,
    employee_id: Optional[str] = None,
    on_or_after: Optional[date] = None,
    on_or_before: Optional[date] = None,
    type_code: Optional[str] = None,
    include_cancelled: bool = False,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if not include_cancelled:
        where.append("a.status = 'RECORDED'")
    if employee_id:
        where.append("a.employee_id = %s")
        params.append(employee_id)
    # Range filters select absences that overlap [on_or_after, on_or_before].
    if on_or_after:
        where.append("a.end_date >= %s")
        params.append(on_or_after)
    if on_or_before:
        where.append("a.start_date <= %s")
        params.append(on_or_before)
    if type_code:
        where.append("a.type_code = %s")
        params.append(type_code)
    if search:
        where.append("(h.display_name ILIKE %s OR a.order_ref ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM absence_records a JOIN human_employees h ON h.employee_id = a.employee_id"
                + where_sql,
                tuple(params),
            )
            total = cur.fetchone()[0]
            cur.execute(
                _RECORD_SELECT + where_sql + " ORDER BY a.start_date DESC, a.absence_id DESC LIMIT %s OFFSET %s",
                tuple(params) + (limit, offset),
            )
            items = _rows(cur)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _get(cur, absence_id: int) -> Optional[Dict[str, Any]]:
    cur.execute(_RECORD_SELECT + "WHERE a.absence_id = %s", (absence_id,))
    rows = _rows(cur)
    return rows[0] if rows else None


def create_absence(
    cfg: Config,
    operator: str,
    employee_id: str,
    type_code: str,
    start_date: date,
    end_date: date,
    order_ref: Optional[str] = None,
    destination: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    if end_date < start_date:
        raise AbsenceError("end_date must be on or after start_date")
    if (end_date - start_date).days > 366:
        raise AbsenceError("an absence cannot span more than one year; record it in parts")
    order_ref = (order_ref or "").strip() or None
    destination = (destination or "").strip() or None
    note = (note or "").strip() or None

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT requires_order_ref FROM absence_types WHERE code = %s AND active;", (type_code,))
            t = cur.fetchone()
            if t is None:
                raise AbsenceError("unknown absence type %s" % type_code)
            if t[0] and not order_ref:
                raise AbsenceError("an order/document reference is required for this absence type")
            cur.execute("SELECT active FROM human_employees WHERE employee_id = %s;", (employee_id,))
            h = cur.fetchone()
            if h is None:
                raise AbsenceError("person %s does not exist" % employee_id)
            if not h[0]:
                raise AbsenceError("person is no longer in the unit")
            try:
                cur.execute(
                    "INSERT INTO absence_records (employee_id, type_code, start_date, end_date, order_ref, "
                    "destination, note, recorded_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING absence_id;",
                    (employee_id, type_code, start_date, end_date, order_ref, destination, note, operator),
                )
            except psycopg2.errors.ExclusionViolation:
                conn.rollback()
                raise AbsenceOverlapError("this person already has a recorded absence on one of these days")
            absence_id = cur.fetchone()[0]
            conn.commit()
            record = _get(cur, absence_id)
    log_sync_event(
        cfg,
        "ABSENCE_RECORDED",
        "absence_id=%s employee_id=%s type=%s %s..%s by=%s"
        % (absence_id, employee_id, type_code, start_date, end_date, operator),
    )
    return record


def cancel_absence(cfg: Config, operator: str, absence_id: int, reason: str) -> Dict[str, Any]:
    if not reason or not reason.strip():
        raise AbsenceError("a reason is required to cancel an absence")
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE absence_records SET status = 'CANCELLED', cancelled_by = %s, cancelled_at = now(), "
                "cancel_reason = %s WHERE absence_id = %s AND status = 'RECORDED' RETURNING absence_id;",
                (operator, reason.strip(), absence_id),
            )
            if cur.fetchone() is None:
                conn.rollback()
                existing = _get(cur, absence_id)
                if existing is None:
                    raise AbsenceNotFound("absence %s does not exist" % absence_id)
                return existing  # already cancelled — idempotent
            conn.commit()
            record = _get(cur, absence_id)
    log_sync_event(cfg, "ABSENCE_CANCELLED", "absence_id=%s by=%s reason=%s" % (absence_id, operator, reason.strip()))
    return record


# --- Holidays ---------------------------------------------------------------


def list_holidays(cfg: Config, year: Optional[int] = None) -> List[Dict[str, Any]]:
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            if year:
                cur.execute(
                    "SELECT holiday_date, name_th FROM holidays WHERE EXTRACT(YEAR FROM holiday_date) = %s "
                    "ORDER BY holiday_date;",
                    (year,),
                )
            else:
                cur.execute("SELECT holiday_date, name_th FROM holidays ORDER BY holiday_date;")
            return _rows(cur)


def upsert_holiday(cfg: Config, operator: str, holiday_date: date, name_th: str) -> Dict[str, Any]:
    name_th = (name_th or "").strip()
    if not name_th:
        raise AbsenceError("holiday name is required")
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO holidays (holiday_date, name_th, created_by) VALUES (%s, %s, %s) "
                "ON CONFLICT (holiday_date) DO UPDATE SET name_th = EXCLUDED.name_th;",
                (holiday_date, name_th, operator),
            )
            conn.commit()
    log_sync_event(cfg, "HOLIDAY_SET", "date=%s name=%s by=%s" % (holiday_date, name_th, operator))
    return {"holiday_date": holiday_date, "name_th": name_th}


def delete_holiday(cfg: Config, operator: str, holiday_date: date) -> None:
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM holidays WHERE holiday_date = %s;", (holiday_date,))
            conn.commit()
    log_sync_event(cfg, "HOLIDAY_DELETED", "date=%s by=%s" % (holiday_date, operator))


# --- Daily roster -------------------------------------------------------------


def classify_person(
    *,
    absence_counts_as: Optional[str],
    scan_exempt: bool,
    first_scan_local: Optional[datetime],
    is_workday: bool,
    late_after: time,
    day_in_progress_before_cutoff: bool,
    tracked: bool = True,
) -> str:
    """One person's status for one day. Order matters: a recorded absence
    wins over everything (they were told not to come), then scan-exempt,
    then fingerprint readiness, then the scan itself.

    `tracked` is false until the day after the person's fingerprint is
    enrolled and verified: before that they cannot scan, so they are
    NOT_ENROLLED — never late or absent."""
    if absence_counts_as:
        return absence_counts_as  # 'LEAVE' or 'DUTY'
    if scan_exempt:
        return "EXEMPT"
    if not tracked:
        return "NOT_ENROLLED" if is_workday else "OFF"
    if first_scan_local is not None:
        if not is_workday:
            return "PRESENT"
        return "LATE" if first_scan_local.time() > late_after else "PRESENT"
    if not is_workday:
        return "OFF"
    if day_in_progress_before_cutoff:
        return "NOT_YET"
    return "ABSENT"


# First day a person is held to scanning: the day after their current
# (open, VERIFIED) fingerprint mapping began. NULL = not enrolled.
_TRACKED_FROM_SQL = (
    "(SELECT (MIN(m.valid_from) AT TIME ZONE %s)::date + 1 FROM employee_device_mappings m "
    " WHERE m.employee_id = h.employee_id AND m.mapping_status = 'VERIFIED' AND m.valid_to IS NULL)"
)


def daily_roster(cfg: Config, day: date, now: Optional[datetime] = None) -> Dict[str, Any]:
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            policy = load_policy(cur)
            tz = ZoneInfo(policy.get("timezone") or "Asia/Bangkok")
            times = policy_times(policy)
            late_after = times["late_after"]
            workdays = set(policy.get("workdays") or [1, 2, 3, 4, 5])
            tz_name_daily = policy.get("timezone") or "Asia/Bangkok"

            cur.execute("SELECT name_th FROM holidays WHERE holiday_date = %s;", (day,))
            hrow = cur.fetchone()
            holiday_name = hrow[0] if hrow else None
            is_workday = day.isoweekday() in workdays and holiday_name is None

            day_start = datetime.combine(day, time(0, 0), tzinfo=tz)
            day_end = day_start + timedelta(days=1)
            win_start, win_end = _window_bounds(day, tz, times)
            cur.execute(
                "SELECT h.employee_id::text AS employee_id, h.display_name, h.rank, h.branch, h.category, "
                "h.scan_exempt, " + _TRACKED_FROM_SQL + " AS tracked_from, a.type_code, t.name_th AS absence_name_th, t.counts_as, a.order_ref, "
                "a.start_date AS absence_start, a.end_date AS absence_end, "
                "(SELECT MIN(l.scan_time) FROM attendance_logs l WHERE l.employee_id = h.employee_id "
                "  AND l.scan_time >= %s AND l.scan_time < %s) AS first_scan, "
                "(SELECT COUNT(*) FROM attendance_logs l WHERE l.employee_id = h.employee_id "
                "  AND l.scan_time >= %s AND l.scan_time < %s "
                "  AND NOT (l.scan_time >= %s AND l.scan_time < %s)) AS scans_outside_window "
                "FROM human_employees h "
                "LEFT JOIN absence_records a ON a.employee_id = h.employee_id AND a.status = 'RECORDED' "
                "  AND %s BETWEEN a.start_date AND a.end_date "
                "LEFT JOIN absence_types t ON t.code = a.type_code "
                "WHERE h.active AND h.production_scope "
                "ORDER BY h.branch NULLS LAST, h.display_name;",
                (tz_name_daily, win_start, win_end, day_start, day_end, win_start, win_end, day),
            )
            people = _rows(cur)

    now = now or datetime.now(tz)
    now_local = now.astimezone(tz)
    # Nobody is absent until the scan window has closed.
    before_cutoff = now_local.date() == day and now_local.time() <= times["end"]
    if now_local.date() < day:
        before_cutoff = True  # future day: nobody is absent yet

    totals = {s: 0 for s in ROSTER_STATUSES}
    by_branch: Dict[str, Dict[str, int]] = {}
    for p in people:
        first = p["first_scan"].astimezone(tz) if p["first_scan"] else None
        status = classify_person(
            absence_counts_as=p["counts_as"],
            scan_exempt=bool(p["scan_exempt"]),
            first_scan_local=first,
            is_workday=is_workday,
            late_after=late_after,
            day_in_progress_before_cutoff=before_cutoff,
            tracked=p["tracked_from"] is not None and day >= p["tracked_from"],
        )
        p["status"] = status
        totals[status] += 1
        branch = p["branch"] or "—"
        bucket = by_branch.setdefault(branch, {s: 0 for s in ROSTER_STATUSES})
        bucket[status] += 1

    return {
        "date": day,
        "is_workday": is_workday,
        "holiday_name": holiday_name,
        "late_after": late_after.strftime("%H:%M"),
        "scan_window": "%s–%s" % (times["start"].strftime("%H:%M"), times["end"].strftime("%H:%M")),
        "total": len(people),
        "totals": totals,
        "by_branch": [{"branch": b, "counts": c} for b, c in by_branch.items()],
        "people": people,
    }


# --- Monthly report -------------------------------------------------------------

# Short codes for the per-day grid (Thai, as used on paper rosters).
STATUS_CODE_TH = {
    "PRESENT": "ม",
    "LATE": "ส",
    "LEAVE": "ล",
    "DUTY": "ร",
    "EXEMPT": "ย",
    "NOT_YET": "",
    "ABSENT": "ข",
    "NOT_ENROLLED": "น",
    "OFF": "-",
}
STATUS_LABEL_TH = {
    "PRESENT": "มา",
    "LATE": "มาสาย",
    "LEAVE": "ลา",
    "DUTY": "ราชการ/ช่วยราชการ",
    "EXEMPT": "ไม่ต้องสแกน",
    "NOT_YET": "ยังไม่ถึง",
    "ABSENT": "ขาด",
    "NOT_ENROLLED": "ยังไม่ลงนิ้ว",
    "OFF": "วันหยุด",
}


def monthly_report(cfg: Config, year: int, month: int, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Per-person, per-day status for one month, using the same rules as
    the daily roster. Future days (and today before the late cutoff) are
    NOT_YET, never ABSENT."""
    first_day = date(year, month, 1)
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    days = [first_day + timedelta(days=i) for i in range((next_month - first_day).days)]

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            policy = load_policy(cur)
            tz_name = policy.get("timezone") or "Asia/Bangkok"
            tz = ZoneInfo(tz_name)
            times = policy_times(policy)
            late_after = times["late_after"]
            workdays = set(policy.get("workdays") or [1, 2, 3, 4, 5])

            cur.execute(
                "SELECT holiday_date, name_th FROM holidays WHERE holiday_date >= %s AND holiday_date < %s;",
                (first_day, next_month),
            )
            holidays = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute(
                "SELECT h.employee_id::text, h.display_name, h.rank, h.branch, h.scan_exempt, "
                + _TRACKED_FROM_SQL
                + " FROM human_employees h WHERE h.active AND h.production_scope "
                "ORDER BY h.branch NULLS LAST, h.display_name;",
                (tz_name,),
            )
            people = [
                {"employee_id": r[0], "display_name": r[1], "rank": r[2], "branch": r[3], "scan_exempt": r[4],
                 "tracked_from": r[5]}
                for r in cur.fetchall()
            ]

            cur.execute(
                "SELECT a.employee_id::text, a.start_date, a.end_date, t.counts_as FROM absence_records a "
                "JOIN absence_types t ON t.code = a.type_code "
                "WHERE a.status = 'RECORDED' AND a.end_date >= %s AND a.start_date < %s;",
                (first_day, next_month),
            )
            absences_by_person: Dict[str, List[Any]] = {}
            for emp, s, e, counts_as in cur.fetchall():
                absences_by_person.setdefault(emp, []).append((s, e, counts_as))

            start_ts = datetime.combine(first_day, time(0, 0), tzinfo=tz)
            end_ts = datetime.combine(next_month, time(0, 0), tzinfo=tz)
            cur.execute(
                "SELECT employee_id::text, (scan_time AT TIME ZONE %s)::date AS d, MIN(scan_time) "
                "FROM attendance_logs WHERE employee_id IS NOT NULL AND scan_time >= %s AND scan_time < %s "
                "AND (scan_time AT TIME ZONE %s)::time >= %s AND (scan_time AT TIME ZONE %s)::time < %s "
                "GROUP BY 1, 2;",
                (
                    tz_name, start_ts, end_ts,
                    tz_name, times["start"], tz_name,
                    (datetime.combine(first_day, times["end"]) + timedelta(minutes=1)).time(),
                ),
            )
            first_scans = {(r[0], r[1]): r[2].astimezone(tz) for r in cur.fetchall()}

    now_local = (now or datetime.now(tz)).astimezone(tz)
    day_meta = []
    for d in days:
        is_workday = d.isoweekday() in workdays and d not in holidays
        pending = d > now_local.date() or (d == now_local.date() and now_local.time() <= times["end"])
        day_meta.append({"date": d, "is_workday": is_workday, "holiday_name": holidays.get(d), "pending": pending})

    by_branch: Dict[str, Dict[str, int]] = {}
    for p in people:
        counts = {s: 0 for s in ROSTER_STATUSES}
        statuses = []
        for m in day_meta:
            d = m["date"]
            counts_as = next(
                (c for s, e, c in absences_by_person.get(p["employee_id"], []) if s <= d <= e), None
            )
            status = classify_person(
                absence_counts_as=counts_as,
                scan_exempt=bool(p["scan_exempt"]),
                first_scan_local=first_scans.get((p["employee_id"], d)),
                is_workday=m["is_workday"],
                late_after=late_after,
                day_in_progress_before_cutoff=m["pending"],
                tracked=p["tracked_from"] is not None and d >= p["tracked_from"],
            )
            # Leave/duty/exempt on a non-working day is just a day off.
            if not m["is_workday"] and status in ("LEAVE", "DUTY", "EXEMPT"):
                status = "OFF"
            statuses.append(status)
            counts[status] += 1
        p["days"] = statuses
        p["counts"] = counts
        bucket = by_branch.setdefault(p["branch"] or "—", {s: 0 for s in ROSTER_STATUSES})
        for s, n in counts.items():
            bucket[s] += n

    return {
        "month": "%04d-%02d" % (year, month),
        "late_after": late_after.strftime("%H:%M"),
        "scan_window": "%s–%s" % (times["start"].strftime("%H:%M"), times["end"].strftime("%H:%M")),
        "workdays": sum(1 for m in day_meta if m["is_workday"]),
        "days": [{k: m[k] for k in ("date", "is_workday", "holiday_name")} for m in day_meta],
        "people": people,
        "by_branch": [{"branch": b, "counts": c} for b, c in by_branch.items()],
    }


def monthly_report_csv(report: Dict[str, Any]) -> str:
    """Excel-friendly CSV (UTF-8 with BOM so Thai renders in Excel): one row
    per person, one column per day using short Thai codes, then totals."""
    import csv
    import io

    totals_order = ["PRESENT", "LATE", "LEAVE", "DUTY", "ABSENT"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["รายงานการมาปฏิบัติงานประจำเดือน", report["month"], "ช่วงสแกน", report.get("scan_window", ""),
                "มาสายหลัง", report["late_after"], "วันทำงาน", report["workdays"]])
    w.writerow(["รหัส: " + "  ".join(f"{STATUS_CODE_TH[s]}={STATUS_LABEL_TH[s]}" for s in STATUS_CODE_TH if STATUS_CODE_TH[s])])
    w.writerow(
        ["ลำดับ", "ยศ", "ชื่อ-สกุล", "แผนก"]
        + [str(d["date"].day) for d in report["days"]]
        + [STATUS_LABEL_TH[s] for s in totals_order]
    )
    for i, p in enumerate(report["people"], 1):
        w.writerow(
            [i, p["rank"] or "", p["display_name"], p["branch"] or ""]
            + [STATUS_CODE_TH[s] for s in p["days"]]
            + [p["counts"][s] for s in totals_order]
        )
    return "﻿" + buf.getvalue()


# --- Fingerprint readiness -------------------------------------------------------


def readiness(cfg: Config) -> Dict[str, Any]:
    """Per-section fingerprint readiness for the people held to scanning
    (active, in scope). Exempt people are counted separately and never
    'missing'."""
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(h.branch, '—') AS branch, "
                "COUNT(*) AS total, "
                "COUNT(*) FILTER (WHERE h.scan_exempt) AS exempt, "
                "COUNT(*) FILTER (WHERE NOT h.scan_exempt AND EXISTS ("
                "  SELECT 1 FROM employee_device_mappings m WHERE m.employee_id = h.employee_id "
                "  AND m.mapping_status = 'VERIFIED' AND m.valid_to IS NULL)) AS enrolled "
                "FROM human_employees h WHERE h.active AND h.production_scope "
                "GROUP BY 1 ORDER BY 1;"
            )
            rows = _rows(cur)
    out = []
    for r in rows:
        required = r["total"] - r["exempt"]
        r["required"] = required
        r["missing"] = required - r["enrolled"]
        r["percent"] = round(100 * r["enrolled"] / required) if required else 100
        out.append(r)
    total = {k: sum(r[k] for r in out) for k in ("total", "exempt", "enrolled", "required", "missing")}
    total["percent"] = round(100 * total["enrolled"] / total["required"]) if total["required"] else 100
    return {"branches": out, "total": total}
