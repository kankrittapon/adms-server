"""
Configuration for the experimental Native Push listener.

Isolated from the polling Collector config. Reads its own env vars so the
experimental service can never alter the Collector's behavior.
"""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from typing import FrozenSet

from dotenv import load_dotenv

load_dotenv()


def _csv(s: str) -> FrozenSet[str]:
    return frozenset(x.strip() for x in s.split(",") if x.strip())


@dataclass(frozen=True)
class NativePushConfig:
    host: str
    port: int
    allowed_sources: FrozenSet[str]
    source_allowlist_enabled: bool
    expected_serial: str
    serial_validation_enabled: bool
    server_name: str
    push_version: str
    max_body_bytes: int
    health_file_path: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    mqtt_host: str
    mqtt_port: int
    mqtt_topic: str
    mqtt_publish_enabled: bool
    on_time_start: str
    on_time_end: str
    device_ip: str
    log_body_max: int = field(default=2048)

    @classmethod
    def from_env(cls) -> "NativePushConfig":
        sources = _csv(os.getenv("PUSH_ALLOWED_SOURCES", "192.168.1.201"))
        return cls(
            host=os.getenv("PUSH_HOST", "0.0.0.0"),
            port=int(os.getenv("PUSH_PORT", "8000")),
            allowed_sources=sources,
            source_allowlist_enabled=os.getenv(
                "PUSH_SOURCE_ALLOWLIST", "true"
            ).lower() in ("1", "true", "yes"),
            expected_serial=os.getenv("PUSH_EXPECTED_SERIAL", "3392113170057"),
            serial_validation_enabled=os.getenv(
                "PUSH_SERIAL_VALIDATION", "true"
            ).lower() in ("1", "true", "yes"),
            server_name=os.getenv("PUSH_SERVER_NAME", "ADMS-EXPERIMENTAL"),
            push_version=os.getenv("PUSH_VERSION", "1.0"),
            max_body_bytes=int(os.getenv("PUSH_MAX_BODY_BYTES", "262144")),
            health_file_path=os.getenv(
                "PUSH_HEALTH_FILE", "/tmp/native_push_health.json"
            ),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_name=os.getenv("DB_NAME", "adms"),
            db_user=os.getenv("DB_USER", "adms"),
            db_password=os.getenv("DB_PASSWORD", "adms_password"),
            mqtt_host=os.getenv("MQTT_HOST", "localhost"),
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            mqtt_topic=os.getenv("MQTT_TOPIC", "attendance/events"),
            mqtt_publish_enabled=os.getenv(
                "PUSH_MQTT_PUBLISH", "false"
            ).lower() in ("1", "true", "yes"),
            on_time_start=os.getenv("ON_TIME_START", "05:00:00"),
            on_time_end=os.getenv("ON_TIME_END", "10:00:00"),
            device_ip=os.getenv("ZK_DEVICE_IP", "192.168.1.201"),
            log_body_max=int(os.getenv("PUSH_LOG_BODY_MAX", "2048")),
        )

    def source_allowed(self, ip: str) -> bool:
        """True if the request source IP is allowed (LAN-only boundary)."""
        if not self.source_allowlist_enabled:
            return True
        try:
            src = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for allowed in self.allowed_sources:
            try:
                net = ipaddress.ip_network(allowed, strict=False)
            except ValueError:
                continue
            if src in net:
                return True
        return False

    def serial_allowed(self, sn: str) -> bool:
        """True if the device serial matches the expected production serial."""
        if not self.serial_validation_enabled:
            return True
        from app.native_push.protocol import normalize_sn
        return normalize_sn(sn) == self.expected_serial
