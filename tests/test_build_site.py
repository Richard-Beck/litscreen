import unittest
from build_site import card, render


class SiteTests(unittest.TestCase):
    def test_unsafe_markup_and_links(self):
        html = card({"title": '<img src=x onerror="alert(1)">Title & text',
                     "url": "javascript:alert(1)", "abstract": '<script>alert(1)</script>',
                     "sources": ["crossref"], "event_flags": []})
        self.assertNotIn("<img", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("javascript:", html)
        self.assertIn("Title &amp; text", html)
        self.assertIn("Unclassified", html)

    def test_all_sources_contribute_matches(self):
        html = card({"title": "Example", "sources": ["crossref", "europe_pmc"],
                     "source_records": [{"source": "europe_pmc", "filter_match": {
                         "matches": [{"keyword": "actin"}], "buckets": ["mechanics"]}}]})
        self.assertIn('data-sources="crossref europe_pmc"', html)
        self.assertIn('data-buckets="mechanics"', html)
        self.assertIn("actin", html)

    def test_empty_harvest_renders(self):
        html = render({"articles": [], "prepared_at_utc": "2026-09-21T13:23:00+00:00"})
        self.assertIn("0 articles", html)
        self.assertNotIn("{{COUNT}}", html)
