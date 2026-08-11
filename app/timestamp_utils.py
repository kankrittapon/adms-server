"""
Timestamp normalization for ZKTeco device attendance records.

ZKTeco terminals (pyzk) return naive datetime objects representing the
device's local wall-clock time.  The SONIC ZEM560_TFT at 192.168.1.201
is configured for Asia/Bangkok (UTC+7).  PostgreSQL stores scan_time as
TIMESTAMPTZ with timezone=UTC.  If a naive datetime is inserted into a
TIMESTAMPTZ column, psycopg2 assumes it is already UTC, producing a
+7 hour offset error.

normalize_device_timestamp() attaches the Bangkok timezone to naive
datetimes and converts aware datetimes to Bangkok, returning an
aware datetime that psycopg2 will correctly convert to UTC on insert.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

log = __import__("logging").getLogger(__name__)

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


def normalize_device_timestamp(value: datetime) -> datetime:
    """
    Normalize a ZKTeco attendance timestamp to an aware datetime in
    Asia/Bangkok.

    - Naive datetime → assume device local (Bangkok), attach ZoneInfo.
    - Aware datetime → convert to Bangkok.
    - None or non-datetime → raise.

    Returns an aware datetime with tzinfo=Asia/Bangkok.  psycopg2 will
    convert this to UTC when inserting into a TIMESTAMPTZ column.
    """
    if value is None:
        raise ValueError("device timestamp is None")
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value).__name__}")
    if value.tzinfo is None:
        return value.replace(tzinfo=BANGKOK_TZ)
    return value.astimezone(BANGKOK_TZ)