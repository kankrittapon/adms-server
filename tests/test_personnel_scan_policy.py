"""Personnel scan policy (migration 015) and workflow filters.

Scan-exempt personnel (commander office, finance) need a reason; clearing
the exemption clears the reason. scan_status filters and the summary must
reject unknown values and use the shared SQL fragments.
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import repository
from app.config import Config
from app.personnel import PersonnelError, update_human
from tests.test_api import ApiTestBase
from tests.test_personnel_master_data import HUMAN_ROW, FakeCursor, make_db


class TestScanExemptUpdate(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def test_exempt_requires_reason(self):
        with self.assertRaises(PersonnelError):
            update_human(self.cfg, HUMAN_ROW["employee_id"], "admin", scan_exempt=True)
        with self.assertRaises(PersonnelError):
            update_human(self.cfg, HUMAN_ROW["employee_id"], "admin", scan_exempt=True, scan_exempt_reason="  ")

    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_exempt_with_reason_is_written(self, mock_conn_fn, mock_log):
        before = dict(HUMAN_ROW, scan_exempt=False, scan_exempt_reason=None)
        after = dict(HUMAN_ROW, scan_exempt=True, scan_exempt_reason="สำนักงาน ผบ.")
        cur = FakeCursor(fetchone_queue=[before, after])
        make_db(mock_conn_fn, cur)
        result = update_human(
            self.cfg, HUMAN_ROW["employee_id"], "admin", scan_exempt=True, scan_exempt_reason=" สำนักงาน ผบ. "
        )
        self.assertTrue(result["scan_exempt"])
        update_sql = [s for s in cur.sql() if s.startswith("UPDATE human_employees")][0]
        self.assertIn("scan_exempt = %s", update_sql)
        self.assertIn("scan_exempt_reason = %s", update_sql)

    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_clearing_exempt_clears_reason(self, mock_conn_fn, mock_log):
        before = dict(HUMAN_ROW, scan_exempt=True, scan_exempt_reason="การเงิน")
        after = dict(HUMAN_ROW, scan_exempt=False, scan_exempt_reason=None)
        cur = FakeCursor(fetchone_queue=[before, after])
        make_db(mock_conn_fn, cur)
        update_human(self.cfg, HUMAN_ROW["employee_id"], "admin", scan_exempt=False)
        params = [p for s, p in cur.executed if s.startswith("UPDATE human_employees")][0]
        self.assertIn(None, params)


class TestScanStatusFilters(unittest.TestCase):
    def test_needs_enrollment_excludes_exempt_and_inactive(self):
        sql = repository._SCAN_STATUS_SQL["needs_enrollment"]
        self.assertIn("NOT scan_exempt", sql)
        self.assertIn("active AND", sql)



class TestScanStatusApi(ApiTestBase):
    def test_api_rejects_unknown_scan_status(self):
        resp = self.client.get("/api/v1/humans?scan_status=bogus")
        self.assertEqual(resp.status_code, 422)

    def test_scan_status_forwarded(self):
        with patch("app.api.repository.list_humans", return_value={"items": [], "total": 0, "limit": 25, "offset": 0}) as m:
            resp = self.client.get("/api/v1/humans?scan_status=needs_enrollment")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(m.call_args.kwargs["scan_status"], "needs_enrollment")

    def test_summary(self):
        with patch(
            "app.api.repository.personnel_summary",
            return_value={"active": 3, "inactive": 1, "scan_exempt": 1, "needs_enrollment": 1, "left_with_terminal_account": 0},
        ):
            resp = self.client.get("/api/v1/humans/summary")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["needs_enrollment"], 1)


if __name__ == "__main__":
    unittest.main()


class TestBulkScanExempt(ApiTestBase):
    IDS = ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]

    def test_admin_bulk_exempt(self):
        client = self.make_write_client("ADMIN")
        with patch("app.api.routers.humans.bulk_set_scan_exempt", return_value=2) as m:
            resp = client.post(
                "/api/v1/humans/scan-exempt",
                json={"employee_ids": self.IDS, "scan_exempt": True, "scan_exempt_reason": "การเงิน"},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["changed"], 2)
        self.assertEqual(m.call_args.args[2], self.IDS)

    def test_operator_cannot_bulk_exempt(self):
        client = self.make_write_client("OPERATOR")
        resp = client.post("/api/v1/humans/scan-exempt", json={"employee_ids": self.IDS, "scan_exempt": False})
        self.assertEqual(resp.status_code, 403)

    def test_bulk_exempt_requires_reason(self):
        from app.personnel import bulk_set_scan_exempt

        with self.assertRaises(PersonnelError):
            bulk_set_scan_exempt(Config.from_env(), "admin", self.IDS, True, " ")
