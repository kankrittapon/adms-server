"""
F1 API contract tests (ADMS-Frontend-F1-API-001).

Covers every endpoint family: health, dashboard, humans, attendance, devices,
device-users, mappings, enrollments, ranks — plus pagination, filtering, 404,
invalid UUID, error model, CORS, and the interim write-guard (OFF by default).

DB access is mocked at the app.api.repository boundary (same convention as
tests/test_enrollment.py / tests/test_mapping_creation.py). Canonical
enrollment/mapping modules are mocked at the router import boundary.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.settings import ApiSettings

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)

PILOT_EMPLOYEE_ID = "039c4486-b30f-4ce1-b780-783cd268858d"

HUMAN_ROW = {
    "employee_id": PILOT_EMPLOYEE_ID,
    "personnel_id": "1001",
    "display_name": "กฤตพล หมาดเส็น",
    "rank": "พ.จ.ต.",
    "rank_metadata": {
        "rank_th_original": "พ.จ.ต.",
        "rank_th_full": "พันจ่าตรี",
        "rank_th_abbreviation": "พ.จ.ต.",
        "rank_en": "Chief Petty Officer 3rd Class",
        "rank_en_abbreviation": "CPO3",
        "rank_category": "NCO",
        "acting": "false",
    },
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

DEVICE_ROW = {
    "device_id": 1,
    "serial_number": "3392113170057",
    "device_name": "SONIC ZEM560 #1",
    "device_ip": "192.168.1.201",
    "platform": "ZEM560_TFT",
    "firmware_version": "Ver 6.60 Aug 26 2011",
    "active": True,
    "first_seen_at": NOW,
    "last_seen_at": NOW,
    "created_at": NOW,
    "updated_at": NOW,
}

DEVICE_USER_ROW = {
    "device_user_pk": 7,
    "device_id": 1,
    "device_user_id": "1001",
    "device_uid": 1,
    "device_display_name": "cpo3 Krittapon M",
    "privilege": 0,
    "active": True,
    "first_seen_at": NOW,
    "last_seen_at": NOW,
    "roster_last_seen_at": NOW,
    "inactive_at": None,
    "created_at": NOW,
    "updated_at": NOW,
}

ATTENDANCE_ROW = {
    "id": 12,
    "user_id": "1001",
    "device_ip": "192.168.1.201",
    "scan_time": datetime(2026, 8, 12, 8, 47, 37, tzinfo=timezone.utc),
    "punch_type": "",
    "status": "ON_TIME",
    "device_id": 1,
    "device_user_pk": 7,
    "employee_id": PILOT_EMPLOYEE_ID,
    "created_at": NOW,
}

ATTENDANCE_DETAIL_ROW = dict(ATTENDANCE_ROW, device_name="SONIC ZEM560 #1",
                             device_user_id="1001", employee_name="กฤตพล หมาดเส็น")

MAPPING_ROW = {
    "mapping_id": 1,
    "employee_id": PILOT_EMPLOYEE_ID,
    "device_user_pk": 7,
    "mapping_status": "VERIFIED",
    "mapping_source": "CONTROLLED_SCAN",
    "verified_by": "owner-krittaphol",
    "verification_method": "CONTROLLED_SCAN",
    "verification_note": "Pilot evidence note",
    "valid_from": datetime(2026, 8, 12, 8, 47, 37, tzinfo=timezone.utc),
    "valid_to": None,
    "verified_at": NOW,
    "created_at": NOW,
    "updated_at": NOW,
    "employee_name": "กฤตพล หมาดเส็น",
    "device_user_id": "1001",
}

ENROLLMENT_ROW = {
    "enrollment_id": 1,
    "employee_id": PILOT_EMPLOYEE_ID,
    "device_id": 1,
    "reserved_device_user_id": "1001",
    "status": "RESERVED",
    "reserved_by": "owner-krittaphol",
    "reserved_at": NOW,
    "terminal_created_at": None,
    "device_uid": None,
    "fingerprint_confirmed_at": None,
    "controlled_scan_window_until": None,
    "controlled_scan_time": None,
    "confirmed_by": None,
    "confirmed_at": None,
    "notes": None,
    "created_at": NOW,
    "updated_at": NOW,
    "employee_name": "กฤตพล หมาดเส็น",
    "device_name": "SONIC ZEM560 #1",
}


def page(items, total=None, limit=50, offset=0):
    return {"items": items, "total": total if total is not None else len(items),
            "limit": limit, "offset": offset}


class ApiTestBase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(settings=ApiSettings(write_enabled=False))
        self.client = TestClient(self.app)

    def make_write_client(self):
        app = create_app(settings=ApiSettings(write_enabled=True))
        return TestClient(app)


class TestHealth(ApiTestBase):
    def test_healthz(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    @patch("app.api.repository.check_database", return_value=True)
    @patch("app.api.repository.check_mqtt", return_value="HEALTHY")
    def test_health_healthy(self, mock_mqtt, mock_db):
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "healthy")
        self.assertEqual(body["database"], "HEALTHY")
        self.assertIn("timestamp", body)

    @patch("app.api.repository.check_database", return_value=False)
    def test_health_db_down_degraded(self, mock_db):
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "degraded")
        self.assertEqual(resp.json()["database"], "UNREACHABLE")


class TestDashboard(ApiTestBase):
    @patch(
        "app.api.repository.dashboard_summary",
        return_value={
            "humans_total": 120,
            "humans_production_eligible": 84,
            "humans_excluded": 36,
            "devices_total": 1,
            "devices_active": 1,
            "device_users_total": 3,
            "device_users_active": 1,
            "device_users_unmapped": 0,
            "attendance_total": 12,
            "attendance_today": 2,
            "attendance_unattributed": 7,
            "mappings_total": 1,
            "mappings_verified_active": 1,
            "enrollments_by_status": {"RESERVED": 1},
        },
    )
    def test_dashboard_summary(self, mock_dash):
        resp = self.client.get("/api/v1/dashboard/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["humans_total"], 120)
        self.assertEqual(body["mappings_verified_active"], 1)
        self.assertIn("enrollments_by_status", body)


class TestHumans(ApiTestBase):
    def test_list_humans_pagination_and_filters(self):
        def fake_list(cfg, limit, offset, production_scope=None, search=None, category=None):
            return page([HUMAN_ROW], limit=limit, offset=offset)

        with patch("app.api.repository.list_humans", side_effect=fake_list) as mock_list:
            resp = self.client.get(
                "/api/v1/humans?limit=10&offset=5&production_scope=true&search=กฤตพล"
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["limit"], 10)
            self.assertEqual(body["offset"], 5)
            self.assertEqual(body["total"], 1)
            self.assertEqual(body["items"][0]["employee_id"], PILOT_EMPLOYEE_ID)
            self.assertEqual(body["items"][0]["rank_metadata"]["rank_en_abbreviation"], "CPO3")
            # filters forwarded to the repository
            call = mock_list.call_args
            self.assertEqual(call.kwargs["production_scope"], True)
            self.assertEqual(call.kwargs["search"], "กฤตพล")

    @patch("app.api.repository.list_humans", return_value=page([]))
    def test_list_humans_invalid_limit_rejected(self, mock_list):
        resp = self.client.get("/api/v1/humans?limit=0")
        self.assertEqual(resp.status_code, 422)

    @patch("app.api.repository.get_human", return_value=HUMAN_ROW)
    def test_get_human(self, mock_get):
        resp = self.client.get(f"/api/v1/humans/{PILOT_EMPLOYEE_ID}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["display_name"], "กฤตพล หมาดเส็น")

    @patch("app.api.repository.get_human", return_value=None)
    def test_get_human_404(self, mock_get):
        resp = self.client.get(f"/api/v1/humans/{PILOT_EMPLOYEE_ID}")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"]["code"], "NOT_FOUND")

    def test_get_human_invalid_uuid_422(self):
        resp = self.client.get("/api/v1/humans/not-a-uuid")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"]["code"], "VALIDATION_ERROR")


class TestAttendance(ApiTestBase):
    @patch("app.api.repository.list_attendance", return_value=page([ATTENDANCE_ROW]))
    def test_list_attendance_filters(self, mock_list):
        resp = self.client.get(
            "/api/v1/attendance?status=ON_TIME&employee_id=%s" % PILOT_EMPLOYEE_ID
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["items"][0]["status"], "ON_TIME")
        self.assertNotIn("raw_payload", body["items"][0])

    @patch("app.api.repository.list_attendance")
    def test_list_attendance_invalid_status_422(self, mock_list):
        resp = self.client.get("/api/v1/attendance?status=BOGUS")
        self.assertEqual(resp.status_code, 422)

    @patch("app.api.repository.list_attendance", return_value=page([]))
    def test_list_attendance_invalid_datetime_422(self, mock_list):
        resp = self.client.get("/api/v1/attendance?date_from=notadate")
        self.assertEqual(resp.status_code, 422)

    @patch("app.api.repository.get_attendance", return_value=ATTENDANCE_DETAIL_ROW)
    def test_get_attendance_detail_joins(self, mock_get):
        resp = self.client.get("/api/v1/attendance/12")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["employee_name"], "กฤตพล หมาดเส็น")
        self.assertNotIn("raw_payload", body)

    @patch("app.api.repository.get_attendance", return_value=None)
    def test_get_attendance_404(self, mock_get):
        resp = self.client.get("/api/v1/attendance/99999")
        self.assertEqual(resp.status_code, 404)

    @patch(
        "app.api.repository.get_attendance_raw_payload",
        return_value={"id": 12, "raw_payload": {"uid": 1}},
    )
    def test_raw_payload_explicit_endpoint(self, mock_get):
        resp = self.client.get("/api/v1/attendance/12/raw-payload")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["raw_payload"], {"uid": 1})


class TestDevices(ApiTestBase):
    @patch("app.api.repository.list_devices", return_value=page([DEVICE_ROW]))
    def test_list_devices(self, mock_list):
        resp = self.client.get("/api/v1/devices")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["items"][0]["device_id"], 1)

    @patch("app.api.repository.get_device", return_value=DEVICE_ROW)
    def test_get_device(self, mock_get):
        resp = self.client.get("/api/v1/devices/1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["serial_number"], "3392113170057")

    @patch("app.api.repository.get_device", return_value=None)
    def test_get_device_404(self, mock_get):
        resp = self.client.get("/api/v1/devices/99")
        self.assertEqual(resp.status_code, 404)


class TestDeviceUsers(ApiTestBase):
    @patch("app.api.repository.list_device_users", return_value=page([DEVICE_USER_ROW]))
    def test_list_device_users_filters(self, mock_list):
        resp = self.client.get("/api/v1/device-users?device_id=1&active=true")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["items"][0]["device_user_id"], "1001")
        # No biometric fields may ever appear.
        self.assertNotIn("fingerprint", str(body["items"][0]).lower())

    @patch("app.api.repository.get_device_user", return_value=DEVICE_USER_ROW)
    def test_get_device_user(self, mock_get):
        resp = self.client.get("/api/v1/device-users/7")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["device_user_pk"], 7)


class TestMappings(ApiTestBase):
    @patch("app.api.repository.list_mappings", return_value=page([MAPPING_ROW]))
    def test_list_mappings_filters(self, mock_list):
        resp = self.client.get("/api/v1/mappings?mapping_status=VERIFIED")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["items"][0]["mapping_status"], "VERIFIED")
        self.assertTrue(
            body["items"][0]["valid_from"].startswith("2026-08-12T08:47:37")
        )
        self.assertIsNone(body["items"][0]["valid_to"])

    @patch("app.api.repository.get_mapping", return_value=MAPPING_ROW)
    def test_get_mapping(self, mock_get):
        resp = self.client.get("/api/v1/mappings/1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["mapping_id"], 1)


class TestEnrollments(ApiTestBase):
    @patch("app.api.repository.list_enrollments", return_value=page([ENROLLMENT_ROW]))
    def test_list_enrollments_filters(self, mock_list):
        resp = self.client.get("/api/v1/enrollments?status=RESERVED")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["items"][0]["status"], "RESERVED")

    @patch("app.api.repository.get_enrollment_row", return_value=ENROLLMENT_ROW)
    def test_get_enrollment(self, mock_get):
        resp = self.client.get("/api/v1/enrollments/1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reserved_device_user_id"], "1001")


class TestRanks(ApiTestBase):
    def test_ranks_from_canonical_catalog(self):
        resp = self.client.get("/api/v1/reference/ranks")
        self.assertEqual(resp.status_code, 200)
        ranks = {r["rank_th_abbreviation"]: r for r in resp.json()}
        self.assertEqual(ranks["พ.จ.ต."]["rank_en"], "Chief Petty Officer 3rd Class")
        self.assertEqual(ranks["พ.จ.ต."]["rank_en_abbreviation"], "CPO3")
        self.assertEqual(ranks["น.อ."]["rank_en_abbreviation"], "Capt")
        self.assertEqual(ranks["พลฯ"]["rank_category"], "ENLISTED")


class TestWriteGuard(ApiTestBase):
    """Interim write safety: all write routes reject when API_WRITE_ENABLED=false."""

    WRITE_PATHS = [
        ("/api/v1/enrollments/reserve", {"employee_id": PILOT_EMPLOYEE_ID,
                                         "device_id": 1, "operator": "tester"}),
        ("/api/v1/enrollments/1/create-terminal-account",
         {"display_name": "Test Name", "operator": "tester"}),
        ("/api/v1/enrollments/1/start-fingerprint-enrollment",
         {"operator": "tester"}),
        ("/api/v1/enrollments/1/confirm-fingerprint", {"operator": "tester"}),
        ("/api/v1/enrollments/1/start-controlled-scan", {"operator": "tester"}),
        ("/api/v1/enrollments/1/confirm-controlled-scan",
         {"operator": "tester", "scan_time": "2026-08-13T08:00:00+00:00"}),
        ("/api/v1/enrollments/1/mark-ready-for-mapping", {"operator": "tester"}),
        ("/api/v1/enrollments/1/cancel", {"operator": "tester", "notes": "test"}),
        ("/api/v1/mappings", {
            "employee_id": PILOT_EMPLOYEE_ID, "device_user_pk": 7,
            "enrollment_id": 1, "controlled_attendance_id": 12,
            "verified_by": "tester", "verification_note": "test",
        }),
    ]

    def test_all_write_routes_reject_when_disabled(self):
        for path, payload in self.WRITE_PATHS:
            with self.subTest(path=path):
                resp = self.client.post(path, json=payload)
                self.assertEqual(resp.status_code, 403)
                self.assertEqual(resp.json()["error"]["code"], "WRITE_DISABLED")

    @patch("app.api.routers.enrollments.reserve_next_device_user_id",
           return_value={"enrollment_id": 9, "reserved_device_user_id": "1002",
                         "status": "RESERVED"})
    def test_reserve_works_when_enabled(self, mock_reserve):
        client = self.make_write_client()
        resp = client.post(
            "/api/v1/enrollments/reserve",
            json={"employee_id": PILOT_EMPLOYEE_ID, "device_id": 1, "operator": "tester"},
        )
        self.assertEqual(resp.status_code, 201)
        mock_reserve.assert_called_once()

    @patch("app.api.routers.enrollments.start_fingerprint_enrollment")
    def test_transition_works_when_enabled(self, mock_transition):
        mock_transition.return_value = {"enrollment_id": 1, "status": "FINGERPRINT_ENROLLMENT_PENDING"}
        client = self.make_write_client()
        resp = client.post(
            "/api/v1/enrollments/1/start-fingerprint-enrollment",
            json={"operator": "tester"},
        )
        self.assertEqual(resp.status_code, 200)
        mock_transition.assert_called_once()

    def test_create_terminal_account_never_through_api(self):
        client = self.make_write_client()
        resp = client.post(
            "/api/v1/enrollments/1/create-terminal-account",
            json={"display_name": "Test Name", "operator": "tester"},
        )
        self.assertEqual(resp.status_code, 501)
        self.assertEqual(resp.json()["error"]["code"], "NOT_IMPLEMENTED")

    @patch("app.api.routers.mappings.create_verified_mapping")
    def test_mapping_works_when_enabled(self, mock_mapping):
        mock_mapping.return_value = {
            "mapping_id": 2, "employee_id": PILOT_EMPLOYEE_ID,
            "device_user_pk": 7, "mapping_status": "VERIFIED",
            "verification_method": "CONTROLLED_SCAN",
            "valid_from": datetime(2026, 8, 13, 8, 0, 0, tzinfo=timezone.utc),
            "valid_to": None,
            "verified_at": datetime(2026, 8, 13, 9, 0, 0, tzinfo=timezone.utc),
        }
        client = self.make_write_client()
        resp = client.post(
            "/api/v1/mappings",
            json={
                "employee_id": PILOT_EMPLOYEE_ID, "device_user_pk": 7,
                "enrollment_id": 1, "controlled_attendance_id": 12,
                "verified_by": "tester", "verification_note": "test",
            },
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["mapping_status"], "VERIFIED")
        mock_mapping.assert_called_once()


class TestCors(ApiTestBase):
    def test_allowed_origin(self):
        resp = self.client.options(
            "/api/v1/humans",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"),
                         "http://localhost:5173")

    def test_disallowed_origin_no_cors_header(self):
        resp = self.client.options(
            "/api/v1/humans",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertIsNone(resp.headers.get("access-control-allow-origin"))

    def test_wildcard_never_with_credentials(self):
        app = create_app(settings=ApiSettings(write_enabled=False, cors_origins=("http://localhost:5173",)))
        client = TestClient(app)
        resp = client.options(
            "/api/v1/humans",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(resp.headers.get("access-control-allow-origin"),
                         "http://localhost:5173")
        self.assertNotEqual(resp.headers.get("access-control-allow-origin"), "*")


class TestErrorModel(ApiTestBase):
    def test_error_envelope_shape(self):
        # human does not exist -> repository returns None -> 404 envelope
        with patch("app.api.repository.get_human", return_value=None):
            resp = self.client.get("/api/v1/humans/00000000-0000-0000-0000-000000000000")
            self.assertEqual(resp.status_code, 404)
            body = resp.json()
            self.assertIn("error", body)
            self.assertIn("code", body["error"])
            self.assertIn("message", body["error"])

    def test_validation_error_envelope(self):
        resp = self.client.get("/api/v1/attendance?status=BAD")
        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")

    def test_no_stack_trace_leak(self):
        app = create_app(settings=ApiSettings(write_enabled=False))
        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.api.repository.list_humans", side_effect=RuntimeError("secret detail")):
            resp = client.get("/api/v1/humans")
            self.assertEqual(resp.status_code, 500)
            self.assertNotIn("secret detail", resp.text)
            self.assertEqual(resp.json()["error"]["code"], "INTERNAL_ERROR")


if __name__ == "__main__":
    unittest.main()
