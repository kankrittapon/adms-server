"""Daily absence report to Telegram.

Sends, once the scan window has closed, the list of people who did not
scan that day (status ABSENT in the daily roster). Leave, official duty,
scan-exempt and not-yet-enrolled people are never listed. Nothing is sent
on non-working days.

Run by the host timer (deploy/systemd/adms-telegram-report.timer):
    docker exec adms_api python -m app.telegram_report
Configured through TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID; when either is
empty the run is a logged no-op.
"""

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from app.absences import daily_roster
from app.config import Config
from app.db import log_sync_event

log = logging.getLogger(__name__)

THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
# Telegram rejects messages over 4096 characters.
MAX_LEN = 4000


class TelegramNotConfigured(Exception):
    pass


class TelegramSendError(Exception):
    pass


def thai_date(d: date) -> str:
    return "%s %d %s %02d" % (THAI_DAYS[d.weekday()], d.day, THAI_MONTHS[d.month - 1], (d.year + 543) % 100)


def build_message(roster: Dict[str, Any]) -> Optional[str]:
    """None on a non-working day (nothing to report)."""
    if not roster["is_workday"]:
        return None
    absent = [p for p in roster["people"] if p["status"] == "ABSENT"]
    header = "📋 รายงานผู้ขาด %s\n(นับสแกน %s)" % (thai_date(roster["date"]), roster.get("scan_window", ""))
    if not absent:
        return header + "\n\n✅ ไม่มีผู้ขาด"
    lines = [header, "", "❌ ขาด %d คน" % len(absent)]
    branch = object()
    for p in absent:  # roster is already ordered by section, then name
        if p["branch"] != branch:
            branch = p["branch"]
            lines.append("")
            lines.append("▪️ %s" % (branch or "ไม่ระบุแผนก"))
        lines.append("• %s%s" % ((p["rank"] + " ") if p.get("rank") else "", p["display_name"]))
    text = "\n".join(lines)
    if len(text) > MAX_LEN:
        text = text[: MAX_LEN - 20].rsplit("\n", 1)[0] + "\n… (ตัดข้อความ)"
    return text


def send_text(text: str, token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
    token = (token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = (chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")).strip()
    if not token or not chat_id:
        raise TelegramNotConfigured("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
    body = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendMessage" % token,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Never echo the URL (it contains the token).
        detail = e.read().decode("utf-8", "replace")[:300]
        raise TelegramSendError("Telegram HTTP %s: %s" % (e.code, detail)) from None
    except urllib.error.URLError as e:
        raise TelegramSendError("Telegram unreachable: %s" % e.reason) from None
    if not payload.get("ok"):
        raise TelegramSendError("Telegram error: %s" % payload.get("description"))


def send_daily_report(cfg: Config, day: Optional[date] = None, force: bool = False) -> Dict[str, Any]:
    day = day or datetime.now(ZoneInfo("Asia/Bangkok")).date()
    roster = daily_roster(cfg, day)
    text = build_message(roster)
    if text is None and not force:
        return {"sent": False, "reason": "non-working day", "text": None}
    if text is None:
        text = "📋 %s — วันหยุด ไม่มีรายงาน" % thai_date(day)
    send_text(text)
    absent = sum(1 for p in roster["people"] if p["status"] == "ABSENT")
    log_sync_event(cfg, "TELEGRAM_REPORT_SENT", "date=%s absent=%d" % (day, absent))
    return {"sent": True, "reason": None, "text": text}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Config.from_env()
    try:
        result = send_daily_report(cfg)
    except TelegramNotConfigured as e:
        log.warning("Telegram report skipped: %s", e)
        return 0
    except TelegramSendError as e:
        log.error("Telegram report failed: %s", e)
        try:
            log_sync_event(cfg, "TELEGRAM_REPORT_FAILED", str(e)[:300])
        except Exception:
            pass
        return 1
    log.info("Telegram report: %s", "sent" if result["sent"] else "skipped (%s)" % result["reason"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
