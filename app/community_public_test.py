from __future__ import annotations

import unittest

from app.community_public import _explicit_loss, _likely_promo_or_seo


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


if __name__ == "__main__":
    unittest.main()
