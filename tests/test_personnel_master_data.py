"""
Personnel Master Data — create/edit/CSV export/import.

PromptID: ADMS-Personnel-MasterData-024

Production data-quality finding (Phase 16, read-only audit): 0 of 120
existing production Human rows have personnel_id populated. CSV import
matching is keyed ONLY on personnel_id (the schema's own UNIQUE
constraint) — never on display_name — so existing legacy rows cannot be
CSV-matched until an ADMIN assigns them a personnel_id via Edit first.
This is a disclosed limitation, not a defect: it is the direct, correct
consequence of refusing to invent name-based identity matching.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.config import Config
from app.personnel import (
    PersonnelDuplicateError,
    PersonnelError,
    create_human,
    update_human,
)
from app.personnel_csv import (
    PersonnelCsvError,
    classify_csv_rows,
    commit_csv_rows,
    export_humans_csv,
)


class FakeCursor:
    """Supports .description (derived from dict-row keys, in column order)
    for the RETURNING-clause pattern used throughout personnel.py, plus a
    fetchall_queue for personnel_csv.py's per-row lookup pattern."""

    def __init__(self, fetchone_queue=None, fetchall_queue=None):
        self.executed = []
        self._fetchone_queue = list(fetchone_queue or [])
        self._fetchall_queue = list(fetchall_queue) if fetchall_queue is not None else None
        self._last_description = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        if self._fetchone_queue:
            row = self._fetchone_queue.pop(0)
            if isinstance(row, dict):
                self._last_description = [(k,) for k in row.keys()]
                return tuple(row.values())
            return row
        return None

    def fetchall(self):
        if self._fetchall_queue is not None and self._fetchall_queue:
            return self._fetchall_queue.pop(0)
        return []

    @property
    def description(self):
        return self._last_description

    def sql(self):
        return [s for s, _ in self.executed]


def make_db(mock_conn_fn, cur):
    mock_conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__.return_value = cur
    cur_ctx.__exit__.return_value = None
    mock_conn.cursor.return_value = cur_ctx
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    mock_ctx.__exit__.return_value = None
    mock_conn_fn.return_value = mock_ctx
    return mock_conn


HUMAN_ROW = {
    "employee_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "personnel_id": "RTN-100",
    "display_name": "ทดสอบ ระบบ",
    "english_name": None,
    "rank": "พ.จ.อ.",
    "position": None,
    "branch": None,
    "category": None,
    "notes": None,
    "active": True,
    "production_scope": True,
    "source": "ADMS_MANUAL",
    "created_at": "2026-08-18T00:00:00Z",
    "updated_at": "2026-08-18T00:00:00Z",
}


