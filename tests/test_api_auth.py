"""
F5 auth tests (ADMS-Frontend-F5-Auth-001).

Covers: password hashing round-trip, login success/failure, token issue +
verification, expiry/revocation rejection, role hierarchy (VIEWER < OPERATOR <
ADMIN), strict no-token 401, and admin operator management endpoints.

DB access is mocked at the app.api.routers.auth / app.api.dependencies
boundaries (same convention as the rest of the suite).
"""

import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.auth import hash_password, verify_password, verify_token_row
from app.api.main import create_app
from app.api.settings import ApiSettings

NOW = datetime.now(timezone.utc)

VALID_TOKEN = "test-token-abc-123"
VALID_TOKEN_HASH = hashlib.sha256(VALID_TOKEN.encode()).hexdigest()

OP_ROW = (1, "admin", "ADMS Admin", "ADMIN", True)


def fake_ctx_conn(cur):
    """Wraps a FakeCursor into the get_db_connection context-manager mock."""
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
    def __init__(self, fetchone_queue=None):
        self._queue = list(fetchone_queue or [])
        self.rowcount = 1

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        if self._queue:
            return self._queue.pop(0)
        return None


class TestPasswordHashing(unittest.TestCase):
    def test_hash_round_trip(self):
        h = hash_password("correct horse battery staple")
        self.assertTrue(h.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("correct horse battery staple", h))
        self.assertFalse(verify_password("wrong password", h))

    def test_hash_is_salted(self):
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        self.assertNotEqual(h1, h2)

    def test_verify_garbage(self):
        self.assertFalse(verify_password("x", "not-a-hash"))
        self.assertFalse(verify_password("x", ""))


class TestTokenVerify(unittest.TestCase):
    def test_valid_token_row(self):
        row = (VALID_TOKEN_HASH, "OPERATOR", NOW + timedelta(hours=1), None,
               2, "op", "Operator", True)
        ctx = verify_token_row(row, now=NOW)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["role"], "OPERATOR")
        self.assertEqual(ctx["username"], "op")

    def test_expired_token_rejected(self):
        row = (VALID_TOKEN_HASH, "OPERATOR", NOW - timedelta(minutes=1), None,
               2, "op", "Operator", True)
        self.assertIsNone(verify_token_row(row, now=NOW))

    def test_revoked_token_rejected(self):
        row = (VALID_TOKEN_HASH, "OPERATOR", NOW + timedelta(hours=1), NOW,
               2, "op", "Operator", True)
        self.assertIsNone(verify_token_row(row, now=NOW))

    def test_inactive_operator_rejected(self):
        row = (VALID_TOKEN_HASH, "OPERATOR", NOW + timedelta(hours=1), None,
               2, "op", "Operator", False)
        self.assertIsNone(verify_token_row(row, now=NOW))

    def test_none_row_rejected(self):
        self.assertIsNone(verify_token_row(None, now=NOW))


class TestAuthEndpoints(unittest.TestCase):
    def setUp(self):
        self.app = create_app(settings=ApiSettings(write_enabled=False))
        self.client = TestClient(self.app)

    def _mock_login(self, operator_row, queue_after=None):
        """operator_row: (operator_id, username, display_name, role, password_hash, active)."""
        cur = FakeCursor(fetchone_queue=[operator_row] + (queue_after or []))
        mock_ctx = fake_ctx_conn(cur)
        p = patch("app.api.routers.auth.get_db_connection", return_value=mock_ctx)
        p.start()
        self.addCleanup(p.stop)
        return cur

    def test_login_success(self):
        pwd_hash = hash_password("correct horse battery staple")
        with patch("app.api.routers.auth.log_sync_event"):
            self._mock_login((1, "admin", "ADMS Admin", "ADMIN", pwd_hash, True))
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "correct horse battery staple"},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["role"], "ADMIN")
        self.assertEqual(body["token_type"], "bearer")
        self.assertIn("token", body)
        self.assertIn("expires_at", body)

    def test_login_wrong_password(self):
        pwd_hash = hash_password("correct horse battery staple")
        with patch("app.api.routers.auth.log_sync_event"):
            self._mock_login((1, "admin", "ADMS Admin", "ADMIN", pwd_hash, True))
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "nope"},
            )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"]["code"], "UNAUTHORIZED")

    def test_login_unknown_user(self):
        with patch("app.api.routers.auth.log_sync_event"):
            self._mock_login(None)
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": "ghost", "password": "whatever"},
            )
        self.assertEqual(resp.status_code, 401)

    def test_login_inactive_operator(self):
        pwd_hash = hash_password("correct horse battery staple")
        with patch("app.api.routers.auth.log_sync_event"):
            self._mock_login((1, "admin", "ADMS Admin", "ADMIN", pwd_hash, False))
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "correct horse battery staple"},
            )
        self.assertEqual(resp.status_code, 401)


