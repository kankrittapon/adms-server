"""Absence records (record-only leave) and the daily roster classification."""

import unittest
import unittest.mock
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


class TestMonthlyReport(unittest.TestCase):
    def test_csv_has_bom_codes_and_totals(self):
        report = {
            "month": "2026-10", "late_after": "10:00", "workdays": 1,
            "days": [{"date": date(2026, 10, 1), "is_workday": True, "holiday_name": None},
                     {"date": date(2026, 10, 3), "is_workday": False, "holiday_name": None}],
            "people": [{"employee_id": "e1", "display_name": "ทดสอบ", "rank": "จ.อ.", "branch": "สส.",
                        "scan_exempt": False, "days": ["LATE", "OFF"],
                        "counts": {s: 0 for s in absences.ROSTER_STATUSES} | {"LATE": 1, "OFF": 1}}],
            "by_branch": [],
        }
        text = absences.monthly_report_csv(report)
        self.assertTrue(text.startswith("﻿"))
        row = text.splitlines()[-1].split(",")
        self.assertEqual(row[:4], ["1", "จ.อ.", "ทดสอบ", "สส."])
        self.assertEqual(row[4:6], ["ส", "-"])
        self.assertEqual(row[6:], ["0", "1", "0", "0", "0"])


class TestMonthlyApi(ApiTestBase):
    def test_invalid_month_rejected(self):
        resp = self.client.get("/api/v1/attendance/monthly?month=2026-13")
        self.assertEqual(resp.status_code, 422)

    def test_month_parsed(self):
        report = {"month": "2026-09", "late_after": "10:00", "workdays": 0, "days": [], "people": [], "by_branch": []}
        with patch("app.absences.monthly_report", return_value=report) as m:
            resp = self.client.get("/api/v1/attendance/monthly?month=2026-09")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(m.call_args.args[1:], (2026, 9))


class TestScanWindow(unittest.TestCase):
    def test_policy_defaults(self):
        t = absences.policy_times({})
        self.assertEqual((t["start"], t["end"], t["late_after"]), (time(6, 30), time(11, 0), TEN))

    def test_window_includes_the_closing_minute(self):
        start, end = absences._window_bounds(date(2026, 10, 5), BKK, absences.policy_times({}))
        self.assertEqual(start, datetime(2026, 10, 5, 6, 30, tzinfo=BKK))
        self.assertEqual(end, datetime(2026, 10, 5, 11, 1, tzinfo=BKK))


class TestWorkSessionSwitch(unittest.TestCase):
    def _request(self, required):
        from types import SimpleNamespace

        from app.api.settings import ApiSettings

        settings = ApiSettings(write_enabled=True, work_session_required=required)
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))

    def test_not_required_skips_the_session_check(self):
        from app.api.dependencies import require_write_session

        with patch("app.write_session.is_write_session_active", side_effect=AssertionError("must not be consulted")):
            self.assertIsNone(require_write_session(self._request(False)))

    def test_required_still_enforced(self):
        from app.api.dependencies import require_write_session
        from app.api.errors import ApiError

        with patch("app.write_session.is_write_session_active", return_value=(False, False)), patch(
            "app.api.dependencies.get_cfg", return_value=None
        ):
            with self.assertRaises(ApiError):
                require_write_session(self._request(True))


class TestReadinessAndTelegram(unittest.TestCase):
    def test_not_enrolled_never_absent_or_late(self):
        self.assertEqual(_c(tracked=False), "NOT_ENROLLED")
        self.assertEqual(_c(tracked=False, first_scan_local=datetime(2026, 10, 5, 10, 30, tzinfo=BKK)), "NOT_ENROLLED")
        self.assertEqual(_c(tracked=False, is_workday=False), "OFF")

    def test_leave_and_exempt_still_win_before_enrollment(self):
        self.assertEqual(_c(tracked=False, absence_counts_as="DUTY"), "DUTY")
        self.assertEqual(_c(tracked=False, scan_exempt=True), "EXEMPT")

    def _roster(self, people, workday=True):
        return {"date": date(2026, 10, 5), "is_workday": workday, "scan_window": "06:30–11:00", "people": people}

    def test_message_lists_only_absent_grouped_by_section(self):
        from app.telegram_report import build_message

        people = [
            {"status": "ABSENT", "branch": "สส.", "rank": "จ.อ.", "display_name": "ก"},
            {"status": "LEAVE", "branch": "สส.", "rank": "จ.อ.", "display_name": "ข"},
            {"status": "NOT_ENROLLED", "branch": "สส.", "rank": None, "display_name": "ค"},
            {"status": "ABSENT", "branch": "อล.", "rank": None, "display_name": "ง"},
        ]
        text = build_message(self._roster(people))
        self.assertIn("ขาด 2 คน", text)
        self.assertIn("• จ.อ. ก", text)
        self.assertIn("• ง", text)
        self.assertNotIn("ข\n", text + "\n")
        self.assertNotIn("• ค", text)
        self.assertLess(text.index("สส."), text.index("อล."))

    def test_no_message_on_non_working_day(self):
        from app.telegram_report import build_message

        self.assertIsNone(build_message(self._roster([], workday=False)))

    def test_send_requires_configuration(self):
        from app.telegram_report import TelegramNotConfigured, send_text

        with self.assertRaises(TelegramNotConfigured):
            send_text("x", token="", chat_id="")


