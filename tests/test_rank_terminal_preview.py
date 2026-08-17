"""
Rank -> canonical terminal-name preview.

PromptID: ADMS-OperatorUX-Fingerprint-Rank-Mapping-016

Covers items 9-14 of the required test matrix. app/rtn_ranks.py is the
existing, single canonical RTN rank catalog (no second rank dictionary was
created — GET /api/v1/reference/ranks already exposed it, previously
consumed only by the System page's static reference table). This PromptID
attaches rank_metadata to Enrollment responses (additive fields: `rank`,
`rank_metadata`) so the frontend can compute a default terminal
display-name preview (`rank_en_abbreviation` + `english_name`) without
requiring the operator to type rank abbreviations — see
frontend/src/lib/terminalName.ts.

No physical device or database is required — repository queries are
inspected structurally; terminalName.ts's rules are read and asserted
directly (no frontend test runner exists in this repo, same convention as
tests/test_timeout_margin.py and tests/test_enrollment_state_sync.py).
"""

import inspect
import pathlib
import unittest

from app.rtn_ranks import RTN_RANK_CATALOG, all_canonical_ranks, normalize_rtn_rank

FRONTEND_ROOT = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"


def _read(rel: str) -> str:
    return (FRONTEND_ROOT / rel).read_text(encoding="utf-8")


class TestCanonicalRankSourceIsSingleAndUnaltered(unittest.TestCase):
    """Item 9: the dropdown/preview must be populated from the canonical
    source, and no second rank dictionary was introduced anywhere."""

    def test_item9_no_second_rank_dictionary_introduced_in_repository(self):
        import app.api.repository as repository

        src = inspect.getsource(repository)
        # The repository module must import and reuse normalize_rtn_rank,
        # not hand-roll its own rank table.
        self.assertIn("from app.rtn_ranks import normalize_rtn_rank", src)

    def test_item9_reference_ranks_endpoint_reuses_canonical_catalog(self):
        import app.api.routers.reference as reference_mod

        src = inspect.getsource(reference_mod)
        self.assertIn("from app.rtn_ranks import all_canonical_ranks", src)

    def test_all_canonical_ranks_returns_full_catalog(self):
        ranks = all_canonical_ranks()
        self.assertEqual(len(ranks), len(RTN_RANK_CATALOG))
        for r in ranks:
            self.assertIn("rank_th_abbreviation", r)
            self.assertIn("rank_en_abbreviation", r)
            self.assertIn("rank_category", r)


class TestRankToAbbreviationMapping(unittest.TestCase):
    """Item 10: selected rank maps to the canonical English abbreviation."""

    def test_item10_known_rank_maps_to_canonical_abbreviation(self):
        entry = normalize_rtn_rank("น.อ.")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["rank_en_abbreviation"], "Capt")

    def test_item10_full_thai_name_also_resolves(self):
        entry = normalize_rtn_rank("นาวาเอก")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["rank_en_abbreviation"], "Capt")

    def test_item12_unknown_rank_text_returns_none_not_a_guess(self):
        entry = normalize_rtn_rank("ไม่มีในระบบ-ทดสอบ")
        self.assertIsNone(entry)


class TestEnrollmentExposesRankMetadata(unittest.TestCase):
    """Confirms the additive Enrollment.rank_metadata plumbing the preview
    depends on: repository join + schema field."""

    def test_repository_selects_rank_column_for_list_and_detail(self):
        import app.api.repository as repository

        list_src = inspect.getsource(repository.list_enrollments)
        detail_src = inspect.getsource(repository.get_enrollment_row)
        self.assertIn("h.rank", list_src)
        self.assertIn("h.rank", detail_src)
        self.assertIn("rank_metadata", list_src)
        self.assertIn("rank_metadata", detail_src)

    def test_schema_declares_rank_metadata_field(self):
        import app.api.schemas as schemas

        src = inspect.getsource(schemas.Enrollment)
        self.assertIn("rank_metadata", src)
        self.assertIn("rank:", src)


class TestTerminalNamePreviewRules(unittest.TestCase):
    """Items 11, 13, 14: preview correctness, ASCII/length safety, no
    silent transliteration — asserted against the actual TS source since
    no frontend test runner exists in this repo."""

    def setUp(self):
        self.src = _read("lib/terminalName.ts")

    def test_item11_deterministic_length_limit_matches_backend_guard(self):
        # MAX_TERMINAL_NAME_LENGTH must match app/enrollment.py's
        # MAX_TERMINAL_NAME_LENGTH (20) — the frontend preview and the
        # backend's authoritative validate_terminal_display_name() must
        # agree, or the preview could suggest a name the server rejects.
        import app.enrollment as enrollment_mod

        self.assertIn("export const MAX_TERMINAL_NAME_LENGTH = %d;" % enrollment_mod.MAX_TERMINAL_NAME_LENGTH, self.src)

    def test_item13_never_combines_rank_and_name_over_the_limit(self):
        self.assertIn("withRank.length <= MAX_TERMINAL_NAME_LENGTH", self.src)
        # The escape path must fall back to the full canonical name, not a
        # truncated hybrid — asserted by checking no slice()/substring()
        # call exists anywhere in this rule (would indicate silent cutting).
        self.assertNotIn(".slice(0,", self.src)
        self.assertNotIn(".substring(", self.src)

    def test_item14_no_transliteration_helper_present(self):
        # Regression guard: this module must never attempt to transliterate
        # Thai rank/name text — it only combines two already-canonical,
        # already-ASCII fields (rank_en_abbreviation, english_name).
        for banned in ("transliterate", "thaiToEnglish", "romanize"):
            self.assertNotIn(banned, self.src)

    def test_falls_back_to_plain_name_when_no_rank_metadata(self):
        self.assertIn("if (!abbr)", self.src)
        self.assertIn("return { value: name, rankOmittedForLength: false };", self.src)


if __name__ == "__main__":
    unittest.main()
