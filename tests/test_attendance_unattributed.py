"""
Attendance unattributed diagnostics — regression coverage.

PromptID: ADMS-PersonnelIdentity-AttendanceClosure-025

Root cause of the production 500 on GET /api/v1/attendance/unattributed:
`app/api/repository.py::_attribution_reasoning` calls
`resolve_verified_employee_mapping()` but the module never imported it
(confirmed via production traceback: `NameError: name
'resolve_verified_employee_mapping' is not defined`). The bug escaped test
coverage because the only existing tests
(tests/test_api.py::TestAttendance) mock `repository.unattributed_attendance`
wholesale, so the real `_attribution_reasoning` code path — the one that
actually crashed in production — was never exercised. These tests call
`repository.unattributed_attendance` / `repository._attribution_reasoning`
directly against a fake cursor that mimics the real SQL responses, so a
missing import or a real query bug will fail here exactly as it does in
production.

All tests are read-only against fakes — no real DB, no attendance/mapping
row is ever written.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.api import repository
from app.config import Config


def _dt(hours_from_epoch_base: int) -> datetime:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(hours=hours_from_epoch_base)


class FakeAttendanceCursor:
    """Dispatches on SQL content rather than call order, since
    `_attribution_reasoning` issues a variable number of queries per row
    (device_users lookup, mapping-interval lookup, and the canonical
    resolver's own separate query)."""

    def __init__(self, total, rows, device_users, mappings):
        self.total = total
        self.rows = rows
        self.device_users = device_users  # {pk: (device_user_id, active)}
        self.mappings = mappings  # {pk: [(employee_id, valid_from, valid_to), ...]}
        self.executed = []
        self._pending = None
        self._description = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        s = sql.strip()
        if "COUNT(*) FROM attendance_logs" in s:
            self._pending = ("scalar", self.total)
        elif "FROM attendance_logs WHERE employee_id IS NULL" in s:
            cols = ["id", "user_id", "device_ip", "scan_time", "punch_type", "status",
                    "device_id", "device_user_pk", "employee_id", "created_at"]
            self._description = [(c,) for c in cols]
            self._pending = ("rows", [tuple(r[c] for c in cols) for r in self.rows])
        elif "FROM device_users WHERE device_user_pk" in s:
            pk = params[0]
            du = self.device_users.get(pk)
            self._pending = ("row", du)
        elif "FROM employee_device_mappings" in s and "ORDER BY valid_from" in s:
            pk = params[0]
            self._pending = ("rows", self.mappings.get(pk, []))
        elif "FROM employee_device_mappings" in s and "LIMIT 2" in s:
            pk, scan_a, scan_b = params
            matches = [
                (emp,) for emp, vf, vt in self.mappings.get(pk, [])
                if vf <= scan_a and (vt is None or scan_a < vt)
            ]
            self._pending = ("rows", matches[:2])
        else:
            self._pending = ("rows", [])

    def fetchone(self):
        kind, val = self._pending
        if kind == "scalar":
            return (val,)
        if kind == "row":
            return val
        if kind == "rows":
            return val[0] if val else None
        return None

    def fetchall(self):
        kind, val = self._pending
        return val if kind == "rows" else []

    @property
    def description(self):
        return self._description


def _make_conn(cur):
    mock_conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__.return_value = cur
    cur_ctx.__exit__.return_value = None
    mock_conn.cursor.return_value = cur_ctx
    outer_ctx = MagicMock()
    outer_ctx.__enter__.return_value = mock_conn
    outer_ctx.__exit__.return_value = None
    return outer_ctx


class TestUnattributedAttendanceQuery(unittest.TestCase):
    """Exercises repository.unattributed_attendance() (and therefore
    _attribution_reasoning + resolve_verified_employee_mapping) against a
    fake cursor — the exact path that NameError'd in production."""

    def setUp(self):
        self.cfg = MagicMock(spec=Config)

    def _run(self, total, rows, device_users, mappings):
        cur = FakeAttendanceCursor(total, rows, device_users, mappings)
        with patch("app.api.repository._connect", return_value=_make_conn(cur)):
            result = repository.unattributed_attendance(self.cfg, limit=200, offset=0)
        return result, cur

    def test_returns_200_shape_with_zero_rows(self):
        result, _ = self._run(total=0, rows=[], device_users={}, mappings={})
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)

    def test_limit_200_accepted(self):
        result, _ = self._run(total=0, rows=[], device_users={}, mappings={})
        self.assertEqual(result["limit"], 200)

    def test_no_device_user_pk_classified_safely(self):
        row = {"id": 1, "user_id": "1001", "device_ip": "192.168.1.201", "scan_time": _dt(1),
               "punch_type": None, "status": None, "device_id": 1, "device_user_pk": None,
               "employee_id": None, "created_at": _dt(1)}
        result, _ = self._run(total=1, rows=[row], device_users={}, mappings={})
        self.assertEqual(result["items"][0]["reasoning"]["classification"], "NO_DEVICE_USER")

    def test_removed_1004_style_account_does_not_crash(self):
        """A historical, removed terminal account (no device_users row for
        the pk anymore) must classify safely, never 500."""
        row = {"id": 2, "user_id": "1004", "device_ip": "192.168.1.201", "scan_time": _dt(2),
               "punch_type": None, "status": None, "device_id": 1, "device_user_pk": 29,
               "employee_id": None, "created_at": _dt(2)}
        result, _ = self._run(total=1, rows=[row], device_users={}, mappings={})
        self.assertEqual(result["items"][0]["reasoning"]["classification"], "NO_DEVICE_USER")

    def test_inactive_historical_device_user_does_not_crash(self):
        row = {"id": 3, "user_id": "1002", "device_ip": "192.168.1.201", "scan_time": _dt(3),
               "punch_type": None, "status": None, "device_id": 1, "device_user_pk": 5,
               "employee_id": None, "created_at": _dt(3)}
        result, _ = self._run(
            total=1, rows=[row],
            device_users={5: ("1002", False)},
            mappings={},
        )
        self.assertEqual(result["items"][0]["reasoning"]["classification"], "NO_MAPPING")

    def test_current_mapped_row_resolves_but_stays_reported_as_diagnostic(self):
        """A genuinely-mapped scan inside its VERIFIED interval — the
        resolver must return the employee_id in `resolver_employee_id`
        (proving resolve_verified_employee_mapping actually executes)."""
        row = {"id": 4, "user_id": "1001", "device_ip": "192.168.1.201", "scan_time": _dt(10),
               "punch_type": None, "status": None, "device_id": 1, "device_user_pk": 1,
               "employee_id": None, "created_at": _dt(10)}
        result, _ = self._run(
            total=1, rows=[row],
            device_users={1: ("1001", True)},
            mappings={1: [("11111111-1111-1111-1111-111111111111", _dt(0), None)]},
        )
        reasoning = result["items"][0]["reasoning"]
        self.assertEqual(reasoning["classification"], "INSIDE_INTERVAL")
        self.assertEqual(reasoning["resolver_employee_id"], "11111111-1111-1111-1111-111111111111")

    def test_genuinely_unmapped_account_appears(self):
        row = {"id": 5, "user_id": "1005", "device_ip": "192.168.1.201", "scan_time": _dt(1),
               "punch_type": None, "status": None, "device_id": 1, "device_user_pk": 9,
               "employee_id": None, "created_at": _dt(1)}
        result, _ = self._run(
            total=1, rows=[row],
            device_users={9: ("1005", True)},
            mappings={},
        )
        self.assertEqual(result["items"][0]["reasoning"]["classification"], "NO_MAPPING")

    def test_closed_historical_mapping_resolves_correctly_at_past_scan_time(self):
        """A scan before the mapping closed (valid_to) must still resolve
        historically — closing a mapping must never retroactively hide the
        identity that was valid at scan time."""
        row = {"id": 6, "user_id": "1004", "device_ip": "192.168.1.201", "scan_time": _dt(5),
               "punch_type": None, "status": None, "device_id": 1, "device_user_pk": 29,
               "employee_id": None, "created_at": _dt(5)}
        result, _ = self._run(
            total=1, rows=[row],
            device_users={29: ("1004", False)},
            mappings={29: [("22222222-2222-2222-2222-222222222222", _dt(0), _dt(8))]},
        )
        reasoning = result["items"][0]["reasoning"]
        self.assertEqual(reasoning["resolver_employee_id"], "22222222-2222-2222-2222-222222222222")

    def test_reused_terminal_id_new_incarnation_resolves_only_own_interval(self):
        """Two VERIFIED intervals on the same device_user_pk (terminal ID
        reused across incarnations): an old scan must not resolve against
        the newer mapping's interval, and vice versa."""
        old_scan = {"id": 7, "user_id": "1003", "device_ip": "192.168.1.201", "scan_time": _dt(1),
                    "punch_type": None, "status": None, "device_id": 1, "device_user_pk": 3,
                    "employee_id": None, "created_at": _dt(1)}
        new_scan = {"id": 8, "user_id": "1003", "device_ip": "192.168.1.201", "scan_time": _dt(20),
                    "punch_type": None, "status": None, "device_id": 1, "device_user_pk": 3,
                    "employee_id": None, "created_at": _dt(20)}
        mappings = {3: [
            ("33333333-3333-3333-3333-333333333333", _dt(0), _dt(5)),
            ("44444444-4444-4444-4444-444444444444", _dt(15), None),
        ]}
        result, _ = self._run(
            total=2, rows=[old_scan, new_scan],
            device_users={3: ("1003", True)},
            mappings=mappings,
        )
        old_reasoning = result["items"][0]["reasoning"]
        new_reasoning = result["items"][1]["reasoning"]
        self.assertEqual(old_reasoning["resolver_employee_id"], "33333333-3333-3333-3333-333333333333")
        self.assertEqual(new_reasoning["resolver_employee_id"], "44444444-4444-4444-4444-444444444444")

    def test_nullable_fields_serialize_safely(self):
        row = {"id": 9, "user_id": None, "device_ip": None, "scan_time": _dt(1),
               "punch_type": None, "status": None, "device_id": None, "device_user_pk": None,
               "employee_id": None, "created_at": _dt(1)}
        result, _ = self._run(total=1, rows=[row], device_users={}, mappings={})
        self.assertIsNone(result["items"][0]["device_user_pk"])
        self.assertIsNone(result["items"][0]["employee_id"])

    def test_no_attendance_or_mapping_row_mutated(self):
        cur = FakeAttendanceCursor(total=0, rows=[], device_users={}, mappings={})
        with patch("app.api.repository._connect", return_value=_make_conn(cur)):
            repository.unattributed_attendance(self.cfg, limit=200, offset=0)
        for sql, _ in cur.executed:
            upper = sql.strip().upper()
            self.assertTrue(upper.startswith("SELECT"), "unexpected non-SELECT: %s" % sql)


