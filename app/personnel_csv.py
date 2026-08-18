"""
Personnel CSV export/import.

PromptID: ADMS-Personnel-MasterData-024, revised by
ADMS-PersonnelIdentity-AttendanceClosure-025.

Export is read-only, never gated by Write Session. Import is a strict
two-phase preview-then-commit flow: preview (`classify_csv_rows`) NEVER
writes to the database — it only parses and validates — and commit
(`commit_csv_rows`) re-validates the exact same rows before writing, in
one transaction, so a caller can never accidentally commit something that
was never previewed.

OWNER CORRECTION (025): PromptID 024 mistakenly made `personnel_id` the
CSV matching key and required it on every row. `personnel_id` is an
OPTIONAL business field that may be NULL — production has 120 legitimate
legacy Humans with no personnel_id, and that is expected, not a
data-quality defect. It must never be required to add, edit, or
CSV-import a Human.

Matching key is now `human_employees.employee_id` — the system's own
canonical UUID, present only in files this system itself exported
(round-trip identity). Two import modes, inferred from whether a row's
`employee_id` column is populated (never from a separate UI toggle):

  Mode 1 — ADMS round-trip file (row has employee_id):
    valid, existing employee_id  -> UPDATE or UNCHANGED
    employee_id present but does not match any Human -> ERROR (friendly
      "please re-export and try again" — never silently created under
      that UUID, never silently ignored)

  Mode 2 — external/new-personnel file (row has no employee_id):
    always classified NEW. If an existing Human already has the exact
    same display_name, a non-blocking `warning_th` advisory is attached
    so an ADMIN can check they are not creating a duplicate — but the
    row is never auto-merged/updated against that existing Human. Name
    matching is advisory only, never authoritative identity.

`personnel_id` is never used for row matching, in either mode. It is
merely one more optional field on the row's data, exactly like `branch`
or `category`. Duplicate `personnel_id` values (in-file or against an
existing different Human) are still rejected — that is the schema's own
UNIQUE constraint, unrelated to import matching semantics.

Import never deletes, deactivates, or touches any Human absent from the
CSV — Personnel Lifecycle (019) remains the only path to deactivation.
Import never creates a terminal account, Enrollment, or Mapping.
"""

import csv
import io
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.config import Config
from app.db import get_db_connection, log_sync_event
from app.personnel import SOURCE_ADMS_MANUAL
from app.rtn_ranks import RTN_RANK_CATALOG

log = logging.getLogger(__name__)

# Full round-trip export: includes the system identity column so a
# re-imported copy of this exact file can update the correct row.
EXPORT_CSV_COLUMNS = [
    "employee_id",
    "personnel_id",
    "rank",
    "display_name",
    "english_name",
    "branch",
    "category",
    "active",
]

# Blank template for adding brand-new personnel: deliberately omits
# employee_id (nothing to round-trip yet) and never requires personnel_id.
TEMPLATE_CSV_COLUMNS = [
    "personnel_id",
    "rank",
    "display_name",
    "english_name",
    "branch",
    "category",
    "active",
]

# Written first for Excel-on-Windows Thai-text compatibility.
UTF8_BOM = "﻿"


class PersonnelCsvError(Exception):
    """Raised for a malformed CSV that cannot be parsed at all (e.g.
    missing required header) — distinct from a single bad row, which is
    reported per-row instead of raising."""


def build_csv_template() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(TEMPLATE_CSV_COLUMNS)
    writer.writerow(["", "พ.จ.อ.", "ตัวอย่าง ทดสอบ", "Example Test", "อล.", "พันจ่า", "true"])
    return UTF8_BOM + buf.getvalue()


def export_humans_csv(cfg: Config, active: Optional[bool] = None) -> str:
    """Read-only export — never gated by Write Session. `active=None`
    exports all; True/False filters, mirroring the existing Personnel page
    filter semantics. Includes employee_id so a re-imported copy of this
    exact file safely round-trips updates to the correct row — ordinary
    UI never needs to show or type this value; it only matters for this
    export -> edit -> re-import cycle."""
    where = ""
    params: tuple = ()
    if active is not None:
        where = " WHERE active = %s"
        params = (active,)
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT employee_id, personnel_id, rank, display_name, english_name, branch, category, active "
                f"FROM human_employees{where} ORDER BY display_name;",
                params,
            )
            rows = cur.fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_CSV_COLUMNS)
    for r in rows:
        employee_id, personnel_id, rank, display_name, english_name, branch, category, active_val = r
        writer.writerow(
            [
                str(employee_id),
                personnel_id or "",
                rank or "",
                display_name or "",
                english_name or "",
                branch or "",
                category or "",
                "true" if active_val else "false",
            ]
        )
    return UTF8_BOM + buf.getvalue()


