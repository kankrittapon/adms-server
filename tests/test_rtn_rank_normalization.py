"""
Tests for Royal Thai Navy rank normalization + พลทหาร exclusion policy.

PromptID: ADMS-Data-HumanDeviceMapping-003

Covers:
  - Canonical catalog completeness and uniqueness
  - Thai abbreviation -> canonical metadata (English name, class)
  - Full Thai name forms accepted
  - ว่าที่ (acting) prefix handling
  - Original rank value preserved (never rewritten)
  - Deterministic พลทหาร exclusion predicate and production-scope gate
  - Unknown values fail safe
"""

import unittest

from app.rtn_ranks import (
    CATEGORY_LABELS,
    INCLUDED_CATEGORIES,
    RTN_RANK_CATALOG,
    all_canonical_ranks,
    classify_rank,
    is_plothan,
    normalize_rtn_rank,
    production_scope_allowed,
)

_REQUIRED_KEYS = (
    "rank_th_full",
    "rank_th_abbreviation",
    "rank_en",
    "rank_en_abbreviation",
    "rank_category",
    "source",
)


class TestCatalogIntegrity(unittest.TestCase):
    def test_catalog_has_expected_entries(self):
        self.assertGreaterEqual(len(RTN_RANK_CATALOG), 16)

    def test_every_entry_has_all_canonical_fields(self):
        for abbr, entry in RTN_RANK_CATALOG.items():
            for key in _REQUIRED_KEYS:
                self.assertIn(key, entry, "missing %s for %s" % (key, abbr))
                self.assertTrue(str(entry[key]).strip())

    def test_abbreviations_unique_and_match_key(self):
        seen = set()
        for abbr, entry in RTN_RANK_CATALOG.items():
            self.assertNotIn(abbr, seen)
            seen.add(abbr)
            self.assertEqual(entry["rank_th_abbreviation"], abbr)

    def test_all_rank_classes_are_known(self):
        for entry in RTN_RANK_CATALOG.values():
            self.assertIn(entry["rank_category"], CATEGORY_LABELS)

    def test_all_canonical_ranks_helper_returns_catalog_size(self):
        self.assertEqual(len(all_canonical_ranks()), len(RTN_RANK_CATALOG))


class TestNormalization(unittest.TestCase):
    def test_nco_abbreviation_cpo3(self):
        info = normalize_rtn_rank("พ.จ.ต.")
        self.assertEqual(info["rank_th_full"], "พันจ่าตรี")
        self.assertEqual(info["rank_en"], "Chief Petty Officer 3rd Class")
        self.assertEqual(info["rank_en_abbreviation"], "CPO3")
        self.assertEqual(info["rank_category"], "NCO")

    def test_officer_abbreviation_commander(self):
        info = normalize_rtn_rank("น.ท.")
        self.assertEqual(info["rank_th_full"], "นาวาโท")
        self.assertEqual(info["rank_en"], "Commander")
        self.assertEqual(info["rank_en_abbreviation"], "Cdr")
        self.assertEqual(info["rank_category"], "OFFICER")

    def test_navy_lieutenant_is_ruea_ek_not_army(self):
        # ร.อ. in the Navy is เรือเอก (Lieutenant), NOT the Army ร้อยเอก.
        info = normalize_rtn_rank("ร.อ.")
        self.assertEqual(info["rank_th_full"], "เรือเอก")
        self.assertEqual(info["rank_en"], "Lieutenant")
        self.assertEqual(info["rank_category"], "OFFICER")

    def test_petty_officer_first_class(self):
        info = normalize_rtn_rank("จ.อ.")
        self.assertEqual(info["rank_th_full"], "จ่าเอก")
        self.assertEqual(info["rank_en"], "Petty Officer 1st Class")
        self.assertEqual(info["rank_en_abbreviation"], "PO1")
        self.assertEqual(info["rank_category"], "NCO")

    def test_enlisted_plothan(self):
        info = normalize_rtn_rank("พลฯ")
        self.assertEqual(info["rank_category"], "ENLISTED")
        self.assertEqual(info["rank_th_full"], "พลทหาร")
        self.assertTrue(info["rank_en"].strip())

    def test_full_thai_form_accepted(self):
        short = normalize_rtn_rank("พ.จ.ต.")
        full = normalize_rtn_rank("พันจ่าตรี")
        self.assertEqual(short["rank_en"], full["rank_en"])
        self.assertEqual(short["rank_category"], full["rank_category"])
        self.assertEqual(short["rank_th_abbreviation"], full["rank_th_abbreviation"])

    def test_original_value_preserved(self):
        info = normalize_rtn_rank("พ.จ.ต.")
        self.assertEqual(info["rank_th_original"], "พ.จ.ต.")
        info2 = normalize_rtn_rank("  พ.จ.ต. ")
        self.assertEqual(info2["rank_th_original"], "พ.จ.ต.")  # whitespace normalized copy

    def test_unknown_rank_returns_none(self):
        self.assertIsNone(normalize_rtn_rank("BOGUS RANK"))
        self.assertIsNone(normalize_rtn_rank(""))
        self.assertIsNone(normalize_rtn_rank(None))

    def test_classify_unknown(self):
        self.assertEqual(classify_rank("BOGUS"), "UNKNOWN")


class TestActingPrefix(unittest.TestCase):
    def test_acting_lt_cdr(self):
        info = normalize_rtn_rank("ว่าที่ น.ต.")
        self.assertEqual(info["acting"], "true")
        self.assertEqual(info["rank_en"], "Acting Lieutenant Commander")
        self.assertIn("Act", info["rank_en_abbreviation"])
        self.assertEqual(info["rank_category"], "OFFICER")

    def test_acting_no_space(self):
        info = normalize_rtn_rank("ว่าที่นาวาตรี")
        self.assertEqual(info["acting"], "true")
        self.assertEqual(info["rank_en"], "Acting Lieutenant Commander")

    def test_non_acting_has_flag_false(self):
        self.assertEqual(normalize_rtn_rank("น.ต.")["acting"], "false")


class TestPlothanExclusion(unittest.TestCase):
    def test_plothan_variants_excluded(self):
        for variant in ("พลฯ", "พลทหาร", "พลทหารกองประจำการ", "พล.ทหาร"):
            self.assertTrue(is_plothan(variant), "expected exclusion for %r" % variant)

    def test_non_plothan_not_excluded(self):
        for value in ("พ.จ.ต.", "น.ท.", "ร.อ.", "จ.อ.", "ว่าที่ น.ต.", "", None):
            self.assertFalse(is_plothan(value), "unexpected exclusion for %r" % value)

    def test_production_scope_gate(self):
        self.assertFalse(production_scope_allowed("พลฯ"))
        self.assertTrue(production_scope_allowed("พ.จ.ต."))
        self.assertTrue(production_scope_allowed("ว่าที่ น.ต."))
        self.assertTrue(production_scope_allowed(""))  # empty rank is not exclusion evidence

    def test_included_categories_exclude_enlisted(self):
        self.assertIn("OFFICER", INCLUDED_CATEGORIES)
        self.assertIn("NCO", INCLUDED_CATEGORIES)
        self.assertNotIn("ENLISTED", INCLUDED_CATEGORIES)


if __name__ == "__main__":
    unittest.main()
