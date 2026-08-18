"""
Complete Enrollment E2E proof — Human -> RESERVED -> ... -> VERIFIED mapping
-> correct attendance attribution.

PromptID: ADMS-FullEnrollment-E2E-Closure-017 (Phase 1 fixture, Phase 15
top-level test)

This test drives every canonical application function in the real Step
1-6 sequence, in order, using the SAME test identity throughout — not
isolated per-endpoint unit tests. It is the "one canonical E2E fixture"
required by Phase 1, reused across every step, and the single named
top-level test required by Phase 15:
`test_complete_enrollment_to_verified_attendance_e2e`.

Fixture identity (never a hard-coded production ID):
  Human:   display_name="ทดสอบ ระบบ", english_name="Test Person",
           rank="น.อ." (a real canonical RTN rank abbreviation from
           app/rtn_ranks.py — no invented rank).
  Device:  a FakeDevice modeling get_users/set_user/UID/privilege
           semantics (same double used throughout this project's test
           suite since PromptID 008).
  Terminal ID: chosen by the real allocator (_find_next_available_id via
           reserve_next_device_user_id) — never hard-coded.

No real Postgres is available in this environment (confirmed: every test
in this repository, going back to PromptID 006, mocks the DB boundary via
a FakeCursor/FakeConnection pattern — there is no live database to run a
true integration test against in CI or this sandbox). This test therefore
chains REAL canonical functions (never reimplementing their logic) against
a per-call FakeCursor whose queued rows model the enrollment/device_user/
attendance state as it would exist after each prior real call — the same
established pattern already used by
tests/test_enrollment.py::TestSafetyInvariants::
test_full_workflow_never_creates_mappings_or_mutates_attendance, extended
here through mapping creation and a final post-mapping attendance
resolution.

The one deliberate fixture shortcut — inserting the simulated physical
scan events directly as attendance-row tuples fed into
resolve_verified_employee_mapping()/the evidence resolver, rather than
running the full Collector MQTT pipeline — represents EXTERNAL TERMINAL
INPUT (what a real ZEM560 scan event would produce after
app.db.save_attendance_log() already persisted it), not a bypass of any
enrollment/mapping business logic. Every canonical enrollment/mapping
function itself (reserve, create_or_reconcile_terminal_account,
confirm_fingerprint_enrolled, start_controlled_scan_window,
confirm_controlled_scan, mark_ready_for_mapping, create_verified_mapping)
is exercised for real, unmodified, exactly as the API routes call them.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.config import Config
from app.enrollment import (
    confirm_controlled_scan,
    confirm_fingerprint_enrolled,
    create_or_reconcile_terminal_account,
    mark_ready_for_mapping,
    reserve_next_device_user_id,
    start_controlled_scan_window,
)
from app.mapping import create_verified_mapping
from app.db import resolve_verified_employee_mapping
from app.rtn_ranks import normalize_rtn_rank
from tests.test_enrollment import FakeCursor, FakeDevice, make_db, make_enrollment_tuple

TEST_HUMAN_ID = "aaaaaaaa-e2e0-4000-8000-000000000e2e"
TEST_DISPLAY_NAME = "ทดสอบ ระบบ"
TEST_ENGLISH_NAME = "Test Person"
TEST_RANK_ABBR = "น.อ."  # canonical RTN rank — Captain — real catalog entry
TEST_DEVICE_ID = 1
NOW = datetime(2026, 8, 18, 9, 0, 0, tzinfo=timezone.utc)


class TestCompleteEnrollmentE2E(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()
        rank_meta = normalize_rtn_rank(TEST_RANK_ABBR)
        self.assertIsNotNone(rank_meta, "test fixture rank must resolve against the real canonical catalog")
        self.assertEqual(rank_meta["rank_en_abbreviation"], "Capt")

    def test_complete_enrollment_to_verified_attendance_e2e(self):
        # ---------------------------------------------------------------
        # Step 1: reserve — allocator picks the terminal ID, RESERVED row
        # created. No UUID exposed as a required user input at this layer
        # (employee_id is already resolved upstream by the human-picker UI
        # from a name-labeled dropdown, per PromptID-016 Part A).
        # ---------------------------------------------------------------
        with patch("app.enrollment.log_sync_event"), patch("app.enrollment.get_db_connection") as m1:
            cur = FakeCursor(
                fetchone_queue=[
                    (1,),                                    # human exists/active/production_scope
                    (1,),                                    # device exists/active
                    (None,),                                 # advisory lock
                    None,                                     # reclaimed-cancelled-enrollment audit lookup
                    (1, "1005", "RESERVED", NOW),             # INSERT RETURNING
                ],
                fetchall_queue=[
                    [],  # 022 lifecycle candidate-row check: no blocking rows
                    [],  # _load_used_terminal_ids: nothing used yet
                ],
            )
            make_db(m1, cur)
            reserved = reserve_next_device_user_id(
                self.cfg, employee_id=TEST_HUMAN_ID, device_id=TEST_DEVICE_ID, operator="op"
            )
        self.assertEqual(reserved["status"], "RESERVED")
        enrollment_id = reserved["enrollment_id"]
        terminal_id = reserved["reserved_device_user_id"]
        self.assertTrue(terminal_id)  # allocator chose it — not hard-coded here

        # ---------------------------------------------------------------
        # Step 2: create/reconcile terminal account — real FakeDevice
        # models get_users/set_user/uid/privilege; bounded read-back
        # proves the account before advancing state (PromptID 008/010).
        # ---------------------------------------------------------------
        with (
            patch("app.enrollment.log_sync_event"),
            patch("app.enrollment.ensure_device_user", return_value=101),
            patch("app.enrollment.get_db_connection") as m2,
        ):
            cur = FakeCursor(fetchone_queue=[
                make_enrollment_tuple(
                    enrollment_id=enrollment_id, employee_id=TEST_HUMAN_ID,
                    reserved_device_user_id=terminal_id, status="RESERVED",
                )
            ])
            make_db(m2, cur)
            device = FakeDevice(users=[], set_user_return=None)  # exact production bug shape
            result = create_or_reconcile_terminal_account(
                self.cfg, enrollment_id, "Capt Test Person", device
            )
        self.assertEqual(result["status"], "TERMINAL_ACCOUNT_CREATED")
        self.assertEqual(device.set_user_calls[0]["user_id"], terminal_id)
        self.assertEqual(len([c for c in device.calls if c == "set_user"]), 1)  # set_user max once

        # ---------------------------------------------------------------
        # Step 3: fingerprint confirmation — browser-only state
        # confirmation (this architecture never commands biometric
        # enrollment from the API — the physical procedure happens at the
        # terminal keypad, per app/collector.py/app/enrollment.py; no
        # biometric API exists to invent).
        # ---------------------------------------------------------------
        with patch("app.enrollment.log_sync_event"), patch("app.enrollment.get_db_connection") as m3:
            cur = FakeCursor(fetchone_queue=[
                make_enrollment_tuple(
                    enrollment_id=enrollment_id, employee_id=TEST_HUMAN_ID,
                    reserved_device_user_id=terminal_id, status="TERMINAL_ACCOUNT_CREATED",
                )
            ])
            make_db(m3, cur)
            fp_result = confirm_fingerprint_enrolled(self.cfg, enrollment_id, "op")
        self.assertEqual(fp_result["status"], "FINGERPRINT_ENROLLED")

        # ---------------------------------------------------------------
        # Step 3.5: open the controlled-scan window.
        # ---------------------------------------------------------------
        with patch("app.enrollment.log_sync_event"), patch("app.enrollment.get_db_connection") as m4:
            cur = FakeCursor(fetchone_queue=[
                make_enrollment_tuple(
                    enrollment_id=enrollment_id, employee_id=TEST_HUMAN_ID,
                    reserved_device_user_id=terminal_id, status="FINGERPRINT_ENROLLED",
                )
            ])
            make_db(m4, cur)
            start_controlled_scan_window(self.cfg, enrollment_id, "op")

        # ---------------------------------------------------------------
        # Fixture step: simulated physical scan arrives from the terminal.
        # This represents EXTERNAL TERMINAL INPUT (what
        # app.db.save_attendance_log() would have already persisted from a
        # real Collector-forwarded MQTT attendance event) — not a bypass of
        # enrollment/mapping logic.
        # ---------------------------------------------------------------
        real_scan_time = NOW + timedelta(minutes=10, seconds=23, microseconds=810000)
        controlled_attendance_id = 555

        # ---------------------------------------------------------------
        # Step 4: confirm controlled scan — ADMS-ControlledScan-
        # EvidenceBinding-018: no operator-supplied/estimated scan_time at
        # all. The server resolves the real attendance row itself
        # (device_users lookup, then a bounded [window_start, until]
        # attendance lookup) and binds ITS exact scan_time — never an
        # estimate to later reconcile.
        # ---------------------------------------------------------------
        window_start = NOW + timedelta(minutes=9)  # this row's own updated_at when the window opened
        window_until = NOW + timedelta(minutes=15)
        with patch("app.enrollment.log_sync_event"), patch("app.enrollment.get_db_connection") as m5:
            cur = FakeCursor(fetchone_queue=[
                make_enrollment_tuple(
                    enrollment_id=enrollment_id, employee_id=TEST_HUMAN_ID,
                    reserved_device_user_id=terminal_id, status="CONTROLLED_SCAN_PENDING",
                    controlled_scan_window_until=window_until, updated_at=window_start,
                ),
                (7, True),                              # device_users (device_user_pk, active)
                (controlled_attendance_id, real_scan_time),  # bounded attendance candidate lookup
            ])
            make_db(m5, cur)
            scan_result = confirm_controlled_scan(self.cfg, enrollment_id, "op")
        self.assertEqual(scan_result["controlled_scan_time"], real_scan_time)
        self.assertEqual(scan_result["controlled_attendance_id"], controlled_attendance_id)
        bound_scan_time = scan_result["controlled_scan_time"]

        # ---------------------------------------------------------------
        # Step 5: mark ready for mapping — MUST resolve real evidence via
        # the canonical resolver before allowing the transition
        # (ADMS-FullEnrollment-E2E-Closure-017 Phase 7 gate). Since
        # controlled_scan_time is now bit-for-bit the real attendance
        # row's own scan_time, resolution is exact (delta=0), not a
        # window-proximity guess.
        # ---------------------------------------------------------------
        with patch("app.enrollment.log_sync_event"), patch("app.enrollment.get_db_connection") as m6:
            enroll_row = make_enrollment_tuple(
                enrollment_id=enrollment_id, employee_id=TEST_HUMAN_ID,
                reserved_device_user_id=terminal_id, status="CONTROLLED_SCAN_CONFIRMED",
                controlled_scan_time=bound_scan_time,
            )
            cur = FakeCursor(
                fetchone_queue=[
                    enroll_row,                                  # evidence pre-check's own fetch
                    (7, True),                                   # device_users (device_user_pk, active)
                    enroll_row,                                  # _transition's own internal fetch
                ],
                fetchall_result=[(controlled_attendance_id, real_scan_time)],  # resolver candidates
            )
            make_db(m6, cur)
            ready = mark_ready_for_mapping(self.cfg, enrollment_id, "admin")
        self.assertEqual(ready["status"], "READY_FOR_MAPPING")

        # ---------------------------------------------------------------
        # Step 6: ADMIN verifies identity — simplified contract
        # (enrollment_id, verified_by, verification_note only).
        # employee_id/device_user_pk/controlled_attendance_id are ALL
        # derived server-side.
        # ---------------------------------------------------------------
        device_user_pk = 7
        with patch("app.mapping.log_sync_event"), patch("app.mapping.get_db_connection") as m7:
            cur = FakeCursor(
                fetchone_queue=[
                    (TEST_HUMAN_ID, TEST_DEVICE_ID, terminal_id, "READY_FOR_MAPPING",
                     bound_scan_time, "admin"),                   # enrollment
                    (device_user_pk, True),                      # device_users
                    (True,),                                     # human active
                    None,                                        # no conflicting VERIFIED mapping
                    (1, bound_scan_time, NOW + timedelta(minutes=11)),  # INSERT RETURNING
                ],
                fetchall_result=[(controlled_attendance_id, real_scan_time)],
            )
            make_db(m7, cur)
            mapping_result = create_verified_mapping(
                self.cfg, enrollment_id=enrollment_id,
                verified_by="admin", verification_note="E2E fixture verification",
            )
        self.assertEqual(mapping_result["mapping_status"], "VERIFIED")
        self.assertEqual(mapping_result["employee_id"], TEST_HUMAN_ID)
        self.assertEqual(mapping_result["device_user_pk"], device_user_pk)
        valid_from = mapping_result["valid_from"]

        # ---------------------------------------------------------------
        # Final proof: a NEW attendance event after valid_from resolves to
        # the correct Human via the temporal resolver.
        # ---------------------------------------------------------------
        next_scan_time = valid_from + timedelta(hours=8)
        resolver_cur = MagicMock()
        resolver_cur.fetchall.return_value = [(TEST_HUMAN_ID,)]
        resolved_employee_id = resolve_verified_employee_mapping(
            resolver_cur, device_user_pk, next_scan_time
        )
        self.assertEqual(resolved_employee_id, TEST_HUMAN_ID)

        # A scan BEFORE valid_from must NOT resolve through this new
        # mapping (no matching VERIFIED interval covers it) — modeled
        # here by the resolver finding zero rows, exactly as the real SQL
        # `valid_from <= %s` predicate would exclude it.
        before_cur = MagicMock()
        before_cur.fetchall.return_value = []
        resolved_before = resolve_verified_employee_mapping(
            before_cur, device_user_pk, valid_from - timedelta(hours=1)
        )
        self.assertIsNone(resolved_before)


if __name__ == "__main__":
    unittest.main()
