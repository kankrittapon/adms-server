"""
Fingerprint re-enrollment — dedicated Collector state, single-owner.

PromptID: ADMS-TerminalManagement-020 Part B

pyzk's enroll_user() is confirmed (by reading its source) to block the
calling thread interactively for up to ~60s per attempt, up to 3 attempts
— fundamentally different from every other pyzk call used elsewhere in
this codebase (single command/response). Calling it from inside the
normal command-drain path (DeviceOwner.drain_pending, invoked between
live_capture() yields) would freeze attendance capture and all other
commands for its entire duration. This suite proves the dedicated
State.FINGERPRINT_ENROLLING architecture: the request is queued fast
(non-blocking), live_capture() is asked to end gracefully at the next
safe point (the same mechanism stop() already uses), the Collector
transitions to the new state, enroll_user() runs there exclusively (no
concurrent queue drain, no MQTT-thread pyzk access), and the Collector
always returns to LIVE afterward — success or failure.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.collector import CollectorStateEngine, State
from app.config import Config


class FakeFinger:
    def __init__(self, uid, fid):
        self.uid = uid
        self.fid = fid


class TestQueueingIsFastAndNonBlocking(unittest.TestCase):
    """Item 10: entering the dedicated state starts with a fast,
    non-blocking queued request — enroll_user() itself is never called
    from _execute_owned_command."""

    def setUp(self):
        self.cfg = Config.from_env()
        self.engine = CollectorStateEngine(self.cfg)
        self.engine.mqtt_service = MagicMock()

    def test_start_fingerprint_reenroll_does_not_call_enroll_user(self):
        device = MagicMock()
        device.get_users.return_value = [MagicMock(user_id="1004", uid=29)]
        self.engine.connection = device
        result = self.engine._execute_owned_command(
            "START_FINGERPRINT_REENROLL", {"device_user_id": "1004", "operator": "admin"}
        )
        self.assertEqual(result, {"device_user_id": "1004", "queued": True})
        device.enroll_user.assert_not_called()
        self.assertEqual(self.engine.pending_fingerprint_enroll, {
            "device_user_id": "1004", "uid": 29, "operator": "admin",
        })

    def test_account_not_found_rejected_fast(self):
        device = MagicMock()
        device.get_users.return_value = []
        self.engine.connection = device
        from app.terminal_management import TerminalAccountNotFound
        with self.assertRaises(TerminalAccountNotFound):
            self.engine._execute_owned_command(
                "START_FINGERPRINT_REENROLL", {"device_user_id": "9999", "operator": "admin"}
            )
        self.assertIsNone(self.engine.pending_fingerprint_enroll)


class TestLiveCaptureSuspension(unittest.TestCase):
    """Item 11: handle_live()'s safe-point check ends live_capture()
    gracefully (same mechanism as stop()) when a request is pending, and
    the state machine transitions to FINGERPRINT_ENROLLING once the
    generator has actually exited — never mid-recv()."""

    def test_handle_live_source_ends_capture_and_transitions_at_safe_point(self):
        import inspect

        src = inspect.getsource(CollectorStateEngine.handle_live)
        pending_idx = src.find("pending_fingerprint_enroll is not None")
        end_capture_idx = src.find("end_live_capture = True")
        transition_idx = src.rfind("transition_to(State.FINGERPRINT_ENROLLING)")
        drain_idx = src.find("device_owner.drain_pending")
        self.assertNotEqual(pending_idx, -1)
        self.assertNotEqual(end_capture_idx, -1)
        self.assertNotEqual(transition_idx, -1)
        # The pending-request check (and end_live_capture) must happen
        # AFTER draining the normal command queue at the same safe point,
        # and the transition must happen only after the for-loop (i.e.
        # after live_capture() actually ended), not inside it.
        self.assertLess(drain_idx, end_capture_idx)
        self.assertGreater(transition_idx, end_capture_idx)


class TestFingerprintEnrollingStateExecution(unittest.TestCase):
    """Items 12-15, 17-18, 20: single-owner execution, success/failure
    read-back confirmation, always returns to LIVE, history untouched."""

    def setUp(self):
        self.cfg = Config.from_env()
        self.engine = CollectorStateEngine(self.cfg)
        self.engine.mqtt_service = MagicMock()
        self.engine.pending_fingerprint_enroll = {
            "device_user_id": "1004", "uid": 29, "operator": "admin",
        }

    @patch("app.collector.log_sync_event")
    def test_item13_success_confirmed_via_template_count_readback(self, mock_log):
        device = MagicMock()
        device.get_templates.side_effect = [
            [],  # before
            [FakeFinger(29, 0)],  # after — one new template
        ]
        device.enroll_user.return_value = True
        self.engine.connection = device
        self.engine.handle_fingerprint_enrolling()

        device.enroll_user.assert_called_once_with(uid=29, user_id="1004")
        self.assertEqual(self.engine.state, State.LIVE)  # item 17: returns to LIVE
        self.assertEqual(self.engine.last_fingerprint_enroll_result, {"device_user_id": "1004", "success": True})
        event_types = [c.args[1] for c in mock_log.call_args_list]
        self.assertIn("TERMINAL_FINGERPRINT_REENROLL_STARTED", event_types)
        self.assertIn("TERMINAL_FINGERPRINT_REENROLL_CONFIRMED", event_types)

    @patch("app.collector.log_sync_event")
    def test_item14_failure_never_trusts_return_value_alone(self, mock_log):
        # enroll_user() reports True, but the read-back shows no new
        # template — must NOT be reported as success (same "return value
        # is not authoritative" principle as set_user(), PromptID 010).
        device = MagicMock()
        device.get_templates.side_effect = [[], []]  # no change
        device.enroll_user.return_value = True
        self.engine.connection = device
        self.engine.handle_fingerprint_enrolling()

        self.assertEqual(self.engine.state, State.LIVE)  # item 18: returns to LIVE even on failure
        self.assertEqual(self.engine.last_fingerprint_enroll_result, {"device_user_id": "1004", "success": False})
        event_types = [c.args[1] for c in mock_log.call_args_list]
        self.assertIn("TERMINAL_FINGERPRINT_REENROLL_FAILED", event_types)

    @patch("app.collector.log_sync_event")
    def test_item15_timeout_reported_as_done_false_still_confirmed_check_runs(self, mock_log):
        # pyzk's enroll_user() itself returns False (not an exception) on
        # its own internal timeout/no-finger-placed case.
        device = MagicMock()
        device.get_templates.side_effect = [[], []]
        device.enroll_user.return_value = False
        self.engine.connection = device
        self.engine.handle_fingerprint_enrolling()
        self.assertEqual(self.engine.last_fingerprint_enroll_result["success"], False)
        self.assertEqual(self.engine.state, State.LIVE)

    @patch("app.collector.log_sync_event")
    def test_item16_connection_exception_triggers_reconnect_not_stuck_state(self, mock_log):
        device = MagicMock()
        device.get_templates.return_value = []
        device.enroll_user.side_effect = ConnectionError("socket closed")
        self.engine.connection = device
        self.engine.handle_fingerprint_enrolling()
        self.assertEqual(self.engine.state, State.BACKOFF)  # reconnect path, not stuck
        event_types = [c.args[1] for c in mock_log.call_args_list]
        self.assertIn("TERMINAL_FINGERPRINT_REENROLL_FAILED", event_types)

    @patch("app.collector.log_sync_event")
    def test_item20_never_touches_human_attendance_enrollment_mapping_tables(self, mock_log):
        import inspect

        src = inspect.getsource(CollectorStateEngine.handle_fingerprint_enrolling)
        for forbidden in ("human_employees", "attendance_logs", "device_user_enrollments", "employee_device_mappings"):
            self.assertNotIn(forbidden, src)

    def test_pending_request_cleared_before_execution(self):
        device = MagicMock()
        device.get_templates.return_value = []
        device.enroll_user.return_value = False
        self.engine.connection = device
        with patch("app.collector.log_sync_event"):
            self.engine.handle_fingerprint_enrolling()
        self.assertIsNone(self.engine.pending_fingerprint_enroll)


class TestSingleOwnerStructural(unittest.TestCase):
    """Item 19: no concurrent roster/device command — MQTT thread still
    never touches self.connection, and enroll_user() is called exclusively
    from handle_fingerprint_enrolling (owner thread only)."""

    def test_enroll_user_called_only_from_owner_state_handler(self):
        import inspect

        import app.collector as collector_mod

        full_src = inspect.getsource(collector_mod)
        occurrences = full_src.count(".enroll_user(")
        handler_src = inspect.getsource(CollectorStateEngine.handle_fingerprint_enrolling)
        self.assertEqual(occurrences, handler_src.count(".enroll_user("))

    def test_handle_device_command_still_never_touches_connection(self):
        import inspect

        src = inspect.getsource(CollectorStateEngine.handle_device_command)
        self.assertNotIn("self.connection.", src)


class TestHealthTelemetryPolling(unittest.TestCase):
    """The real result arrives asynchronously — API polls the same
    Collector-health-bridge file every other telemetry field uses."""

    def test_write_health_status_exposes_pending_and_last_result(self):
        import inspect

        src = inspect.getsource(CollectorStateEngine.write_health_status)
        self.assertIn("pending_fingerprint_enroll_device_user_id", src)
        self.assertIn("last_fingerprint_enroll_result", src)


class TestReenrollAPIEndpointGating(unittest.TestCase):
    def test_endpoint_admin_and_write_session_gated(self):
        import inspect

        import app.api.routers.terminal_management as tm_router

        src = inspect.getsource(tm_router)
        idx = src.find("/fingerprint/reenroll\"")
        segment = src[idx:idx + 400]
        self.assertIn("ROLES_ADMIN_ONLY", segment)
        self.assertIn("require_write_session", segment)

    def test_status_endpoint_is_read_only(self):
        import inspect

        import app.api.routers.terminal_management as tm_router

        src = inspect.getsource(tm_router)
        idx = src.find("reenroll-status")
        segment = src[idx:idx + 400]
        self.assertNotIn("require_write_session", segment)


if __name__ == "__main__":
    unittest.main()
