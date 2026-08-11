import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    device_ip: str
    device_port: int
    device_password: int
    device_timeout: int
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    mqtt_host: str
    mqtt_port: int
    mqtt_topic: str
    on_time_start: str
    on_time_end: str
    initial_backoff: float
    max_backoff: float
    backoff_multiplier: float
    backoff_jitter: float
    stable_live_window: float
    backfill_overlap_minutes: float
    backfill_batch_size: int
    periodic_reconciliation_minutes: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            device_ip=os.getenv("ZK_DEVICE_IP", "192.168.1.201"),
            device_port=int(os.getenv("ZK_DEVICE_PORT", "4370")),
            device_password=int(os.getenv("ZK_DEVICE_PASSWORD", "600")),
            device_timeout=int(os.getenv("ZK_TIMEOUT", "5")),
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_name=os.getenv("DB_NAME", "adms"),
            db_user=os.getenv("DB_USER", "adms"),
            db_password=os.getenv("DB_PASSWORD", "adms_password"),
            mqtt_host=os.getenv("MQTT_HOST", "localhost"),
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            mqtt_topic=os.getenv("MQTT_TOPIC", "attendance/events"),
            on_time_start=os.getenv("ON_TIME_START", "08:00"),
            on_time_end=os.getenv("ON_TIME_END", "08:30"),
            initial_backoff=float(os.getenv("INITIAL_BACKOFF_SECONDS", "2.0")),
            max_backoff=float(os.getenv("MAX_BACKOFF_SECONDS", "60.0")),
            backoff_multiplier=float(os.getenv("BACKOFF_MULTIPLIER", "2.0")),
            backoff_jitter=float(os.getenv("BACKOFF_JITTER", "0.2")),
            stable_live_window=float(os.getenv("STABLE_LIVE_WINDOW_SECONDS", "30.0")),
            backfill_overlap_minutes=float(os.getenv("BACKFILL_OVERLAP_MINUTES", "5.0")),
            backfill_batch_size=int(os.getenv("BACKFILL_BATCH_SIZE", "500")),
            periodic_reconciliation_minutes=int(os.getenv("PERIODIC_RECONCILIATION_MINUTES", "0")),
        )
