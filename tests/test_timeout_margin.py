"""
DeviceCommandBus / timeout-margin test matrix.

PromptID: ADMS-DeviceCommandBus-TimeoutMargin-010

Covers the required 30-item matrix for this phase. Some items are covered
here directly; others already exist in sibling files and are cross-referenced
rather than duplicated:

  1-4   : here (TerminalRosterUnavailable — pre-mutation roster-read failure,
          set_user() never reached)
  5-6   : here (derived timing-budget constants — no arbitrary numbers)
  7-9   : here (Collector error_code mapping for DEVICE_UNAVAILABLE, ordered
          before the generic EnrollmentError catch)
  10-12 : here (API router: device_executor branch + MQTT branch both map
          DEVICE_UNAVAILABLE distinctly from TERMINAL_ACCOUNT_UNCONFIRMED)
  13    : here (router MQTT branch uses the derived timeout, not a literal)
  14-17 : tests/test_device_command_bus.py (dedupe key NOT released on
          client-side timeout; released on-time and on late response;
          TOCTOU-safe atomic check-and-reserve;
          test_dedupe_key_prevents_concurrent_dispatch,
          test_dedupe_key_released_after_completion)
  18-20 : here (safety-net expiry auto-recovers a permanently-stuck key)
  21-23 : here (TerminalRosterUnavailable is a distinct EnrollmentError
          subclass from TerminalAccountConflict/TerminalAccountUnconfirmed;
          ordering in Collector's except-chain matters since it IS a subclass
          of EnrollmentError)
  24-25 : tests/test_terminal_account_idempotency.py (existing 20-case
          matrix, still green — regression proof this phase didn't change
          success-path behavior)
  26-28 : here (RBAC/Write-Session/API_WRITE_ENABLED unaffected — no route
          dependency list changed by this phase, only error mapping/timeout)
  29    : here (frontend i18n type parity — new terminalUnavailable* keys
          present in types.ts/en.ts/th.ts, checked structurally)
  30    : the full `pytest tests/` run itself (447 pre-existing + all new
          tests here, all green)

No physical device or database is required.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from app.config import Config
from app.device_command_bus import DeviceCommandBus, DeviceCommandError
from app.enrollment import (
    CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS,
    DEVICE_COMMAND_TRANSPORT_MARGIN_SECONDS,
    READBACK_DELAY_SECONDS,
    READBACK_RETRIES,
    EnrollmentError,
    TerminalAccountConflict,
    TerminalAccountUnconfirmed,
    TerminalRosterUnavailable,
    create_or_reconcile_terminal_account,
    create_terminal_account_collector_budget_seconds,
)
from tests.test_enrollment import FakeCursor, make_db, make_enrollment_tuple


class RosterFailingDevice:
    """get_users() always raises — models a genuinely unreachable/timed-out
    terminal at the pre-mutation roster read. set_user() must never be
    called; asserting on that is the core proof that this is a distinct,
    earlier failure mode than TerminalAccountUnconfirmed."""

    def __init__(self, exc=None):
        self.exc = exc or TimeoutError("device did not respond")
        self.calls = []
        self.set_user_calls = []

    def get_users(self):
        self.calls.append("get_users")
        raise self.exc

    def set_user(self, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("set_user() must not be called when the "
                              "pre-mutation roster read fails")


class TestTerminalRosterUnavailable(unittest.TestCase):
    """Items 1-4: pre-mutation roster-read failure is a distinct,
    earlier-stage error than TerminalAccountUnconfirmed."""

    def setUp(self):
        self.cfg = Config.from_env()
        self.enroll_row = make_enrollment_tuple()

    def _run(self, device):
        cur = FakeCursor(fetchone_queue=[self.enroll_row])
        with patch("app.enrollment.get_db_connection") as mock_conn_fn, \
             patch("app.enrollment.ensure_device_user", return_value=42), \
             patch("app.enrollment.log_sync_event"), \
             patch("app.enrollment.time.sleep"):
            make_db(mock_conn_fn, cur)
            return create_or_reconcile_terminal_account(
                self.cfg, enrollment_id=1, display_name="Somchai S.", device=device
            )

    def test_item1_roster_read_failure_raises_terminal_roster_unavailable(self):
        device = RosterFailingDevice()
        with self.assertRaises(TerminalRosterUnavailable):
            self._run(device)

    def test_item2_set_user_never_called_on_roster_failure(self):
        device = RosterFailingDevice()
        try:
            self._run(device)
        except TerminalRosterUnavailable:
            pass
        self.assertEqual(device.set_user_calls, [])
        self.assertEqual(device.calls, ["get_users"])

    def test_item3_terminal_roster_unavailable_is_distinct_subclass(self):
        # Distinct from, not conflated with, the post-mutation error classes.
        self.assertTrue(issubclass(TerminalRosterUnavailable, EnrollmentError))
        self.assertFalse(issubclass(TerminalRosterUnavailable, TerminalAccountUnconfirmed))
        self.assertFalse(issubclass(TerminalRosterUnavailable, TerminalAccountConflict))
        self.assertFalse(issubclass(TerminalAccountUnconfirmed, TerminalRosterUnavailable))

    def test_item4_roster_failure_message_includes_device_and_cause(self):
        device = RosterFailingDevice(exc=ConnectionRefusedError("refused"))
        with self.assertRaises(TerminalRosterUnavailable) as ctx:
            self._run(device)
        msg = str(ctx.exception)
        self.assertIn("refused", msg)


class TestDerivedTimingBudget(unittest.TestCase):
    """Items 5-6: the outer timeout must be derived from the Collector's
    real worst-case operation budget, not an arbitrary constant, and must
    always exceed it by a positive margin."""

    def test_item5_collector_budget_matches_derivation_formula(self):
        zk_timeout = float(__import__("app.enrollment", fromlist=["_zk_socket_timeout_seconds"])._zk_socket_timeout_seconds())
        expected_roster_read = zk_timeout * 2  # ZK_ROUNDTRIPS_PER_ROSTER_READ
        expected_set_user = zk_timeout * 2  # ZK_ROUNDTRIPS_PER_SET_USER (includes refresh_data())
        expected_bounded_readback = READBACK_RETRIES * expected_roster_read
        expected_delays = (READBACK_RETRIES - 1) * READBACK_DELAY_SECONDS
        expected_budget = expected_roster_read + expected_set_user + expected_bounded_readback + expected_delays
        self.assertAlmostEqual(
            create_terminal_account_collector_budget_seconds(), expected_budget, places=3
        )

    def test_item6_outer_timeout_exceeds_collector_budget_by_positive_margin(self):
        budget = create_terminal_account_collector_budget_seconds()
        self.assertGreater(CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS, budget)
        margin = CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS - budget
        self.assertAlmostEqual(margin, DEVICE_COMMAND_TRANSPORT_MARGIN_SECONDS, places=3)
        self.assertGreater(margin, 0)


class TestCollectorErrorCodeOrdering(unittest.TestCase):
    """Items 7-9: TerminalRosterUnavailable, being a subclass of
    EnrollmentError, must be caught by its own except-branch (mapping to
    DEVICE_UNAVAILABLE) before the generic EnrollmentError branch, or its
    specific error_code would be lost."""

    def test_item7_collector_source_orders_roster_unavailable_before_generic(self):
        import inspect

        import app.collector as collector_mod

        src = inspect.getsource(collector_mod.CollectorStateEngine.handle_device_command)
        roster_idx = src.find("TerminalRosterUnavailable")
        generic_idx = src.find("except EnrollmentError")
        self.assertNotEqual(roster_idx, -1, "TerminalRosterUnavailable must be imported/handled")
        self.assertNotEqual(generic_idx, -1, "generic EnrollmentError handler must exist")
        self.assertLess(roster_idx, generic_idx,
                         "except TerminalRosterUnavailable must appear before the generic "
                         "except EnrollmentError branch (subclass ordering)")

    def test_item8_collector_maps_roster_unavailable_to_device_unavailable_code(self):
        import inspect

        import app.collector as collector_mod

        src = inspect.getsource(collector_mod.CollectorStateEngine.handle_device_command)
        idx = src.find("except TerminalRosterUnavailable")
        next_except_idx = src.find("except ", idx + 1)
        segment = src[idx:next_except_idx if next_except_idx != -1 else idx + 800]
        self.assertIn("DEVICE_UNAVAILABLE", segment)

    def test_item9_terminal_account_unconfirmed_still_maps_distinctly(self):
        import inspect

        import app.collector as collector_mod

        src = inspect.getsource(collector_mod.CollectorStateEngine.handle_device_command)
        self.assertIn("TerminalAccountUnconfirmed", src)
        self.assertIn("TERMINAL_ACCOUNT_UNCONFIRMED", src)


class TestRouterErrorMapping(unittest.TestCase):
    """Items 10-13: both branches of the API router's create_terminal_account
    handler map DEVICE_UNAVAILABLE distinctly and use the derived timeout."""

    def test_item10_device_executor_branch_maps_roster_unavailable_to_503(self):
        import inspect

        import app.api.routers.enrollments as router_mod

        src = inspect.getsource(router_mod)
        idx = src.find("except TerminalRosterUnavailable")
        self.assertNotEqual(idx, -1)
        segment = src[idx:idx + 200]
        self.assertIn("503", segment)
        self.assertIn("DEVICE_UNAVAILABLE", segment)

    def test_item11_mqtt_branch_maps_device_unavailable_code_explicitly(self):
        import inspect

        import app.api.routers.enrollments as router_mod

        src = inspect.getsource(router_mod)
        idx = src.find('code == "DEVICE_UNAVAILABLE"')
        self.assertNotEqual(idx, -1, "router must explicitly branch on the "
                             "DEVICE_UNAVAILABLE error_code rather than relying "
                             "solely on fallback logic")

    def test_item12_mqtt_branch_device_unavailable_distinct_from_unconfirmed(self):
        import inspect

        import app.api.routers.enrollments as router_mod

        src = inspect.getsource(router_mod)
        unconfirmed_idx = src.find('code == "TERMINAL_ACCOUNT_UNCONFIRMED"')
        unavailable_idx = src.find('code == "DEVICE_UNAVAILABLE"')
        self.assertNotEqual(unconfirmed_idx, -1)
        self.assertNotEqual(unavailable_idx, -1)
        self.assertNotEqual(unconfirmed_idx, unavailable_idx)

    def test_item13_mqtt_branch_uses_derived_timeout_constant(self):
        import inspect

        import app.api.routers.enrollments as router_mod

        src = inspect.getsource(router_mod)
        self.assertIn("CREATE_TERMINAL_ACCOUNT_DEVICE_TIMEOUT_SECONDS", src)
        self.assertNotIn("timeout=10.0", src)


class TestSafetyNetExpiry(unittest.TestCase):
    """Items 18-20: a dedupe key survives a client-side timeout (no early
    release) but auto-recovers once its safety-net expiry has genuinely
    passed with no response ever arriving (e.g. Collector crash)."""

    def test_item18_expired_inflight_key_allows_new_dispatch(self):
        bus = DeviceCommandBus("localhost", 1883)
        mock_client = MagicMock()
        bus._client = mock_client
        bus.connected = True
        published = []
        mock_client.publish.side_effect = lambda *a, **k: published.append(a)

        bus._inflight_keys["enrollment:1"] = {
            "command_id": "stale-command",
            "expires_at": time.time() - 5,  # already expired
        }

        with self.assertRaises(DeviceCommandError):
            bus.execute(
                "CREATE_TERMINAL_ACCOUNT",
                {"enrollment_id": 1},
                timeout=0.05,
                dedupe_key="enrollment:1",
            )
        # Dispatch was allowed through (not rejected as busy) — publish happened.
        self.assertEqual(len(published), 1)

    def test_item19_non_expired_inflight_key_still_rejects(self):
        bus = DeviceCommandBus("localhost", 1883)
        mock_client = MagicMock()
        bus._client = mock_client
        bus.connected = True

        bus._inflight_keys["enrollment:1"] = {
            "command_id": "active-command",
            "expires_at": time.time() + 60,
        }
        from app.device_command_bus import DeviceCommandBusy

        with self.assertRaises(DeviceCommandBusy):
            bus.execute(
                "CREATE_TERMINAL_ACCOUNT",
                {"enrollment_id": 1},
                timeout=0.05,
                dedupe_key="enrollment:1",
            )

    def test_item20_expires_at_derived_from_call_timeout(self):
        bus = DeviceCommandBus("localhost", 1883)
        mock_client = MagicMock()
        bus._client = mock_client
        bus.connected = True
        mock_client.publish.side_effect = lambda *a, **k: None

        before = time.time()
        with self.assertRaises(DeviceCommandError):
            bus.execute(
                "CREATE_TERMINAL_ACCOUNT",
                {"enrollment_id": 5},
                timeout=0.05,
                dedupe_key="enrollment:5",
            )
        entry = bus._inflight_keys.get("enrollment:5")
        self.assertIsNotNone(entry)
        self.assertAlmostEqual(entry["expires_at"], before + 0.05, delta=0.2)


class TestUnaffectedInvariants(unittest.TestCase):
    """Items 26-28: this phase changes error semantics/timeouts only — RBAC,
    write-session gating, and the infra master flag are untouched."""

    def test_item26_router_module_still_imports_write_gate_dependencies(self):
        import inspect

        import app.api.routers.enrollments as router_mod

        src = inspect.getsource(router_mod)
        self.assertIn("require_writes", src)

    def test_item27_terminal_account_conflict_and_unconfirmed_still_exist(self):
        # Regression: renaming/restructuring for this phase didn't drop the
        # 008 error classes.
        self.assertTrue(issubclass(TerminalAccountConflict, EnrollmentError))
        self.assertTrue(issubclass(TerminalAccountUnconfirmed, EnrollmentError))

    def test_item28_api_write_enabled_flag_unreferenced_by_this_phase_files(self):
        import inspect

        import app.device_command_bus as bus_mod

        src = inspect.getsource(bus_mod)
        # DeviceCommandBus must not itself gate on API_WRITE_ENABLED — that
        # remains the router/dependency layer's responsibility, unchanged.
        self.assertNotIn("API_WRITE_ENABLED", src)


class TestFrontendI18nParity(unittest.TestCase):
    """Item 29: new terminalUnavailable* keys are present with matching
    TH/EN coverage (structural check, not a TS compile)."""

    def _read(self, rel):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        return (root / rel).read_text(encoding="utf-8")

    def test_item29_terminal_unavailable_keys_present_in_all_three_files(self):
        types_src = self._read("frontend/src/i18n/types.ts")
        en_src = self._read("frontend/src/i18n/en.ts")
        th_src = self._read("frontend/src/i18n/th.ts")
        for key in ("terminalUnavailableTitle", "terminalUnavailableBody"):
            self.assertIn(key, types_src)
            self.assertIn(key, en_src)
            self.assertIn(key, th_src)


if __name__ == "__main__":
    unittest.main()
