"""
Controlled VERIFIED Human <-> Device mapping creation.

PromptID: ADMS-Data-HumanDeviceMapping-003

Creates EXACTLY ONE VERIFIED temporal mapping from controlled-scan pilot
evidence. This is the single canonical path by which production ownership is
recorded; the enrollment module (app/enrollment.py) never creates mappings.

Safety invariants enforced here:

- Exactly one VERIFIED mapping per call. No bulk, no automatic, no
  name/rank/Excel-row/numeric-equality mapping.
- The mapping Human is the owner-confirmed pilot Human; the valid_from is the
  recorded controlled-scan timestamp (evidence-backed ownership boundary).
- All preconditions are re-verified inside the same transaction:
    * device user exists and is active
    * Human exists and is active
    * enrollment is READY_FOR_MAPPING and matches (Human, device account)
    * controlled-scan attendance evidence still exists and matches the
      recorded controlled_scan_time exactly
    * no conflicting VERIFIED mapping (open-ended or overlapping) exists
- Attendance rows are NEVER modified here (no employee_id backfill). The
  temporal resolver attributes new events automatically; historical
  reconciliation is a separate, separately-authorized phase.
- No terminal access and no biometric data access.
"""

import logging
from typing import Any, Dict, Optional

from app.config import Config
from app.db import get_db_connection, log_sync_event

log = logging.getLogger(__name__)

VERIFIED = "VERIFIED"
VERIFICATION_METHOD_CONTROLLED_SCAN = "CONTROLLED_SCAN"
MAPPING_SOURCE_CONTROLLED_SCAN = "CONTROLLED_SCAN"


class MappingError(Exception):
    """Raised when a mapping operation violates a safety or evidence rule."""


def _fetch_row(cur: Any, sql: str, params: tuple) -> Optional[tuple]:
    cur.execute(sql, params)
    return cur.fetchone()