def _parse_bool(raw: str) -> Optional[bool]:
    v = (raw or "").strip().lower()
    if v in ("true", "1", "yes", "y", "ใช้งานอยู่"):
        return True
    if v in ("false", "0", "no", "n", "ย้ายออกแล้ว", ""):
        return False
    return None


def _row_error(row_number: int, reason_key: str, reason_th: str) -> Dict[str, Any]:
    return {
        "row_number": row_number,
        "classification": "ERROR",
        "reason_key": reason_key,
        "reason_th": "แถว %d: %s" % (row_number, reason_th),
    }


def classify_csv_rows(cfg: Config, csv_text: str) -> Dict[str, Any]:
    """Parses + validates a CSV, NEVER writes to the database. Returns
    {summary: {new, update, unchanged, error}, rows: [...]}.

    Matching is by `employee_id` only (see module docstring). A row with
    no `employee_id` column/value is always a NEW candidate — it is never
    required to carry a personnel_id."""
    text = csv_text.lstrip(UTF8_BOM)
    try:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise PersonnelCsvError("empty file")
        header = [h.strip() for h in reader.fieldnames]
    except csv.Error as e:
        raise PersonnelCsvError(str(e))

    required = {"display_name"}
    missing_required = required - set(header)
    if missing_required:
        raise PersonnelCsvError(
            "missing required column(s): %s" % ", ".join(sorted(missing_required))
        )

    seen_employee_ids: Dict[str, int] = {}
    seen_personnel_ids: Dict[str, int] = {}
    results: List[Dict[str, Any]] = []

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            for idx, raw_row in enumerate(reader, start=2):  # header is row 1
                employee_id_raw = (raw_row.get("employee_id") or "").strip() or None
                personnel_id = (raw_row.get("personnel_id") or "").strip() or None
                display_name = (raw_row.get("display_name") or "").strip()
                rank = (raw_row.get("rank") or "").strip() or None
                english_name = (raw_row.get("english_name") or "").strip() or None
                branch = (raw_row.get("branch") or "").strip() or None
                category = (raw_row.get("category") or "").strip() or None
                active_raw = raw_row.get("active")
                active = _parse_bool(active_raw) if active_raw not in (None, "") else True

                if not display_name:
                    results.append(_row_error(idx, "MISSING_DISPLAY_NAME", "ไม่มีชื่อ-นามสกุล"))
                    continue
                if rank is not None and rank not in RTN_RANK_CATALOG:
                    results.append(_row_error(idx, "UNKNOWN_RANK", "ไม่พบยศนี้"))
                    continue

                candidate = {
                    "personnel_id": personnel_id,
                    "display_name": display_name,
                    "english_name": english_name,
                    "rank": rank,
                    "branch": branch,
                    "category": category,
                    "active": active,
                }

                # --- personnel_id uniqueness (optional field, still unique when present) ---
                if personnel_id is not None:
                    if personnel_id in seen_personnel_ids:
                        results.append(_row_error(idx, "DUPLICATE_PERSONNEL_ID_IN_FILE", "หมายเลขประจำตัวซ้ำในไฟล์นี้"))
                        continue
                    cur.execute(
                        "SELECT employee_id FROM human_employees WHERE personnel_id = %s;",
                        (personnel_id,),
                    )
                    existing_owner = cur.fetchone()
                    if existing_owner is not None and str(existing_owner[0]) != employee_id_raw:
                        results.append(
                            _row_error(idx, "DUPLICATE_PERSONNEL_ID", "หมายเลขประจำตัวนี้มีอยู่ในระบบแล้ว กับกำลังพลรายอื่น")
                        )
                        continue
                    seen_personnel_ids[personnel_id] = idx

                # --- Mode 1: round-trip update, matched by employee_id ---
                if employee_id_raw is not None:
                    try:
                        uuid.UUID(employee_id_raw)
                    except ValueError:
                        results.append(
                            _row_error(idx, "INVALID_REFERENCE", "ไม่พบรายการกำลังพลเดิมที่ไฟล์นี้อ้างอิง กรุณาส่งออกไฟล์ใหม่จากระบบแล้วลองอีกครั้ง")
                        )
                        continue
                    if employee_id_raw in seen_employee_ids:
                        results.append(_row_error(idx, "DUPLICATE_REFERENCE_IN_FILE", "ไฟล์นี้อ้างอิงกำลังพลรายเดียวกันซ้ำหลายแถว"))
                        continue
                    seen_employee_ids[employee_id_raw] = idx

                    cur.execute(
                        "SELECT employee_id, display_name, english_name, rank, branch, category, active, personnel_id "
                        "FROM human_employees WHERE employee_id = %s;",
                        (employee_id_raw,),
                    )
                    existing = cur.fetchone()
                    if existing is None:
                        results.append(
                            _row_error(idx, "REFERENCE_NOT_FOUND", "ไม่พบรายการกำลังพลเดิมที่ไฟล์นี้อ้างอิง กรุณาส่งออกไฟล์ใหม่จากระบบแล้วลองอีกครั้ง")
                        )
                        continue

                    (emp_id, ex_name, ex_en, ex_rank, ex_branch, ex_category, ex_active, ex_pid) = existing
                    existing_dict = {
                        "display_name": ex_name,
                        "english_name": ex_en,
                        "rank": ex_rank,
                        "branch": ex_branch,
                        "category": ex_category,
                        "active": ex_active,
                        "personnel_id": ex_pid,
                    }
                    changed = {k: v for k, v in candidate.items() if existing_dict.get(k) != v}
                    if changed:
                        results.append(
                            {
                                "row_number": idx,
                                "classification": "UPDATE",
                                "employee_id": str(emp_id),
                                "data": candidate,
                                "changed_fields": sorted(changed.keys()),
                            }
                        )
                    else:
                        results.append(
                            {
                                "row_number": idx,
                                "classification": "UNCHANGED",
                                "employee_id": str(emp_id),
                                "data": candidate,
                            }
                        )
                    continue

                # --- Mode 2: external/new-personnel row, always NEW ---
                warning_th: Optional[str] = None
                cur.execute(
                    "SELECT 1 FROM human_employees WHERE display_name = %s LIMIT 1;",
                    (display_name,),
                )
                if cur.fetchone() is not None:
                    warning_th = (
                        "แถว %d: มีชื่อ “%s” อยู่ในระบบแล้ว กรุณาตรวจสอบว่าไม่ใช่บุคคลเดียวกันก่อนเพิ่มใหม่"
                        % (idx, display_name)
                    )
                row_result: Dict[str, Any] = {
                    "row_number": idx,
                    "classification": "NEW",
                    "data": candidate,
                }
                if warning_th:
                    row_result["warning_th"] = warning_th
                results.append(row_result)

    summary = {"new": 0, "update": 0, "unchanged": 0, "error": 0}
    for r in results:
        summary[r["classification"].lower()] += 1
    return {"summary": summary, "rows": results}


