"""
Tests for the experimental ZKTeco Native Push listener
(ADMS-NativePush-Experimental-001).

Covers:
  - protocol: SN extraction, ATTLOG line/body parsing, OPTIONS response
  - config: source allowlist (LAN-only) + serial validation
  - canonical ingestion reuse: device resolution, Asia/Bangkok timestamp
    normalization, temporal mapping, dedupe via save_attendance_log
  - safety: no Human creation, no automatic mapping, no biometric handling,
    malformed/unknown-table payloads fail safely
"""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.native_push.config import NativePushConfig
from app.native_push.protocol import (
    parse_sn,
    parse_attlog_line,
    parse_attlog_body,
    build_options_response,
    TABLE_ATTLOG,
    ATTLOG_DATETIME_FMT,
)
from app.native_push.service import (
    build_canonical_config,
    NativePushHandler,
    NativePushServer,
)


def make_npc(**overrides):
    base = {
        "host": "0.0.0.0",
        "port": 8000,
        "allowed_sources": frozenset({"192.168.1.201"}),
        "source_allowlist_enabled": True,
        "expected_serial": "3392113170057",
        "serial_validation_enabled": True,
        "server_name": "ADMS-EXPERIMENTAL",
        "push_version": "1.0",
        "max_body_bytes": 262144,
        "health_file_path": "/tmp/np_test_health.json",
        "db_host": "localhost",
        "db_port": 5432,
        "db_name": "adms",
        "db_user": "adms",
        "db_password": "pw",
        "mqtt_host": "localhost",
        "mqtt_port": 1883,
        "mqtt_topic": "attendance/events",
        "mqtt_publish_enabled": False,
        "on_time_start": "05:00:00",
        "on_time_end": "10:00:00",
        "device_ip": "192.168.1.201",
        "log_body_max": 2048,
    }
    base.update(overrides)
    return NativePushConfig(**base)


def _fake_server(npc=None):
    npc = npc or make_npc()
    server = object.__new__(NativePushServer)
    server.npc = npc
    server.mqtt_service = None
    return server


class TestProtocolSN(unittest.TestCase):
    def test_extract_sn_from_query(self):
        self.assertEqual(parse_sn("/iclock/cdata?SN=3392113170057"), "3392113170057")

    def test_extract_sn_with_extra_params(self):
        self.assertEqual(
            parse_sn("/iclock/cdata?SN=3392113170057&options=all"), "3392113170057"
        )

    def test_extract_sn_missing(self):
        self.assertEqual(parse_sn("/iclock/cdata"), "")