def create_verified_mapping(
    cfg: Config,
    employee_id: str,
    device_user_pk: int,
    enrollment_id: int,
    controlled_attendance_id: int,
    verified_by: str,
    verification_note: str,
) -> Dict[str, Any]:
    """
    Creates exactly ONE VERIFIED temporal mapping.

    Args:
        cfg: application Config (DB connection).
        employee_id: the owner-confirmed pilot Human (UUID).
        device_user_pk: the device_users primary key for the production account.
        enrollment_id: the READY_FOR_MAPPING enrollment row.
        controlled_attendance_id: the controlled-scan attendance event id that
            constitutes the physical identity evidence.
        verified_by: explicit operator/owner identity.
        verification_note: audit note; must reference the pilot evidence.

    Returns the inserted mapping row (mapping_id, valid_from, verified_at).
    """
    if not verified_by or not str(verified_by).strip():
        raise MappingError("verified_by (operator) is required for a VERIFIED mapping")
    if not verification_note or not str(verification_note).strip():
        raise MappingError("verification_note is required for a VERIFIED mapping")

    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            # 1. Device user must exist and be active.
            du = _fetch_row(
                cur,
                "SELECT device_user_id, device_id, active "
                "FROM device_users WHERE device_user_pk = %s;",
                (device_user_pk,),
            )
            if du is None:
                raise MappingError(
                    "device_user_pk %s does not exist" % device_user_pk
                )
            device_user_id, device_id, du_active = du
            if not du_active:
                raise MappingError(
                    "device_user_pk %s is inactive — mapping not allowed" % device_user_pk
                )

            # 2. Human must exist and be active.
            hm = _fetch_row(
                cur,
                "SELECT active FROM human_employees WHERE employee_id = %s;",
                (employee_id,),
            )
            if hm is None:
                raise MappingError("Human %s does not exist" % employee_id)
            if not hm[0]:
                raise MappingError("Human %s is inactive — mapping not allowed" % employee_id)

            # 3. Enrollment must be READY_FOR_MAPPING and match this Human/device.
            enroll = _fetch_row(
                cur,
                "SELECT employee_id, device_id, reserved_device_user_id, status, "
                "controlled_scan_time, confirmed_by "
                "FROM device_user_enrollments WHERE enrollment_id = %s;",
                (enrollment_id,),
            )
            if enroll is None:
                raise MappingError("enrollment %s does not exist" % enrollment_id)
            (
                enroll_employee_id,
                enroll_device_id,
                enroll_terminal_id,
                enroll_status,
                enroll_scan_time,
                enroll_confirmed_by,
            ) = enroll
            if enroll_status != "READY_FOR_MAPPING":
                raise MappingError(
                    "enrollment %s is in state %s, expected READY_FOR_MAPPING"
                    % (enrollment_id, enroll_status)
                )
            if str(enroll_employee_id) != str(employee_id):
                raise MappingError(
                    "enrollment %s belongs to a different Human — mapping refused"
                    % enrollment_id
                )
            if enroll_device_id != device_id:
                raise MappingError(
                    "enrollment %s is on a different device — mapping refused"
                    % enrollment_id
                )
            if str(enroll_terminal_id) != str(device_user_id):
                raise MappingError(
                    "enrollment terminal account %s does not match device user %s "
                    "(pk %s) — mapping refused"
                    % (enroll_terminal_id, device_user_id, device_user_pk)
                )
            if enroll_scan_time is None:
                raise MappingError(
                    "enrollment %s has no controlled_scan_time — evidence missing"
                    % enrollment_id
                )
            valid_from = enroll_scan_time
            if enroll_confirmed_by is None:
                raise MappingError(
                    "enrollment %s has no confirmed_by — owner confirmation missing"
                    % enrollment_id
                )

            # 4. Controlled-scan attendance evidence must still exist and match.
            att = _fetch_row(
                cur,
                "SELECT id, device_user_pk, scan_time, employee_id "
                "FROM attendance_logs WHERE id = %s;",
                (controlled_attendance_id,),
            )
            if att is None:
                raise MappingError(
                    "controlled attendance id %s does not exist" % controlled_attendance_id
                )
            att_id, att_pk, att_scan_time, att_employee_id = att
            if att_pk != device_user_pk:
                raise MappingError(
                    "attendance id %s is for device_user_pk %s, expected %s"
                    % (att_id, att_pk, device_user_pk)
                )
            if att_scan_time != valid_from:
                raise MappingError(
                    "attendance id %s scan_time %s does not match enrollment "
                    "controlled_scan_time %s"
                    % (att_id, att_scan_time.isoformat(), valid_from.isoformat())
                )

            # 5. No conflicting VERIFIED mapping for this device user.
            conflict = _fetch_row(
                cur,
                "SELECT 1 FROM employee_device_mappings "
                "WHERE device_user_pk = %s AND mapping_status = 'VERIFIED' "
                "AND (valid_to IS NULL OR valid_to > %s) LIMIT 1;",
                (device_user_pk, valid_from),
            )
            if conflict is not None:
                raise MappingError(
                    "a conflicting VERIFIED mapping already exists for device_user_pk %s"
                    % device_user_pk
                )

            # 6. Insert exactly one VERIFIED mapping.
            cur.execute(
                "INSERT INTO employee_device_mappings ("
                "  employee_id, device_user_pk, mapping_status, mapping_source,"
                "  verified_by, verification_method, verification_note,"
                "  valid_from, valid_to, verified_at"
                ") VALUES (%s, %s, 'VERIFIED', %s, %s, %s, %s, %s, NULL, now()) "
                "RETURNING mapping_id, valid_from, verified_at;",
                (
                    employee_id,
                    device_user_pk,
                    MAPPING_SOURCE_CONTROLLED_SCAN,
                    verified_by,
                    VERIFICATION_METHOD_CONTROLLED_SCAN,
                    verification_note,
                    valid_from,
                ),
            )
            row = cur.fetchone()
            if row is None:
                raise MappingError("mapping insert failed")
            conn.commit()

    log_sync_event(
        cfg,
        "MAPPING_VERIFIED",
        "mapping_id=%s employee_id=%s device_user_pk=%s valid_from=%s verified_by=%s"
        % (row[0], employee_id, device_user_pk, valid_from.isoformat(), verified_by),
    )
    return {
        "mapping_id": row[0],
        "valid_from": valid_from,
        "verified_at": row[2],
        "employee_id": employee_id,
        "device_user_pk": device_user_pk,
        "mapping_status": VERIFIED,
        "verification_method": VERIFICATION_METHOD_CONTROLLED_SCAN,
        "valid_to": None,
    }
