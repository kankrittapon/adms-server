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
        # NOTE: do NOT p.start() here — the tests use `with p:` which starts
        # and stops the patch. Calling start() first double-activates it so
        # the single stop() from the context manager leaves the patch leaked
        # into every subsequent test in the process (silent auth bypass).
        return client, p

    def test_operator_can_reserve(self):
        client, p = self._client_with("OPERATOR")
        with p, patch(
            "app.api.routers.enrollments.reserve_next_device_user_id",
            return_value={"enrollment_id": 9, "reserved_device_user_id": "1002",
                          "status": "RESERVED",
                          "reserved_at": datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc),
                          "employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                          "device_id": 1},
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
        # NOTE: do NOT p.start() here — tests use `with self._admin_client():`
        # which starts and stops the patch. Double-starting leaks the patch
        # into every subsequent test in the process (silent auth bypass).
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
    def test_admin_create_enrollment_operator(self):
        with self._admin_client():
            with patch("app.api.routers.operators.log_sync_event"):
                with patch("app.api.routers.operators.get_db_connection") as m:
                    cur = FakeCursor(fetchone_queue=[(8, NOW, NOW)])
                    m.return_value = fake_ctx_conn(cur)
                    resp = self.client.post(
                        "/api/v1/operators",
                        json={"username": "enroll_op", "display_name": "Enrollment Specialist",
                              "password": "a-long-enough-password", "role": "ENROLLMENT_OPERATOR"},
                    )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["username"], "enroll_op")
        self.assertEqual(body["role"], "ENROLLMENT_OPERATOR")


class TestEnrollmentOperatorRole(unittest.TestCase):
    """Specific tests for ENROLLMENT_OPERATOR capability scoping."""

    def _client(self, write_enabled=True):
        app = create_app(settings=ApiSettings(write_enabled=write_enabled))
        client = TestClient(app)
        from app.api.dependencies import OperatorContext
        ctx = OperatorContext(2, "enroll_user", "Enrollment Op", "ENROLLMENT_OPERATOR")
        p = patch("app.api.dependencies._load_token_context", return_value=ctx)
        return client, p

    def test_enrollment_operator_can_access_enrollment_workspace(self):
        client, p = self._client(write_enabled=True)
        with p:
            with patch("app.api.repository.list_enrollments", return_value={"items": [], "total": 0, "limit": 50, "offset": 0}):
                resp = client.get("/api/v1/enrollments")
            self.assertEqual(resp.status_code, 200)

            with patch("app.api.repository.list_humans", return_value={"items": [], "total": 0, "limit": 50, "offset": 0}):
                resp_h = client.get("/api/v1/humans?production_scope=true")
            self.assertEqual(resp_h.status_code, 200)

            with patch("app.api.repository.list_devices", return_value={"items": [], "total": 0, "limit": 50, "offset": 0}):
                resp_d = client.get("/api/v1/devices")
            self.assertEqual(resp_d.status_code, 200)

    def test_enrollment_operator_can_reserve_when_writes_enabled(self):
        client, p = self._client(write_enabled=True)
        with p, patch(
            "app.api.routers.enrollments.reserve_next_device_user_id",
            return_value={"enrollment_id": 9, "reserved_device_user_id": "1002",
                          "status": "RESERVED",
                          "reserved_at": datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc),
                          "employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                          "device_id": 1},
        ):
            resp = client.post(
                "/api/v1/enrollments/reserve",
                json={"employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                      "device_id": 1, "operator": "enroll_user"},
            )
        self.assertEqual(resp.status_code, 201)

    def test_enrollment_operator_reserve_blocked_when_writes_disabled(self):
        client, p = self._client(write_enabled=False)
        with p:
            resp = client.post(
                "/api/v1/enrollments/reserve",
                json={"employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                      "device_id": 1, "operator": "enroll_user"},
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "WRITE_DISABLED")

    def test_enrollment_operator_strictly_forbidden_from_unrelated_endpoints(self):
        client, p = self._client(write_enabled=True)
        with p:
            # 1. Operators management
            resp = client.get("/api/v1/operators")
            self.assertEqual(resp.status_code, 403)

            resp = client.post("/api/v1/operators", json={
                "username": "bad", "display_name": "Bad", "password": "long-password-1234", "role": "VIEWER"
            })
            self.assertEqual(resp.status_code, 403)

            # 2. Audit events
            resp = client.get("/api/v1/audit/events")
            self.assertEqual(resp.status_code, 403)

            # 3. Mappings creation
            resp = client.post("/api/v1/mappings", json={
                "employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                "device_user_pk": 7, "enrollment_id": 1,
                "controlled_attendance_id": 12,
                "verified_by": "op", "verification_note": "test",
            })
            self.assertEqual(resp.status_code, 403)

            # 4. Attendance list and unattributed diagnostics
            resp = client.get("/api/v1/attendance")
            self.assertEqual(resp.status_code, 403)

            resp = client.get("/api/v1/attendance/unattributed")
            self.assertEqual(resp.status_code, 403)

            # 5. Device users list
            resp = client.get("/api/v1/device-users")
            self.assertEqual(resp.status_code, 403)

            # 6. Dashboard summary
            resp = client.get("/api/v1/dashboard/summary")
            self.assertEqual(resp.status_code, 403)

            # 7. Personnel English name PATCH
            resp = client.patch(
                "/api/v1/humans/039c4486-b30f-4ce1-b780-783cd268858d",
                json={"english_name": "Test Name"},
            )
            self.assertEqual(resp.status_code, 403)


class TestPersonnelEnglishName(unittest.TestCase):
    def _client(self, role="ADMIN", write_enabled=True):
        app = create_app(settings=ApiSettings(write_enabled=write_enabled))
        client = TestClient(app)
        from app.api.dependencies import OperatorContext
        ctx = OperatorContext(1, "admin_user", "Admin", role)
        p = patch("app.api.dependencies._load_token_context", return_value=ctx)
        return client, p

    def test_admin_patch_english_name_success(self):
        client, p = self._client(role="ADMIN", write_enabled=True)
        updated_row = {
            "employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
            "personnel_id": "RTN-001",
            "display_name": "กฤตพล หมาดเส็น",
            "english_name": "Krittapon Madsen",
            "rank": "พ.จ.ต.",
            "rank_metadata": None,
            "position": None,
            "branch": None,
            "category": None,
            "notes": None,
            "active": True,
            "production_scope": True,
            "source": "EXCEL_IMPORT",
            "created_at": NOW,
            "updated_at": NOW,
        }
        with p, patch("app.api.repository.update_human_english_name", return_value=updated_row):
            resp = client.patch(
                "/api/v1/humans/039c4486-b30f-4ce1-b780-783cd268858d",
                json={"english_name": "Krittapon Madsen"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["english_name"], "Krittapon Madsen")

    def test_admin_patch_english_name_write_disabled_rejected(self):
        client, p = self._client(role="ADMIN", write_enabled=False)
        with p:
            resp = client.patch(
                "/api/v1/humans/039c4486-b30f-4ce1-b780-783cd268858d",
                json={"english_name": "Krittapon Madsen"},
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "WRITE_DISABLED")

    def test_operator_cannot_patch_english_name(self):
        client, p = self._client(role="OPERATOR", write_enabled=True)
        with p:
            resp = client.patch(
                "/api/v1/humans/039c4486-b30f-4ce1-b780-783cd268858d",
                json={"english_name": "Krittapon Madsen"},
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