class TestATTLOGParsing(unittest.TestCase):
    def test_classic_line(self):
        row = parse_attlog_line("1001\t2026-08-12 08:47:37\t0\t0\t1")
        self.assertIsNotNone(row)
        user_id, ts, check, verify, work = row
        self.assertEqual(user_id, "1001")
        self.assertEqual(ts, "2026-08-12 08:47:37")
        self.assertEqual(check, "0")
        self.assertEqual(verify, "0")
        self.assertEqual(work, "1")

    def test_line_with_attlog_table_tag(self):
        row = parse_attlog_line("ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0")
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "1001")
        self.assertEqual(row[1], "2026-08-12 08:47:37")

    def test_uid_first_layout(self):
        """uid-first variant: ATTLOG<TAB>uid<TAB>user_id<TAB>datetime..."""
        row = parse_attlog_line("ATTLOG\t7\t1001\t2026-08-12 08:47:37\t0\t0")
        self.assertIsNotNone(row)
        # user_id must be the SECOND field (1001), not the uid (7)
        self.assertEqual(row[0], "1001")
        self.assertEqual(row[1], "2026-08-12 08:47:37")

    def test_uid_first_layout_without_tag(self):
        row = parse_attlog_line("7\t1001\t2026-08-12 08:47:37\t0\t0")
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "1001")

    def test_hhmmss_timestamp_parses(self):
        row = parse_attlog_line("1001\t2026-08-12 08:47:37\t0\t0\t0")
        self.assertIsNotNone(row)
        parsed = datetime.strptime(row[1], ATTLOG_DATETIME_FMT)
        self.assertEqual(parsed.hour, 8)
        self.assertEqual(parsed.second, 37)

    def test_malformed_line_returns_none(self):
        self.assertIsNone(parse_attlog_line(""))
        self.assertIsNone(parse_attlog_line("   "))
        self.assertIsNone(parse_attlog_line("1001\tnot-a-date"))
        self.assertIsNone(parse_attlog_line("1001"))

    def test_body_multiple_rows(self):
        body = (
            "ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0\t1\n"
            "ATTLOG\t1001\t2026-08-12 09:10:00\t1\t0\t1\n"
            "garbage line\n"
        )
        rows = parse_attlog_body(body)
        self.assertEqual(len(rows), 2)

    def test_body_mixed_layouts(self):
        body = (
            "ATTLOG\t7\t1001\t2026-08-12 08:47:37\t0\t0\n"
            "ATTLOG\t1001\t2026-08-12 09:10:00\t1\t0\t1\n"
        )
        rows = parse_attlog_body(body)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "1001")
        self.assertEqual(rows[1][0], "1001")


    def test_body_single_row_no_tag(self):
        rows = parse_attlog_body("1001\t2026-08-12 08:47:37\t0\t0\t0\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "1001")


class TestOptionsResponse(unittest.TestCase):
    def test_contains_required_lines(self):
        body = build_options_response("ADMS-EXPERIMENTAL", "1.0")
        self.assertIn("GET OPTIONS FROM: ADMS-EXPERIMENTAL", body)
        self.assertIn("COMMAND=OPTIONS", body)
        self.assertIn("ErrorDelay=", body)
        self.assertIn("TransTimes=", body)
        self.assertIn("TransInterval=", body)
        self.assertIn("TransFlag=", body)
        self.assertIn("Realtime=", body)
        self.assertIn("PushVersion=1.0", body)


class TestConfigSecurity(unittest.TestCase):
    def test_source_allowed_lan_device(self):
        npc = make_npc()
        self.assertTrue(npc.source_allowed("192.168.1.201"))

    def test_source_allowed_subnet(self):
        npc = make_npc(allowed_sources=frozenset({"192.168.1.0/24"}))
        self.assertTrue(npc.source_allowed("192.168.1.50"))

    def test_source_rejected_outside_lan(self):
        npc = make_npc()
        self.assertFalse(npc.source_allowed("203.0.113.5"))

    def test_source_rejected_invalid(self):
        npc = make_npc()
        self.assertFalse(npc.source_allowed("not-an-ip"))

    def test_source_allowlist_disabled(self):
        npc = make_npc(source_allowlist_enabled=False)
        self.assertTrue(npc.source_allowed("203.0.113.5"))

    def test_serial_allowed(self):
        npc = make_npc()
        self.assertTrue(npc.serial_allowed("3392113170057"))

    def test_serial_rejected(self):
        npc = make_npc()
        self.assertFalse(npc.serial_allowed("9999999999999"))

    def test_serial_validation_disabled(self):
        npc = make_npc(serial_validation_enabled=False)
        self.assertTrue(npc.serial_allowed("9999999999999"))


class TestCanonicalIngestion(unittest.TestCase):
    def test_build_canonical_config_maps_fields(self):
        npc = make_npc()
        cfg = build_canonical_config(npc)
        self.assertEqual(cfg.device_ip, "192.168.1.201")
        self.assertEqual(cfg.db_host, "localhost")
        self.assertEqual(cfg.on_time_start, "05:00:00")
        self.assertEqual(cfg.on_time_end, "10:00:00")

    @patch("app.native_push.service.save_attendance_log", return_value=True)
    def test_attlog_ingest_calls_canonical_save(self, mock_save):
        npc = make_npc()
        handler = object.__new__(NativePushHandler)
        handler.server = SimpleNamespace(npc=npc, mqtt_service=None)
        handler._ingest_attlog(
            npc,
            "3392113170057",
            "ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0\t1\n",
        )
        mock_save.assert_called_once()
        att = mock_save.call_args[0][1]
        self.assertEqual(att.user_id, "1001")
        # timestamp must be naive (normalizer attaches Asia/Bangkok)
        self.assertIsNone(att.timestamp.tzinfo)
        self.assertEqual(att.status, 0)
        self.assertEqual(att.punch, "1")

    @patch("app.native_push.service.save_attendance_log", return_value=True)
    def test_unmapped_user_no_employee_creation(self, mock_save):
        """Ingest must only call canonical save — never insert Human records."""
        npc = make_npc()
        handler = object.__new__(NativePushHandler)
        handler.server = SimpleNamespace(npc=npc, mqtt_service=None)
        handler._ingest_attlog(npc, "3392113170057", "ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0\t0\n")
        for c in mock_save.call_args_list:
            self.assertEqual(c[0][0].device_ip, "192.168.1.201")

    @patch("app.native_push.service.save_attendance_log", return_value=False)
    def test_duplicate_skipped(self, mock_save):
        """Duplicate event (same user/device/scan_time) -> save returns False, no error."""
        npc = make_npc()
        handler = object.__new__(NativePushHandler)
        handler.server = SimpleNamespace(npc=npc, mqtt_service=None)
        # no exception should be raised
        handler._ingest_attlog(npc, "3392113170057", "ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0\t1\n")

    @patch("app.native_push.service.save_attendance_log", return_value=True)
    def test_malformed_body_no_save_calls(self, mock_save):
        npc = make_npc()
        handler = object.__new__(NativePushHandler)
        handler.server = SimpleNamespace(npc=npc, mqtt_service=None)
        handler._ingest_attlog(npc, "3392113170057", "garbage\nnot-a-row\twhatever\n")
        mock_save.assert_not_called()


class TestHandlerRouting(unittest.TestCase):
    def _make_server(self, npc=None):
        npc = npc or make_npc()
        server = object.__new__(NativePushServer)
        server.npc = npc
        server.mqtt_service = None
        return server

    def test_get_options_route(self):
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/iclock/cdata?SN=3392113170057"
        handler.client_address = ("192.168.1.201", 40000)
        handler.headers = {}
        handler.rfile = None
        with patch.object(handler, "_send") as mock_send:
            handler._route("GET")
            mock_send.assert_called_once()
            body = mock_send.call_args[0][0]
            self.assertIn("GET OPTIONS FROM:", body)

    def test_getrequest_route_ok(self):
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/iclock/getrequest?SN=3392113170057"
        handler.client_address = ("192.168.1.201", 40000)
        with patch.object(handler, "_ok") as mock_ok:
            handler._route("GET")
            mock_ok.assert_called_once_with("OK")

    def test_source_rejected(self):
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/iclock/cdata?SN=3392113170057"
        handler.client_address = ("203.0.113.5", 40000)
        with patch.object(handler, "_send") as mock_send:
            handler._route("GET")
            mock_send.assert_called_once()
            self.assertEqual(mock_send.call_args[1]["code"], 403)

    def test_serial_rejected(self):
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/iclock/cdata?SN=9999999999999"
        handler.client_address = ("192.168.1.201", 40000)
        with patch.object(handler, "_send") as mock_send:
            handler._route("GET")
            mock_send.assert_called_once()
            self.assertEqual(mock_send.call_args[1]["code"], 403)

    def test_unknown_path_404(self):
        """Unknown paths: serial+source pass, then 404. (Security checks run first.)"""
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/totally/unknown?SN=3392113170057"
        handler.client_address = ("192.168.1.201", 40000)
        with patch.object(handler, "_send") as mock_send:
            handler._route("GET")
            self.assertEqual(mock_send.call_args[1]["code"], 404)

    def test_unknown_path_without_serial_403(self):
        """Unknown path without valid SN is rejected by serial validation first."""
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/totally/unknown"
        handler.client_address = ("192.168.1.201", 40000)
        with patch.object(handler, "_send") as mock_send:
            handler._route("GET")
            self.assertEqual(mock_send.call_args[1]["code"], 403)

    def test_healthz_endpoint(self):
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/healthz"
        handler.client_address = ("192.168.1.201", 40000)
        with patch.object(handler, "_send") as mock_send:
            handler._route("GET")
            body = mock_send.call_args[0][0]
            self.assertIn("adms-native-push", body)

    def test_post_attlog_route_ingests(self):
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/iclock/cdata?SN=3392113170057&table=ATTLOG&Stamp=1&OpStamp=1"
        handler.client_address = ("192.168.1.201", 40000)
        body = "ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0\t1\n"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = type(
            "R", (), {"read": lambda self, n: body.encode("utf-8")}
        )()
        with patch.object(handler, "_ingest_attlog", return_value={"rows": 1, "inserted": 1, "dupes": 0, "errors": 0}) as mock_ingest, \
             patch.object(handler, "_ok") as mock_ok:
            handler._route("POST")
            mock_ingest.assert_called_once()
            mock_ok.assert_called_once_with("OK")

    def test_post_attlog_route_fails_when_no_rows(self):
        """Unparseable ATTLOG body -> non-200 so device retains + retries."""
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/iclock/cdata?SN=3392113170057&table=ATTLOG&Stamp=1&OpStamp=1"
        handler.client_address = ("192.168.1.201", 40000)
        body = "garbage\tline\n"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = type(
            "R", (), {"read": lambda self, n: body.encode("utf-8")}
        )()
        with patch.object(handler, "_ingest_attlog", return_value={"rows": 0, "inserted": 0, "dupes": 0, "errors": 0}) as mock_ingest, \
             patch.object(handler, "_send") as mock_send:
            handler._route("POST")
            mock_ingest.assert_called_once()
            self.assertEqual(mock_send.call_args[1]["code"], 422)

    def test_post_attlog_route_fails_on_ingest_errors(self):
        """Any ingest error -> non-200 so device retains + retries."""
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/iclock/cdata?SN=3392113170057&table=ATTLOG&Stamp=1&OpStamp=1"
        handler.client_address = ("192.168.1.201", 40000)
        body = "ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0\t1\n"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = type(
            "R", (), {"read": lambda self, n: body.encode("utf-8")}
        )()
        with patch.object(handler, "_ingest_attlog", return_value={"rows": 1, "inserted": 0, "dupes": 0, "errors": 1}) as mock_ingest, \
             patch.object(handler, "_send") as mock_send:
            handler._route("POST")
            self.assertEqual(mock_send.call_args[1]["code"], 500)

    def test_oversized_body_413(self):
        npc = make_npc(max_body_bytes=16)
        server = self._make_server(npc)
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/iclock/cdata?SN=3392113170057&table=ATTLOG"
        handler.client_address = ("192.168.1.201", 40000)
        body = "ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0\t1\n"  # > 16 bytes
        handler.headers = {"Content-Length": str(len(body))}
        with patch.object(handler, "_send") as mock_send:
            handler._route("POST")
            self.assertEqual(mock_send.call_args[1]["code"], 413)

    def test_unknown_table_ignored(self):
        server = self._make_server()
        handler = object.__new__(NativePushHandler)
        handler.server = server
        handler.path = "/iclock/cdata?SN=3392113170057&table=BIOPHOTO"
        handler.client_address = ("192.168.1.201", 40000)
        body = "PIN=1\tSIZE=100\n"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = type(
            "R", (), {"read": lambda self, n: body.encode("utf-8")}
        )()
        with patch.object(handler, "_ingest_attlog") as mock_ingest, \
             patch.object(handler, "_ok") as mock_ok:
            handler._route("POST")
            mock_ingest.assert_not_called()
            mock_ok.assert_called_once_with("OK")


class TestIngestErrorHandling(unittest.TestCase):
    """_ingest_attlog must count per-row errors without crashing."""

    @patch("app.native_push.service.save_attendance_log", side_effect=RuntimeError("db down"))
    def test_ingest_error_counted(self, mock_save):
        npc = make_npc()
        handler = object.__new__(NativePushHandler)
        handler.server = _fake_server(npc)
        result = handler._ingest_attlog(
            npc, "3392113170057", "ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0\t1\n"
        )
        self.assertEqual(result["rows"], 1)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["inserted"], 0)

    @patch("app.native_push.service.save_attendance_log", return_value=True)
    def test_mqtt_publish_when_enabled(self, mock_save):
        npc = make_npc()
        mqtt_mock = MagicMock()
        server = _fake_server(npc)
        server.mqtt_service = mqtt_mock
        handler = object.__new__(NativePushHandler)
        handler.server = server
        result = handler._ingest_attlog(
            npc, "3392113170057", "ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0\t1\n"
        )
        self.assertEqual(result["inserted"], 1)
        mqtt_mock.publish_attendance.assert_called_once()

    @patch("app.native_push.service.save_attendance_log", return_value=True)
    def test_mqtt_not_published_when_disabled(self, mock_save):
        npc = make_npc()
        handler = object.__new__(NativePushHandler)
        handler.server = _fake_server(npc)  # mqtt_service is None
        result = handler._ingest_attlog(
            npc, "3392113170057", "ATTLOG\t1001\t2026-08-12 08:47:37\t0\t0\t1\n"
        )
        self.assertEqual(result["inserted"], 1)


