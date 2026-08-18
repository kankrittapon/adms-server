"""
Terminal Management frontend UI — structural checks.

PromptID: ADMS-TerminalManagement-020 Part A

No frontend test runner exists in this repo (same convention as
tests/test_timeout_margin.py, tests/test_enrollment_state_sync.py, etc.)
— these assert against the actual page source.
"""

import pathlib
import unittest

FRONTEND_ROOT = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"


def _read(rel: str) -> str:
    return (FRONTEND_ROOT / rel).read_text(encoding="utf-8")


class TestTerminalManagementUI(unittest.TestCase):
    def setUp(self):
        self.page_src = _read("pages/TerminalManagement.tsx")
        self.types_src = _read("i18n/types.ts")
        self.th_src = _read("i18n/th.ts")
        self.en_src = _read("i18n/en.ts")

    def test_item1_page_loads_inventory(self):
        self.assertIn("api.terminalInventory", self.page_src)

    def test_item2_elderly_thai_labels_present_in_bundle_source(self):
        self.assertIn("จัดการเครื่องสแกนลายนิ้วมือ", self.th_src)
        self.assertIn("นำผู้ใช้ออกจากเครื่อง", self.th_src)
        self.assertIn("ลงลายนิ้วใหม่", self.th_src)

    def test_item3_admin_actions_visible_only_when_admin(self):
        self.assertIn('isAdmin = me?.role === "ADMIN"', self.page_src)

    def test_item4_viewer_sees_no_access_message_not_actions(self):
        idx = self.page_src.find("if (!isAdmin)")
        segment = self.page_src[idx:idx + 300]
        self.assertIn("viewerNoAccess", segment)
        self.assertNotIn("removeAccountButton", segment)

    def test_item5_active_human_destructive_warning_present(self):
        self.assertIn("removeAccountActiveWarning", self.page_src)
        self.assertIn("human_active === true", self.page_src)
        self.assertIn("acctAcknowledge", self.page_src)

    def test_item6_inactive_human_wording_distinct(self):
        self.assertIn("humanInactive", self.page_src)
        self.assertNotEqual(
            self._th_value("humanActive"), self._th_value("humanInactive")
        )

    def test_item7_fingerprint_delete_modal_present(self):
        self.assertIn("removeFingerprintConfirmTitle", self.page_src)
        self.assertIn("ConfirmModal", self.page_src)

    def test_item8_terminal_account_delete_modal_present(self):
        self.assertIn("removeAccountConfirmTitle", self.page_src)

    def test_item9_uncertain_result_offers_verify_again(self):
        self.assertIn("refreshButton", self.page_src)
        self.assertIn("inv.reload()", self.page_src)

    def test_no_internal_ids_exposed_in_ui_copy(self):
        for forbidden in ("device_user_pk", "account_incarnation", "pyzk", "delete_user_template", "delete_user("):
            self.assertNotIn(forbidden, self.th_src)
            self.assertNotIn(forbidden, self.en_src)

    def test_reenroll_cannot_cancel_notice_present(self):
        self.assertIn("reenrollCannotCancelNotice", self.page_src)

    def test_write_session_badge_shown(self):
        self.assertIn("WriteSessionBadge", self.page_src)

    def _th_value(self, key: str) -> str:
        idx = self.th_src.find("%s:" % key)
        line = self.th_src[idx:self.th_src.find("\n", idx)]
        return line


if __name__ == "__main__":
    unittest.main()
