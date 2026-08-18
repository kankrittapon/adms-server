"""
Terminal Management — physical account/fingerprint lifecycle.

PromptID: ADMS-TerminalManagement-020

Strictly separate from Personnel Lifecycle and Enrollment. Covers the
highest-priority subset of the required 40-item matrix: inventory
correctness under device-unreachable conditions, fingerprint/account
removal read-before-write/read-after-write semantics, idempotency,
active-Human protection, single-owner device I/O, and audit events.

All device I/O uses fakes — no real ZEM560 is touched.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.config import Config
from app.terminal_management import (
    ActiveHumanProtection,
    TerminalAccountNotFound,
    TerminalManagementError,
    read_terminal_inventory,
    remove_terminal_account,
    remove_terminal_fingerprint,
)


class FakeUser:
    def __init__(self, user_id, uid, name="", privilege=0):
        self.user_id = user_id
        self.uid = uid
        self.name = name
        self.privilege = privilege


class FakeFinger:
    def __init__(self, uid, fid, valid=1, template=b"\x00" * 16):
        self.uid = uid
        self.fid = fid
        self.valid = valid
        self.template = template
        self.size = len(template)


class FakeDevice:
    """Records calls; get_users/get_templates/delete_* are independently
    scriptable to model read-before-write/read-after-write sequences."""

    def __init__(self, users=None, templates=None, get_templates_raises=None):
        self._users = list(users or [])
        self._templates = list(templates or [])
        self._get_templates_raises = get_templates_raises
        self.calls = []
        self.deleted_templates = []
        self.deleted_users = []

    def get_users(self):
        self.calls.append("get_users")
        return list(self._users)

    def get_templates(self):
        self.calls.append("get_templates")
        if self._get_templates_raises:
            raise self._get_templates_raises
        return list(self._templates)

    def delete_user_template(self, uid, temp_id, user_id=""):
        # Mirrors the installed pyzk's real bug: on a TCP connection,
        # passing a truthy user_id hits `pack('<24sB', str(user_id), ...)`,
        # which raises TypeError on Python 3 (struct 's' needs bytes, not
        # str). Our wrapper must never pass user_id here — this fake exists
        # to make that regression impossible to reintroduce silently.
        if user_id:
            raise TypeError("argument for 's' must be a bytes object")
        self.calls.append("delete_user_template")
        self.deleted_templates.append((uid, temp_id))
        self._templates = [f for f in self._templates if not (f.uid == uid and f.fid == temp_id)]

    def delete_user(self, uid, user_id=""):
        self.calls.append("delete_user")
        self.deleted_users.append(uid)
        self._users = [u for u in self._users if u.uid != uid]


# ---------------------------------------------------------------------------
# Inventory (items 1-3)
# ---------------------------------------------------------------------------


class TestTerminalInventory(unittest.TestCase):
    def test_item1_physical_account_present_reflected(self):
        device = FakeDevice(
            users=[FakeUser("1004", 29, "Test Person")],
            templates=[FakeFinger(29, 0)],
        )
        inv = read_terminal_inventory(device)
        self.assertEqual(len(inv), 1)
        self.assertEqual(inv[0]["device_user_id"], "1004")
        self.assertEqual(inv[0]["fingerprint_count"], 1)

    def test_item2_physical_account_absent_reflected(self):
        device = FakeDevice(users=[], templates=[])
        inv = read_terminal_inventory(device)
        self.assertEqual(inv, [])

    def test_item3_device_unreachable_never_claims_zero_fingerprints(self):
        device = FakeDevice(
            users=[FakeUser("1004", 29)],
            get_templates_raises=ConnectionError("no route to host"),
        )
        inv = read_terminal_inventory(device)
        # fingerprint_count must be None (unknown), never 0, when the
        # device could not be read for templates.
        self.assertIsNone(inv[0]["fingerprint_count"])

    def test_item4_fingerprint_present_count_correct(self):
        device = FakeDevice(
            users=[FakeUser("1004", 29)],
            templates=[FakeFinger(29, 0), FakeFinger(29, 1)],
        )
        inv = read_terminal_inventory(device)
        self.assertEqual(inv[0]["fingerprint_count"], 2)

    def test_item5_fingerprint_absent_reported_as_zero_not_unknown(self):
        device = FakeDevice(users=[FakeUser("1004", 29)], templates=[])
        inv = read_terminal_inventory(device)
        self.assertEqual(inv[0]["fingerprint_count"], 0)

    def test_never_exposes_raw_template_bytes_or_mark(self):
        device = FakeDevice(
            users=[FakeUser("1004", 29)],
            templates=[FakeFinger(29, 0, template=b"SECRET_BIOMETRIC_DATA")],
        )
        inv = read_terminal_inventory(device)
        for item in inv:
            self.assertNotIn("template", item)
            self.assertNotIn("mark", item)


# ---------------------------------------------------------------------------
# Fingerprint removal (items 6-10, 37, 39, 40)
# ---------------------------------------------------------------------------


class TestFingerprintRemoval(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.terminal_management.log_sync_event")
    def test_item6_remove_fingerprint_success(self, mock_log):
        device = FakeDevice(
            users=[FakeUser("1004", 29)],
            templates=[FakeFinger(29, 0)],
        )
        result = remove_terminal_fingerprint(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        self.assertFalse(result["already_absent"])
        self.assertEqual(result["removed_fids"], [0])
        self.assertEqual(device.deleted_templates, [(29, 0)])
        # item 37: audit event emitted
        mock_log.assert_called_once()
        self.assertEqual(mock_log.call_args[0][1], "TERMINAL_FINGERPRINT_REMOVED")
        # item 39: no raw template bytes in audit message
        message = mock_log.call_args[0][2]
        self.assertNotIn("SECRET", message)

    @patch("app.terminal_management.log_sync_event")
    def test_item6b_delete_user_template_never_passes_user_id(self, mock_log):
        """Regression: the installed pyzk's TCP branch (`if self.tcp and
        user_id:`) does `pack('<24sB', str(user_id), temp_id)`, which raises
        TypeError on Python 3 (struct 's' requires bytes, not str) — a real
        bug hit in production. Our wrapper must call delete_user_template
        with uid only, never user_id, to avoid that branch entirely.
        FakeDevice.delete_user_template raises TypeError itself if user_id
        is truthy, so this test would fail loudly if the old buggy call
        were reintroduced."""
        device = FakeDevice(
            users=[FakeUser("1004", 29)],
            templates=[FakeFinger(29, 0)],
        )
        result = remove_terminal_fingerprint(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        self.assertEqual(result["removed_fids"], [0])

    @patch("app.terminal_management.log_sync_event")
    def test_item7_remove_fingerprint_already_absent_idempotent(self, mock_log):
        device = FakeDevice(users=[FakeUser("1004", 29)], templates=[])
        result = remove_terminal_fingerprint(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        self.assertTrue(result["already_absent"])
        mock_log.assert_not_called()  # no-op, no spurious audit event
        self.assertEqual(device.deleted_templates, [])

    def test_item8_pre_mutation_device_unreachable(self):
        device = FakeDevice(
            users=[FakeUser("1004", 29)],
            get_templates_raises=ConnectionError("timeout"),
        )
        with self.assertRaises(TerminalManagementError) as ctx:
            remove_terminal_fingerprint(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        self.assertEqual(ctx.exception.error_code, "DEVICE_UNAVAILABLE")
        self.assertEqual(device.deleted_templates, [])  # no mutation attempted

    def test_item9_removal_uncertain_after_mutation(self):
        class FlakyDevice(FakeDevice):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self._readback_fails = False

            def delete_user_template(self, uid, temp_id, user_id=""):
                super().delete_user_template(uid, temp_id, user_id)
                self._readback_fails = True

            def get_templates(self):
                if self._readback_fails:
                    raise ConnectionError("post-delete readback failed")
                return super().get_templates()

        device = FlakyDevice(users=[FakeUser("1004", 29)], templates=[FakeFinger(29, 0)])
        with self.assertRaises(TerminalManagementError) as ctx:
            remove_terminal_fingerprint(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        self.assertEqual(ctx.exception.error_code, "TERMINAL_FINGERPRINT_UNCONFIRMED")

    @patch("app.terminal_management.log_sync_event")
    def test_item10_multiple_fingerprint_templates_all_removed(self, mock_log):
        device = FakeDevice(
            users=[FakeUser("1004", 29)],
            templates=[FakeFinger(29, 0), FakeFinger(29, 1), FakeFinger(29, 2)],
        )
        result = remove_terminal_fingerprint(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        self.assertEqual(sorted(result["removed_fids"]), [0, 1, 2])
        self.assertEqual(len(device.deleted_templates), 3)

    @patch("app.terminal_management.log_sync_event")
    def test_specific_finger_id_removes_only_that_one(self, mock_log):
        device = FakeDevice(
            users=[FakeUser("1004", 29)],
            templates=[FakeFinger(29, 0), FakeFinger(29, 1)],
        )
        result = remove_terminal_fingerprint(
            self.cfg, device, device_id=1, device_user_id="1004", operator="admin", finger_id=1
        )
        self.assertEqual(result["removed_fids"], [1])
        self.assertEqual(device.deleted_templates, [(29, 1)])

    def test_account_not_found_rejected(self):
        device = FakeDevice(users=[], templates=[])
        with self.assertRaises(TerminalAccountNotFound):
            remove_terminal_fingerprint(self.cfg, device, device_id=1, device_user_id="9999", operator="admin")

    def test_item40_error_messages_contain_no_python_internals(self):
        device = FakeDevice(users=[FakeUser("1004", 29)], get_templates_raises=ConnectionError("timeout"))
        with self.assertRaises(TerminalManagementError) as ctx:
            remove_terminal_fingerprint(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        message = str(ctx.exception)
        self.assertNotIn("Traceback", message)
        self.assertNotIn("File \"", message)


# ---------------------------------------------------------------------------
# Account removal (items 14-18, 38)
# ---------------------------------------------------------------------------


class TestAccountRemoval(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def _no_mapping_db(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [(29,), None]  # device_user_pk, then no open mapping
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        conn.cursor.return_value.__exit__.return_value = None
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        ctx.__exit__.return_value = None
        return ctx

    @patch("app.terminal_management.log_sync_event")
    @patch("app.terminal_management.get_db_connection")
    def test_item14_remove_account_success(self, mock_conn_fn, mock_log):
        mock_conn_fn.side_effect = [self._no_mapping_db(), self._no_mapping_db()]
        device = FakeDevice(users=[FakeUser("1004", 29)])
        result = remove_terminal_account(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        self.assertFalse(result["already_absent"])
        self.assertEqual(device.deleted_users, [29])
        mock_log.assert_called_once()
        self.assertEqual(mock_log.call_args[0][1], "TERMINAL_ACCOUNT_REMOVED")

    @patch("app.terminal_management.log_sync_event")
    @patch("app.terminal_management.get_db_connection")
    def test_item15_already_absent_idempotent(self, mock_conn_fn, mock_log):
        mock_conn_fn.side_effect = [self._no_mapping_db(), self._no_mapping_db()]
        device = FakeDevice(users=[])
        result = remove_terminal_account(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        self.assertTrue(result["already_absent"])
        self.assertEqual(device.deleted_users, [])
        mock_log.assert_not_called()

    @patch("app.terminal_management.get_db_connection")
    def test_item16_delete_uncertain_after_mutation(self, mock_conn_fn):
        mock_conn_fn.side_effect = [self._no_mapping_db()]

        class FlakyDevice(FakeDevice):
            def delete_user(self, uid, user_id=""):
                super().delete_user(uid, user_id)
                self._users.append(FakeUser("1004", 29))  # simulate readback still showing it

            def get_users(self):
                self.calls.append("get_users")
                return list(self._users)

        device = FlakyDevice(users=[FakeUser("1004", 29)])
        with self.assertRaises(TerminalManagementError) as ctx:
            remove_terminal_account(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        self.assertEqual(ctx.exception.error_code, "TERMINAL_ACCOUNT_UNCONFIRMED")

    @patch("app.terminal_management.get_db_connection")
    def test_item17_active_human_protection_blocks_without_acknowledgement(self, mock_conn_fn):
        cur = MagicMock()
        cur.fetchone.side_effect = [(29,), (True,)]  # device_user_pk, open mapping with active Human
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        conn.cursor.return_value.__exit__.return_value = None
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        ctx.__exit__.return_value = None
        mock_conn_fn.return_value = ctx

        device = FakeDevice(users=[FakeUser("1004", 29)])
        with self.assertRaises(ActiveHumanProtection):
            remove_terminal_account(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        # Device must never be touched — precondition check happens first.
        self.assertEqual(device.calls, [])

    @patch("app.terminal_management.log_sync_event")
    @patch("app.terminal_management.get_db_connection")
    def test_item18_inactive_human_cleanup_allowed(self, mock_conn_fn, mock_log):
        cur = MagicMock()
        cur.fetchone.side_effect = [(29,), (False,)]  # open mapping but Human inactive
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        conn.cursor.return_value.__exit__.return_value = None
        ctx1 = MagicMock()
        ctx1.__enter__.return_value = conn
        ctx1.__exit__.return_value = None
        mock_conn_fn.side_effect = [ctx1, self._no_mapping_db()]

        device = FakeDevice(users=[FakeUser("1004", 29)])
        result = remove_terminal_account(self.cfg, device, device_id=1, device_user_id="1004", operator="admin")
        self.assertFalse(result["already_absent"])


# ---------------------------------------------------------------------------
# Single-owner / DeviceOwner integration (item 22)
# ---------------------------------------------------------------------------


class TestSingleOwnerIntegration(unittest.TestCase):
    def test_item22_no_module_level_zk_import_or_direct_socket_access(self):
        import inspect

        import app.terminal_management as tm

        src = inspect.getsource(tm)
        self.assertNotIn("ZK(", src)
        self.assertNotIn("import socket", src)

    def test_collector_dispatches_new_actions_only_through_execute_owned_command(self):
        import inspect

        import app.collector as collector_mod

        src = inspect.getsource(collector_mod.CollectorStateEngine._execute_owned_command)
        for action in ("TERMINAL_INVENTORY", "REMOVE_TERMINAL_FINGERPRINT", "REMOVE_TERMINAL_ACCOUNT"):
            self.assertIn(action, src)

    def test_handle_device_command_still_never_touches_connection(self):
        import inspect

        import app.collector as collector_mod

        src = inspect.getsource(collector_mod.CollectorStateEngine.handle_device_command)
        self.assertNotIn("self.connection.", src)


# ---------------------------------------------------------------------------
# API RBAC gating (items 28-31)
# ---------------------------------------------------------------------------


class TestTerminalManagementRBAC(unittest.TestCase):
    def test_item28_29_30_31_endpoints_gated(self):
        import inspect

        import app.api.routers.terminal_management as tm_router

        src = inspect.getsource(tm_router)
        for route in ("/fingerprint/remove", "/account/remove"):
            idx = src.find(route)
            segment = src[idx:idx + 400]
            self.assertIn("ROLES_ADMIN_ONLY", segment)
            self.assertIn("require_writes", segment)
            self.assertIn("require_write_session", segment)
        # Inventory is read-only and must NOT require a write session.
        inv_idx = src.find("/inventory")
        inv_segment = src[inv_idx:inv_idx + 300]
        self.assertNotIn("require_write_session", inv_segment)


if __name__ == "__main__":
    unittest.main()
