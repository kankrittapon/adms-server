import json
import logging
import threading
from datetime import datetime
from typing import Any, Optional
import paho.mqtt.client as mqtt
from app.config import Config
from app.timestamp_utils import normalize_device_timestamp

log = logging.getLogger(__name__)

class MQTTService:
    def __init__(self, cfg: Config, command_handler: Optional[Any] = None):
        self.cfg = cfg
        self.command_handler = command_handler
        self.client: Optional[mqtt.Client] = None
        self.connected = False

    def start(self):
        # Start connection in a background thread to prevent blocking state engine initialization
        t = threading.Thread(target=self._connect_async, daemon=True)
        t.start()

    def _connect_async(self):
        try:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id="adms-zkteco-listener"
            )
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            self.client.connect(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=60)
            self.client.loop_start()
            log.info("MQTT client connecting asynchronously to %s:%s", self.cfg.mqtt_host, self.cfg.mqtt_port)
        except Exception as e:
            log.warning("MQTT initial connection warning: %s", e)
            self.connected = False

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            log.info("MQTT connected successfully")
            self.connected = True
            client.subscribe("adms/device/command/request", qos=1)
        else:
            log.warning("MQTT connect failed with rc=%s", rc)
            self.connected = False

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        log.warning("MQTT disconnected (rc=%s)", rc)
        self.connected = False

    def _on_message(self, client, userdata, msg):
        if msg.topic == "adms/device/command/request":
            if self.command_handler:
                try:
                    payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
                    self.command_handler(payload)
                except Exception as e:
                    log.warning("MQTT command message handler error: %s", e)

    def publish_command_response(self, command_id: str, success: bool, result: Optional[dict] = None, error: Optional[str] = None) -> bool:
        if not self.client or not self.connected:
            return False
        try:
            payload = json.dumps({
                "command_id": command_id,
                "success": success,
                "result": result,
                "error": error,
                "timestamp": datetime.now().isoformat()
            })
            topic = f"adms/device/command/response/{command_id}"
            info = self.client.publish(topic, payload, qos=1)
            info.wait_for_publish(timeout=2.0)
            return True
        except Exception as e:
            log.warning("MQTT publish command response failed: %s", e)
            return False

    def publish_attendance(self, attendance: Any, status: str) -> bool:
        if not self.client or not self.connected:
            log.warning("MQTT not connected; skipping event publish for user %s", attendance.user_id)
            return False
        try:
            scan_time = normalize_device_timestamp(attendance.timestamp)
            payload = json.dumps({
                "user_id": str(attendance.user_id),
                "device_ip": self.cfg.device_ip,
                "scan_time": scan_time.isoformat(),
                "punch_type": str(getattr(attendance, "punch", "")),
                "status": status,
                "event_type": "ATTENDANCE_SCAN"
            })
            info = self.client.publish(self.cfg.mqtt_topic, payload, qos=1)
            info.wait_for_publish(timeout=2.0)
            return True
        except Exception as e:
            log.warning("MQTT publish failed: %s", e)
            return False

    def stop(self):
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
                log.info("MQTT client stopped cleanly")
            except Exception as e:
                log.warning("MQTT stop error: %s", e)
            finally:
                self.client = None
                self.connected = False
