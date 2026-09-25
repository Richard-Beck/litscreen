import io
import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

import fetch_articles as harvest
import fetch_biorxiv as network


def response(payload):
    return io.StringIO(json.dumps(payload))


class RetryTests(unittest.TestCase):
    @patch.object(network.time, "sleep")
    @patch.object(network, "urlopen")
    def test_europe_pmc_error_on_later_page_retries_same_cursor(self, urlopen, sleep):
        urlopen.side_effect = [
            response({"hitCount": 2, "nextCursorMark": "next+token",
                      "resultList": {"result": [{"source": "MED", "id": "1"}]}}),
            response({"error": "Temporary service failure"}),
            response({"hitCount": 2,
                      "resultList": {"result": [{"source": "MED", "id": "2"}]}}),
        ]
        rows = harvest.fetch_europe_pmc("2026-09-22", "2026-09-23")
        self.assertEqual([r["source_id"] for r in rows], ["1", "2"])
        urls = [call.args[0].full_url for call in urlopen.call_args_list]
        self.assertEqual(urls[1], urls[2])
        self.assertIn("cursorMark=next%2Btoken", urls[1])

    @patch.object(network.time, "sleep")
    @patch.object(network, "urlopen")
    def test_connection_refused_recovers_after_old_retry_limit(self, urlopen, sleep):
        urlopen.side_effect = [URLError(ConnectionRefusedError(111, "Connection refused"))] * 3 + [
            response({"messages": [{"status": "ok", "total": 0}], "collection": []})]
        self.assertEqual(network.fetch_articles("2026-09-23", "2026-09-24"), [])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 10, 20])

    @patch.object(network.time, "sleep")
    @patch.object(network, "urlopen")
    def test_malformed_json_is_retried(self, urlopen, sleep):
        urlopen.side_effect = [io.StringIO("<html>Unavailable</html>"), response({"ok": True})]
        self.assertEqual(network.get_page("https://example.org"), {"ok": True})

    @patch.object(network.time, "sleep")
    @patch.object(network, "urlopen")
    def test_persistent_invalid_envelope_fails_with_context(self, urlopen, sleep):
        urlopen.side_effect = [response({"error": "unavailable"}) for _ in range(6)]
        with self.assertRaisesRegex(ValueError, "after 6 attempts.*Invalid Europe PMC response"):
            harvest.fetch_europe_pmc("2026-09-22", "2026-09-23")
        self.assertEqual(urlopen.call_count, 6)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 10, 20, 40, 60])

    @patch.object(network.time, "sleep")
    @patch.object(network, "urlopen")
    def test_permanent_http_error_is_not_retried(self, urlopen, sleep):
        urlopen.side_effect = HTTPError("https://example.org", 400, "Bad request", {}, None)
        with self.assertRaises(HTTPError):
            network.get_page("https://example.org")
        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    @patch.object(network.time, "sleep")
    @patch.object(network, "urlopen")
    def test_biorxiv_error_envelope_is_retried(self, urlopen, sleep):
        urlopen.side_effect = [
            response({"messages": [{"status": "unavailable"}]}),
            response({"messages": [{"status": "ok", "total": 0}], "collection": []}),
        ]
        self.assertEqual(network.fetch_articles("2026-09-23", "2026-09-24"), [])
        self.assertEqual(urlopen.call_count, 2)
