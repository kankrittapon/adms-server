"""
Auth hydration / role-flicker — structural checks.

PromptID: ADMS-UX-FinalPolish-021 Part A

CONFIRMED root cause (this session): Layout.tsx rendered role-dependent UI
directly off `me` without checking `loading`, and the role-badge ternary
had no explicit branch for "identity unknown" — `me === null` fell through
every `===` comparison straight to the VIEWER label. Separately, neither
Login.tsx nor Layout.tsx's logout() ever told AuthProvider to refetch
/auth/me after a client-side navigate() (which never remounts the
provider) — so the wrong/stale role could persist indefinitely until a
hard page refresh forced a remount, not just flicker for one frame.

No frontend test runner exists in this repo (same convention as
tests/test_terminal_management_ui.py) — these assert against source.
"""

import pathlib
import unittest

FRONTEND_ROOT = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"


def _read(rel: str) -> str:
    return (FRONTEND_ROOT / rel).read_text(encoding="utf-8")


class TestAuthHydration(unittest.TestCase):
    def setUp(self):
        self.auth_src = _read("auth.tsx")
        self.layout_src = _read("components/Layout.tsx")
        self.login_src = _read("pages/Login.tsx")

    def test_item1_initial_state_is_unknown_not_a_role(self):
        # me starts null and loading starts true — "unknown", not a role.
        self.assertIn('useState<MeResponse | null>(null)', self.auth_src)
        self.assertIn("useState(true)", self.auth_src)

    def test_item2_never_defaults_to_viewer_in_context(self):
        # The context/provider itself must never seed a VIEWER-shaped me.
        self.assertNotIn('role: "VIEWER"', self.auth_src)
        self.assertNotIn("role: 'VIEWER'", self.auth_src)

    def test_item2b_badge_has_explicit_loading_branch_before_viewer_fallthrough(self):
        # The old bug: a ternary chain with no unknown-branch collapses
        # `me === null` into the final (VIEWER) else. There must now be an
        # explicit `loading` check ahead of any role comparison.
        badge_start = self.layout_src.index("roles.loadingAccount")
        role_admin_check = self.layout_src.index('me?.role === "ADMIN"', badge_start)
        self.assertLess(badge_start, role_admin_check)

    def test_item3_admin_branch_present(self):
        self.assertIn('me?.role === "ADMIN"\n                    ? t.roles.admin', self.layout_src)

    def test_item4_viewer_is_the_final_fallback_only_after_loading_and_error_checks(self):
        idx_loading = self.layout_src.index("t.roles.loadingAccount", self.layout_src.index("roles.loadingAccount"))
        idx_error = self.layout_src.index("t.roles.sessionErrorTitle")
        idx_viewer = self.layout_src.rindex("t.roles.viewer")
        self.assertLess(idx_loading, idx_error)
        self.assertLess(idx_error, idx_viewer)

    def test_item5_enrollment_operator_branch_present(self):
        self.assertIn('me?.role === "ENROLLMENT_OPERATOR"', self.layout_src)

    def test_item6_auth_me_failure_sets_error_flag_not_silent_downgrade(self):
        self.assertIn("setAuthError(true)", self.auth_src)
        self.assertIn("authError", self.auth_src)
        # The failure path must not synthesize any role — only null identity.
        catch_idx = self.auth_src.index(".catch(() => {")
        finally_idx = self.auth_src.index(".finally(", catch_idx)
        catch_body = self.auth_src[catch_idx:finally_idx]
        self.assertNotIn("role:", catch_body)

    def test_item7_admin_nav_gated_on_proven_admin_role_only(self):
        # ADMIN_NAV visibility keys off me?.role === "ADMIN" directly — since
        # me is null during loading, this is false-by-construction until
        # /auth/me actually resolves, so it can't flicker into view early.
        self.assertIn('me?.role === "ADMIN" && (', self.layout_src)

    def test_item8_destructive_admin_controls_hidden_while_role_unknown(self):
        terminal_mgmt_src = _read("pages/TerminalManagement.tsx")
        self.assertIn('isAdmin = me?.role === "ADMIN"', terminal_mgmt_src)

    def test_item9_login_triggers_deterministic_auth_refetch(self):
        # Without this, client-side navigate() after login never remounts
        # AuthProvider, so `me` from the previous session (or null) stays
        # stuck until a hard refresh — confirmed by direct user report.
        self.assertIn("reload()", self.login_src)
        setToken_idx = self.login_src.index("setToken(res.token)")
        reload_idx = self.login_src.index("reload()", setToken_idx)
        navigate_idx = self.login_src.index('navigate("/"', setToken_idx)
        self.assertLess(setToken_idx, reload_idx)
        self.assertLess(reload_idx, navigate_idx)

    def test_item10_logout_clears_identity_state(self):
        self.assertIn("clearToken()", self.layout_src)
        clear_idx = self.layout_src.index("clearToken()")
        reload_idx = self.layout_src.index("reload()", clear_idx)
        self.assertLess(clear_idx, reload_idx)

    def test_session_error_shows_relogin_action_not_silent_viewer(self):
        self.assertIn("authError &&", self.layout_src)
        self.assertIn("t.roles.reloginButton", self.layout_src)

    def test_no_raw_english_fallback_string_hardcoded_for_role(self):
        # Loading/error copy must come from i18n (TH default), not a
        # hardcoded English string that would bypass TH-first UX.
        self.assertNotIn('"Loading..."', self.layout_src)


if __name__ == "__main__":
    unittest.main()
