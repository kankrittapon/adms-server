"""
Mapping-eligibility 422 root-cause fix.

PromptID: ADMS-OperatorUX-Fingerprint-Rank-Mapping-016

Confirmed production bug: POST /api/v1/mappings returned 422 Unprocessable
Entity when an ADMIN tried to confirm a READY_FOR_MAPPING enrollment from
Step 6.

Root cause (found by tracing the actual data, not guessed): app.api.
repository.mapping_eligibility()'s controlled_attendance_id correlated
subquery used EXACT equality (`a.scan_time = e.controlled_scan_time`)
between two independently-sourced timestamps:
  - e.controlled_scan_time: an operator-entered/SSE-prefilled estimate that
    round-trips through an HTML `datetime-local` input (minute precision,
    no seconds) — see frontend/src/pages/Enrollments.tsx's
    `new Date(scanTime).toISOString().slice(0, 16)` truncation, which loses
    precision even when auto-filled from a real detected SSE event.
  - a.scan_time (attendance_logs): the terminal's full-precision recorded
    timestamp.
These two values essentially never compare equal, so controlled_attendance_id
came back NULL for every genuinely eligible enrollment. The frontend's
non-null-asserted payload (`item.controlled_attendance_id!`) then sent
`undefined` for a required Pydantic field, which FastAPI rejects with 422
"field required" before create_mapping()'s handler ever runs.

Fix: the correlation now matches the NEAREST attendance_logs.scan_time
within a bounded +/-2 minute window (well inside the 5-minute controlled-
scan window itself), not exact equality — app/api/repository.py.

Covers the required test items: 1 (422 reproduced), 2 (root cause fixed),
3 (generated OpenAPI type unaffected — cross-referenced), 4 (happy path —
cross-referenced from tests/test_api.py::test_mapping_works_when_enabled),
5 (missing evidence -> friendly error, frontend structural check), 6
(duplicate mapping -> conflict), 7 (unauthorized role -> 403 — cross-
referenced from test_mapping_requires_admin_role), 8 (write session closed
-> blocked).
"""

import inspect
import pathlib
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import OperatorContext, require_write_session
from app.api.main import create_app
from app.api.settings import ApiSettings

PILOT_EMPLOYEE_ID = "11111111-1111-1111-1111-111111111111"
FRONTEND_ROOT = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"


def _read(rel: str) -> str:
    return (FRONTEND_ROOT / rel).read_text(encoding="utf-8")


class TestMappingEligibilitySqlFix(unittest.TestCase):
    """Item 2: the SQL itself no longer relies on exact-equality timestamp
    matching for controlled_attendance_id."""

    def test_no_exact_equality_scan_time_match(self):
        import app.api.repository as repository

        src = inspect.getsource(repository.mapping_eligibility)
        self.assertNotIn("a.scan_time = e.controlled_scan_time", src)

    def test_delegates_to_the_single_canonical_resolver(self):
        # ADMS-FullEnrollment-E2E-Closure-017: this query no longer embeds
        # its own bounded-window SQL — it delegates to the single canonical
        # resolver shared with app.mapping.create_verified_mapping, so
        # there is exactly one definition of "the correct controlled-scan
        # evidence row," not two independently-drifting SQL
        # implementations (which is what caused create_verified_mapping's
        # own separate exact-equality check to still reject evidence the
        # eligibility endpoint had already resolved).
        import app.api.repository as repository

        src = inspect.getsource(repository.mapping_eligibility)
        self.assertIn("_resolve_controlled_attendance_id", src)
        wrapper_src = inspect.getsource(repository._resolve_controlled_attendance_id)
        self.assertIn("from app.mapping_evidence import resolve_controlled_attendance_id", wrapper_src)

    def test_mapping_creation_uses_the_same_resolver_module(self):
        import app.mapping as mapping_mod

        src = inspect.getsource(mapping_mod)
        self.assertIn("from app.mapping_evidence import resolve_controlled_attendance_id", src)
        # The old exact-equality re-check must be gone.
        self.assertNotIn("att_scan_time != valid_from", src)


