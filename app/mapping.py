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
from app.mapping_evidence import resolve_controlled_attendance_id

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
    enrollment_id: int,
    verified_by: str,
    verification_note: str,
) -> Dict[str, Any]:
    """
    Creates exactly ONE VERIFIED temporal mapping from a READY_FOR_MAPPING
    enrollment.

    ADMS-FullEnrollment-E2E-Closure-017: `employee_id`, `device_user_pk`,
    and `controlled_attendance_id` are ALL derived server-side from the
    enrollment row itself — the caller (an ADMIN confirming Step 6) never
    supplies them. This closes the entire "frontend reconstructs
    security-critical identity evidence from stale/nullable data" bug
    class: there is no longer any client-suppliable field this function
    would have to independently re-validate against a second, potentially
    drifting piece of client input. controlled_attendance_id resolution
    uses the single canonical resolver (app.mapping_evidence), the same
    one app.api.repository.mapping_eligibility() uses to advertise
    eligibility in the first place — never two independently-drifting
    implementations of "which attendance row is the evidence."

    Args:
        cfg: application Config (DB connection).
        enrollment_id: the READY_FOR_MAPPING enrollment row.
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
            # 1. Enrollment must exist and be READY_FOR_MAPPING.
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
                employee_id,
                device_id,
                reserved_device_user_id,
                enroll_status,
                enroll_scan_time,
                enroll_confirmed_by,
            ) = enroll
            if enroll_status != "READY_FOR_MAPPING":
                raise MappingError(
                    "enrollment %s is in state %s, expected READY_FOR_MAPPING"
                    % (enrollment_id, enroll_status)
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

            # 2. Device user must exist and be active — derived from the
            # enrollment's own (device_id, reserved_device_user_id), not
            # supplied by the caller.
            du = _fetch_row(
                cur,
                "SELECT device_user_pk, active FROM device_users "
                "WHERE device_id = %s AND device_user_id = %s;",
                (device_id, reserved_device_user_id),
            )
            if du is None:
                raise MappingError(
                    "no device_users row for enrollment %s's terminal account "
                    "(device_id=%s, device_user_id=%s) — was it ever created?"
                    % (enrollment_id, device_id, reserved_device_user_id)
                )
            device_user_pk, du_active = du
            if not du_active:
                raise MappingError(
                    "device_user_pk %s is inactive — mapping not allowed" % device_user_pk
                )

            # 3. Human must exist and be active.
            hm = _fetch_row(
                cur,
                "SELECT active FROM human_employees WHERE employee_id = %s;",
                (employee_id,),
            )
            if hm is None:
                raise MappingError("Human %s does not exist" % employee_id)
            if not hm[0]:
                raise MappingError("Human %s is inactive — mapping not allowed" % employee_id)

            # 4. Controlled-scan attendance evidence must resolve via the
            # canonical resolver — same matcher mapping_eligibility() used
            # to advertise this enrollment as eligible in the first place.
            controlled_attendance_id = resolve_controlled_attendance_id(
                cur, device_user_pk, valid_from
            )
            if controlled_attendance_id is None:
                raise MappingError(
                    "no controlled-scan attendance evidence resolves for enrollment "
                    "%s (device_user_pk=%s, controlled_scan_time=%s) — cannot verify "
                    "identity without it" % (enrollment_id, device_user_pk, valid_from.isoformat())
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
