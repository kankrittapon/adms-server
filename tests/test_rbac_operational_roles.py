"""
RBAC role-capability matrix — ADMS-RBAC-OperationalRoles-023.

Verifies the actual `require_roles(...)` set used by each router/endpoint
directly from source (never guessed from role names), and exercises the
dependency function itself against every role. Complements
tests/test_write_session.py (which covers the endpoint-level open/close
TestClient behavior in detail) and the existing per-router test suites
(test_api.py, test_terminal_management.py, etc.) which already prove
ADMIN-only gating on mapping creation, Personnel lifecycle, fingerprint/
terminal delete, and operator management — this file's job is to prove
those gates were NOT accidentally loosened by this PromptID, and that the
Work Session gate is the one, deliberate exception that moved from
ADMIN-only to OPERATOR-or-ADMIN.

Core invariant under test throughout:

    allow_write = API_WRITE_ENABLED AND active_write_session AND role_permits_action

Granting OPERATOR the ability to open/close a Work Session (Layer 2 gate)
must never grant OPERATOR access to any ADMIN-only endpoint — each of
those retains its own independent require_roles(ROLES_ADMIN_ONLY).
"""

import inspect
import unittest

from fastapi import Request

from app.api.auth import (
    ROLES_ADMIN_ONLY,
    ROLES_ALL_AUTHENTICATED,
    ROLES_ENROLLMENT_MUTATE,
    ROLES_ENROLLMENT_READ,
    ROLES_GENERAL_READ,
    ROLES_OPERATOR_PLUS,
    VALID_ROLES,
)
from app.api.dependencies import OperatorContext, require_roles
from app.api.errors import ApiError

ALL_ROLES = ("VIEWER", "ENROLLMENT_OPERATOR", "OPERATOR", "ADMIN")


def _ctx(role: str) -> OperatorContext:
    return OperatorContext(operator_id=1, username="u", display_name="U", role=role)


def _allowed(role_set, role: str) -> bool:
    dep = require_roles(role_set)
    try:
        dep(request=None, ctx=_ctx(role))
        return True
    except ApiError as e:
        assert e.status_code == 403
        return False


class TestCanonicalRoleSets(unittest.TestCase):
    """Items 14-25: the canonical sets themselves encode the owner-approved
    policy — asserted directly, not re-derived per test."""

    def test_valid_roles_unchanged(self):
        self.assertEqual(VALID_ROLES, {"VIEWER", "ENROLLMENT_OPERATOR", "OPERATOR", "ADMIN"})

    def test_admin_only_is_exactly_admin(self):
        self.assertEqual(ROLES_ADMIN_ONLY, {"ADMIN"})

    def test_operator_plus_is_operator_and_admin_only(self):
        """The Work Session gate (Phase 3) and any future OPERATOR-tier
        capability must use this exact set — VIEWER/ENROLLMENT_OPERATOR
        must never be included."""
        self.assertEqual(ROLES_OPERATOR_PLUS, {"OPERATOR", "ADMIN"})
        self.assertNotIn("VIEWER", ROLES_OPERATOR_PLUS)
        self.assertNotIn("ENROLLMENT_OPERATOR", ROLES_OPERATOR_PLUS)

    def test_enrollment_mutate_excludes_viewer(self):
        self.assertEqual(ROLES_ENROLLMENT_MUTATE, {"ENROLLMENT_OPERATOR", "OPERATOR", "ADMIN"})
        self.assertNotIn("VIEWER", ROLES_ENROLLMENT_MUTATE)


