from __future__ import annotations

import unittest

from .config import _DEFAULT_X_SEARCH_QUERIES
from .lead_classifier import classify, source_kind
from .x_leads import _parse_payload


class XLeadTests(unittest.TestCase):
    def test_default_queries_cover_four_languages_and_exclude_retweets(self):
        self.assertEqual(len(_DEFAULT_X_SEARCH_QUERIES), 4)
        for language in ("ru", "de", "en", "nl"):
            self.assertTrue(any(f"lang:{language}" in query for query in _DEFAULT_X_SEARCH_QUERIES))
        self.assertTrue(all("-is:retweet" in query for query in _DEFAULT_X_SEARCH_QUERIES))

    def test_parses_only_public_post_ids_and_text(self):
        rows, newest = _parse_payload({
            "data": [
                {"id": "123456789", "text": "I was scammed by a broker.", "lang": "en"},
                {"id": "bad-id", "text": "ignore"},
                {"id": "987654321", "text": ""},
            ],
            "meta": {"newest_id": "123456789"},
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "123456789")
        self.assertEqual(rows[0]["lang"], "en")
        self.assertEqual(newest, "123456789")

    def test_direct_x_post_is_an_approved_user_generated_source(self):
        url = "https://x.com/i/web/status/123456789"
        self.assertEqual(source_kind(url), "user_generated")
        candidate = classify(
            "I was scammed by a forex broker and lost my money. I need a lawyer.",
            url,
            source="x:api",
        )
        self.assertEqual(candidate.kind, "lead")

    def test_x_profile_or_search_page_is_not_a_lead_source(self):
        url = "https://x.com/someprofile"
        self.assertEqual(source_kind(url), "unknown")
        candidate = classify(
            "I was scammed by a forex broker and lost my money. I need a lawyer.",
            url,
            source="x:api",
        )
        self.assertEqual(candidate.kind, "ignore")

    def test_generic_x_mention_is_rejected_without_help_request(self):
        candidate = classify(
            "I lost money with a crypto broker.",
            "https://x.com/i/web/status/123456789",
            source="x:api",
        )
        self.assertEqual(candidate.kind, "ignore")


if __name__ == "__main__":
    unittest.main()
