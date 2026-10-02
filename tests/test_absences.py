"""Absence records (record-only leave) and the daily roster classification."""

import unittest
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import absences
from app.absences import classify_person
from tests.test_api import ApiTestBase

BKK = ZoneInfo("Asia/Bangkok")
TEN = time(10, 0)


def _c(**kw):
    base = dict(
        absence_counts_as=None,
        scan_exempt=False,
        first_scan_local=None,
        is_workday=True,
        late_after=TEN,
        day_in_progress_before_cutoff=False,
    )
    base.update(kw)
    return classify_person(**base)


class TestClassifyPerson(unittest.TestCase):
    def test_scan_at_or_before_10_is_present(self):
        self.assertEqual(_c(first_scan_local=datetime(2026, 10, 2, 10, 0, tzinfo=BKK)), "PRESENT")

    def test_scan_after_10_is_late(self):
        self.assertEqual(_c(first_scan_local=datetime(2026, 10, 2, 10, 1, tzinfo=BKK)), "LATE")

    def test_recorded_leave_wins_even_without_scan(self):
        self.assertEqual(_c(absence_counts_as="LEAVE"), "LEAVE")
        self.assertEqual(_c(absence_counts_as="DUTY"), "DUTY")

    def test_exempt_never_absent(self):
        self.assertEqual(_c(scan_exempt=True), "EXEMPT")

    def test_no_scan_before_cutoff_is_not_yet(self):
        self.assertEqual(_c(day_in_progress_before_cutoff=True), "NOT_YET")

    def test_no_scan_after_cutoff_is_absent(self):
        self.assertEqual(_c(), "ABSENT")

    def test_non_workday_without_scan_is_off(self):
        self.assertEqual(_c(is_workday=False), "OFF")


class TestCreateValidation(unittest.TestCase):
    def test_end_before_start_rejected_without_db(self):
        with self.assertRaises(absences.AbsenceError):
            absences.create_absence(
                None, "op", "00000000-0000-0000-0000-000000000000", "SICK", date(2026, 10, 5), date(2026, 10, 4)
            )


RECORD = {
    "absence_id": 1, "employee_id": "e1", "employee_name": "ทดสอบ", "rank": None, "branch": "สส.",
    "type_code": "SICK", "type_name_th": "ลาป่วย", "type_name_en": "Sick leave", "counts_as": "LEAVE",
    "start_date": date(2026, 10, 5), "end_date": date(2026, 10, 6), "days": 2, "order_ref": None,
    "destination": None, "note": None, "status": "RECORDED", "recorded_by": "tester",
    "recorded_at": datetime(2026, 10, 2, tzinfo=BKK), "cancelled_by": None, "cancelled_at": None,
    "cancel_reason": None,
}
BODY = {"employee_id": "e1", "type_code": "SICK", "start_date": "2026-10-05", "end_date": "2026-10-06"}


class TestAbsenceApi(ApiTestBase):
    def test_viewer_cannot_record(self):
        resp = self.client.post("/api/v1/absences", json=BODY)
        self.assertEqual(resp.status_code, 403)

    def test_operator_records(self):
        client = self.make_write_client("OPERATOR")
        with patch("app.absences.create_absence", return_value=RECORD) as m:
            resp = client.post("/api/v1/absences", json=BODY)
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(m.call_args.args[1], "tester")

    def test_enrollment_operator_cannot_record(self):
        client = self.make_write_client("ENROLLMENT_OPERATOR")
        resp = client.post("/api/v1/absences", json=BODY)
        self.assertEqual(resp.status_code, 403)

    def test_overlap_is_409(self):
        client = self.make_write_client("ADMIN")
        with patch("app.absences.create_absence", side_effect=absences.AbsenceOverlapError("x")):
            resp = client.post("/api/v1/absences", json=BODY)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"]["code"], "ABSENCE_OVERLAP")

    def test_daily_route_not_swallowed_by_attendance_id(self):
        roster = {"date": date(2026, 10, 2), "is_workday": True, "holiday_name": None, "late_after": "10:00",
                  "total": 0, "totals": {}, "by_branch": [], "people": []}
        with patch("app.absences.daily_roster", return_value=roster) as m:
            resp = self.client.get("/api/v1/attendance/daily?date=2026-10-02")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(m.call_args.args[1], date(2026, 10, 2))


if __name__ == "__main__":
    unittest.main()
