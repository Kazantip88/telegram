from __future__ import annotations

import unittest

from app.lead_classifier import classify, has_direct_victim_language, has_financial_context, has_help_request, source_kind


class LeadClassifierTests(unittest.TestCase):
    def test_direct_ru_victim_asking_for_help_is_lead(self):
        result = classify(
            "Я потерял 20000 евро у брокера, не могу вывести деньги. Подскажите, что делать?",
            source="telegram",
        )
        self.assertEqual(result.kind, "lead")
        self.assertTrue(result.direct_victim)
        self.assertTrue(result.help_request)
        self.assertTrue(result.financial_context)

    def test_ru_kicked_out_and_lawyer_request_is_lead(self):
        result = classify(
            "Меня кинули на $200 тысяч, хочу вернуть деньги. Посоветуйте юриста.",
            source="telegram",
        )
        self.assertEqual(result.kind, "lead")

    def test_direct_loss_without_help_request_is_not_qualified(self):
        result = classify("Я потерял 20000 евро у брокера и не могу вывести деньги", source="telegram")
        self.assertEqual(result.kind, "ignore")
        self.assertIn("no explicit request", result.reasons[0])

    def test_non_financial_scam_request_is_not_a_lead(self):
        result = classify(
            "I was scammed on a game server. Can anyone help?",
            source="telegram",
        )
        self.assertEqual(result.kind, "ignore")
        self.assertFalse(result.financial_context)

    def test_generic_ru_article_is_not_lead(self):
        result = classify(
            "Жертва может даже не осознавать, что ее обманули, а потерю средств воспринимает как инвестиционную неудачу",
            "https://amp.dw.com/ru/example",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "intelligence")
        self.assertEqual(result.source_kind, "news")

    def test_first_person_quote_inside_article_is_not_lead(self):
        result = classify(
            "Я уже потерял деньги на подобных схемах, говорится в статье. Помогите.",
            "https://bankstoday.net/rejting-brokerov/zalarium-com-obzor",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "ignore")
        self.assertEqual(result.source_kind, "unknown")

    def test_legal_page_is_not_lead(self):
        result = classify(
            "Wer bereits Geld verloren hat, kann sein Geld zurückfordern. Kostenfreie Ersteinschätzung.",
            "https://www.anwalt.de/rechtstipps/example-123.html",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "intelligence")
        self.assertEqual(result.source_kind, "legal")

    def test_news_with_direct_quote_is_not_lead(self):
        result = classify(
            "I was scammed and need a lawyer, says the victim in the report.",
            "https://www.reuters.com/example",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "intelligence")

    def test_generic_investment_question_is_ignored(self):
        result = classify("Welchen Broker sollte ich für Investitionen wählen?", source="telegram")
        self.assertEqual(result.kind, "ignore")
        self.assertFalse(result.direct_victim)

    def test_generic_money_back_question_is_ignored(self):
        result = classify("Wie bekomme ich mein Geld zurück? Welcher Broker ist seriös?", source="telegram")
        self.assertEqual(result.kind, "ignore")

    def test_german_direct_victim_asking_what_to_do_is_lead(self):
        result = classify(
            "Ich habe 12000 Euro bei einem Broker verloren und kann mein Geld nicht auszahlen. Was kann ich tun?",
            "https://www.gutefrage.net/frage/beispiel",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "lead")

    def test_qna_url_requires_personal_loss_and_help_request(self):
        result = classify(
            "Ich habe 8000 Euro bei einem Broker verloren. Was kann ich tun?",
            "https://www.banki.ru/forum/topic/example",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "lead")
        self.assertEqual(result.source_kind, "user_generated")

    def test_reddit_must_be_a_direct_post_not_search_page(self):
        result = classify(
            "I was scammed and need a lawyer.",
            "https://www.reddit.com/search/?q=broker",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "ignore")

    def test_reddit_direct_victim_post_is_lead(self):
        result = classify(
            "I was scammed by a broker and need a lawyer. Any advice?",
            "https://www.reddit.com/r/Scams/comments/abc123/example/",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "lead")

    def test_unknown_external_site_is_not_a_lead(self):
        result = classify(
            "I lost 10000 euros to a broker and need help.",
            "https://example.com/story",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "ignore")
        self.assertEqual(result.source_kind, "unknown")

    def test_nl_direct_victim_and_help_are_recognized(self):
        text = "Ik ben opgelicht door een broker en heb mijn spaargeld verloren. Wat kan ik doen?"
        self.assertTrue(has_direct_victim_language(text))
        self.assertTrue(has_help_request(text))
        result = classify(
            text,
            "https://www.reddit.com/r/Scams/comments/abc123/example/",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "lead")

    def test_sources_are_classified(self):
        self.assertEqual(source_kind("https://www.anwalt.de/rechtstipps/example"), "legal")
        self.assertEqual(source_kind("https://rus.postimees.ee/8566334/example"), "news")
        self.assertEqual(source_kind("https://www.banki.ru/forum/topic/example"), "user_generated")
        self.assertEqual(source_kind("https://www.reddit.com/r/Scams/comments/abc/title"), "user_generated")


if __name__ == "__main__":
    unittest.main()