class TestCreateHuman(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item1_admin_can_create(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[None, HUMAN_ROW])  # dup-check None, then INSERT RETURNING
        make_db(mock_conn_fn, cur)
        result = create_human(self.cfg, operator="admin", display_name="ทดสอบ ระบบ", rank="พ.จ.อ.", personnel_id="RTN-100")
        self.assertEqual(result["personnel_id"], "RTN-100")
        mock_log.assert_called_once()
        self.assertEqual(mock_log.call_args[0][1], "PERSONNEL_CREATED")

    def test_operator_required(self):
        with self.assertRaises(PersonnelError):
            create_human(self.cfg, operator="  ", display_name="X")

    def test_display_name_required(self):
        with self.assertRaises(PersonnelError):
            create_human(self.cfg, operator="admin", display_name="  ")

    def test_item9_invalid_rank_rejected(self):
        with self.assertRaises(PersonnelError):
            create_human(self.cfg, operator="admin", display_name="X", rank="NOT_A_REAL_RANK")

    @patch("app.personnel.get_db_connection")
    def test_item5_duplicate_personnel_id_rejected(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[("existing-uuid",)])  # dup-check finds a match
        make_db(mock_conn_fn, cur)
        with self.assertRaises(PersonnelDuplicateError):
            create_human(self.cfg, operator="admin", display_name="ทดสอบ", personnel_id="RTN-100")

    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item6_no_personnel_id_never_blocks_on_name_alone(self, mock_conn_fn, mock_log):
        """No duplicate check at all fires when personnel_id is omitted —
        Thai names may legitimately repeat."""
        cur = FakeCursor(fetchone_queue=[HUMAN_ROW])  # only the INSERT RETURNING call
        make_db(mock_conn_fn, cur)
        create_human(self.cfg, operator="admin", display_name="ทดสอบ ระบบ")
        dup_checks = [s for s in cur.sql() if "WHERE personnel_id" in s]
        self.assertEqual(len(dup_checks), 0)

    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_created_source_is_adms_manual_not_excel_import(self, mock_conn_fn, mock_log):
        cur = FakeCursor(fetchone_queue=[HUMAN_ROW])
        make_db(mock_conn_fn, cur)
        create_human(self.cfg, operator="admin", display_name="ทดสอบ ระบบ")
        insert_call = [p for s, p in cur.executed if "INSERT INTO human_employees" in s][0]
        self.assertIn("ADMS_MANUAL", insert_call)


class TestUpdateHuman(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item7_edit_english_name(self, mock_conn_fn, mock_log):
        before = dict(HUMAN_ROW, english_name=None)
        after = dict(HUMAN_ROW, english_name="Test System")
        cur = FakeCursor(fetchone_queue=[before, after])
        make_db(mock_conn_fn, cur)
        result = update_human(self.cfg, HUMAN_ROW["employee_id"], "admin", english_name="Test System")
        self.assertEqual(result["english_name"], "Test System")
        mock_log.assert_called_once()
        self.assertEqual(mock_log.call_args[0][1], "PERSONNEL_UPDATED")

    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_item8_edit_rank_with_canonical_value(self, mock_conn_fn, mock_log):
        before = dict(HUMAN_ROW, rank="จ.อ.")
        after = dict(HUMAN_ROW, rank="พ.จ.อ.")
        cur = FakeCursor(fetchone_queue=[before, after])
        make_db(mock_conn_fn, cur)
        result = update_human(self.cfg, HUMAN_ROW["employee_id"], "admin", rank="พ.จ.อ.")
        self.assertEqual(result["rank"], "พ.จ.อ.")

    def test_item9_invalid_rank_rejected_on_edit(self):
        with self.assertRaises(PersonnelError):
            update_human(self.cfg, HUMAN_ROW["employee_id"], "admin", rank="FAKE_RANK")

    def test_item10_employee_id_not_an_editable_field(self):
        """employee_id is a positional argument of update_human(), never a
        **fields kwarg the caller could smuggle in via the API's
        exclude_unset payload — the router's UpdateHumanRequest schema
        doesn't even define an employee_id field, and _EDITABLE_HUMAN_FIELDS
        excludes it structurally."""
        from app.personnel import _EDITABLE_HUMAN_FIELDS

        self.assertNotIn("employee_id", _EDITABLE_HUMAN_FIELDS)

    def test_unsafe_field_rejected(self):
        with self.assertRaises(PersonnelError):
            update_human(self.cfg, HUMAN_ROW["employee_id"], "admin", active=False)

    def test_no_fields_rejected(self):
        with self.assertRaises(PersonnelError):
            update_human(self.cfg, HUMAN_ROW["employee_id"], "admin")

    @patch("app.personnel.get_db_connection")
    def test_missing_human_returns_none(self, mock_conn_fn):
        cur = FakeCursor(fetchone_queue=[None])
        make_db(mock_conn_fn, cur)
        result = update_human(self.cfg, "nonexistent", "admin", english_name="X")
        self.assertIsNone(result)

    @patch("app.personnel.get_db_connection")
    def test_item5_edit_duplicate_personnel_id_rejected(self, mock_conn_fn):
        before = dict(HUMAN_ROW)
        cur = FakeCursor(fetchone_queue=[before, ("other-uuid",)])
        make_db(mock_conn_fn, cur)
        with self.assertRaises(PersonnelDuplicateError):
            update_human(self.cfg, HUMAN_ROW["employee_id"], "admin", personnel_id="RTN-999")

    @patch("app.personnel.log_sync_event")
    @patch("app.personnel.get_db_connection")
    def test_unchanged_value_emits_no_audit_event(self, mock_conn_fn, mock_log):
        same = dict(HUMAN_ROW)
        cur = FakeCursor(fetchone_queue=[same, same])
        make_db(mock_conn_fn, cur)
        update_human(self.cfg, HUMAN_ROW["employee_id"], "admin", english_name=None)
        mock_log.assert_not_called()

    def test_update_human_never_references_attendance_mapping_enrollment_tables(self):
        import inspect

        import app.personnel as personnel_module

        source = inspect.getsource(personnel_module.update_human) + inspect.getsource(personnel_module.create_human)
        for forbidden in ("attendance_logs", "employee_device_mappings", "device_user_enrollments", "device_users"):
            self.assertNotIn(forbidden, source)


class TestCsvExport(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    @patch("app.personnel_csv.get_db_connection")
    def test_item22_23_export_valid_csv_with_bom_and_thai(self, mock_conn_fn):
        cur = FakeCursor(fetchall_queue=[[("RTN-1", "พ.จ.อ.", "ทดสอบ ระบบ", "Test System", "อล.", "พันจ่า", True)]])
        make_db(mock_conn_fn, cur)
        csv_text = export_humans_csv(self.cfg)
        self.assertTrue(csv_text.startswith("﻿"))
        self.assertIn("ทดสอบ ระบบ", csv_text)
        self.assertIn("personnel_id", csv_text)

    @patch("app.personnel_csv.get_db_connection")
    def test_item24_active_inactive_filter(self, mock_conn_fn):
        cur = FakeCursor(fetchall_queue=[[]])
        make_db(mock_conn_fn, cur)
        export_humans_csv(self.cfg, active=True)
        where_clauses = [p for s, p in cur.executed if "WHERE active" in s]
        self.assertEqual(where_clauses[0], (True,))

    @patch("app.personnel_csv.get_db_connection")
    def test_item25_no_sensitive_internal_fields_by_default(self, mock_conn_fn):
        cur = FakeCursor(fetchall_queue=[[]])
        make_db(mock_conn_fn, cur)
        csv_text = export_humans_csv(self.cfg)
        for forbidden in ("employee_id", "password", "device_user_pk", "token"):
            self.assertNotIn(forbidden, csv_text)


class TestCsvImportPreview(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def _csv(self, rows_body):
        header = "personnel_id,rank,display_name,english_name,branch,category,active\n"
        return header + rows_body

    @patch("app.personnel_csv.get_db_connection")
    def test_item26_valid_new_row(self, mock_conn_fn):
        cur = FakeCursor(fetchall_queue=[])
        cur._fetchall_queue = None
        cur.fetchone = lambda: None  # no existing match -> NEW
        make_db(mock_conn_fn, cur)
        result = classify_csv_rows(self.cfg, self._csv("RTN-1,พ.จ.อ.,ทดสอบ ระบบ,Test System,อล.,พันจ่า,true\n"))
        self.assertEqual(result["summary"]["new"], 1)
        self.assertEqual(result["rows"][0]["classification"], "NEW")

    @patch("app.personnel_csv.get_db_connection")
    def test_item27_valid_update_row(self, mock_conn_fn):
        cur = FakeCursor()
        cur.fetchone = lambda: ("uuid-1", "OLD NAME", None, "จ.อ.", None, None, True)
        make_db(mock_conn_fn, cur)
        result = classify_csv_rows(self.cfg, self._csv("RTN-1,พ.จ.อ.,NEW NAME,Test System,อล.,พันจ่า,true\n"))
        self.assertEqual(result["summary"]["update"], 1)
        self.assertEqual(result["rows"][0]["classification"], "UPDATE")

    @patch("app.personnel_csv.get_db_connection")
    def test_item28_unchanged_row(self, mock_conn_fn):
        cur = FakeCursor()
        cur.fetchone = lambda: ("uuid-1", "ทดสอบ ระบบ", "Test System", "พ.จ.อ.", "อล.", "พันจ่า", True)
        make_db(mock_conn_fn, cur)
        result = classify_csv_rows(self.cfg, self._csv("RTN-1,พ.จ.อ.,ทดสอบ ระบบ,Test System,อล.,พันจ่า,true\n"))
        self.assertEqual(result["summary"]["unchanged"], 1)

    @patch("app.personnel_csv.get_db_connection")
    def test_item29_invalid_rank_reported_as_error(self, mock_conn_fn):
        cur = FakeCursor()
        make_db(mock_conn_fn, cur)
        result = classify_csv_rows(self.cfg, self._csv("RTN-1,NOT_A_RANK,ทดสอบ,,,, true\n"))
        self.assertEqual(result["summary"]["error"], 1)
        self.assertIn("ไม่พบยศนี้", result["rows"][0]["reason_th"])

    def test_item30_duplicate_personnel_id_within_file(self):
        body = "RTN-1,,คนที่หนึ่ง,,,,true\nRTN-1,,คนที่สอง,,,,true\n"
        with patch("app.personnel_csv.get_db_connection") as mock_conn_fn:
            cur = FakeCursor()
            cur.fetchone = lambda: None
            make_db(mock_conn_fn, cur)
            result = classify_csv_rows(self.cfg, self._csv(body))
        self.assertEqual(result["summary"]["error"], 1)
        self.assertIn("ซ้ำ", result["rows"][1]["reason_th"])

    def test_item31_malformed_csv_missing_required_column(self):
        with self.assertRaises(PersonnelCsvError):
            classify_csv_rows(self.cfg, "foo,bar\n1,2\n")

    @patch("app.personnel_csv.get_db_connection")
    def test_item32_missing_required_field(self, mock_conn_fn):
        cur = FakeCursor()
        make_db(mock_conn_fn, cur)
        result = classify_csv_rows(self.cfg, self._csv(",,,,,,\n"))
        self.assertEqual(result["summary"]["error"], 1)
        self.assertIn("ชื่อ-นามสกุล", result["rows"][0]["reason_th"])

    @patch("app.personnel_csv.get_db_connection")
    def test_item33_preview_never_writes(self, mock_conn_fn):
        cur = FakeCursor()
        cur.fetchone = lambda: None
        make_db(mock_conn_fn, cur)
        classify_csv_rows(self.cfg, self._csv("RTN-1,พ.จ.อ.,ทดสอบ,Test,,,true\n"))
        for sql, _ in cur.executed:
            self.assertNotIn("INSERT", sql.upper())
            self.assertNotIn("UPDATE", sql.upper())
            self.assertNotIn("DELETE", sql.upper())


class TestCsvImportCommit(unittest.TestCase):
    def setUp(self):
        self.cfg = Config.from_env()

    def _csv(self, rows_body):
        header = "personnel_id,rank,display_name,english_name,branch,category,active\n"
        return header + rows_body

    @patch("app.personnel_csv.log_sync_event")
    @patch("app.personnel_csv.get_db_connection")
    def test_item34_commit_creates_new(self, mock_conn_fn, mock_log):
        cur = FakeCursor()
        cur.fetchone = lambda: None
        make_db(mock_conn_fn, cur)
        result = commit_csv_rows(self.cfg, self._csv("RTN-1,พ.จ.อ.,ทดสอบ,Test,,,true\n"), operator="admin")
        self.assertEqual(result["created"], 1)
        insert_calls = [s for s in cur.sql() if "INSERT INTO human_employees" in s]
        self.assertEqual(len(insert_calls), 1)

    @patch("app.personnel_csv.log_sync_event")
    @patch("app.personnel_csv.get_db_connection")
    def test_item35_commit_updates_existing(self, mock_conn_fn, mock_log):
        cur = FakeCursor()
        cur.fetchone = lambda: ("uuid-1", "OLD", None, None, None, None, True)
        make_db(mock_conn_fn, cur)
        result = commit_csv_rows(self.cfg, self._csv("RTN-1,,NEW,,,,true\n"), operator="admin")
        self.assertEqual(result["updated"], 1)

    @patch("app.personnel_csv.log_sync_event")
    @patch("app.personnel_csv.get_db_connection")
    def test_item37_no_auto_deactivation_for_missing_rows(self, mock_conn_fn, mock_log):
        """Import never touches any row whose personnel_id isn't in the
        file — no bulk/blanket UPDATE statement exists at all."""
        cur = FakeCursor()
        cur.fetchone = lambda: None
        make_db(mock_conn_fn, cur)
        commit_csv_rows(self.cfg, self._csv("RTN-1,,ทดสอบ,,,,true\n"), operator="admin")
        for sql, _ in cur.executed:
            self.assertNotIn("SET active = false", sql)

    @patch("app.personnel_csv.log_sync_event")
    @patch("app.personnel_csv.get_db_connection")
    def test_item38_39_no_terminal_or_enrollment_created(self, mock_conn_fn, mock_log):
        import inspect

        import app.personnel_csv as csv_module

        source = inspect.getsource(csv_module.commit_csv_rows)
        for forbidden in ("device_users", "device_user_enrollments", "employee_device_mappings", "reserve_next_device_user_id"):
            self.assertNotIn(forbidden, source)

    @patch("app.personnel_csv.log_sync_event")
    @patch("app.personnel_csv.get_db_connection")
    def test_item41_audit_import_summary(self, mock_conn_fn, mock_log):
        cur = FakeCursor()
        cur.fetchone = lambda: None
        make_db(mock_conn_fn, cur)
        commit_csv_rows(self.cfg, self._csv("RTN-1,,ทดสอบ,,,,true\n"), operator="admin")
        mock_log.assert_called_once()
        self.assertEqual(mock_log.call_args[0][1], "PERSONNEL_CSV_IMPORT")
        # No raw CSV content in the audit message.
        self.assertNotIn("ทดสอบ", mock_log.call_args[0][2])

    @patch("app.personnel_csv.log_sync_event")
    @patch("app.personnel_csv.get_db_connection")
    def test_item36_second_identical_import_is_idempotent(self, mock_conn_fn, mock_log):
        """Simulates re-running the same file after the first commit —
        the row now matches exactly, so it must classify UNCHANGED, not
        create a duplicate."""
        cur = FakeCursor()
        cur.fetchone = lambda: ("uuid-1", "ทดสอบ", None, "พ.จ.อ.", None, None, True)
        make_db(mock_conn_fn, cur)
        result = commit_csv_rows(self.cfg, self._csv("RTN-1,พ.จ.อ.,ทดสอบ,,,,true\n"), operator="admin")
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["unchanged"], 1)


class TestPersonnelMasterDataRBAC(unittest.TestCase):
    """Items 2, 3, 4, 42, 43: router-level RBAC/write-gate matrix, using
    the same TestClient convention as tests/test_api_auth.py."""

    def _client_with(self, role, write_enabled=True, bypass_write_session=True):
        from fastapi.testclient import TestClient

        from app.api.dependencies import OperatorContext, require_write_session
        from app.api.main import create_app
        from app.api.settings import ApiSettings

        app = create_app(settings=ApiSettings(write_enabled=write_enabled))
        if bypass_write_session:
            app.dependency_overrides[require_write_session] = lambda: None
        client = TestClient(app)
        ctx = OperatorContext(1, "u", "U", role)
        p = patch("app.api.dependencies._load_token_context", return_value=ctx)
        return client, p

    def test_item2_non_admin_cannot_create_human(self):
        for role in ("VIEWER", "ENROLLMENT_OPERATOR", "OPERATOR"):
            with self.subTest(role=role):
                client, p = self._client_with(role)
                with p:
                    resp = client.post("/api/v1/humans", json={"display_name": "ทดสอบ"})
                self.assertEqual(resp.status_code, 403)

    def test_item1_admin_can_create_human(self):
        client, p = self._client_with("ADMIN")
        with p, patch("app.api.routers.humans.create_human", return_value=dict(HUMAN_ROW)), patch(
            "app.api.repository.get_human", return_value=dict(HUMAN_ROW)
        ):
            resp = client.post("/api/v1/humans", json={"display_name": "ทดสอบ ระบบ"})
        self.assertEqual(resp.status_code, 201)

    def test_item3_write_session_required_for_create(self):
        client, p = self._client_with("ADMIN", bypass_write_session=False)
        with p, patch("app.write_session.is_write_session_active", return_value=(False, False)):
            resp = client.post("/api/v1/humans", json={"display_name": "ทดสอบ"})
        self.assertEqual(resp.status_code, 403)

    def test_item4_write_disabled_blocks_create(self):
        client, p = self._client_with("ADMIN", write_enabled=False)
        with p:
            resp = client.post("/api/v1/humans", json={"display_name": "ทดสอบ"})
        self.assertEqual(resp.status_code, 403)

    def test_item5_duplicate_personnel_id_returns_409_not_500(self):
        from app.personnel import PersonnelDuplicateError

        client, p = self._client_with("ADMIN")
        with p, patch(
            "app.api.routers.humans.create_human",
            side_effect=PersonnelDuplicateError("a Human with personnel_id RTN-1 already exists"),
        ):
            resp = client.post("/api/v1/humans", json={"display_name": "ทดสอบ", "personnel_id": "RTN-1"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"]["code"], "PERSONNEL_DUPLICATE")

    def test_item42_non_admin_cannot_commit_csv_import(self):
        for role in ("VIEWER", "ENROLLMENT_OPERATOR", "OPERATOR"):
            with self.subTest(role=role):
                client, p = self._client_with(role)
                with p:
                    resp = client.post(
                        "/api/v1/humans/import/commit",
                        files={"file": ("p.csv", b"display_name\nfoo\n", "text/csv")},
                    )
                self.assertEqual(resp.status_code, 403)

    def test_item43_closed_write_session_blocks_commit(self):
        client, p = self._client_with("ADMIN", bypass_write_session=False)
        with p, patch("app.write_session.is_write_session_active", return_value=(False, False)):
            resp = client.post(
                "/api/v1/humans/import/commit",
                files={"file": ("p.csv", b"display_name\nfoo\n", "text/csv")},
            )
        self.assertEqual(resp.status_code, 403)

    def test_preview_does_not_require_write_session(self):
        """Phase 12: CSV preview is read-only — must succeed even with no
        write session bypass configured, i.e. it must not depend on
        require_write_session at all."""
        client, p = self._client_with("ADMIN", bypass_write_session=False)
        with p, patch("app.api.routers.humans.classify_csv_rows", return_value={"summary": {"new": 0, "update": 0, "unchanged": 0, "error": 0}, "rows": []}):
            resp = client.post(
                "/api/v1/humans/import/preview",
                files={"file": ("p.csv", b"display_name\nfoo\n", "text/csv")},
            )
        self.assertEqual(resp.status_code, 200)

    def test_preview_still_requires_admin(self):
        client, p = self._client_with("OPERATOR")
        with p:
            resp = client.post(
                "/api/v1/humans/import/preview",
                files={"file": ("p.csv", b"display_name\nfoo\n", "text/csv")},
            )
        self.assertEqual(resp.status_code, 403)

    def test_export_available_to_general_read_roles(self):
        for role in ("VIEWER", "OPERATOR", "ADMIN"):
            with self.subTest(role=role):
                client, p = self._client_with(role)
                with p, patch("app.api.routers.humans.export_humans_csv", return_value="personnel_id\n"):
                    resp = client.get("/api/v1/humans/export.csv")
                self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
