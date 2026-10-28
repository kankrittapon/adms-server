"""Telegram alert when the scanner (or the collector itself) is offline.

Run every 5 minutes by the host timer (deploy/systemd/adms-device-alert.timer):
    docker exec adms_api python -m app.device_alert

Reads the collector health file. Offline = the collector reports
device_connected=false, or the health file is missing / stale (collector
down). One alert is sent once the outage has lasted ALERT_AFTER_MINUTES, and
one recovery message when it comes back; state is kept in
system_configurations['device_alert'] so nothing repeats every run.

Sent to TELEGRAM_ALERT_CHAT_ID (developer chat), falling back to
TELEGRAM_CHAT_ID.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.config import Config
from app.db import get_db_connection, log_sync_event
from app.telegram_report import TelegramNotConfigured, TelegramSendError, send_text

log = logging.getLogger(__name__)

ALERT_AFTER_MINUTES = 30
HEALTH_STALE_SECONDS = 300


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read_health() -> Optional[Dict[str, Any]]:
    path = os.getenv("HEALTH_FILE_PATH", "/var/run/adms/collector_health.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def is_online(health: Optional[Dict[str, Any]], now: datetime) -> bool:
    if not health:
        return False
    updated = _parse(health.get("updated_at"))
    if updated is None or (now - updated).total_seconds() > HEALTH_STALE_SECONDS:
        return False
    return bool(health.get("device_connected"))


def _fmt_local(dt: datetime) -> str:
    from app.timestamp_utils import BANGKOK_TZ

    return dt.astimezone(BANGKOK_TZ).strftime("%d/%m %H:%M")


def _fmt_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return "%d นาที" % minutes
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return "%d ชม. %d นาที" % (hours, minutes)
    return "%d วัน %d ชม." % divmod(hours, 24)


def decide(state: Dict[str, Any], online: bool, now: datetime) -> tuple:
    """Pure transition: (new_state, message or None)."""
    since = _parse(state.get("offline_since"))
    if online:
        if since and state.get("alerted"):
            msg = "✅ เครื่องสแกนกลับมาเชื่อมต่อแล้ว (ขาดไป %s)" % _fmt_duration((now - since).total_seconds())
            return {}, msg
        return {}, None
    if since is None:
        return {"offline_since": now.isoformat(), "alerted": False}, None
    if not state.get("alerted") and (now - since).total_seconds() >= ALERT_AFTER_MINUTES * 60:
        msg = (
            "⚠️ เครื่องสแกนขาดการเชื่อมต่อตั้งแต่ %s (%s)\n"
            "ตรวจไฟ/สาย LAN ของเครื่อง — ระหว่างนี้การสแกนจะค้างในเครื่องและดึงเข้าเมื่อกลับมาเชื่อมต่อ"
            % (_fmt_local(since), _fmt_duration((now - since).total_seconds()))
        )
        return {"offline_since": since.isoformat(), "alerted": True}, msg
    return state, None


def _load_state(cfg: Config) -> Dict[str, Any]:
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM system_configurations WHERE key = 'device_alert';")
            row = cur.fetchone()
    return dict(row[0]) if row and row[0] else {}


def _save_state(cfg: Config, state: Dict[str, Any]) -> None:
    with get_db_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO system_configurations (key, value) VALUES ('device_alert', %s::jsonb) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();",
                (json.dumps(state),),
            )
            conn.commit()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Config.from_env()
    now = datetime.now(timezone.utc)
    online = is_online(read_health(), now)
    state = _load_state(cfg)
    new_state, msg = decide(state, online, now)
    if msg:
        chat = os.getenv("TELEGRAM_ALERT_CHAT_ID", "").strip() or None
        try:
            send_text(msg, chat_id=chat)
            log_sync_event(cfg, "DEVICE_ALERT_SENT", msg.splitlines()[0][:200])
        except TelegramNotConfigured as e:
            log.warning("Device alert not sent: %s", e)
        except TelegramSendError as e:
            log.error("Device alert failed: %s", e)
            return 1  # keep state unchanged so the next run retries
    if new_state != state:
        _save_state(cfg, new_state)
    log.info("device %s; alert state %s", "online" if online else "OFFLINE", new_state or "clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