class TestStrictAuth(unittest.TestCase):
    """Strict posture: no token -> 401 on every /api/v1 route (except healthz/login)."""

    def setUp(self):
        self.app = create_app(settings=ApiSettings(write_enabled=False))
        self.client = TestClient(self.app)

    def test_healthz_public(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)

    def test_no_token_rejected_everywhere(self):
        for path in [
            "/api/v1/health",
            "/api/v1/dashboard/summary",
            "/api/v1/humans",
            "/api/v1/devices",
            "/api/v1/device-users",
            "/api/v1/attendance",
            "/api/v1/mappings",
            "/api/v1/enrollments",
            "/api/v1/reference/ranks",
        ]:
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 401)
                self.assertEqual(resp.json()["error"]["code"], "UNAUTHORIZED")

    def test_bad_token_rejected(self):
        # Token lookup returns None -> 401.
        with patch("app.api.dependencies._load_token_context", return_value=None):
            resp = self.client.get("/api/v1/humans", headers={"Authorization": "Bearer nope"})
        self.assertEqual(resp.status_code, 401)

    def test_viewer_can_read(self):
        from app.api.dependencies import OperatorContext

        ctx = OperatorContext(1, "viewer", "Viewer", "VIEWER")
        with patch("app.api.dependencies._load_token_context", return_value=ctx):
            resp = self.client.get("/api/v1/reference/ranks")
        self.assertEqual(resp.status_code, 200)