class TestEndToEndHTTP(unittest.TestCase):
    """Real ThreadingHTTPServer + urllib against the listener."""

    def setUp(self):
        import threading
        import urllib.request
        import urllib.error

        self.urllib_request = urllib.request
        self.urllib_error = urllib.error
        npc = make_npc(
            host="127.0.0.1",
            port=0,  # ephemeral
            allowed_sources=frozenset({"192.168.1.201", "127.0.0.1"}),
            health_file_path="/tmp/np_e2e_health.json",
        )
        server = NativePushServer(("127.0.0.1", 0), npc)
        self.server = server
        self.port = server.server_address[1]
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _get(self, path):
        return self.urllib_request.urlopen(
            f"http://127.0.0.1:{self.port}{path}", timeout=10
        )

    def test_healthz(self):
        resp = self._get("/healthz")
        self.assertEqual(resp.status, 200)
        self.assertIn(b"adms-native-push", resp.read())

    def test_cdata_get_options(self):
        resp = self._get("/iclock/cdata?SN=3392113170057")
        self.assertEqual(resp.status, 200)
        body = resp.read().decode()
        self.assertIn("GET OPTIONS FROM:", body)

    def test_getrequest_ok(self):
        resp = self._get("/iclock/getrequest?SN=3392113170057")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.read().decode(), "OK")

    def test_source_rejected_403(self):
        # Simulate a non-allowlisted source by patching client_address
        from app.native_push import service as svc
        orig = svc.NativePushHandler._route

        def patched(self, method):
            self.client_address = ("203.0.113.5", 50000)
            return orig(self, method)

        svc.NativePushHandler._route = patched
        try:
            with self.assertRaises(self.urllib_error.HTTPError) as ctx:
                self._get("/iclock/cdata?SN=3392113170057")
            self.assertEqual(ctx.exception.code, 403)
        finally:
            svc.NativePushHandler._route = orig

    def test_serial_rejected_403(self):
        with self.assertRaises(self.urllib_error.HTTPError) as ctx:
            self._get("/iclock/cdata?SN=0000000000000")
        self.assertEqual(ctx.exception.code, 403)

    def test_unknown_path_404(self):
        with self.assertRaises(self.urllib_error.HTTPError) as ctx:
            self._get("/nope?SN=3392113170057")
        self.assertEqual(ctx.exception.code, 404)


class TestTimestampNormalization(unittest.TestCase):
    def test_attlog_naive_timestamp_becomes_bangkok_aware(self):
        """The canonical normalizer must attach Asia/Bangkok (UTC+7)."""
        from app.timestamp_utils import normalize_device_timestamp, BANGKOK_TZ
        naive = datetime(2026, 8, 12, 8, 47, 37)
        aware = normalize_device_timestamp(naive)
        self.assertEqual(aware.tzinfo, BANGKOK_TZ)
        self.assertEqual(aware.utcoffset().total_seconds(), 7 * 3600)


if __name__ == "__main__":
    unittest.main()
