"""
Personnel CSV export/import.

PromptID: ADMS-Personnel-MasterData-024

Export is read-only, never gated by Write Session. Import is a strict
two-phase preview-then-commit flow: preview (`classify_csv_rows`) NEVER
writes to the database — it only parses and validates — and commit
(`commit_csv_rows`) re-validates the exact same rows before writing, in
one transaction, so a caller can never accidentally commit something that
was never previewed.

Matching key: `human_employees.personnel_id` ONLY — the schema's own
UNIQUE constraint, never `display_name` (Thai naming conventions make
name-only matching unreliable; two different people can share a name,
and CSV row order must never silently merge them).

Production data-quality note (this PromptID's Phase 16 audit): as of this
implementation, 0 of 120 existing production Human rows have a populated
`personnel_id` — every existing row was Excel-imported before this field
was consistently populated. This means CSV import cannot yet UPDATE any
existing legacy row (there is nothing to match against) — every legacy
Human must first be assigned a personnel_id via the Edit Personnel form
before a CSV row can ever match it. This is a genuine, disclosed
limitation, not a bug: import correctness depends on NOT inventing a
name-based fallback matcher.

Import never deletes, deactivates, or touches any Human absent from the
CSV — Personnel Lifecycle (019) remains the only path to deactivation.
Import never creates a terminal account, Enrollment, or Mapping.
"""

import csv
import io
import logging
from typing import Any, Dict, List, Optional

from app.config import Config
from app.db import get_db_connection, log_sync_event
from app.personnel import SOURCE_ADMS_MANUAL
from app.rtn_ranks import RTN_RANK_CATALOG

log = logging.getLogger(__name__)

CSV_COLUMNS = [
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
    writer.writerow(CSV_COLUMNS)
    writer.writerow(["", "พ.จ.อ.", "ตัวอย่าง ทดสอบ", "Example Test", "อล.", "พันจ่า", "true"])
    return UTF8_BOM + buf.getvalue()


def export_humans_csv(cfg: Config, active: Optional[bool] = None) -> str:
    """Read-only export — never gated by Write Session. `active=None`
    exports all; True/False filters, mirroring the existing Personnel page
    filter semantics."""
    where = ""
    params: tuple = ()
    if active is not None:
        where = " WHERE active = %s"
        params = (active,)
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT personnel_id, rank, display_name, english_name, branch, category, active "
                f"FROM human_employees{where} ORDER BY display_name;",
                params,
            )
            rows = cur.fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for r in rows:
        personnel_id, rank, display_name, english_name, branch, category, active_val = r
        writer.writerow(
            [
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
    {summary: {new, update, unchanged, error}, rows: [...]}."""
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

    seen_personnel_ids: Dict[str, int] = {}
    results: List[Dict[str, Any]] = []

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            for idx, raw_row in enumerate(reader, start=2):  # header is row 1
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
                if not personnel_id:
                    results.append(_row_error(idx, "MISSING_PERSONNEL_ID", "ไม่มีหมายเลขประจำตัว"))
                    continue
                if personnel_id in seen_personnel_ids:
                    results.append(_row_error(idx, "DUPLICATE_IN_FILE", "หมายเลขประจำตัวซ้ำ"))
                    continue
                seen_personnel_ids[personnel_id] = idx

                cur.execute(
                    "SELECT employee_id, display_name, english_name, rank, branch, category, active "
                    "FROM human_employees WHERE personnel_id = %s;",
                    (personnel_id,),
                )
                existing = cur.fetchone()

                candidate = {
                    "personnel_id": personnel_id,
                    "display_name": display_name,
                    "english_name": english_name,
                    "rank": rank,
                    "branch": branch,
                    "category": category,
                    "active": active,
                }

                if existing is None:
                    results.append(
                        {
                            "row_number": idx,
                            "classification": "NEW",
                            "data": candidate,
                        }
                    )
                    continue

                (emp_id, ex_name, ex_en, ex_rank, ex_branch, ex_category, ex_active) = existing
                existing_dict = {
                    "display_name": ex_name,
                    "english_name": ex_en,
                    "rank": ex_rank,
                    "branch": ex_branch,
                    "category": ex_category,
                    "active": ex_active,
                }
                changed = {
                    k: v for k, v in candidate.items()
                    if k != "personnel_id" and existing_dict.get(k) != v
                }
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
                        "branch=%s, category=%s, active=%s, updated_at=now() "
                        "WHERE employee_id=%s;",
                        (
                            d["display_name"], d["rank"], d["english_name"],
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
