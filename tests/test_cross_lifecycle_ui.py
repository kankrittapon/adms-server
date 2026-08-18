"""
Cross-lifecycle UI consistency — ADMS-UX-CrossLifecycleClosure-021B, Part B2.

Structural checks against frontend source (same convention as
tests/test_terminal_management_ui.py — no frontend test runner in this
repo).
"""

import pathlib
import unittest

FRONTEND_ROOT = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"


def _read(rel: str) -> str:
    return (FRONTEND_ROOT / rel).read_text(encoding="utf-8")


class TestEnrollmentWorkspaceLifecycleFiltering(unittest.TestCase):
    def setUp(self):
        self.enrollments_src = _read("pages/Enrollments.tsx")

    def test_item1_active_queue_filters_on_derived_lifecycle_state_not_raw_status(self):
        """The historical bug: filtering on raw `status !== 'RETIRED'` misses
        an enrollment whose status is stuck at an earlier value (e.g. real
        production Enrollment #4, still READY_FOR_MAPPING) despite its
        mapping already being closed. Must filter on lifecycle_state."""
        self.assertIn('e.lifecycle_state === "IN_PROGRESS"', self.enrollments_src)
        self.assertIn('e.lifecycle_state !== "IN_PROGRESS"', self.enrollments_src)

    def test_item11_autoselect_only_considers_active_items(self):
        idx_effect = self.enrollments_src.index("Auto-select the first or newest active")
        segment = self.enrollments_src[idx_effect : idx_effect + 400]
        self.assertIn("activeItems", segment)
        self.assertNotIn("historyItems", segment)

    def test_item3_history_section_present_and_distinct_from_active_queue(self):
        self.assertIn("t.enrollment.historyTitle", self.enrollments_src)
        self.assertIn("historyItems.map", self.enrollments_src)

    def test_history_rows_are_not_clickable_into_mutable_inspector(self):
        history_idx = self.enrollments_src.index("historyItems.map")
        next_idx = self.enrollments_src.index("Right Col:", history_idx)
        history_block = self.enrollments_src[history_idx:next_idx]
        self.assertNotIn("onClick", history_block)
        self.assertNotIn("setSelectedId", history_block)

    def test_item7_completed_and_removed_from_terminal_labels_distinct(self):
        self.assertIn("t.enrollment.completedTitle", self.enrollments_src)
        self.assertIn("t.enrollment.removedFromTerminalLabel", self.enrollments_src)

    def test_item14_no_raw_lifecycle_enums_in_history_section_copy(self):
        history_idx = self.enrollments_src.index("historyItems.map")
        next_idx = self.enrollments_src.index("Right Col:", history_idx)
        history_block = self.enrollments_src[history_idx:next_idx]
        for forbidden in ("READY_FOR_MAPPING", "device_user_pk", "valid_to", "account_incarnation"):
            self.assertNotIn(forbidden, history_block)


class TestPersonnelNoTerminalAccountCard(unittest.TestCase):
    def setUp(self):
        self.personnel_src = _read("pages/Personnel.tsx")

    def test_item4_no_terminal_account_card_present(self):
        self.assertIn("has_active_terminal_account === false", self.personnel_src)
        self.assertIn("t.personnel.noTerminalAccountTitle", self.personnel_src)
        self.assertIn("t.personnel.startNewEnrollmentButton", self.personnel_src)

    def test_active_human_with_no_account_is_not_called_inactive(self):
        # The card must be gated on data.active being TRUE — removing a
        # terminal account must never be conflated with the Human leaving.
        idx = self.personnel_src.index("has_active_terminal_account === false")
        segment = self.personnel_src[max(0, idx - 60) : idx]
        self.assertIn("data.active &&", segment)

    def test_item14b_no_internal_ids_in_no_terminal_account_card_copy(self):
        idx = self.personnel_src.index("noTerminalAccountTitle")
        segment = self.personnel_src[idx : idx + 600]
        for forbidden in ("device_user_pk", "mapping_id", "READY_FOR_MAPPING", "RETIRED"):
            self.assertNotIn(forbidden, segment)


class TestCanonicalBackendDerivation(unittest.TestCase):
    """Item 8: frontend must consume the server-derived field, never
    reimplement the join/derivation itself."""

    def test_enrollment_type_carries_lifecycle_state(self):
        types_src = _read("api/types.ts")
        generated_src = _read("api/generated.ts")
        # Enrollment type is a re-export of the generated OpenAPI schema —
        # lifecycle_state must appear in the generated types (proves the
        # backend contract, not a frontend-invented field).
        self.assertIn("lifecycle_state", generated_src)
        self.assertTrue("Enrollment" in types_src or "generated" in types_src)

    def test_no_frontend_reimplementation_of_lifecycle_join(self):
        enrollments_src = _read("pages/Enrollments.tsx")
        # The frontend must not itself combine status + device_users.active +
        # mapping.valid_to to decide lifecycle — those raw joined fields
        # should never even appear in this file.
        for forbidden in ("device_user_active", "verified_mapping_status", "mapping_valid_to"):
            self.assertNotIn(forbidden, enrollments_src)


if __name__ == "__main__":
    unittest.main()
