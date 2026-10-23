from __future__ import annotations

import unittest

from app.community_public import _explicit_loss, _is_direct_user_post, _likely_promo_or_seo


class CommunityPublicFilterTests(unittest.TestCase):
    def test_rejects_long_promotional_trading_post(self):
        title = "I Got Burned Twice by Prop Firms Before I Learned How to Research Them"
        text = (title + " " + ("I lost money and learned to research. " * 100)
                + "This comparison site has verified reviews and discount codes.")
        self.assertTrue(_likely_promo_or_seo(text, title))

    def test_keeps_clear_withdrawal_complaint(self):
        title = "Broker blocked my withdrawal"
        text = title + ". I cannot withdraw my money and support stopped responding."
        self.assertFalse(_likely_promo_or_seo(text, title))
        self.assertTrue(_explicit_loss(text))

    def test_detects_first_person_loss_in_russian(self):
        self.assertTrue(_explicit_loss("Я потерял деньги после перевода брокеру."))

    def test_rejects_long_generic_post_without_complaint_title(self):
        title = "My experience researching prop firms"
        text = title + " " + ("I lost money once, but here are my recommendations. " * 70)
        self.assertTrue(_likely_promo_or_seo(text, title))

    def test_accepts_first_person_post_from_reddit(self):
        text = "I lost money to a broker and cannot withdraw my funds."
        self.assertTrue(_is_direct_user_post(
            text, "https://www.reddit.com/r/scams/comments/abc123/example/"
        ))

    def test_rejects_law_firm_article_even_with_first_person_phrase(self):
        text = "I lost money to a broker and cannot withdraw my funds."
        self.assertFalse(_is_direct_user_post(
            text, "https://www.anwalt.de/rechtstipps/example.html"
        ))

    def test_rejects_unknown_domain_even_with_first_person_phrase(self):
        text = "I lost money to a broker and cannot withdraw my funds."
        self.assertFalse(_is_direct_user_post(text, "https://example.com/post/123"))


if __name__ == "__main__":
    unittest.main()
