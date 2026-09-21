import unittest

from filter_articles import compile_keywords, evaluate


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.keywords = compile_keywords({"keywords": [
            {"keyword": "Rac", "strength": "strong", "bucket": "migration"},
            {"keyword": "migration", "strength": "strong", "bucket": "migration"},
            {"keyword": "actin", "strength": "weak", "bucket": "migration"},
            {"keyword": "cortex", "strength": "weak", "bucket": "migration"},
            {"keyword": "microscopy", "strength": "weak", "bucket": "imaging"},
            {"keyword": "live-cell imaging", "strength": "strong", "bucket": "imaging"},
        ]})

    def rules(self, title=None, abstract=None):
        return evaluate({"title": title, "abstract": abstract}, self.keywords)["rules"]

    def test_strong_title_only(self):
        self.assertEqual(self.rules("RAC signalling"), ["strong_keyword_in_title"])
        self.assertEqual(self.rules(abstract="Rac migration"), [])

    def test_two_distinct_weak_keywords_across_fields(self):
        self.assertEqual(self.rules("actin", "cortex"), ["two_distinct_weak_keywords"])
        self.assertEqual(self.rules("actin actin", "actin"), [])

    def test_cross_bucket(self):
        self.assertEqual(self.rules(abstract="Rac and microscopy"), ["keywords_from_two_buckets"])

    def test_word_boundaries(self):
        self.assertEqual(self.rules("fraction interacting"), [])

    def test_markup_and_hyphen_normalization(self):
        self.assertEqual(self.rules("Live&#8209;cell <i>imaging</i>"), ["strong_keyword_in_title"])
        self.assertEqual(self.rules("live cell imaging"), ["strong_keyword_in_title"])

    def test_missing_text_and_other_fields_ignored(self):
        self.assertEqual(self.rules(), [])
        self.assertEqual(evaluate({"keywords": ["Rac"]}, self.keywords)["rules"], [])


if __name__ == "__main__":
    unittest.main()
