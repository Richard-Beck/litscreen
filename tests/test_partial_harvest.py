import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_site
import fetch_articles
import filter_articles
import prepare_screening


class PartialHarvestTests(unittest.TestCase):
    def test_one_source_fails_but_complete_sources_publish_with_warning(self):
        def broken(*args):
            raise ValueError("Invalid response")

        def complete(*args):
            return [{"source": "europe_pmc", "source_id": "MED1", "doi": "10.1234/example",
                     "title": "Cancer cell migration", "abstract": "Cell migration and motility",
                     "authors": "A. Author", "date": "2026-09-24", "keywords": [], "subjects": []}]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, filtered, screened, site = (root / name for name in
                                            ("raw.json", "filtered.json", "screened.json", "site"))
            with patch.dict(fetch_articles.FETCHERS, {"biorxiv": broken, "europe_pmc": complete}):
                with patch("sys.argv", ["fetch_articles.py", "--sources", "biorxiv", "europe_pmc",
                                        "--output", str(raw)]):
                    self.assertEqual(fetch_articles.main(), 0)
            harvested = json.loads(raw.read_text())
            self.assertEqual(harvested["source_counts"], {"europe_pmc": 1})
            self.assertEqual(list(harvested["failed_sources"]), ["biorxiv"])
            self.assertEqual(harvested["record_count"], 1)

            with patch("sys.argv", ["filter_articles.py", "--input", str(raw),
                                    "--output", str(filtered)]):
                self.assertEqual(filter_articles.main(), 0)
            with patch("sys.argv", ["prepare_screening.py", "--input", str(filtered),
                                    "--output", str(screened)]):
                self.assertEqual(prepare_screening.main(), 0)
            with patch("sys.argv", ["build_site.py", "--input", str(screened),
                                    "--output", str(site)]):
                build_site.main()
            html = (site / "index.html").read_text()
            self.assertIn("Incomplete refresh: biorxiv could not be harvested", html)
            self.assertIn("Cancer cell migration", html)
            self.assertEqual(json.loads((site / "articles.json").read_text())
                             ["input_metadata"]["harvest_metadata"]["failed_sources"],
                             {"biorxiv": "Invalid response"})

    def test_all_sources_fail_without_replacing_previous_output(self):
        def broken(*args):
            raise RuntimeError("Unavailable")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "raw.json"
            output.write_text("previous complete result")
            with patch.dict(fetch_articles.FETCHERS, {"biorxiv": broken, "europe_pmc": broken}):
                with patch("sys.argv", ["fetch_articles.py", "--sources", "biorxiv", "europe_pmc",
                                        "--output", str(output)]):
                    self.assertEqual(fetch_articles.main(), 1)
            self.assertEqual(output.read_text(), "previous complete result")