def commit_csv_rows(cfg: Config, csv_text: str, operator: str) -> Dict[str, Any]:
    """Re-validates the SAME csv_text (never trusts a stale client-held
    preview) and writes only NEW/UPDATE rows inside one transaction. ERROR
    rows are skipped and reported — never silently dropped, never block
    the valid rows (all-valid-rows-commit, invalid-rows-reported policy,
    disclosed explicitly to the operator in the UI). UNCHANGED rows are
    skipped as a no-op. No Human absent from the file is touched."""
    preview = classify_csv_rows(cfg, csv_text)
    created = 0
    updated = 0
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            for r in preview["rows"]:
                if r["classification"] == "NEW":
                    d = r["data"]
                    cur.execute(
                        "INSERT INTO human_employees "
                        "(display_name, rank, english_name, personnel_id, branch, category, "
                        " active, production_scope, source) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, true, %s);",
                        (
                            d["display_name"], d["rank"], d["english_name"], d["personnel_id"],
                            d["branch"], d["category"], d["active"], SOURCE_ADMS_MANUAL,
                        ),
                    )
                    created += 1
                elif r["classification"] == "UPDATE":
                    d = r["data"]
                    cur.execute(
                        "UPDATE human_employees SET display_name=%s, rank=%s, english_name=%s, "
                        "personnel_id=%s, branch=%s, category=%s, active=%s, updated_at=now() "
                        "WHERE employee_id=%s;",
                        (
                            d["display_name"], d["rank"], d["english_name"], d["personnel_id"],
                            d["branch"], d["category"], d["active"], r["employee_id"],
                        ),
                    )
                    updated += 1
            conn.commit()

    log_sync_event(
        cfg,
        "PERSONNEL_CSV_IMPORT",
        "operator=%s created=%d updated=%d unchanged=%d errors=%d"
        % (operator, created, updated, preview["summary"]["unchanged"], preview["summary"]["error"]),
    )
    return {
        "created": created,
        "updated": updated,
        "unchanged": preview["summary"]["unchanged"],
        "errors": preview["summary"]["error"],
    }