class TestWorkSessionGateMatrix(unittest.TestCase):
    """Items 1-8: the require_roles(...) dependency itself, for every role,
    against the exact set app/api/routers/write_session.py now uses."""

    def test_matrix(self):
        expectations = {
            "VIEWER": False,
            "ENROLLMENT_OPERATOR": False,
            "OPERATOR": True,
            "ADMIN": True,
        }
        for role, expected in expectations.items():
            with self.subTest(role=role, action="open/close work session"):
                self.assertEqual(_allowed(ROLES_OPERATOR_PLUS, role), expected)

    def test_write_session_router_uses_operator_plus_not_admin_only(self):
        """Regression guard: proves the router file was actually changed,
        not just that the role set constant exists correctly in isolation."""
        import app.api.routers.write_session as ws

        source = inspect.getsource(ws)
        import_line = next(line for line in source.splitlines() if line.startswith("from app.api.auth import"))
        self.assertIn("ROLES_OPERATOR_PLUS", import_line)
        self.assertNotIn("ROLES_ADMIN_ONLY", import_line)
        self.assertNotIn("Depends(require_roles(ROLES_ADMIN_ONLY))", source)


class TestEnrollmentRoleCannotOpenOrCloseSession(unittest.TestCase):
    """Item: 'ENROLLMENT must NOT be able to unlock the write gate for
    itself' — the core critical requirement of this PromptID."""

    def test_enrollment_operator_excluded_from_operator_plus(self):
        self.assertFalse(_allowed(ROLES_OPERATOR_PLUS, "ENROLLMENT_OPERATOR"))

    def test_enrollment_operator_included_in_enrollment_mutate(self):
        """...but IS allowed to perform enrollment writes once a session is
        already open (gated separately by require_write_session)."""
        self.assertTrue(_allowed(ROLES_ENROLLMENT_MUTATE, "ENROLLMENT_OPERATOR"))


class TestOperatorCannotAccessAdminOnlyEndpoints(unittest.TestCase):
    """Items 14-17, 21: OPERATOR gains the Work Session gate but nothing
    else — every ADMIN-only endpoint's actual require_roles(...) call is
    read directly from source, not assumed."""

    def _admin_only_role_sets_in(self, module) -> list:
        source = inspect.getsource(module)
        return [line for line in source.splitlines() if "require_roles(ROLES_ADMIN_ONLY)" in line]

    def test_operators_router_is_entirely_admin_only(self):
        import app.api.routers.operators as operators_router

        calls = self._admin_only_role_sets_in(operators_router)
        self.assertGreater(len(calls), 0, "operator management must use ROLES_ADMIN_ONLY somewhere")
        self.assertFalse(_allowed(ROLES_ADMIN_ONLY, "OPERATOR"))
        self.assertFalse(_allowed(ROLES_ADMIN_ONLY, "ENROLLMENT_OPERATOR"))
        self.assertTrue(_allowed(ROLES_ADMIN_ONLY, "ADMIN"))

    def test_terminal_management_destructive_endpoints_remain_admin_only(self):
        import app.api.routers.terminal_management as tm

        source = inspect.getsource(tm)
        # Fingerprint delete / account delete / re-enroll — all destructive
        # actions must still require ROLES_ADMIN_ONLY.
        admin_only_count = source.count("Depends(require_roles(ROLES_ADMIN_ONLY))")
        self.assertGreaterEqual(admin_only_count, 3)
        self.assertFalse(_allowed(ROLES_ADMIN_ONLY, "OPERATOR"))

    def test_personnel_lifecycle_endpoints_remain_admin_only(self):
        import app.api.routers.humans as humans_router

        source = inspect.getsource(humans_router)
        # deactivate, reactivate, and english-name PATCH are all ADMIN-only.
        admin_only_count = source.count("Depends(require_roles(ROLES_ADMIN_ONLY))")
        self.assertGreaterEqual(admin_only_count, 3)
        self.assertFalse(_allowed(ROLES_ADMIN_ONLY, "OPERATOR"))

    def test_mapping_create_remains_admin_only(self):
        import app.api.routers.mappings as mappings_router

        source = inspect.getsource(mappings_router)
        self.assertIn("Depends(require_roles(ROLES_ADMIN_ONLY))", source)
        self.assertFalse(_allowed(ROLES_ADMIN_ONLY, "OPERATOR"))
        self.assertFalse(_allowed(ROLES_ADMIN_ONLY, "ENROLLMENT_OPERATOR"))