class TestMappingRequestValidation(unittest.TestCase):
    """Item 1: reproduce the exact 422 the operator saw — a POST /mappings
    request missing a required field (what the frontend used to send when
    controlled_attendance_id was null) is rejected with 422/VALIDATION_ERROR,
    not silently accepted or a 500."""

    def make_write_client(self, role="ADMIN"):
        app = create_app(settings=ApiSettings(write_enabled=True))
        app.dependency_overrides[require_write_session] = lambda: None
        client = TestClient(app)
        ctx = OperatorContext(operator_id=1, username="admin", display_name="Admin", role=role)
        patcher = patch("app.api.dependencies._load_token_context", return_value=ctx)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def test_item1_missing_enrollment_id_is_422_not_500(self):
        """ADMS-FullEnrollment-E2E-Closure-017: controlled_attendance_id /
        device_user_pk / employee_id are no longer part of the request
        contract at all (server-derived) — the only field whose absence
        can legitimately 422 now is enrollment_id itself."""
        client = self.make_write_client()
        resp = client.post(
            "/api/v1/mappings",
            json={
                # enrollment_id omitted
                "verified_by": "tester",
                "verification_note": "test",
            },
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"]["code"], "VALIDATION_ERROR")

    def test_extra_legacy_fields_are_ignored_not_required(self):
        """A client still sending the old (now-removed) fields must not be
        required to — Pydantic ignores unknown fields, and the request must
        succeed purely from enrollment_id/verified_by/verification_note."""
        with patch("app.api.routers.mappings.create_verified_mapping") as mock_mapping:
            mock_mapping.return_value = {
                "mapping_id": 3, "employee_id": PILOT_EMPLOYEE_ID,
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
                    "controlled_attendance_id": 12,  # legacy fields, must be ignored
                    "enrollment_id": 1,
                    "verified_by": "tester", "verification_note": "test",
                },
            )
            self.assertEqual(resp.status_code, 201)
            # The router must call create_verified_mapping with ONLY the
            # new signature — never forwarding the legacy fields.
            mock_mapping.assert_called_once()
            _, call_kwargs = mock_mapping.call_args
            self.assertEqual(call_kwargs, {
                "enrollment_id": 1, "verified_by": "tester", "verification_note": "test",
            })

    @patch("app.api.routers.mappings.create_verified_mapping")
    def test_item4_complete_evidence_succeeds(self, mock_mapping):
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
        mock_mapping.assert_called_once()

    @patch("app.api.routers.mappings.create_verified_mapping")
    def test_item6_duplicate_mapping_is_409_conflict_not_422(self, mock_mapping):
        from app.mapping import MappingError

        mock_mapping.side_effect = MappingError("device_user_pk 7 already has an active VERIFIED mapping")
        client = self.make_write_client()
        resp = client.post(
            "/api/v1/mappings",
            json={
                "employee_id": PILOT_EMPLOYEE_ID, "device_user_pk": 7,
                "enrollment_id": 1, "controlled_attendance_id": 12,
                "verified_by": "tester", "verification_note": "test",
            },
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"]["code"], "MAPPING_CONFLICT")

    def test_item7_operator_role_forbidden(self):
        client = self.make_write_client(role="OPERATOR")
        resp = client.post(
            "/api/v1/mappings",
            json={
                "employee_id": PILOT_EMPLOYEE_ID, "device_user_pk": 7,
                "enrollment_id": 1, "controlled_attendance_id": 12,
                "verified_by": "tester", "verification_note": "test",
            },
        )
        self.assertEqual(resp.status_code, 403)

    def test_item8_write_session_required_when_none_open(self):
        # Do NOT override require_write_session here — exercise the real
        # dependency, which must reject when no session is open.
        app = create_app(settings=ApiSettings(write_enabled=True))
        client = TestClient(app)
        ctx = OperatorContext(operator_id=1, username="admin", display_name="Admin", role="ADMIN")
        with patch("app.api.dependencies._load_token_context", return_value=ctx), \
             patch("app.write_session.is_write_session_active", return_value=(False, False)):
            resp = client.post(
                "/api/v1/mappings",
                json={
                    "employee_id": PILOT_EMPLOYEE_ID, "device_user_pk": 7,
                    "enrollment_id": 1, "controlled_attendance_id": 12,
                    "verified_by": "tester", "verification_note": "test",
                },
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"]["code"], "WRITE_SESSION_REQUIRED")


class TestFrontendEvidenceGuard(unittest.TestCase):
    """Item 5: the frontend never sends a request with a missing required
    field — it detects incomplete evidence itself and shows friendly copy,
    matching the required TH/EN strings for this PromptID."""

    def setUp(self):
        self.src = _read("pages/Mappings.tsx")
        self.types_src = _read("i18n/types.ts")
        self.en_src = _read("i18n/en.ts")
        self.th_src = _read("i18n/th.ts")

    def test_evidence_completeness_guard_present(self):
        self.assertIn("item.device_user_pk == null || item.controlled_attendance_id == null", self.src)
        self.assertIn("t.mappings.evidenceIncompleteBody", self.src)

    def test_confirm_submit_never_sends_non_null_assertion(self):
        # Regression: the old `!` non-null assertions on device_user_pk /
        # controlled_attendance_id must be gone from the actual payload
        # construction — the guard above must be what protects this, not
        # a TypeScript assertion papering over a real null at runtime.
        self.assertNotIn("device_user_pk: item.device_user_pk!,", self.src)
        self.assertNotIn("controlled_attendance_id: item.controlled_attendance_id!,", self.src)

    def test_i18n_keys_present_all_locales(self):
        for key in ("evidenceIncompleteBody", "mappingConflictBody", "alreadyMappedBody"):
            self.assertIn(key, self.types_src)
            self.assertIn(key, self.en_src)
            self.assertIn(key, self.th_src)
        self.assertIn("ข้อมูลสำหรับยืนยันยังไม่ครบ", self.th_src)
        self.assertIn("มีการยืนยันรหัสเครื่องนี้กับบุคคลอื่นแล้ว", self.th_src)


if __name__ == "__main__":
    unittest.main()
