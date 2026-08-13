"""F5 hardening tests (ADMS-Frontend-F5-Hardening-001).

Covers: rate-limiter window/eviction semantics, login 429 + Retry-After,
failed-login audit logging, the admin audit endpoint (role gate, filters,
pagination, event-types), and change-password (wrong current, weak new,
revoke-others-keep-current).

Same mocking conventions as tests/test_api_auth.py.
"""

import hashlib
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api import ratelimit
from app.api.auth import hash_password
from app.api.main import create_app
from app.api.settings import ApiSettings

NOW_TS = "2026-08-13T12:00:00+00:00"

PILOT_EMPLOYEE_ID = "039c4486-b30f-4ce1-b780-783cd268858d"


def fake_ctx_conn(cur):
    mock_conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__.return_value = cur
    cur_ctx.__exit__.return_value = None
    mock_conn.cursor.return_value = cur_ctx
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    mock_ctx.__exit__.return_value = None
    return mock_ctx


class FakeCursor:
    def __init__(self, fetchone_queue=None, rowcount=1):
        self._queue = list(fetchone_queue or [])
        self.rowcount = rowcount
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self._queue:
            return self._queue.pop(0)
        return None


class TestRateLimiter(unittest.TestCase):
    def setUp(self):
        ratelimit.reset()

    def tearDown(self):
        ratelimit.reset()

    def test_allows_within_window(self):
        for _ in range(5):
            allowed, _ = ratelimit.check_limit("1.2.3.4", "login", 5)
            self.assertTrue(allowed)

    def test_blocks_after_limit(self):
        for _ in range(5):
            ratelimit.check_limit("1.2.3.4", "login", 5)
        allowed, retry = ratelimit.check_limit("1.2.3.4", "login", 5)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry, 1)

    def test_scopes_are_independent(self):
        ratelimit.check_limit("1.2.3.4", "login", 1)
        allowed, _ = ratelimit.check_limit("1.2.3.4", "global", 1)
        self.assertTrue(allowed)

    def test_keys_are_independent(self):
        ratelimit.check_limit("1.2.3.4", "login", 1)
        allowed, _ = ratelimit.check_limit("5.6.7.8", "login", 1)
        self.assertTrue(allowed)

    def test_zero_per_min_disables(self):
        allowed, _ = ratelimit.check_limit("1.2.3.4", "login", 0)
        self.assertTrue(allowed)


class TestLoginRateLimit(unittest.TestCase):
    def setUp(self):
        ratelimit.reset()

    def tearDown(self):
        ratelimit.reset()

    def _client(self):
        app = create_app(settings=ApiSettings(write_enabled=False, rate_limit_enabled=True, login_rate_per_min=3))
        return TestClient(app)

    def test_login_429_after_limit_with_retry_after(self):
        client = self._client()
        with patch("app.api.routers.auth.log_sync_event"), patch(
            "app.api.routers.auth.get_db_connection"
        ) as m:
            cur = FakeCursor(fetchone_queue=[None])  # operator not found
            m.return_value = fake_ctx_conn(cur)
            for i in range(3):
                resp = client.post("/api/v1/auth/login",
                                   json={"username": "x", "password": "y"})
                self.assertEqual(resp.status_code, 401)
            resp = client.post("/api/v1/auth/login",
                               json={"username": "x", "password": "y"})
            self.assertEqual(resp.status_code, 429)
            self.assertEqual(resp.json()["error"]["code"], "RATE_LIMITED")
            self.assertIn("retry-after", resp.headers)
        ratelimit.reset()

    def test_failed_login_logged(self):
        client = self._client()
        with patch("app.api.routers.auth.get_db_connection") as m, patch(
            "app.api.routers.auth.log_sync_event"
        ) as mock_log:
            cur = FakeCursor(fetchone_queue=[None])
            m.return_value = fake_ctx_conn(cur)
            client.post("/api/v1/auth/login", json={"username": "ghost", "password": "nope"})
            calls = [c.args for c in mock_log.call_args_list]
            self.assertTrue(
                any(c[1] == "AUTH_LOGIN_FAILED" for c in calls),
                "expected AUTH_LOGIN_FAILED audit event",
            )
            msg = next(c[2] for c in calls if c[1] == "AUTH_LOGIN_FAILED")
            self.assertIn("ghost", msg)
            self.assertNotIn("nope", msg)  # never log passwords

    def test_healthz_not_rate_limited(self):
        client = self._client()
        for _ in range(10):
            resp = client.get("/healthz")
            self.assertEqual(resp.status_code, 200)


