"""
Enrollment Workspace state-sync / cancel-consistency regression tests.

PromptID: ADMS-Enrollment-StateSync-UXFix-012

Two confirmed browser bugs:

  Bug A — Enrollment Step 2's terminal display-name field went stale: it was
  initialized from enrollment.english_name via a React useState *initializer*,
  which only runs once on mount. Because the inspector component is not
  remounted when the operator selects a different enrollment (same JSX
  position, same component type), switching sessions — or an english_name
  edit in Personnel followed by a normal reload — never updated the field.
  Root cause and fix are both in the frontend (frontend/src/pages/
  Enrollments.tsx); the backend already returned the correct, current
  english_name on every request (no caching layer exists there).

  Bug B — a second cancel click could reach the backend while the first was
  still in flight (the Confirm button in the cancel drawer had no `disabled`
  guard, unlike every other action button on the page), producing a raw
  "invalid enrollment transition CANCELLED -> CANCELLED" string surfaced
  directly to the operator. Root cause and fix are both in the frontend;
  the backend's strict transition semantics (CANCELLED has no outgoing
  transitions) were deliberately left unchanged — see the design rationale
  below.

Design decision recorded here per the task's explicit instruction to justify
it: the backend's cancel transition stays strict (CANCELLED -> CANCELLED is
still a conflict), rather than being made idempotent, because cancel_enrollment
overwrites the `notes` column with a fresh operator+reason string on every
call — a "make CANCELLED->CANCELLED a silent no-op" change would silently
discard a second cancel attempt's reason text without any audit trail of the
duplicate attempt, which is an audit-semantics change this task was
explicitly told to avoid making without dedicated review. The smallest safe
fix is therefore frontend-only: make duplicate submission practically
impossible (disable-on-click) and map the resulting conflict, if it still
occurs, to a friendly, localized message instead of raw transition text.

Since this repository has no frontend test runner (no vitest/RTL configured
— confirmed by the absence of a "test" script or vitest devDependency in
frontend/package.json), the frontend-side assertions here are structural
source checks against frontend/src/pages/Enrollments.tsx and the i18n
modules, following the same pattern already established in
tests/test_timeout_margin.py for backend/frontend boundary checks. Backend
behavior is tested directly.
"""

import inspect
import pathlib
import unittest
from unittest.mock import patch

from app.config import Config
from app.enrollment import ALLOWED_TRANSITIONS, cancel_enrollment
from tests.test_enrollment import FakeCursor, make_db, make_enrollment_tuple

FRONTEND_ROOT = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"


