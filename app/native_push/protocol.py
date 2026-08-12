"""
Classic ZKTeco iclock push protocol primitives (pure, testable).

Implements the community-documented classic iclock variant used by
ZEM560-class standalone firmware (libhttppush.so strings: AuthFromHttpServer,
pushsdk_options, /iclock/cdata, /iclock/getrequest).

Key endpoints:
  - GET  /iclock/cdata?SN=<serial>[&options=all]  -> OPTIONS text block
  - POST /iclock/cdata?SN=<serial>&table=ATTLOG[&Stamp=&OpStamp=]
        -> tab-separated ATTLOG rows; server replies "OK"
  - GET  /iclock/getrequest?SN=<serial>           -> command (or "OK")
  - GET  /iclock/devicecmd?SN=<serial>            -> device replies; server "OK"
  - GET  /iclock/ping?SN=<serial>                 -> "OK"

Reference implementations:
  - fedotovaleksandr/iclockhelper (Python, ATTLOG/Transaction parsing)
  - RodrigoAWeber/example-zkteco-push-protocol-communication (C# ZK Push)

Confidence: COMMUNITY-DOCUMENTED + FIRMWARE-VERIFIED strings on this device.
Actual observed behavior on the ZEM560 (Ver 6.60) will be recorded live.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

# Table names used in POST /iclock/cdata?table=<TABLE>
TABLE_ATTLOG = "ATTLOG"
TABLE_OPERLOG = "OPERLOG"
TABLE_ATTPHOTO = "ATTPHOTO"
TABLE_USER = "USER"
TABLE_FP = "FP"
KNOWN_TABLES = {TABLE_ATTLOG, TABLE_OPERLOG, TABLE_ATTPHOTO, TABLE_USER, TABLE_FP}

# ATTLOG transaction fields (iclockhelper Transaction.from_str):
#   flds[0] = pin / user_id
#   flds[1] = server_datetime  (YYYY-MM-DD HH:MM:SS)
#   flds[2] = check_type  (punch status 0=check-in, 1=check-out, ...)
#   flds[3] = verify_code (0=fingerprint, 1=password, 2=card, ...)
#   flds[4] = work_code
#   flds[5] = reserved
ATTLOG_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def parse_sn(url: str) -> str:
    """Extract the SN query parameter from an iclock request URL."""
    qs = parse_qs(urlparse(url).query)
    sn = qs.get("SN", [""])
    return sn[0] if sn else ""


def parse_cdata_params(url: str) -> Dict[str, str]:
    """Parse query params of a /iclock/cdata request (single-value)."""
    qs = parse_qs(urlparse(url).query)
    return {k: v[0] for k, v in qs.items()}


def _looks_like_datetime(s: str) -> bool:
    """True if s matches the ATTLOG datetime format."""
    if not s:
        return False
    try:
        time.strptime(s, ATTLOG_DATETIME_FMT)
    except ValueError:
        return False
    return True


def parse_attlog_line(line: str) -> Optional[Tuple[str, str, str, str, str]]:
    """
    Parse one ATTLOG line into (user_id, datetime_str, check_type,
    verify_code, work_code).

    Accepts both documented layouts (defensive — firmware variants differ):
      - pin-first:    "1001<TAB>2026-08-12 08:47:37<TAB>0<TAB>0<TAB>1"
      - uid-first:    "ATTLOG<TAB>7<TAB>1001<TAB>2026-08-12 08:47:37<TAB>0<TAB>0"
                      (uid column present; the SECOND field is user_id)
    The datetime column position decides the layout; the other numeric field
    is taken as user_id. Returns None for malformed lines (fail-safe).
    """
    if not line or not line.strip():
        return None
    parts = line.split("\t")
    if parts and parts[0].strip().upper() == TABLE_ATTLOG:
        parts = parts[1:]
    if len(parts) < 2:
        return None

    ts_idx = None
    for i, p in enumerate(parts):
        if _looks_like_datetime(p.strip()):
            ts_idx = i
            break
    if ts_idx is None:
        # No plausible datetime column → do not guess identity
        return None
    if ts_idx == 0:
        # malformed (datetime cannot be the user id)
        return None

    user_id = parts[ts_idx - 1].strip()
    ts_str = parts[ts_idx].strip()
    check_type = parts[ts_idx + 1].strip() if len(parts) > ts_idx + 1 else ""
    verify_code = parts[ts_idx + 2].strip() if len(parts) > ts_idx + 2 else ""
    work_code = parts[ts_idx + 3].strip() if len(parts) > ts_idx + 3 else ""
    return user_id, ts_str, check_type, verify_code, work_code


def parse_attlog_body(body: str) -> List[Tuple[str, str, str, str, str]]:
    """Parse the POST /iclock/cdata ATTLOG body into transaction tuples."""
    rows = []
    for line in body.split("\n"):
        parsed = parse_attlog_line(line)
        if parsed:
            rows.append(parsed)
    return rows


def build_options_response(
    server_name: str = "ADMS-EXPERIMENTAL",
    push_version: str = "1.0",
) -> str:
    """
    Build the OPTIONS text block returned for GET /iclock/cdata?SN=...

    Community-documented classic format (mirrors ZK ADMS server responses):
      GET OPTIONS FROM: <server>
      OpStamp=<ts>|COMMAND=OPTIONS|Stamp=<ts>
      ErrorDelay=10
      Delay=10
      TransTimes=00:00;14:05
      TransInterval=1
      TransFlag=1111000000
      Realtime=1
      Encrypt=0

    PushOptions equivalents observed in firmware strings (pushsdk_options).
    """
    stamp = int(time.time())
    lines = [
        f"GET OPTIONS FROM: {server_name}",
        f"OpStamp={stamp}|COMMAND=OPTIONS|Stamp={stamp}",
        f"PushVersion={push_version}",
        "ErrorDelay=10",
        "Delay=10",
        "TransTimes=00:00;14:05",
        "TransInterval=1",
        "TransFlag=1111000000",
        "Realtime=1",
        "Encrypt=0",
    ]
    return "\n".join(lines)


def normalize_sn(sn: str) -> str:
    """Trim/clean a serial from a request for comparison."""
    return (sn or "").strip().strip("\x00")
