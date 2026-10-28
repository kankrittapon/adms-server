import unittest
from datetime import date
from unittest.mock import patch

from app import absence_import

PEOPLE = {"1001": {"employee_id": "1001", "name": "ร.ท. สมหญิง รักชาติ"}}
NAMES = {"สมหญิง รักชาติ": [PEOPLE["1001"]]}
TYPES = {"SICK": "SICK", "ลาป่วย": "SICK", "OFFICIAL_DUTY": "OFFICIAL_DUTY", "ไปราชการ": "OFFICIAL_DUTY"}
LOOKUPS = (PEOPLE, NAMES, TYPES, {"OFFICIAL_DUTY"})
HEADER = "รหัสกำลังพล,ชื่อ,ประเภท,วันเริ่ม,วันสิ้นสุด,เลขที่คำสั่ง,สถานที่,หมายเหตุ\n"


class TestParseDate(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(absence_import.parse_date("10/11/2569"), date(2026, 11, 10))
        self.assertEqual(absence_import.parse_date("10/11/2026"), date(2026, 11, 10))
        self.assertEqual(absence_import.parse_date("2026-11-10"), date(2026, 11, 10))
        with self.assertRaises(ValueError):
            absence_import.parse_date("พรุ่งนี้")


@patch("app.absence_import._lookups", return_value=LOOKUPS)
class TestValidate(unittest.TestCase):
    def test_template_examples_are_skipped(self, _):
        text = absence_import.template_bytes().decode("utf-8-sig")
        self.assertEqual(absence_import.validate(None, text)["rows"], [])

    def test_valid_row_by_id_and_by_name(self, _):
        r = absence_import.validate(None, HEADER + "1001,,ลาป่วย,10/11/2569,,,,\n,สมหญิง รักชาติ,SICK,11/11/2569,12/11/2569,,,\n")
        self.assertEqual((r["valid"], r["invalid"]), (2, 0))
        self.assertEqual(r["rows"][0]["end_date"], date(2026, 11, 10))

    def test_errors(self, _):
        r = absence_import.validate(None, HEADER + "9999,,ลาเที่ยว,12/11/2569,10/11/2569,,,\n1001,,ไปราชการ,10/11/2569,,,,\n")
        self.assertEqual(r["invalid"], 2)
        self.assertEqual(len(r["rows"][0]["errors"]), 3)
        self.assertIn("เลขที่คำสั่ง", r["rows"][1]["errors"][0])

    @patch("app.absence_import.absences.create_absence")
    def test_commit_is_all_or_nothing(self, create, _):
        r = absence_import.commit(None, "op", HEADER + "1001,,ลาป่วย,10/11/2569,,,,\n9999,,ลาป่วย,10/11/2569,,,,\n")
        self.assertEqual(r["created"], 0)
        create.assert_not_called()
        r = absence_import.commit(None, "op", HEADER + "1001,,ลาป่วย,10/11/2569,,,,\n")
        self.assertEqual(r["created"], 1)


if __name__ == "__main__":
    unittest.main()
