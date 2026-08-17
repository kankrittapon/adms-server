"""
Runtime write session tests (Layer 2 of the two-layer write model).

PromptID: ADMS-FullSystem-P0P1-Hardening-007

Covers the concurrency-safe open/close/expiry logic in app/write_session.py
directly (mocked DB, mirroring the FakeCursor convention used across the
suite) and the router/RBAC/error-code surface via TestClient.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import OperatorContext
from app.api.main import create_app
from app.api.settings import ApiSettings
from app.config import Config
from app.write_session import (
    WriteSessionAlreadyActive,
    WriteSessionError,
    close_write_session,
    get_write_session_status,
    is_write_session_active,
    open_write_session,
)

NOW = datetime.now(timezone.utc)
CFG = Config.from_env()


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
    def __init__(self, fetchone_queue=None):
        self._queue = list(fetchone_queue or [])
        self.rowcount = 1

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        if self._queue:
            return self._queue.pop(0)
        return None


ACTIVE_ROW = (1, 5, "Admin Alice", NOW, NOW + timedelta(minutes=30), "Enrollment session")
EXPIRED_REAP_ROW = (1, 5, NOW - timedelta(minutes=45), NOW - timedelta(minutes=15), "Old session")
INSERTED_ROW = (2, NOW, NOW + timedelta(minutes=30))
CLOSED_AT_ROW = (NOW,)


class WriteSessionModuleTests(unittest.TestCase):
    """Direct tests of app/write_session.py business logic."""

    def _run(self, fetchone_queue, func, *args, **kwargs):
        cur = FakeCursor(fetchone_queue=fetchone_queue)
        with patch("app.write_session.get_db_connection", return_value=fake_ctx_conn(cur)):
            with patch("app.write_session.log_sync_event") as mock_audit:
                result = func(*args, **kwargs)
        return result, mock_audit

    def test_status_inactive_when_nothing_open(self):
        status, audit = self._run([None, None], get_write_session_status, CFG)
        self.assertEqual(status, {"active": False})
        audit.assert_not_called()

    def test_status_active_when_session_open(self):
        status, audit = self._run([None, ACTIVE_ROW], get_write_session_status, CFG)
        self.assertTrue(status["active"])
        self.assertEqual(status["session_id"], 1)
        self.assertEqual(status["opened_by_name"], "Admin Alice")
        audit.assert_not_called()

    def test_expired_unclosed_row_reaped_and_audited_once(self):
        """A session can be logically expired while closed_at is still NULL —
        it must be reaped transparently and must NOT block a subsequent
        status/open call, and the expiry audit event fires exactly once."""
        status, audit = self._run([EXPIRED_REAP_ROW, None], get_write_session_status, CFG)
        self.assertEqual(status, {"active": False})
        audit.assert_called_once()
        self.assertEqual(audit.call_args[0][1], "WRITE_SESSION_EXPIRED")

    def test_is_write_session_active_distinguishes_expired_from_never_opened(self):
        active, just_expired = self._run(
            [None, None], is_write_session_active, CFG
        )[0]
        self.assertFalse(active)
        self.assertFalse(just_expired)

        active2, just_expired2 = self._run(
            [EXPIRED_REAP_ROW, None], is_write_session_active, CFG
        )[0]
        self.assertFalse(active2)
        self.assertTrue(just_expired2)

    def test_open_succeeds_when_nothing_active(self):
        result, audit = self._run(
            [None, None, INSERTED_ROW],
            open_write_session,
            CFG,
            opened_by_operator_id=5,
            opened_by_username="admin_alice",
            reason="Enrollment session",
        )
        self.assertTrue(result["active"])
        self.assertEqual(result["session_id"], 2)
        audit.assert_called_once()
        self.assertEqual(audit.call_args[0][1], "WRITE_SESSION_OPENED")

    def test_open_rejected_when_already_active(self):
        with self.assertRaises(WriteSessionAlreadyActive):
            self._run(
                [None, ACTIVE_ROW],
                open_write_session,
                CFG,
                opened_by_operator_id=9,
                opened_by_username="admin_bob",
                reason="Trying to double-open",
            )

    def test_open_reaps_expired_row_then_succeeds(self):
        """An expired-but-unclosed row must never permanently block opening
        a new session."""
        result, audit = self._run(
            [EXPIRED_REAP_ROW, None, INSERTED_ROW],
            open_write_session,
            CFG,
            opened_by_operator_id=5,
            opened_by_username="admin_alice",
            reason="New session after expiry",
        )
        self.assertTrue(result["active"])
        # Both the expiry event and the open event are audited.
        self.assertEqual(audit.call_count, 2)
        codes = [c[0][1] for c in audit.call_args_list]
        self.assertIn("WRITE_SESSION_EXPIRED", codes)
        self.assertIn("WRITE_SESSION_OPENED", codes)

    def test_open_requires_nonempty_reason(self):
        with self.assertRaises(WriteSessionError):
            open_write_session(CFG, opened_by_operator_id=5, opened_by_username="a", reason="   ")

    def test_close_active_session(self):
        result, audit = self._run(
            [None, ACTIVE_ROW, CLOSED_AT_ROW],
            close_write_session,
            CFG,
            closed_by_operator_id=5,
            closed_by_username="admin_alice",
        )
        self.assertEqual(result["active"], False)
        self.assertIsNotNone(result["closed_at"])
        audit.assert_called_once()
        self.assertEqual(audit.call_args[0][1], "WRITE_SESSION_CLOSED")

    def test_close_is_idempotent_when_nothing_active(self):
        result, audit = self._run([None, None], close_write_session, CFG, closed_by_operator_id=5, closed_by_username="a")
        self.assertEqual(result, {"active": False, "closed_at": None})
        audit.assert_not_called()


class WriteSessionRouterTests(unittest.TestCase):
    """Router / RBAC / error-code surface via TestClient."""

    def _app(self, write_enabled=True):
        return create_app(settings=ApiSettings(write_enabled=write_enabled))

    def _ctx(self, role="ADMIN"):
        return OperatorContext(operator_id=5, username="admin_alice", display_name="Admin Alice", role=role)

    def test_non_admin_cannot_open(self):
        app = self._app()
        client = TestClient(app)
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx(role="OPERATOR")):
            resp = client.post("/api/v1/write-session/open", json={"reason": "test"})
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_open(self):
        app = self._app()
        client = TestClient(app)
        cur = FakeCursor(fetchone_queue=[None, None, INSERTED_ROW])
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx()):
            with patch("app.write_session.get_db_connection", return_value=fake_ctx_conn(cur)):
                with patch("app.write_session.log_sync_event"):
                    resp = client.post("/api/v1/write-session/open", json={"reason": "Enrollment session"})
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["active"])
        self.assertEqual(body["session_id"], 2)

    def test_open_blocked_when_infra_master_gate_closed(self):
        """Layer 1 (API_WRITE_ENABLED=false) unconditionally overrides Layer 2
        — even ADMIN cannot open a runtime session when writes are off."""
        app = self._app(write_enabled=False)
        client = TestClient(app)
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx()):
            resp = client.post("/api/v1/write-session/open", json={"reason": "test"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "WRITE_DISABLED")

    def test_concurrent_open_second_caller_gets_already_active(self):
        app = self._app()
        client = TestClient(app)
        cur = FakeCursor(fetchone_queue=[None, ACTIVE_ROW])
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx()):
            with patch("app.write_session.get_db_connection", return_value=fake_ctx_conn(cur)):
                with patch("app.write_session.log_sync_event"):
                    resp = client.post("/api/v1/write-session/open", json={"reason": "second caller"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"]["code"], "WRITE_SESSION_ALREADY_ACTIVE")

    def test_get_status_any_authenticated_role(self):
        app = self._app()
        client = TestClient(app)
        cur = FakeCursor(fetchone_queue=[None, None])
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx(role="VIEWER")):
            with patch("app.write_session.get_db_connection", return_value=fake_ctx_conn(cur)):
                resp = client.get("/api/v1/write-session")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["active"], False)

    def test_domain_write_blocked_when_no_session_open(self):
        """require_write_session must block a domain-mutating route even when
        Layer 1 (API_WRITE_ENABLED) is on, if no runtime session is active."""
        app = self._app(write_enabled=True)
        client = TestClient(app)
        cur = FakeCursor(fetchone_queue=[None, None])
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx(role="ADMIN")):
            with patch("app.write_session.get_db_connection", return_value=fake_ctx_conn(cur)):
                resp = client.post(
                    "/api/v1/enrollments/reserve",
                    json={"employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                          "device_id": 1, "operator": "admin_alice"},
                )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "WRITE_SESSION_REQUIRED")

    def test_domain_write_allowed_when_session_open(self):
        app = self._app(write_enabled=True)
        client = TestClient(app)
        cur = FakeCursor(fetchone_queue=[None, ACTIVE_ROW])
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx(role="ADMIN")):
            with patch("app.write_session.get_db_connection", return_value=fake_ctx_conn(cur)):
                with patch(
                    "app.api.routers.enrollments.reserve_next_device_user_id",
                    return_value={
                        "enrollment_id": 9, "reserved_device_user_id": "1002",
                        "status": "RESERVED", "reserved_at": NOW,
                        "employee_id": "039c4486-b30f-4ce1-b780-783cd268858d", "device_id": 1,
                    },
                ):
                    resp = client.post(
                        "/api/v1/enrollments/reserve",
                        json={"employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                              "device_id": 1, "operator": "admin_alice"},
                    )
        self.assertEqual(resp.status_code, 201)

    def test_domain_write_expired_session_reports_expired_not_required(self):
        app = self._app(write_enabled=True)
        client = TestClient(app)
        cur = FakeCursor(fetchone_queue=[EXPIRED_REAP_ROW, None])
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx(role="ADMIN")):
            with patch("app.write_session.get_db_connection", return_value=fake_ctx_conn(cur)):
                with patch("app.write_session.log_sync_event"):
                    resp = client.post(
                        "/api/v1/enrollments/reserve",
                        json={"employee_id": "039c4486-b30f-4ce1-b780-783cd268858d",
                              "device_id": 1, "operator": "admin_alice"},
                    )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "WRITE_SESSION_EXPIRED")

    def test_close_does_not_require_infra_master_gate(self):
        """Closing is a de-escalation action — must work even if Layer 1 is
        already off, so an ADMIN can always narrow permissions."""
        app = self._app(write_enabled=False)
        client = TestClient(app)
        cur = FakeCursor(fetchone_queue=[None, ACTIVE_ROW, CLOSED_AT_ROW])
        with patch("app.api.dependencies._load_token_context", return_value=self._ctx()):
            with patch("app.write_session.get_db_connection", return_value=fake_ctx_conn(cur)):
                with patch("app.write_session.log_sync_event"):
                    resp = client.post("/api/v1/write-session/close")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["active"])


if __name__ == "__main__":
    unittest.main()