class TestRoleMatrix(unittest.TestCase):
    def _client_with(self, role):
        app = create_app(settings=ApiSettings(write_enabled=True))
        client = TestClient(app)
        from app.api.dependencies import OperatorContext

        ctx = OperatorContext(1, "u", "U", role)
        p = patch("app.api.dependencies._load_token_context", return_value=ctx)
        p.start()
        return client, p

    def test_operator_can_reserve(self):
        client, p = self._client_with("OPERATOR")
        with p, patch(
            "app.api.routers.enrollments.reserve_next_device_user_id",
            return_value={"enrollment_id": 9, "reserved_device_user_id": "1002", "status": "RESERVED"},
        ):
            resp = client.post(
                "/api/v1/enrollments/reserve",
                json={"employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                      "device_id": 1, "operator": "op"},
            )
        self.assertEqual(resp.status_code, 201)

    def test_viewer_cannot_reserve(self):
        client, p = self._client_with("VIEWER")
        with p:
            resp = client.post(
                "/api/v1/enrollments/reserve",
                json={"employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                      "device_id": 1, "operator": "viewer"},
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "FORBIDDEN")

    def test_operator_cannot_create_mapping(self):
        client, p = self._client_with("OPERATOR")
        with p:
            resp = client.post(
                "/api/v1/mappings",
                json={
                    "employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                    "device_user_pk": 7, "enrollment_id": 1,
                    "controlled_attendance_id": 12,
                    "verified_by": "op", "verification_note": "test",
                },
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "FORBIDDEN")

    def test_admin_can_create_mapping(self):
        client, p = self._client_with("ADMIN")
        with p, patch(
            "app.api.routers.mappings.create_verified_mapping",
            return_value={
                "mapping_id": 2, "employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                "device_user_pk": 7, "mapping_status": "VERIFIED",
                "verification_method": "CONTROLLED_SCAN",
                "valid_from": datetime(2026, 8, 13, 8, 0, 0, tzinfo=timezone.utc),
                "valid_to": None,
                "verified_at": datetime(2026, 8, 13, 9, 0, 0, tzinfo=timezone.utc),
            },
        ):
            resp = client.post(
                "/api/v1/mappings",
                json={
                    "employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                    "device_user_pk": 7, "enrollment_id": 1,
                    "controlled_attendance_id": 12,
                    "verified_by": "admin", "verification_note": "test",
                },
            )
        self.assertEqual(resp.status_code, 201)

    def test_write_flag_still_blocks_even_admin(self):
        """API_WRITE_ENABLED=false must block writes even for ADMIN (defense in depth)."""
        app = create_app(settings=ApiSettings(write_enabled=False))
        client = TestClient(app)
        from app.api.dependencies import OperatorContext

        ctx = OperatorContext(1, "admin", "Admin", "ADMIN")
        with patch("app.api.dependencies._load_token_context", return_value=ctx):
            resp = client.post(
                "/api/v1/enrollments/reserve",
                json={"employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                      "device_id": 1, "operator": "admin"},
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "WRITE_DISABLED")


class TestOperatorManagement(unittest.TestCase):
    def setUp(self):
        self.app = create_app(settings=ApiSettings(write_enabled=False))
        self.client = TestClient(self.app)

    def _admin_client(self):
        from app.api.dependencies import OperatorContext

        ctx = OperatorContext(1, "admin", "Admin", "ADMIN")
        p = patch("app.api.dependencies._load_token_context", return_value=ctx)
        p.start()
        return p

    def test_viewer_cannot_list_operators(self):
        from app.api.dependencies import OperatorContext

        ctx = OperatorContext(1, "v", "V", "VIEWER")
        with patch("app.api.dependencies._load_token_context", return_value=ctx):
            resp = self.client.get("/api/v1/operators")
        self.assertEqual(resp.status_code, 403)

    def test_admin_create_operator(self):
        with self._admin_client():
            with patch("app.api.routers.operators.log_sync_event"):
                with patch("app.api.routers.operators.get_db_connection") as m:
                    cur = FakeCursor(fetchone_queue=[(7, NOW, NOW)])
                    m.return_value = fake_ctx_conn(cur)
                    resp = self.client.post(
                        "/api/v1/operators",
                        json={"username": "newop", "display_name": "New Op",
                              "password": "a-long-enough-password", "role": "OPERATOR"},
                    )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["username"], "newop")
        self.assertEqual(body["role"], "OPERATOR")
        self.assertNotIn("password", body)

    def test_admin_list_operators(self):
        with self._admin_client():
            with patch("app.api.routers.operators.get_db_connection") as m:
                cur = MagicMock()
                cur.fetchall.return_value = [
                    (1, "admin", "Admin", "ADMIN", True, NOW, NOW),
                    (2, "op", "Op", "OPERATOR", True, NOW, NOW),
                ]
                m.return_value = fake_ctx_conn(cur)
                resp = self.client.get("/api/v1/operators")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_weak_password_rejected(self):
        with self._admin_client():
            resp = self.client.post(
                "/api/v1/operators",
                json={"username": "newop", "display_name": "New Op",
                      "password": "short", "role": "OPERATOR"},
            )
        self.assertEqual(resp.status_code, 422)

    def test_self_deactivation_rejected(self):
        with self._admin_client():
            with patch("app.api.routers.operators.log_sync_event"):
                resp = self.client.post(
                    "/api/v1/operators/1/toggle-active", json={"active": False}
                )
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
