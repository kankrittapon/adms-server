"""Scanner display-name sync: name derived from rank + English name, and a
read-back verified in-place rename that keeps uid / user_id / privilege."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.terminal_management import (
    TerminalAccountNotFound,
    TerminalManagementError,
    expected_terminal_name,
    rename_terminal_account,
)


class FakeDevice:
    def __init__(self, users, apply=True):
        self.users = users
        self.apply = apply
        self.calls = []

    def get_users(self):
        return self.users

    def set_user(self, **kw):
        self.calls.append(kw)
        if self.apply:
            for u in self.users:
                if u.uid == kw["uid"]:
                    u.name = kw["name"]


def user(uid, user_id, name):
    return SimpleNamespace(uid=uid, user_id=user_id, name=name, privilege=0, password="", group_id="", card=0)


class TestExpectedName(unittest.TestCase):
    def test_rank_prefix(self):
        self.assertEqual(expected_terminal_name("Krittapon M", "CPO2"), "CPO2 Krittapon M")

    def test_rank_dropped_when_too_long(self):
        self.assertEqual(expected_terminal_name("Tapanapong Siriphot", "CPO3"), "Tapanapong Siriphot")

    def test_empty_without_english_name(self):
        self.assertEqual(expected_terminal_name(None, "CPO2"), "")


@patch("app.terminal_management.log_sync_event")
@patch("app.terminal_management._store_display_name")
class TestRename(unittest.TestCase):
    def test_renames_in_place_keeping_identity(self, store, log):
        dev = FakeDevice([user(1, "1001", "cpo3 Krittapon M")])
        r = rename_terminal_account(None, dev, 1, "1001", "CPO2 Krittapon M", "admin")
        self.assertTrue(r["changed"])
        self.assertEqual(dev.calls[0]["uid"], 1)
        self.assertEqual(dev.calls[0]["user_id"], "1001")
        store.assert_called_once()

    def test_no_write_when_already_correct(self, store, log):
        dev = FakeDevice([user(1, "1001", "CPO2 Krittapon M")])
        r = rename_terminal_account(None, dev, 1, "1001", "CPO2 Krittapon M", "admin")
        self.assertFalse(r["changed"])
        self.assertEqual(dev.calls, [])

    def test_unconfirmed_when_device_did_not_change(self, store, log):
        dev = FakeDevice([user(1, "1001", "old")], apply=False)
        with self.assertRaises(TerminalManagementError):
            rename_terminal_account(None, dev, 1, "1001", "CPO2 Krittapon M", "admin")
        store.assert_not_called()

    def test_missing_account(self, store, log):
        with self.assertRaises(TerminalAccountNotFound):
            rename_terminal_account(None, FakeDevice([]), 1, "1001", "X", "admin")

    def test_rejects_non_ascii(self, store, log):
        from app.enrollment import EnrollmentError

        with self.assertRaises(EnrollmentError):
            rename_terminal_account(None, FakeDevice([user(1, "1001", "a")]), 1, "1001", "กฤตพล", "admin")


if __name__ == "__main__":
    unittest.main()


class TestAutoSync(unittest.TestCase):
    ROWS = [
        {"employee_id": "e1", "display_name": "ก", "english_name": "Krittapon M", "rank": "พ.จ.ท.",
         "device_id": 1, "device_user_id": "1001", "device_display_name": "cpo3 Krittapon M"},
        {"employee_id": "e2", "display_name": "ข", "english_name": "Pimai Khawsaad", "rank": "พ.จ.ต.",
         "device_id": 1, "device_user_id": "1003", "device_display_name": "CPO3 Pimai Khawsaad"},
        {"employee_id": "e3", "display_name": "ค", "english_name": None, "rank": "ร.ท.",
         "device_id": 1, "device_user_id": "1006", "device_display_name": "thapakorn chalui"},
    ]

    def test_only_mismatched_accounts_are_renamed(self):
        from app.api.routers import humans

        with patch("app.api.repository.terminal_name_rows", return_value=[dict(r) for r in self.ROWS]), patch(
            "app.api.routers.terminal_management._dispatch"
        ) as dispatch:
            summary = humans.sync_terminal_names(None, "admin")
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(dispatch.call_args.args[1]["device_user_id"], "1001")
        self.assertEqual(summary["renamed"], 1)
        self.assertEqual(summary["skipped_no_english_name"], 1)

    def test_device_failure_never_raises(self):
        from app.api.errors import ApiError
        from app.api.routers import humans

        with patch("app.api.repository.terminal_name_rows", return_value=[dict(self.ROWS[0])]), patch(
            "app.api.routers.terminal_management._dispatch", side_effect=ApiError(503, "DEVICE_UNAVAILABLE", "x")
        ):
            summary = humans.sync_terminal_names(None, "admin")
        self.assertEqual(summary["failed"], 1)
        self.assertIn("1001: DEVICE_UNAVAILABLE", summary["errors"])