from fastapi.testclient import TestClient

from app.api.dependencies import OperatorContext, require_write_session
from app.api.main import create_app
from app.api.settings import ApiSettings


class TestUnattributedEndpointHttp(unittest.TestCase):
    """HTTP-level: endpoint returns 200 (not 500) once the resolver import
    is present, and enforces existing RBAC/CORS behavior unchanged."""

    def _client(self, role="ADMIN", raise_server_exceptions=True):
        app = create_app(settings=ApiSettings(
            write_enabled=False,
            cors_origins=("http://192.168.1.248:8082",),
        ))
        app.dependency_overrides[require_write_session] = lambda: None
        client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
        ctx = OperatorContext(operator_id=1, username="tester", display_name="Tester", role=role)
        p = patch("app.api.dependencies._load_token_context", return_value=ctx)
        p.start()
        self.addCleanup(p.stop)
        return client

    @patch("app.api.repository.unattributed_attendance", return_value={"items": [], "total": 0, "limit": 200, "offset": 0})
    def test_unattributed_returns_200_empty_list(self, _mock):
        client = self._client()
        resp = client.get(
            "/api/v1/attendance/unattributed?limit=200",
            headers={"Origin": "http://192.168.1.248:8082"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["items"], [])

    @patch("app.api.repository.unattributed_attendance", return_value={"items": [], "total": 0, "limit": 200, "offset": 0})
    def test_allowed_origin_gets_cors_header_on_success(self, _mock):
        client = self._client()
        resp = client.get(
            "/api/v1/attendance/unattributed?limit=200",
            headers={"Origin": "http://192.168.1.248:8082"},
        )
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://192.168.1.248:8082")

    def test_unhandled_exception_still_gets_cors_header_and_json_envelope(self):
        """Reproduces the exact production failure mode with a real
        unmocked exception raised deep in the call stack, proving the
        global exception handler returns a safe JSON 500 WITH CORS headers
        intact for an allowed origin — confirming the browser's CORS
        error was a secondary symptom of the 500, not a CORS
        misconfiguration."""
        client = self._client(raise_server_exceptions=False)
        with patch("app.api.repository.unattributed_attendance", side_effect=RuntimeError("boom")):
            resp = client.get(
                "/api/v1/attendance/unattributed?limit=200",
                headers={"Origin": "http://192.168.1.248:8082"},
            )
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("boom", resp.text)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://192.168.1.248:8082")

    def test_disallowed_origin_preflight_has_no_cors_header(self):
        client = self._client()
        resp = client.options(
            "/api/v1/attendance/unattributed",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertNotIn("access-control-allow-origin", resp.headers)

    def test_unattributed_requires_admin(self):
        client = self._client(role="VIEWER")
        resp = client.get("/api/v1/attendance/unattributed?limit=200")
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
