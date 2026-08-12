"""
Experimental Native Push HTTP listener service.

Routes (classic iclock protocol):
  - GET  /iclock/cdata         -> OPTIONS block (handshake/registration)
  - POST /iclock/cdata         -> ATTLOG/OPERLOG ingestion
  - GET  /iclock/getrequest    -> "OK" (no queued commands in experiment)
  - GET  /iclock/devicecmd     -> "OK"
  - GET  /iclock/ping          -> "OK"
  - GET  /healthz              -> JSON health

Canonical ingestion: every parsed ATTLOG transaction is converted into a
pyzk-like attendance object and persisted through app.db.save_attendance_log(),
which reuses device resolution, device_user resolution, Asia/Bangkok timestamp
normalization, parse_time/determine_status, the temporal
resolve_verified_employee_mapping(), and the UNIQUE(user_id, device_ip,
scan_time) dedupe contract. No separate identity system.

MQTT: publishing is OPTIONAL (config flag, default OFF during the experiment)
because the polling Collector's live_capture path already publishes exactly one
notification per physical scan; enabling push-side MQTT while the Collector is
live would create duplicate broadcasts. The capability is implemented + tested.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import Optional, Tuple
from urllib.parse import urlparse

from app.config import Config
from app.db import (
    get_db_connection,
    get_or_create_device,
    ensure_device_user,
    resolve_verified_employee_mapping,
    determine_status,
    save_attendance_log,
    log_sync_event,
)
from app.timestamp_utils import normalize_device_timestamp
from app.native_push.config import NativePushConfig
from app.native_push.protocol import (
    TABLE_ATTLOG,
    parse_cdata_params,
    parse_attlog_body,
    parse_sn,
    build_options_response,
    ATTLOG_DATETIME_FMT,
)

log = logging.getLogger("adms.native_push")

HEALTH_DEFAULT = "/tmp/native_push_health.json" if os.name != "nt" else os.path.join(
    tempfile.gettempdir(), "native_push_health.json"
)


def build_canonical_config(npc: NativePushConfig) -> Config:
    """
    Build the canonical app.config.Config from the push config so the
    experimental service can reuse app.db functions unchanged.
    """
    return Config(
        device_ip=npc.device_ip,
        device_port=4370,
        device_password=600,
        device_timeout=5,
        db_host=npc.db_host,
        db_port=npc.db_port,
        db_name=npc.db_name,
        db_user=npc.db_user,
        db_password=npc.db_password,
        mqtt_host=npc.mqtt_host,
        mqtt_port=npc.mqtt_port,
        mqtt_topic=npc.mqtt_topic,
        on_time_start=npc.on_time_start,
        on_time_end=npc.on_time_end,
        initial_backoff=2.0,
        max_backoff=60.0,
        backoff_multiplier=2.0,
        backoff_jitter=0.2,
        stable_live_window=30.0,
        backfill_overlap_minutes=5.0,
        backfill_batch_size=500,
        periodic_reconciliation_minutes=0,
        roster_poll_interval_seconds=300,
    )


def _write_health(npc: NativePushConfig, status: dict) -> None:
    try:
        path = npc.health_file_path
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:  # pragma: no cover - defensive
        log.warning("failed to write push health file: %s", e)


class NativePushHandler(BaseHTTPRequestHandler):
    server: "NativePushServer"  # type: ignore

    # ---- HTTP plumbing -------------------------------------------------
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silence default stderr noise
        log.debug("http: " + fmt, *args)

    def _send(self, body: str, code: int = 200, ctype: str = "text/plain;charset=UTF-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _ok(self, body: str = "OK"):
        self._send(body)

    # ---- entry points ---------------------------------------------------
    def do_GET(self):  # noqa: N802
        self._route(method="GET")

    def do_POST(self):  # noqa: N802
        self._route(method="POST")

    # ---- routing ---------------------------------------------------------
    def _route(self, method: str):
        npc = self.server.npc
        parsed = urlparse(self.path)
        path = parsed.path
        sn = parse_sn(self.path)

        # health endpoint
        if path == "/healthz":
            self._send(json.dumps({
                "service": "adms-native-push",
                "experimental": True,
                "status": "UP",
                "time": datetime.utcnow().isoformat() + "Z",
            }), ctype="application/json")
            return

        # Source-IP allowlist (LAN-only boundary) — checked for ALL iclock routes
        client_ip = self.client_address[0]
        if npc.source_allowlist_enabled and not npc.source_allowed(client_ip):
            log.warning("REJECT source=%s path=%s — not in allowlist", client_ip, path)
            self._send("OK", code=403)
            return

        # Serial validation (log + reject unknown serials)
        if npc.serial_validation_enabled and not npc.serial_allowed(sn):
            log.warning(
                "UNEXPECTED_SERIAL sn=%r source=%s path=%s — rejected",
                sn, client_ip, path,
            )
            self._send("OK", code=403)
            return

        if path in ("/iclock/cdata", "/iclock/fdata"):
            if method == "GET":
                self._handle_cdata_get(npc, sn)
            elif method == "POST":
                self._handle_cdata_post(npc, sn)
            else:
                self._send("OK", code=405)
            return

        if path == "/iclock/getrequest":
            # Command polling — experiment returns no queued commands
            log.info("GETREQ sn=%s source=%s", sn, client_ip)
            self._ok("OK")
            return

        if path in ("/iclock/devicecmd", "/iclock/ping", "/iclock/registry"):
            log.info("%s sn=%s source=%s", path.upper(), sn, client_ip)
            self._ok("OK")
            return

        log.info("UNKNOWN_PATH %s %s sn=%s source=%s", method, path, sn, client_ip)
        self._send("OK", code=404)

    # ---- handlers ----------------------------------------------------------
    def _handle_cdata_get(self, npc: NativePushConfig, sn: str):
        opts = parse_cdata_params(self.path)
        log.info(
            "CDATA_GET sn=%s source=%s options=%s",
            sn, self.client_address[0], opts.get("options", ""),
        )
        body = build_options_response(npc.server_name, npc.push_version)
        self._send(body)

    def _handle_cdata_post(self, npc: NativePushConfig, sn: str):
        params = parse_cdata_params(self.path)
        table = params.get("table", "").upper()
        stamp = params.get("Stamp", "")
        op_stamp = params.get("OpStamp", "")

        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > npc.max_body_bytes:
            log.warning("CDATA_POST oversized sn=%s len=%d (max %d)", sn, length, npc.max_body_bytes)
            self._send("FAIL", code=413)
            return
        raw = self.rfile.read(length) if length else b""
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError:
            body = raw.decode("latin-1", errors="replace")

        log.info(
            "CDATA_POST sn=%s source=%s table=%s stamp=%s opstamp=%s body_bytes=%d",
            sn, self.client_address[0], table, stamp, op_stamp, len(raw),
        )
        if body.strip():
            log.info("CDATA_POST body_head: %s",
                     body.strip()[: npc.log_body_max].replace("\t", "\\t"))

        if table == TABLE_ATTLOG:
            result = self._ingest_attlog(npc, sn, body)
            # FAIL (non-200) if nothing could be parsed OR ingest errored:
            # the device retains + retries the batch instead of clearing it.
            if result["rows"] == 0 and body.strip():
                log.warning("ATTLOG sn=%s FAIL — no parseable rows; device will retry", sn)
                self._send("FAIL", code=422)
                return
            if result["errors"] > 0:
                log.error("ATTLOG sn=%s FAIL — %d ingest errors; device will retry",
                          sn, result["errors"])
                self._send("FAIL", code=500)
                return
            self._ok("OK")
            return

        # Unknown / non-ATTLOG tables: log safely, reply OK (no template handling)
        log.info("CDATA_POST table=%s IGNORED (no processing) sn=%s", table, sn)
        self._ok("OK")

    def _ingest_attlog(self, npc: NativePushConfig, sn: str, body: str) -> dict:
        rows = parse_attlog_body(body)
        result = {"rows": len(rows), "inserted": 0, "dupes": 0, "errors": 0}
        if not rows:
            log.warning("ATTLOG sn=%s — no parseable rows in %d-byte body", sn, len(body))
            return result
        cfg = build_canonical_config(npc)
        for (user_id, ts_str, check_type, verify_code, work_code) in rows:
            try:
                naive_ts = datetime.strptime(ts_str, ATTLOG_DATETIME_FMT)
                att = SimpleNamespace(
                    uid=None,
                    user_id=user_id,
                    timestamp=naive_ts,
                    status=int(check_type) if check_type.isdigit() else check_type,
                    punch=work_code,
                )
                # Canonical persistence — dedupe via UNIQUE(user_id, device_ip, scan_time)
                ok = save_attendance_log(cfg, att)
                if ok:
                    result["inserted"] += 1
                    # Optional MQTT publish (default OFF while Collector live)
                    if getattr(self.server, "mqtt_service", None):
                        status_str = determine_status(
                            normalize_device_timestamp(naive_ts),
                            npc.on_time_start, npc.on_time_end,
                        )
                        self.server.mqtt_service.publish_attendance(att, status_str)
                else:
                    result["dupes"] += 1
            except Exception as e:
                result["errors"] += 1
                log.error("ATTLOG ingest error user_id=%s ts=%s: %s", user_id, ts_str, e)
        log.info("ATTLOG sn=%s rows=%d inserted=%d dupes=%d errors=%d",
                 sn, result["rows"], result["inserted"], result["dupes"], result["errors"])
        try:
            log_sync_event(cfg, "NATIVE_PUSH_ATTLOG",
                           f"sn={sn} rows={result['rows']} inserted={result['inserted']} "
                           f"dupes={result['dupes']} errors={result['errors']}")
        except Exception:
            pass
        return result


class NativePushServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: Tuple[str, int], npc: NativePushConfig,
                 mqtt_service=None):
        self.npc = npc
        self.mqtt_service = mqtt_service
        self._stop_event = threading.Event()
        super().__init__(address, NativePushHandler)
        self._write_health({"state": "STARTING", "updated_at": datetime.utcnow().isoformat() + "Z"})

    def _write_health(self, status: dict):
        _write_health(self.npc, status)

    def serve_forever_loop(self):
        self._write_health({
            "state": "RUNNING",
            "bind": f"{self.npc.host}:{self.npc.port}",
            "experimental": True,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        })
        log.info("Native Push listener serving on %s:%s (LAN-only, allowlist=%s)",
                 self.npc.host, self.npc.port,
                 ",".join(sorted(self.npc.allowed_sources)) or "DISABLED")
        try:
            self.serve_forever()
        finally:
            self._write_health({"state": "STOPPED", "updated_at": datetime.utcnow().isoformat() + "Z"})
