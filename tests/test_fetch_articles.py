import unittest
from unittest.mock import patch

import fetch_articles as harvest


class HarvestTests(unittest.TestCase):
    @patch.object(harvest.time, "sleep")
    @patch.object(harvest, "get_page")
    def test_europe_pmc_pagination_and_missing_doi(self, get_page, sleep):
        get_page.side_effect = [
            {"hitCount": 2, "nextCursorMark": "next+token", "resultList": {"result": [
                {"source": "MED", "id": "1", "title": "First",
                 "keywordList": {"keyword": ["Biology"]}}]}},
            {"hitCount": 2, "resultList": {"result": [
                {"source": "PMC", "id": "PMC2", "title": "Second"}]}},
        ]
        rows = harvest.fetch_europe_pmc("2026-09-20", "2026-09-21")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["keywords"], ["Biology"])
        self.assertIsNone(rows[1]["doi"])
        self.assertIn("cursorMark=next%2Btoken", get_page.call_args.args[0])

    @patch.object(harvest.time, "sleep")
    @patch.object(harvest, "get_page")
    def test_crossref_reusable_cursor_and_subjects(self, get_page, sleep):
        get_page.side_effect = [
            {"status": "ok", "message": {"total-results": 1001, "next-cursor": "*", "items": [
                {"DOI": "10.1/A", "title": ["First"], "subject": ["Biology"],
                 "published": {"date-parts": [[2026, 9]]}}] + [
                     {"DOI": f"10.1/filler{i}"} for i in range(999)]}},
            {"status": "ok", "message": {"total-results": 1020, "items": [
                {"DOI": "10.1/B", "title": ["Second"]}]}},
        ]
        rows = harvest.fetch_crossref("2026-09-20", "2026-09-21")
        self.assertEqual(len(rows), 1001)
        self.assertEqual(rows[0]["date"], "2026-09")
        self.assertEqual(rows[0]["subjects"], ["Biology"])
        self.assertEqual(rows[0]["keywords"], [])
        self.assertIsNone(rows[1]["abstract"])

    @patch.object(harvest, "get_page")
    def test_incomplete_results_raise(self, get_page):
        get_page.return_value = {"hitCount": 1, "resultList": {"result": []}}
        with self.assertRaisesRegex(ValueError, "pagination"):
            harvest.fetch_europe_pmc("2026-09-20", "2026-09-21")

    @patch.object(harvest, "get_page")
    def test_empty_results_are_valid(self, get_page):
        get_page.return_value = {"status": "ok", "message": {"total-results": 0, "items": []}}
        self.assertEqual(harvest.fetch_crossref("2026-09-20", "2026-09-21"), [])


if __name__ == "__main__":
    unittest.main()
