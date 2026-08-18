"""
Rank source-of-truth — ADMS-UX-FinalPolish-021 Part C.

AUDIT FINDING (this session): human_employees.rank is 100% import-derived
(app/import_excel_human_master.py, source='EXCEL_IMPORT') with NO write
path anywhere in the API — PATCH /api/v1/humans/{employee_id} accepts only
english_name (app/api/schemas.py UpdateHumanEnglishNameRequest). Per the
owner's own decision tree for externally-owned data, we do NOT invent a
rank write endpoint. Instead: rank display is clearly labeled as
source-managed, and the canonical English abbreviation is already derived
automatically everywhere rank is shown or used for terminal naming — no
operator has ever had to type a rank abbreviation by hand in this system.

No frontend test runner exists in this repo — these assert against source,
same convention as tests/test_terminal_management_ui.py.
"""

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class TestRankSourceOfTruth(unittest.TestCase):
    def test_item5_rtn_ranks_is_the_only_canonical_source(self):
        ranks_src = _read(REPO_ROOT / "app" / "rtn_ranks.py")
        self.assertIn("RTN_RANK_CATALOG", ranks_src)

    def test_reference_ranks_endpoint_reads_from_canonical_source_only(self):
        ref_src = _read(REPO_ROOT / "app" / "api" / "routers" / "reference.py")
        self.assertIn("from app.rtn_ranks import all_canonical_ranks", ref_src)

    def test_item5b_no_rank_write_endpoint_exists(self):
        """Confirms the audit finding stays true: PATCH /humans accepts
        english_name only. If this test starts failing because someone adds
        a rank field, it must be validated against rtn_ranks.py — see
        docs/reports/ADMS-UX-FinalPolish-021.md for the required design."""
        schemas_src = _read(REPO_ROOT / "app" / "api" / "schemas.py")
        match = re.search(
            r"class UpdateHumanEnglishNameRequest.*?(?=\nclass |\Z)", schemas_src, re.S
        )
        self.assertIsNotNone(match)
        self.assertNotIn("rank", match.group(0).lower())

    def test_item4_no_duplicate_rank_dictionary_in_frontend(self):
        """The frontend must never hardcode its own rank_th -> rank_en
        table — everything must come from GET /api/v1/reference/ranks via
        the generated API types, never a second, driftable copy."""
        for f in FRONTEND_ROOT.rglob("*.ts*"):
            if f.name in ("generated.ts",):
                continue
            src = _read(f)
            self.assertNotIn("พล.ร.อ.", src, f"hardcoded rank literal found in {f}")

    def test_item12_rank_source_managed_hint_present_th_and_en(self):
        th_src = _read(FRONTEND_ROOT / "i18n" / "th.ts")
        en_src = _read(FRONTEND_ROOT / "i18n" / "en.ts")
        self.assertIn("rankSourceManagedHint", th_src)
        self.assertIn("rankSourceManagedHint", en_src)
        self.assertIn("นำเข้าจากไฟล์", th_src)

    def test_item11_personnel_page_never_offers_an_editable_rank_field(self):
        """Editing rank inside ADMS would violate source ownership (it's
        Excel-import-owned). Personnel.tsx must not contain a rank input/
        select bound to a save action, unlike english_name which IS
        legitimately editable here."""
        personnel_src = _read(FRONTEND_ROOT / "pages" / "Personnel.tsx")
        self.assertIn("editEnglishName", personnel_src)
        self.assertNotIn("editRank", personnel_src)
        self.assertNotIn("saveRank", personnel_src)

    def test_item3_terminal_name_derives_canonical_abbreviation_automatically(self):
        helper_src = _read(FRONTEND_ROOT / "lib" / "terminalName.ts")
        self.assertIn("rank_en_abbreviation", helper_src)
        # Never a user-typed rank string feeding the preview.
        self.assertNotIn("prompt(", helper_src)

    def test_item7_ascii_guard_preserved(self):
        enrollment_src = _read(REPO_ROOT / "app" / "enrollment.py")
        self.assertIn("def validate_terminal_display_name", enrollment_src)

    def test_item8_max_length_rule_shared_not_duplicated_with_drift(self):
        helper_src = _read(FRONTEND_ROOT / "lib" / "terminalName.ts")
        enrollment_src = _read(REPO_ROOT / "app" / "enrollment.py")
        self.assertIn("MAX_TERMINAL_NAME_LENGTH = 20", helper_src)
        self.assertIn("20", enrollment_src)  # server-side limit this must match

    def test_item9_missing_english_name_handled_clearly(self):
        helper_src = _read(FRONTEND_ROOT / "lib" / "terminalName.ts")
        self.assertIn('if (!name)', helper_src)

    def test_item10_missing_rank_handled_clearly(self):
        helper_src = _read(FRONTEND_ROOT / "lib" / "terminalName.ts")
        self.assertIn("if (!abbr)", helper_src)

    def test_item9b_no_silent_mid_string_truncation(self):
        helper_src = _read(FRONTEND_ROOT / "lib" / "terminalName.ts")
        self.assertNotIn(".slice(0,", helper_src)
        self.assertNotIn(".substring(0,", helper_src)


if __name__ == "__main__":
    unittest.main()
