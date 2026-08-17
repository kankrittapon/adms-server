"""
CORS preflight regression tests.

PromptID: ADMS-CORS-PATCH-Fix-011

Production bug: browser PATCH to /api/v1/humans/{human_id} (used by the
Personnel English-name edit feature) was blocked by the CORS preflight —
CORSMiddleware's allow_methods did not include "PATCH", so the browser's
OPTIONS preflight request for a PATCH call never received an
Access-Control-Allow-Methods response permitting it.

These tests exercise the actual CORSMiddleware configured in
app.api.main.create_app() (not a hand-built ASGI app), so a regression here
is caught the same way the browser would hit it: via a real OPTIONS
preflight request carrying Access-Control-Request-Method/-Headers.
"""

import unittest

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.settings import ApiSettings

PROD_WEB_ORIGIN = "http://192.168.1.248:8082"


class TestCorsPreflight(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            settings=ApiSettings(write_enabled=True, cors_origins=(PROD_WEB_ORIGIN,))
        )
        self.client = TestClient(self.app)

    def _preflight(self, method: str, path: str = "/api/v1/humans/1"):
        return self.client.options(
            path,
            headers={
                "Origin": PROD_WEB_ORIGIN,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    def test_patch_preflight_succeeds(self):
        """The exact production failure: OPTIONS preflight for a PATCH to
        /api/v1/humans/{id} must succeed and explicitly allow PATCH."""
        resp = self._preflight("PATCH")
        self.assertIn(resp.status_code, (200, 204))
        self.assertEqual(resp.headers.get("access-control-allow-origin"), PROD_WEB_ORIGIN)
        allowed_methods = resp.headers.get("access-control-allow-methods", "")
        self.assertIn("PATCH", allowed_methods)

    def test_patch_preflight_allows_authorization_and_content_type_headers(self):
        resp = self._preflight("PATCH")
        allowed_headers = resp.headers.get("access-control-allow-headers", "")
        # allow_headers=["*"] echoes back whatever was requested.
        self.assertIn("authorization", allowed_headers.lower())
        self.assertIn("content-type", allowed_headers.lower())

    def test_get_and_post_preflight_still_allowed(self):
        """Regression guard: fixing PATCH must not narrow the existing
        GET/POST allowance."""
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                resp = self._preflight(method)
                self.assertIn(resp.status_code, (200, 204))
                self.assertIn(method, resp.headers.get("access-control-allow-methods", ""))

    def test_disallowed_method_not_granted(self):
        """DELETE was never requested by this PromptID and must not be
        silently granted as a side effect of the PATCH fix."""
        resp = self._preflight("DELETE")
        allowed_methods = resp.headers.get("access-control-allow-methods", "")
        self.assertNotIn("DELETE", allowed_methods)

    def test_preflight_from_unlisted_origin_not_granted(self):
        """CORS origins must not be broadened as a side effect of this fix —
        an origin not in cors_origins gets no allow-origin header."""
        resp = self.client.options(
            "/api/v1/humans/1",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        self.assertNotEqual(resp.headers.get("access-control-allow-origin"), "http://evil.example.com")

    def test_actual_patch_request_carries_cors_headers(self):
        """Sanity check beyond the preflight itself: the real PATCH response
        (not just OPTIONS) also carries the allow-origin header, matching
        what the browser checks before exposing the response to JS."""
        resp = self.client.patch(
            "/api/v1/humans/nonexistent-id",
            json={"english_name": "Test"},
            headers={"Origin": PROD_WEB_ORIGIN, "Authorization": "Bearer invalid"},
        )
        self.assertEqual(resp.headers.get("access-control-allow-origin"), PROD_WEB_ORIGIN)


if __name__ == "__main__":
    unittest.main()