class TestViewerCannotWriteAnywhere(unittest.TestCase):
    def test_viewer_excluded_from_every_mutate_set(self):
        for role_set in (ROLES_ADMIN_ONLY, ROLES_OPERATOR_PLUS, ROLES_ENROLLMENT_MUTATE):
            with self.subTest(role_set=role_set):
                self.assertFalse(_allowed(role_set, "VIEWER"))

    def test_viewer_can_still_read(self):
        for role_set in (ROLES_GENERAL_READ, ROLES_ENROLLMENT_READ, ROLES_ALL_AUTHENTICATED):
            with self.subTest(role_set=role_set):
                self.assertTrue(_allowed(role_set, "VIEWER"))


class TestAdminCanDoEverything(unittest.TestCase):
    def test_admin_in_every_role_set(self):
        for role_set in (
            ROLES_ADMIN_ONLY,
            ROLES_OPERATOR_PLUS,
            ROLES_ENROLLMENT_MUTATE,
            ROLES_ENROLLMENT_READ,
            ROLES_GENERAL_READ,
            ROLES_ALL_AUTHENTICATED,
        ):
            with self.subTest(role_set=role_set):
                self.assertTrue(_allowed(role_set, "ADMIN"))


class TestFrontendCapabilityMatrixMatchesBackend(unittest.TestCase):
    """Item 34: the frontend's canonical capability helpers (auth.tsx) must
    encode the SAME policy as the backend role sets — read from source on
    both sides, not merely trusted to agree."""

    def setUp(self):
        import pathlib

        self.auth_tsx = (
            pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "auth.tsx"
        ).read_text(encoding="utf-8")

    def test_can_open_work_session_mirrors_operator_plus(self):
        self.assertIn("canOpenWorkSession", self.auth_tsx)
        idx = self.auth_tsx.index("canOpenWorkSession: isOperatorOrAdmin")
        self.assertGreater(idx, 0)

    def test_admin_only_capabilities_all_gated_on_isadmin(self):
        for cap in ("canVerifyIdentity", "canManagePersonnel", "canManageTerminal", "canManageOperators"):
            with self.subTest(capability=cap):
                self.assertIn(f"{cap}: isAdmin", self.auth_tsx)

    def test_can_enroll_mirrors_write_capable_roles(self):
        self.assertIn("canEnroll: canWrite", self.auth_tsx)
        self.assertIn('"ENROLLMENT_OPERATOR"', self.auth_tsx)

    def test_write_session_control_uses_capability_not_raw_role(self):
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "components"
            / "WriteSessionControl.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("canOpenWorkSession", src)
        # The control panel must not independently re-derive admin-ness.
        self.assertNotIn('role === "ADMIN"', src)


class TestRoleDescriptionCopyExists(unittest.TestCase):
    """Item 35: TH/EN role description copy, updated per Phase 6."""

    def setUp(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n"
        self.th = (root / "th.ts").read_text(encoding="utf-8")
        self.en = (root / "en.ts").read_text(encoding="utf-8")

    def test_all_four_role_descriptions_present_th(self):
        for key in ("viewerDesc", "enrollmentOperatorDesc", "operatorDesc", "adminDesc"):
            self.assertIn(key, self.th)

    def test_all_four_role_descriptions_present_en(self):
        for key in ("viewerDesc", "enrollmentOperatorDesc", "operatorDesc", "adminDesc"):
            self.assertIn(key, self.en)

    def test_operator_desc_mentions_work_session_capability_th(self):
        idx = self.th.index("operatorDesc:")
        line = self.th[idx : self.th.index("\n", idx)]
        self.assertIn("เปิด", line)
        self.assertIn("ปิด", line)

    def test_enrollment_desc_explicitly_denies_session_control_th(self):
        idx = self.th.index("enrollmentOperatorDesc:")
        line = self.th[idx : self.th.index("\n", idx)]
        self.assertIn("ไม่สามารถเปิดช่วงปฏิบัติงาน", line)


if __name__ == "__main__":
    unittest.main()