def _read(rel: str) -> str:
    return (FRONTEND_ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Backend: english_name is always current, never cached (items 1-2)
# ---------------------------------------------------------------------------


class TestEnglishNameAlwaysCurrent(unittest.TestCase):
    """Item 1 is cross-referenced from tests/test_terminal_account_idempotency.py
    ::test_case17_repository_query_selects_english_name (both list and detail
    queries join h.english_name). Item 2 is proven here: two sequential
    get_enrollment_row() calls against a mocked cursor that returns different
    english_name values each time must return the new value on the second
    call — there is no caching/memoization layer in the repository."""

    def test_item2_no_memoization_across_sequential_fetches(self):
        import app.api.repository as repository

        columns = [
            "enrollment_id", "employee_id", "device_id", "reserved_device_user_id",
            "status", "reserved_by", "reserved_at", "terminal_created_at", "device_uid",
            "fingerprint_confirmed_at", "controlled_scan_window_until", "controlled_scan_time",
            "confirmed_by", "confirmed_at", "notes", "created_at", "updated_at",
            "employee_name", "english_name", "device_name",
        ]

        def row(english_name):
            base = {c: None for c in columns}
            base.update(
                enrollment_id=1, employee_id="emp-1", device_id=1,
                reserved_device_user_id="1001", status="RESERVED", reserved_by="op",
                employee_name="พิมาย ขาวสอาด", english_name=english_name, device_name="device-1",
            )
            return tuple(base[c] for c in columns)

        class DescribedFakeCursor:
            def __init__(self, rows):
                self.description = [(c,) for c in columns]
                self._rows = list(rows)

            def execute(self, sql, params=None):
                pass

            def fetchall(self):
                return [self._rows.pop(0)]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

        cfg = Config.from_env()
        cur = DescribedFakeCursor([row(None), row("Pimai Khawsaad")])

        class FakeConn:
            def cursor(self):
                return cur

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

        with patch("app.api.repository._connect", return_value=FakeConn()):
            first = repository.get_enrollment_row(cfg, 1)
            second = repository.get_enrollment_row(cfg, 1)
        self.assertIsNone(first["english_name"])
        self.assertEqual(second["english_name"], "Pimai Khawsaad")


# ---------------------------------------------------------------------------
# Backend: cancel transition semantics (design decision verification)
# ---------------------------------------------------------------------------


class TestCancelTransitionSemantics(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def test_cancelled_has_no_outgoing_transitions(self):
        # Confirms the strict-backend design decision's premise still holds:
        # CANCELLED is genuinely terminal, so a second cancel is a real
        # conflict, not a code bug to "fix" by loosening the state machine.
        self.assertEqual(ALLOWED_TRANSITIONS["CANCELLED"], set())

    def test_cancel_already_cancelled_raises_enrollment_conflict_with_clear_message(self):
        from app.enrollment import EnrollmentError

        row = make_enrollment_tuple(status="CANCELLED")
        cur = FakeCursor(fetchone_queue=[row])
        with patch("app.enrollment.get_db_connection") as mock_conn_fn:
            make_db(mock_conn_fn, cur)
            with self.assertRaises(EnrollmentError) as ctx:
                cancel_enrollment(self.cfg, 1, "operator", notes="duplicate click")
        # The raw message format the frontend must never show verbatim —
        # asserting its exact shape here is what lets the frontend test
        # below assert it correctly detects this specific substring.
        self.assertIn("CANCELLED -> CANCELLED", str(ctx.exception))

    def test_cancel_requires_a_reason_regardless_of_state(self):
        from app.enrollment import EnrollmentError

        with self.assertRaises(EnrollmentError):
            cancel_enrollment(self.cfg, 1, "operator", notes="")


# ---------------------------------------------------------------------------
# Frontend structural checks (Bug A — english_name sync)
# ---------------------------------------------------------------------------


class TestFrontendDisplayNameSync(unittest.TestCase):
    def setUp(self):
        self.src = _read("pages/Enrollments.tsx")

    def test_item3_resyncs_display_name_when_selected_enrollment_changes(self):
        self.assertIn("lastSyncedEnrollmentId", self.src)
        self.assertIn("enrollment.enrollment_id !== lastSyncedEnrollmentId", self.src)

    def test_item4_and_5_blank_when_no_english_name_no_thai_fallback(self):
        # The synced value is derived via computeTerminalNamePreview(), whose
        # own contract (frontend/src/lib/terminalName.ts) guarantees "" when
        # english_name is absent and never falls back to the Thai name — the
        # page itself must only ever feed it enrollment.english_name, never
        # employee_name/display_name (the Thai field).
        self.assertIn("computeTerminalNamePreview(enrollment.english_name, enrollment.rank_metadata)", self.src)
        # Regression guard: no code path assigns the Thai name into the
        # terminal display-name state.
        self.assertNotIn("setDisplayName(enrollment.employee_name", self.src)
        preview_src = _read("lib/terminalName.ts")
        self.assertIn('return { value: "", rankOmittedForLength: false };', preview_src)

    def test_item6_touched_flag_prevents_clobbering_an_active_manual_edit(self):
        self.assertIn("displayNameTouched", self.src)
        self.assertIn("setDisplayNameTouched(true)", self.src)
        # Auto-resync while the same enrollment is selected must be gated
        # on "not touched" — otherwise a canonical refetch could overwrite
        # an in-progress manual edit mid-keystroke.
        self.assertIn("!displayNameTouched", self.src)


# ---------------------------------------------------------------------------
# Frontend structural checks (Bug B — cancel consistency)
# ---------------------------------------------------------------------------


class TestFrontendCancelConsistency(unittest.TestCase):
    def setUp(self):
        self.src = _read("pages/Enrollments.tsx")

    def test_item8_cancel_confirm_button_disabled_while_in_flight(self):
        # The Confirm button in the cancel drawer must be disabled while a
        # cancel is in flight, matching the guard pattern used by every
        # other action button on this page.
        idx = self.src.find('onRunAction("cancel", { notes: cancelNotes.trim() })')
        self.assertNotEqual(idx, -1)
        button_region = self.src[idx:idx + 300]
        self.assertIn('busyAction === "cancel"', button_region)
        self.assertIn("disabled=", button_region)

    def test_item9_successful_cancel_clears_selection(self):
        idx = self.src.find('action === "cancel"')
        segment = self.src[idx:idx + 700]
        self.assertIn("setSelectedId(null)", segment)

    def test_item7_all_mutations_trigger_canonical_refetch(self):
        # The unconditional list.reload()/nextActions.reload() pair after
        # the try block's action dispatch (covers reserve/terminal-account/
        # fingerprint/scan/ready/cancel uniformly) must still be present.
        idx = self.src.find("action === \"cancel\"")
        after = self.src[idx:idx + 1000]
        self.assertIn("list.reload();", after)
        self.assertIn("nextActions.reload();", after)

    def test_item11_cancel_button_hidden_for_terminal_states(self):
        self.assertIn(
            'enrollment.status !== "RETIRED" && enrollment.status !== "CANCELLED"', self.src
        )


# ---------------------------------------------------------------------------
# Frontend structural checks (Active Queue filtering — items 10)
# ---------------------------------------------------------------------------


class TestActiveQueueFiltering(unittest.TestCase):
    def setUp(self):
        self.src = _read("pages/Enrollments.tsx")

    def test_item10_terminal_statuses_excluded_from_active_queue(self):
        self.assertIn('TERMINAL_STATUSES = new Set(["CANCELLED", "RETIRED"])', self.src)
        self.assertIn("activeItems", self.src)
        # The rendered queue list and its count must both derive from the
        # filtered set, not the raw unfiltered list.data.items.
        self.assertIn("{activeItems.map(", self.src)
        self.assertIn("{activeItems.length}", self.src)


# ---------------------------------------------------------------------------
# Frontend structural checks (error UX — items 12-13)
# ---------------------------------------------------------------------------


class TestFrontendErrorUX(unittest.TestCase):
    def setUp(self):
        self.src = _read("pages/Enrollments.tsx")
        self.types_src = _read("i18n/types.ts")
        self.en_src = _read("i18n/en.ts")
        self.th_src = _read("i18n/th.ts")

    def test_item12_enrollment_conflict_maps_to_friendly_copy(self):
        for key in ("enrollmentConflictBody", "alreadyCancelledBody"):
            self.assertIn(key, self.types_src)
            self.assertIn(key, self.en_src)
            self.assertIn(key, self.th_src)
        # TH copy matches the exact strings specified for this PromptID.
        self.assertIn("รายการลงทะเบียนมีการเปลี่ยนสถานะแล้ว", self.th_src)
        self.assertIn("รายการนี้ถูกยกเลิกแล้ว", self.th_src)

    def test_item13_enrollment_conflict_handled_before_raw_fallback(self):
        # Every `err.code === "ENROLLMENT_CONFLICT"` branch must appear
        # before its enclosing fallback that would otherwise print the raw
        # `${err.code}: ${err.message}` string.
        occurrences = [
            i for i in range(len(self.src))
            if self.src.startswith('err.code === "ENROLLMENT_CONFLICT"', i)
        ]
        self.assertGreaterEqual(len(occurrences), 2, "expected ENROLLMENT_CONFLICT handled in "
                                 "both the create-terminal-account branch and the general fallback")
        for idx in occurrences:
            # Each ENROLLMENT_CONFLICT branch must resolve to the friendly
            # copy, not the raw `${err.code}: ${err.message}` fallback.
            self.assertIn("t.enrollment.alreadyCancelledBody", self.src[idx:idx + 700])


if __name__ == "__main__":
    unittest.main()
