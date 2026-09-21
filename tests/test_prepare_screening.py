import unittest

from prepare_screening import canonical_doi, event_flags, prepare


class ScreeningTests(unittest.TestCase):
    def test_doi_normalization(self):
        self.assertEqual(canonical_doi("https://doi.org/10.1234%2FABC"), "10.1234/abc")
        self.assertEqual(canonical_doi(" DOI:10.1234/ABC "), "10.1234/abc")
        self.assertIsNone(canonical_doi("NA"))

    def test_dedup_preserves_evidence_and_versions(self):
        rows = [
            {"doi": "10.1234/ABC", "source": "biorxiv", "version": "1", "title": "First"},
            {"doi": "https://doi.org/10.1234/abc", "source": "biorxiv", "version": "2", "title": "Revised"},
            {"doi": "10.1234/abc", "source": "europe_pmc", "title": "Revised"},
        ]
        result = prepare(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Revised")
        self.assertEqual(result[0]["version"], "2")
        self.assertEqual(len(result[0]["source_records"]), 3)
        self.assertEqual(result[0]["event_flags"], ["first_preprint_version", "preprint_revision"])

    def test_missing_dois_and_different_dois_not_title_merged(self):
        rows = [{"title": "Identical"}, {"title": "Identical"},
                {"title": "Identical", "doi": "10.1234/a"},
                {"title": "Identical", "doi": "10.1234/b"}]
        self.assertEqual(len(prepare(rows)), 4)

    def test_notice_prefixes(self):
        for title in ("[Corrigendum] Original title", "Correction: Original title", "Erratum to Original title"):
            self.assertEqual(event_flags({"title": title})[0]["type"], "correction_notice")
        for title in ("Error correction in imaging", "Correction of cell polarity", "An Update Review"):
            self.assertEqual(event_flags({"title": title}), [])

    def test_metadata_revision_is_not_article_revision(self):
        result = prepare([{"source": "crossref", "dateOfRevision": "2026-09-21"}])[0]
        self.assertEqual(result["publication_status"], "unclassified")


if __name__ == "__main__":
    unittest.main()
