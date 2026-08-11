"""
Unit Tests for Excel Human Master Import Utility
PromptID: ADMS-Data-ExcelImport-002
"""

import unittest
import os
import hashlib
from app.import_excel_human_master import (
    normalize_text,
    extract_rank_and_name,
    compute_source_hash,
    parse_workbook,
    reconcile_import,
    DEFAULT_WORKBOOK_PATH,
    DEFAULT_SHEET_NAME
)

class TestExcelHumanMasterImport(unittest.TestCase):
    
    def test_whitespace_normalization(self):
        self.assertEqual(normalize_text("  พล.อ.   สมชาย   ใจดี  "), "พล.อ. สมชาย ใจดี")
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")

    def test_rank_and_name_extraction(self):
        r, n = extract_rank_and_name("น.ท. จตุภัทร ลิมปนารมณ์")
        self.assertEqual(r, "น.ท.")
        self.assertEqual(n, "จตุภัทร ลิมปนารมณ์")

        r, n = extract_rank_and_name("พ.จ.อ. จักร์กฤษ สุริยะมณี")
        self.assertEqual(r, "พ.จ.อ.")
        self.assertEqual(n, "จักร์กฤษ สุริยะมณี")

        r, n = extract_rank_and_name("พลฯ นัทธพงศ์ คงเผื่อน")
        self.assertEqual(r, "พลฯ")
        self.assertEqual(n, "นัทธพงศ์ คงเผื่อน")

    def test_deterministic_hash(self):
        h1 = compute_source_hash("น.ท.", "จตุภัทร ลิมปนารมณ์", "นว.ก.", "นายทหาร", "")
        h2 = compute_source_hash("น.ท.", "จตุภัทร ลิมปนารมณ์", "นว.ก.", "นายทหาร", "")
        h3 = compute_source_hash("น.ท.", "จตุภัทร ลิมปนารมณ์", "นว.ก.", "นายทหาร", "ป่วย")
        
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_workbook_parsing(self):
        if not os.path.exists(DEFAULT_WORKBOOK_PATH):
            self.skipTest("Source workbook not found for test execution")
            
        records = parse_workbook(DEFAULT_WORKBOOK_PATH, DEFAULT_SHEET_NAME)
        self.assertEqual(len(records), 120)
        
        categories = {}
        for r in records:
            cat = r["category"]
            categories[cat] = categories.get(cat, 0) + 1
            
        self.assertEqual(categories.get("นายทหาร"), 20)
        self.assertEqual(categories.get("พันจ่า"), 58)
        self.assertEqual(categories.get("จ่า"), 6)
        self.assertEqual(categories.get("พลทหาร"), 36)

    def test_dry_run_reconciliation(self):
        records = [
            {
                "source_row": 4,
                "seq_num": 1,
                "rank": "น.ท.",
                "display_name": "จตุภัทร ลิมปนารมณ์",
                "branch": "นว.ก.",
                "category": "นายทหาร",
                "notes": "",
                "source_record_key": "EXCEL_FEB69_CAT_1_ROW_004",
                "source_hash": compute_source_hash("น.ท.", "จตุภัทร ลิมปนารมณ์", "นว.ก.", "นายทหาร", ""),
                "source_file": "excel/files/test.xlsx",
                "source_sheet": "Sheet1"
            }
        ]
        summary = reconcile_import(records, apply=False)
        self.assertEqual(summary["total_parsed"], 1)
        self.assertEqual(summary["valid"], 1)
        self.assertEqual(summary["invalid"], 0)
        self.assertFalse(summary["applied"])

if __name__ == "__main__":
    unittest.main()
