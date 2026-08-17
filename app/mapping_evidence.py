"""
Canonical controlled-scan evidence resolver.

PromptID: ADMS-FullEnrollment-E2E-Closure-017

Root cause class fixed here: TWO separate places independently re-derived
"which attendance_logs row is this enrollment's controlled-scan evidence" —
app.api.repository.mapping_eligibility() (a correlated SQL subquery) and
app.mapping.create_verified_mapping() (an exact-equality re-check,
`att_scan_time != valid_from`). Both compared a full-precision
attendance_logs.scan_time against an operator-entered/SSE-prefilled
controlled_scan_time that round-trips through an HTML `datetime-local`
input (minute precision, no seconds) — so even after PromptID-016 fixed the
eligibility query's window, create_verified_mapping()'s own internal
exact-equality re-check could still silently reject the very
controlled_attendance_id the eligibility endpoint had just resolved,
reproducing the "Attendance ID #?" / 422 class of failure at Step 6.

This module is the single canonical resolver — used by BOTH the
eligibility listing and the mapping-creation transaction — so there is
exactly one definition of "the correct controlled-scan evidence row" in
the whole system, never two independently-drifting ones.

Evidence-matching invariant:
  1. Device + terminal-user constraint applies FIRST, structurally, not as
     a time-window coincidence: candidates are fetched by device_user_pk,
     which is already unique per (device_id, device_user_id) — an
     attendance row from a different device or a different terminal user
     can never even become a candidate, regardless of how close its
     timestamp is.
  2. Among same-device_user_pk candidates, the row with scan_time nearest
     to the enrollment's controlled_scan_time is selected, bounded to a
     deterministic window (default +/-120s — comfortably inside the
     5-minute controlled-scan window itself, tight enough to exclude an
     unrelated later scan by the same terminal user).
  3. Ties (equal distance) are broken deterministically by the lowest
     attendance id (earliest ingested) — never arbitrary/unordered.
  4. No candidate within the window => no evidence => None. Callers must
     treat None as "cannot proceed," never guess.
"""

from datetime import timedelta
from typing import Any, List, Optional, Sequence, Tuple

DEFAULT_EVIDENCE_WINDOW_SECONDS = 120


def pick_nearest_attendance(
    candidates: Sequence[Tuple[int, Any]],
    controlled_scan_time: Any,
) -> Optional[int]:
    """Pure decision function — no DB access.

    `candidates` must already be scoped to the correct device_user_pk (the
    device/terminal-user constraint) by the caller; this function only
    picks the nearest-in-time one, deterministically. Each candidate is
    (attendance_id, scan_time). Returns the winning attendance_id, or None
    if `candidates` is empty.
    """
    best_id: Optional[int] = None
    best_delta: Optional[float] = None
    for att_id, scan_time in candidates:
        delta = abs((scan_time - controlled_scan_time).total_seconds())
        if (
            best_delta is None
            or delta < best_delta
            or (delta == best_delta and att_id < best_id)  # type: ignore[operator]
        ):
            best_id = att_id
            best_delta = delta
    return best_id


def resolve_controlled_attendance_id(
    cur: Any,
    device_user_pk: int,
    controlled_scan_time: Any,
    window_seconds: int = DEFAULT_EVIDENCE_WINDOW_SECONDS,
) -> Optional[int]:
    """DB-scoped resolver: fetches attendance_logs candidates constrained to
    `device_user_pk` (device + terminal-user, structurally, via the SQL
    WHERE clause — never a coincidental time-only match) within a bounded
    window around `controlled_scan_time`, then applies the deterministic
    pure decision function above. Returns the winning attendance_id, or
    None if no evidence resolves.
    """
    window = timedelta(seconds=window_seconds)
    cur.execute(
        "SELECT id, scan_time FROM attendance_logs "
        "WHERE device_user_pk = %s "
        "AND scan_time BETWEEN %s AND %s;",
        (
            device_user_pk,
            controlled_scan_time - window,
            controlled_scan_time + window,
        ),
    )
    candidates: List[Tuple[int, Any]] = list(cur.fetchall())
    return pick_nearest_attendance(candidates, controlled_scan_time)