class TestAuditEndpoint(unittest.TestCase):
    def setUp(self):
        ratelimit.reset()
        self.app = create_app(settings=ApiSettings(write_enabled=False))
        self.client = TestClient(self.app)

    def tearDown(self):
        ratelimit.reset()

    def _ctx(self, role):
        from app.api.dependencies import OperatorContext

        return OperatorContext(1, "tester", "Tester", role)

    def test_audit_requires_admin(self):
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx("VIEWER")):
            resp = self.client.get("/api/v1/audit/events")
        self.assertEqual(resp.status_code, 403)

    def test_audit_list_and_filters(self):
        rows = [
            {"id": 2, "device_ip": "192.168.1.201", "event_type": "AUTH_LOGIN",
             "message": "operator=admin role=ADMIN", "created_at": NOW_TS},
            {"id": 1, "device_ip": None, "event_type": "AUTH_LOGIN_FAILED",
             "message": "username=ghost", "created_at": NOW_TS},
        ]
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx("ADMIN")), patch(
            "app.api.repository.list_audit_events",
            return_value={"items": rows, "total": 2, "limit": 50, "offset": 0},
        ) as mock_rep:
            resp = self.client.get("/api/v1/audit/events?event_type=AUTH_LOGIN&limit=10")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["items"][0]["event_type"], "AUTH_LOGIN")
        self.assertEqual(mock_rep.call_args.kwargs["event_type"], "AUTH_LOGIN")
        self.assertEqual(mock_rep.call_args.kwargs["limit"], 10)

    def test_audit_event_types(self):
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx("ADMIN")), patch(
            "app.api.repository.list_audit_event_types", return_value=["AUTH_LOGIN", "AUTH_LOGOUT"],
        ):
            resp = self.client.get("/api/v1/audit/event-types")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("AUTH_LOGIN", resp.json()["event_types"])

    def test_audit_invalid_date_422(self):
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx("ADMIN")):
            resp = self.client.get("/api/v1/audit/events?date_from=notadate")
        self.assertEqual(resp.status_code, 422)


class TestChangePassword(unittest.TestCase):
    def setUp(self):
        ratelimit.reset()
        self.app = create_app(settings=ApiSettings(write_enabled=False))
        self.client = TestClient(self.app)

    def tearDown(self):
        ratelimit.reset()

    def _authed(self, role="VIEWER"):
        from app.api.dependencies import OperatorContext

        ctx = OperatorContext(1, "tester", "Tester", role)
        p = patch("app.api.dependencies._load_token_context", return_value=ctx)
        p.start()
        self.addCleanup(p.stop)

    AUTH_HEADERS = {"Authorization": "Bearer test-current-token-xyz"}

    def test_wrong_current_password_401(self):
        self._authed()
        stored = hash_password("the-real-password")
        with patch("app.api.routers.auth.get_db_connection") as m:
            cur = FakeCursor(fetchone_queue=[(stored,)])
            m.return_value = fake_ctx_conn(cur)
            resp = self.client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "wrong", "new_password": "a-brand-new-password-123"},
                headers=self.AUTH_HEADERS,
            )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["code"], "UNAUTHORIZED")

    def test_weak_new_password_422(self):
        self._authed()
        resp = self.client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "whatever", "new_password": "short"},
            headers=self.AUTH_HEADERS,
        )
        self.assertEqual(resp.status_code, 422)

    def test_success_revokes_other_tokens(self):
        self._authed()
        stored = hash_password("the-real-password")
        # execute order: SELECT hash (fetchone), UPDATE operators, UPDATE api_tokens (rowcount=2)
        cur = FakeCursor(fetchone_queue=[(stored,)], rowcount=2)
        with patch("app.api.routers.auth.get_db_connection") as m, patch(
            "app.api.routers.auth.log_sync_event"
        ):
            m.return_value = fake_ctx_conn(cur)
            resp = self.client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "the-real-password",
                      "new_password": "a-brand-new-password-123"},
                headers=self.AUTH_HEADERS,
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["changed"])
        self.assertEqual(body["other_tokens_revoked"], 2)
        # the UPDATE for tokens must exclude the current token hash
        token_updates = [
            s for s, _ in cur.executed if s.startswith("UPDATE api_tokens")
        ]
        self.assertTrue(token_updates)
        self.assertIn("token_hash <> %s", token_updates[0])
        self.assertIn("operator_id = %s", token_updates[0])


if __name__ == "__main__":
    unittest.main()
