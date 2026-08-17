"""Tests for DeviceCommandBus and Collector command dispatching.

PromptID: ADMS-Frontend-FullControlUX-002
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from app.config import Config
from app.device_command_bus import DeviceCommandBus, DeviceCommandError
from app.collector import CollectorStateEngine, State


class TestDeviceCommandBus(unittest.TestCase):
    def test_bus_execute_success(self):
        bus = DeviceCommandBus("localhost", 1883)
        mock_client = MagicMock()
        bus._client = mock_client
        bus.connected = True

        def fake_publish(topic, payload, qos=1):
            data = json.loads(payload)
            cid = data["command_id"]
            # Simulate collector replying on the response topic
            bus._on_message(
                mock_client,
                None,
                MagicMock(
                    topic=f"adms/device/command/response/{cid}",
                    payload=json.dumps({
                        "command_id": cid,
                        "success": True,
                        "result": {
                            "enrollment_id": 1,
                            "status": "TERMINAL_ACCOUNT_CREATED",
                            "terminal_id": "1001",
                        },
                    }).encode(),
                ),
            )
            return MagicMock()

        mock_client.publish.side_effect = fake_publish

        res = bus.execute("CREATE_TERMINAL_ACCOUNT", {"enrollment_id": 1, "display_name": "Test"}, timeout=2.0)
        self.assertEqual(res["status"], "TERMINAL_ACCOUNT_CREATED")
        self.assertEqual(res["terminal_id"], "1001")

    def test_bus_execute_failure_response(self):
        bus = DeviceCommandBus("localhost", 1883)
        mock_client = MagicMock()
        bus._client = mock_client
        bus.connected = True

        def fake_publish(topic, payload, qos=1):
            data = json.loads(payload)
            cid = data["command_id"]
            bus._on_message(
                mock_client,
                None,
                MagicMock(
                    topic=f"adms/device/command/response/{cid}",
                    payload=json.dumps({
                        "command_id": cid,
                        "success": False,
                        "error": "terminal account 1001 already exists — FAIL SAFE",
                    }).encode(),
                ),
            )
            return MagicMock()

        mock_client.publish.side_effect = fake_publish

        with self.assertRaises(DeviceCommandError) as ctx:
            bus.execute("CREATE_TERMINAL_ACCOUNT", {"enrollment_id": 1, "display_name": "Test"}, timeout=2.0)
        self.assertIn("already exists", str(ctx.exception))

    def test_bus_execute_timeout(self):
        bus = DeviceCommandBus("localhost", 1883)
        mock_client = MagicMock()
        bus._client = mock_client
        bus.connected = True

        # Do not send any response
        mock_client.publish.return_value = MagicMock()

        with self.assertRaises(DeviceCommandError) as ctx:
            bus.execute("CREATE_TERMINAL_ACCOUNT", {"enrollment_id": 1, "display_name": "Test"}, timeout=0.1)
        self.assertIn("timed out", str(ctx.exception))


class TestCollectorCommandHandler(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()
        self.engine = CollectorStateEngine(self.cfg)
        self.engine.mqtt_service = MagicMock()

    def test_command_rejected_when_not_live(self):
        self.engine.state = State.CONNECTING
        self.engine.connection = None

        self.engine.handle_device_command({
            "command_id": "cmd-123",
            "action": "CREATE_TERMINAL_ACCOUNT",
            "params": {"enrollment_id": 1, "display_name": "Test"},
        })

        self.engine.mqtt_service.publish_command_response.assert_called_once_with(
            "cmd-123",
            success=False,
            error="Collector is not in LIVE state (current state: CONNECTING)",
        )

    @patch("app.enrollment.create_reserved_terminal_account")
    def test_command_executed_when_live(self, mock_create):
        mock_device = MagicMock()
        self.engine.state = State.LIVE
        self.engine.connection = mock_device
        self.engine.perform_roster_lifecycle_check = MagicMock()

        mock_create.return_value = {
            "enrollment_id": 2,
            "status": "TERMINAL_ACCOUNT_CREATED",
            "terminal_id": "1002",
        }

        self.engine.handle_device_command({
            "command_id": "cmd-456",
            "action": "CREATE_TERMINAL_ACCOUNT",
            "params": {"enrollment_id": 2, "display_name": "Somchai S."},
        })

        mock_create.assert_called_once_with(
            self.cfg,
            enrollment_id=2,
            display_name="Somchai S.",
            device=mock_device,
        )
        self.engine.perform_roster_lifecycle_check.assert_called_once()
        self.engine.mqtt_service.publish_command_response.assert_called_once_with(
            "cmd-456",
            success=True,
            result={
                "enrollment_id": 2,
                "status": "TERMINAL_ACCOUNT_CREATED",
                "terminal_id": "1002",
            },
        )
