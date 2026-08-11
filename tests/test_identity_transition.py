import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.config import Config
from app.db import (
    get_or_create_device,
    ensure_device_user,
    resolve_verified_employee_mapping,
    save_attendance_log,
    save_attendance_batch
)

class MockAttendanceRecord:
    def __init__(self, uid, user_id, timestamp, status=1, punch=0):
        self.uid = uid
        self.user_id = user_id
        self.timestamp = timestamp
        self.status = status
        self.punch = punch

class TestIdentityTransition(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def test_get_or_create_device(self):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [1]
        device_id = get_or_create_device(mock_cur, serial_number="3392113170057", device_ip="192.168.1.201")
        self.assertEqual(device_id, 1)
        mock_cur.execute.assert_called()

    def test_ensure_device_user(self):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [10]
        dpk = ensure_device_user(mock_cur, device_id=1, device_user_id="1")
        self.assertEqual(dpk, 10)
        mock_cur.execute.assert_called()
        # Verify zero queries targeting legacy employees table
        for call_args in mock_cur.execute.call_args_list:
            query = call_args[0][0].lower()
            self.assertNotIn("employees", query)

    def test_resolve_verified_employee_mapping_unmapped(self):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        emp_id = resolve_verified_employee_mapping(mock_cur, device_user_pk=10)
        self.assertIsNone(emp_id)

    def test_resolve_verified_employee_mapping_verified(self):
        mock_cur = MagicMock()
        uuid_str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
        mock_cur.fetchone.return_value = [uuid_str]
        emp_id = resolve_verified_employee_mapping(mock_cur, device_user_pk=10)
        self.assertEqual(emp_id, uuid_str)

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_save_attendance_log_unmapped(self, mock_map, mock_user, mock_dev, mock_conn):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        rec = MockAttendanceRecord(1, "1", datetime.now(timezone.utc))
        res = save_attendance_log(self.cfg, rec)

        self.assertTrue(res)
        mock_dev.assert_called_once()
        mock_user.assert_called_once()
        mock_map.assert_called_once()

    @patch("app.db.get_db_connection")
    @patch("app.db.get_or_create_device", return_value=1)
    @patch("app.db.ensure_device_user", return_value=10)
    @patch("app.db.resolve_verified_employee_mapping", return_value=None)
    def test_save_attendance_batch_unmapped(self, mock_map, mock_user, mock_dev, mock_conn):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [100]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        recs = [MockAttendanceRecord(i, str(i), datetime.now(timezone.utc)) for i in range(1, 4)]
        inserted, skipped = save_attendance_batch(self.cfg, recs)

        self.assertEqual(inserted, 3)
        self.assertEqual(skipped, 0)

if __name__ == "__main__":
    unittest.main()
