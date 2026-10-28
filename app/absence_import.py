"""Bulk absence import from the downloadable CSV template.

Template: app/templates/absence_import_template.csv (UTF-8 BOM, opens in Excel).
Rows whose first cell starts with '#' are examples/comments and are skipped.
Person = รหัสกำลังพล (employee_id or personnel_id), falling back to an exact
display-name match. Type = code (SICK) or Thai name (ลาป่วย). Dates accept
YYYY-MM-DD or D/M/YYYY with a Buddhist (>2400) or Christian year.

Preview validates everything without writing; commit writes only when every
row is valid (all-or-nothing up front), then records each row through
absences.create_absence so overlap checks and audit logging stay identical
to a manual entry.
"""

import csv
import io
import os
import re
from datetime import date
from typing import Any, Dict, List, Optional

from app import absences
from app.config import Config
from app.db import get_db_connection

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "absence_import_template.csv")
MAX_ROWS = 1000


def template_bytes() -> bytes:
    with open(TEMPLATE_PATH, "rb") as f:
        return f.read()


def parse_date(value: str) -> date:
    v = value.strip()
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", v):
        y, m, d = (int(x) for x in v.split("-"))
    else:
        m_ = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", v)
        if not m_:
            raise ValueError("รูปแบบวันที่ไม่ถูกต้อง: %r (ใช้ 10/11/2569)" % value)
        d, m, y = (int(x) for x in m_.groups())
    if y > 2400:
        y -= 543
    return date(y, m, d)


def _lookups(cfg: Config) -> tuple:
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT employee_id, personnel_id, display_name, rank FROM human_employees "
                "WHERE active AND production_scope;"
            )
            people = cur.fetchall()
            cur.execute("SELECT code, name_th, requires_order_ref FROM absence_types WHERE active;")
            types = cur.fetchall()
    by_id: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for emp, pid, name, rank in people:
        p = {"employee_id": emp, "name": ("%s %s" % (rank, name)).strip() if rank else name}
        by_id[str(emp)] = p
        if pid:
            by_id.setdefault(str(pid).strip(), p)
        by_name.setdefault(name.strip(), []).append(p)
    type_map: Dict[str, str] = {}
    needs_order = set()
    for code, name_th, requires_order in types:
        type_map[code.upper()] = code
        type_map[name_th.strip()] = code
        if requires_order:
            needs_order.add(code)
    return by_id, by_name, type_map, needs_order


def _cell(row: List[str], i: int) -> str:
    return row[i].strip() if i < len(row) else ""


def validate(cfg: Config, text: str) -> Dict[str, Any]:
    by_id, by_name, type_map, needs_order = _lookups(cfg)
    rows = list(csv.reader(io.StringIO(text)))
    out: List[Dict[str, Any]] = []
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row) or _cell(row, 0).startswith("#"):
            continue
        if len(out) >= MAX_ROWS:
            raise ValueError("ไฟล์มีเกิน %d แถว" % MAX_ROWS)
        errors: List[str] = []
        key, name = _cell(row, 0), _cell(row, 1)
        person = by_id.get(key) if key else None
        if person is None and name:
            # Name column may carry a rank prefix; try the full cell, then the last two words.
            cands = by_name.get(name) or by_name.get(" ".join(name.split()[-2:]), [])
            if len(cands) == 1:
                person = cands[0]
            elif len(cands) > 1:
                errors.append("ชื่อซ้ำหลายคน ใส่รหัสกำลังพล")
        if person is None and not errors:
            errors.append("ไม่พบกำลังพล (รหัส %r)" % key if key else "ไม่พบกำลังพล")
        type_raw = _cell(row, 2)
        type_code = type_map.get(type_raw.upper()) or type_map.get(type_raw)
        if not type_code:
            errors.append("ไม่รู้จักประเภท %r" % type_raw)
        start = end = None
        try:
            start = parse_date(_cell(row, 3))
            end = parse_date(_cell(row, 4)) if _cell(row, 4) else start
            if end < start:
                errors.append("วันสิ้นสุดก่อนวันเริ่ม")
        except ValueError as e:
            errors.append(str(e))
        order_ref = _cell(row, 5) or None
        if type_code in needs_order and not order_ref:
            errors.append("ประเภทนี้ต้องมีเลขที่คำสั่ง")
        out.append(
            {
                "line": line_no,
                "employee_id": person["employee_id"] if person else None,
                "name": person["name"] if person else name or key,
                "type_code": type_code,
                "start_date": start,
                "end_date": end,
                "order_ref": order_ref,
                "destination": _cell(row, 6) or None,
                "note": _cell(row, 7) or None,
                "errors": errors,
            }
        )
    return {"rows": out, "valid": sum(1 for r in out if not r["errors"]), "invalid": sum(1 for r in out if r["errors"])}


def commit(cfg: Config, operator: str, text: str) -> Dict[str, Any]:
    result = validate(cfg, text)
    if result["invalid"] or not result["rows"]:
        return {**result, "created": 0}
    created = 0
    for r in result["rows"]:
        try:
            absences.create_absence(
                cfg, operator, r["employee_id"], r["type_code"], r["start_date"], r["end_date"],
                order_ref=r["order_ref"], destination=r["destination"], note=r["note"],
            )
            created += 1
        except absences.AbsenceError as e:
            r["errors"].append("บันทึกไม่ได้: %s" % e)
    result["invalid"] = sum(1 for r in result["rows"] if r["errors"])
    result["valid"] = len(result["rows"]) - result["invalid"]
    return {**result, "created": created}


def decode(raw: bytes) -> Optional[str]:
    for enc in ("utf-8-sig", "cp874"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None