class TestGoLive(unittest.TestCase):
    def _roster(self, live):
        return {"date": date(2026, 10, 6), "is_workday": True, "scan_window": "06:30–11:00", "live": live,
                "people": [{"status": "ABSENT", "branch": "สส.", "rank": None, "display_name": "ก"}]}

    def test_timer_silent_before_go_live(self):
        from app import telegram_report

        with patch("app.telegram_report.daily_roster", return_value=self._roster(False)), patch(
            "app.telegram_report.send_text"
        ) as send:
            result = telegram_report.send_daily_report(None, date(2026, 10, 6))
        self.assertFalse(result["sent"])
        send.assert_not_called()

    def test_admin_test_send_before_go_live_is_marked_trial(self):
        from app import telegram_report

        with patch("app.telegram_report.daily_roster", return_value=self._roster(False)), patch(
            "app.telegram_report.send_text"
        ) as send, patch("app.telegram_report.log_sync_event"):
            telegram_report.send_daily_report(None, date(2026, 10, 6), force=True)
        self.assertTrue(send.call_args.args[0].startswith("🧪 [ทดลอง"))

    def test_sends_when_live(self):
        from app import telegram_report

        with patch("app.telegram_report.daily_roster", return_value=self._roster(True)), patch(
            "app.telegram_report.send_text"
        ) as send, patch("app.telegram_report.log_sync_event"):
            self.assertTrue(telegram_report.send_daily_report(None, date(2026, 10, 6))["sent"])
        self.assertNotIn("ทดลอง", send.call_args.args[0])

    def test_invalid_mode_rejected(self):
        with self.assertRaises(absences.AbsenceError):
            absences.set_tracking_mode(None, "admin", "maybe")


class TestGoLiveLatch(unittest.TestCase):
    def _run(self, policy, missing):
        cur = unittest.mock.MagicMock()
        conn = unittest.mock.MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cur
        with patch("app.absences.get_db_connection", return_value=conn), patch(
            "app.absences.load_policy", return_value=policy
        ), patch(
            "app.absences.readiness",
            return_value={"total": {"required": 10, "missing": missing, "enrolled": 10 - missing}},
        ), patch("app.absences.log_sync_event") as log:
            # Uses today: going live latches live_since = today, so a fixed
            # past date would read as "before go-live" once the calendar moves on.
            return absences.tracking_state(None, datetime.now(BKK).date()), cur, log

    def test_goes_live_and_latches_when_complete(self):
        state, cur, log = self._run({"tracking_mode": "auto"}, missing=0)
        self.assertTrue(state["live"])
        self.assertIn("live_since", cur.execute.call_args.args[1][0])
        log.assert_called_once()

    def test_stays_live_when_returnees_lower_readiness(self):
        state, cur, _ = self._run({"tracking_mode": "auto", "live_since": "2026-10-10"}, missing=3)
        self.assertTrue(state["live"])
        cur.execute.assert_not_called()

    def test_not_live_before_complete(self):
        state, _, _ = self._run({"tracking_mode": "auto"}, missing=3)
        self.assertFalse(state["live"])

    def test_off_wins_over_latch(self):
        state, _, _ = self._run({"tracking_mode": "off", "live_since": "2026-10-10"}, missing=0)
        self.assertFalse(state["live"])


class TestGoLiveDate(unittest.TestCase):
    def test_date_mode_requires_a_date(self):
        with self.assertRaises(absences.AbsenceError):
            absences.set_tracking_mode(None, "admin", "date")

    def _state(self, day):
        conn = unittest.mock.MagicMock()
        conn.__enter__.return_value = conn
        with patch("app.absences.get_db_connection", return_value=conn), patch(
            "app.absences.load_policy", return_value={"tracking_mode": "date", "counting_from": "2026-11-09"}
        ), patch("app.absences.readiness", return_value={"total": {"required": 84, "missing": 80}}):
            return absences.tracking_state(None, day)

    def test_live_from_the_date_regardless_of_readiness(self):
        self.assertFalse(self._state(date(2026, 11, 8))["live"])
        self.assertTrue(self._state(date(2026, 11, 9))["live"])
