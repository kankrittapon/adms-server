"""Tests for app/enrollment_cli.py — operator CLI for physical enrollment steps.

PromptID: ADMS-Frontend-WriteEnablement-001
"""

import argparse
import io
import sys
import unittest
from unittest.mock import patch

from app.enrollment import PRIVILEGE_NORMAL_USER
from app.enrollment_cli import (
    build_parser,
    cmd_create_terminal_account,
    cmd_status,
    _connect_device,
)

from tests.test_enrollment import (
    FakeCursor,
    FakeDevice,
    FakeUser,
    make_db,
    make_enrollment_tuple,
)


class EnrollmentCliTest(unittest.TestCase):
    def _status_ns(self, enrollment_id=1):
        return argparse.Namespace(enrollment_id=enrollment_id)

    def _create_ns(self, enrollment_id=1, display_name="Somchai S.", confirm=False):
        return argparse.Namespace(
            enrollment_id=enrollment_id,
            display_name=display_name,
            confirm_collector_paused=confirm,
        )

    def _run(self, func, ns):
        buf = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = buf, buf
        try:
            rc = func(ns)
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        return rc, buf.getvalue()

    # --- status ------------------------------------------------------------

    def test_status_read_only_shows_state(self):
        cur = FakeCursor(fetchone_queue=[make_enrollment_tuple()])
        with patch("app.enrollment.get_db_connection") as m:
            make_db(m, cur)
            rc, out = self._run(cmd_status, self._status_ns(1))
        self.assertEqual(rc, 0)
        self.assertIn("status: RESERVED", out)
        self.assertIn("reserved_device_user_id: 1001", out)
        # read-only: no writes executed
        self.assertEqual([s for s, _ in cur.executed][0].split()[0].upper(), "SELECT")

    def test_status_missing_enrollment_fails_cleanly(self):
        with patch("app.enrollment.get_db_connection") as m:
            make_db(m, FakeCursor(fetchone_queue=[]))
            rc, out = self._run(cmd_status, self._status_ns(999))
        self.assertEqual(rc, 1)
        self.assertIn("ERROR", out)

    # --- collector-paused guard -------------------------------------------

    def test_create_terminal_account_refuses_without_confirm(self):
        rc, out = self._run(
            cmd_create_terminal_account, self._create_ns(confirm=False)
        )
        self.assertEqual(rc, 1)
        self.assertIn("--confirm-collector-paused", out)

    # --- create-terminal-account (full canonical path) --------------------

    def test_create_terminal_account_full_path(self):
        """Runs the real create_or_reconcile_terminal_account() with a FakeDevice."""
        # first fetch: CLI pre-write status check; second: canonical _fetch_enrollment
        cur = FakeCursor(
            fetchone_queue=[make_enrollment_tuple(), make_enrollment_tuple()],
            rowcount=1,
        )
        device = FakeDevice(users=[])  # empty roster -> set_user allowed
        with (
            patch("app.enrollment_cli._connect_device", return_value=device),
            patch("app.enrollment.get_db_connection") as m,
            patch("app.enrollment.ensure_device_user", return_value=42),
            patch("app.enrollment.log_sync_event"),
        ):
            make_db(m, cur)
            rc, out = self._run(
                cmd_create_terminal_account,
                self._create_ns(enrollment_id=1, display_name="Somchai S.", confirm=True),
            )
        self.assertEqual(rc, 0)
        self.assertIn("OK: terminal account created", out)
        # canonical function must have performed exactly one set_user with
        # NORMAL privilege and the reserved ID
        self.assertEqual(len(device.set_user_calls), 1)
        call = device.set_user_calls[0]
        self.assertEqual(call["user_id"], "1001")
        self.assertEqual(call["name"], "Somchai S.")
        self.assertEqual(call["privilege"], PRIVILEGE_NORMAL_USER)
        # state transition executed
        self.assertTrue(
            any(
                "TERMINAL_ACCOUNT_CREATED" in sql
                for sql, _ in cur.executed
            )
        )

    def test_create_terminal_account_reconciles_existing_matching_account(self):
        """Roster already has the reserved ID with matching (NORMAL) privilege
        -> canonical function reconciles without calling set_user() again."""
        # first fetch: CLI pre-write status check; second: canonical function
        cur = FakeCursor(fetchone_queue=[make_enrollment_tuple(), make_enrollment_tuple()])
        device = FakeDevice(users=[FakeUser("1001", uid=7, name="Someone Else")], commit_on_set_user=False)
        with (
            patch("app.enrollment_cli._connect_device", return_value=device),
            patch("app.enrollment.get_db_connection") as m,
            patch("app.enrollment.ensure_device_user", return_value=42),
            patch("app.enrollment.log_sync_event"),
        ):
            make_db(m, cur)
            rc, out = self._run(
                cmd_create_terminal_account,
                self._create_ns(enrollment_id=1, display_name="Somchai S.", confirm=True),
            )
        self.assertEqual(rc, 0)
        self.assertIn("OK: terminal account reconciled", out)
        self.assertEqual(device.set_user_calls, [])  # never overwritten

    def test_create_terminal_account_refuses_conflicting_account(self):
        """Roster has the reserved ID but with the wrong privilege -> STOP,
        never overwrite/delete."""
        # first fetch: CLI pre-write status check; second: canonical function
        cur = FakeCursor(fetchone_queue=[make_enrollment_tuple(), make_enrollment_tuple()])
        device = FakeDevice(
            users=[FakeUser("1001", uid=7, name="Someone Else", privilege=14)],
            commit_on_set_user=False,
        )
        with (
            patch("app.enrollment_cli._connect_device", return_value=device),
            patch("app.enrollment.get_db_connection") as m,
        ):
            make_db(m, cur)
            rc, out = self._run(
                cmd_create_terminal_account,
                self._create_ns(enrollment_id=1, display_name="Somchai S.", confirm=True),
            )
        self.assertEqual(rc, 1)
        self.assertIn("CONFLICT", out)
        self.assertEqual(device.set_user_calls, [])  # never overwritten

    def test_create_terminal_account_wrong_state_fails(self):
        """Enrollment not in RESERVED -> canonical function rejects it."""
        cur = FakeCursor(
            fetchone_queue=[make_enrollment_tuple(status="FINGERPRINT_ENROLLED")]
        )
        device = FakeDevice(users=[])
        with (
            patch("app.enrollment_cli._connect_device", return_value=device),
            patch("app.enrollment.get_db_connection") as m,
        ):
            make_db(m, cur)
            rc, out = self._run(
                cmd_create_terminal_account,
                self._create_ns(enrollment_id=1, display_name="Somchai S.", confirm=True),
            )
        self.assertEqual(rc, 1)
        self.assertIn("ERROR", out)
        self.assertEqual(device.set_user_calls, [])

    # --- device connection -------------------------------------------------

    def test_pyzk_missing_fails_helpfully(self):
        with patch.dict("sys.modules", {"zk": None}):
            with self.assertRaises(SystemExit) as ctx:
                _connect_device(None)
        self.assertIn("listener container", str(ctx.exception))

    def test_connect_failure_fails(self):
        import types

        class _NoZk:
            def __init__(self, *a, **k):
                pass

            def connect(self):
                return None

        fake_zk = types.ModuleType("zk")
        fake_zk.ZK = _NoZk
        class _Cfg:
            device_ip = "192.168.1.201"
            device_port = 4370
            device_timeout = 5
            device_password = 600
        with patch.dict("sys.modules", {"zk": fake_zk}):
            with self.assertRaises(SystemExit) as ctx:
                _connect_device(_Cfg())
        self.assertIn("could not connect", str(ctx.exception))

    # --- parser ------------------------------------------------------------

    def test_parser_requires_subcommand(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])


if __name__ == "__main__":
    unittest.main()
