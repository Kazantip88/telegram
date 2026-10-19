from __future__ import annotations

import unittest

from app.lead_classifier import classify, has_direct_victim_language, source_kind


class LeadClassifierTests(unittest.TestCase):
    def test_direct_ru_victim_is_lead(self):
        result = classify("Я потерял 20000 евро у брокера, не могу вывести деньги", source="telegram")
        self.assertEqual(result.kind, "lead")
        self.assertTrue(result.direct_victim)

    def test_ru_kicked_out_is_direct_victim_signal(self):
        self.assertTrue(has_direct_victim_language("Меня кинули на $200 тысяч, хочу вернуть деньги"))

    def test_generic_ru_article_is_not_lead(self):
        result = classify(
            "Жертва может даже не осознавать, что ее обманули, а потерю средств воспринимает как инвестиционную неудачу",
            "https://amp.dw.com/ru/example",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "intelligence")
        self.assertEqual(result.source_kind, "news")

    def test_bankstoday_article_with_first_person_quote_is_not_lead(self):
        result = classify(
            "Я уже потерял деньги на подобных схемах, говорится в статье.",
            "https://bankstoday.net/rejting-brokerov/zalarium-com-obzor",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "ignore")
        self.assertEqual(result.source_kind, "unknown")

    def test_legal_anwalt_page_is_not_lead(self):
        result = classify(
            "Wer bereits Geld verloren hat, kann sein Geld zurückfordern. Kostenfreie Ersteinschätzung.",
            "https://www.anwalt.de/rechtstipps/example-123.html",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "intelligence")
        self.assertEqual(result.source_kind, "legal")

    def test_broker_warning_is_intelligence(self):
        result = classify(
            "RheinBridge Capital: alter Betrug auf neuer Webseite. Geld wird nicht zurückgezahlt.",
            "https://www.anwalt.de/rechtstipps/rheinbridge-capital-example.html",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "intelligence")

    def test_generic_investment_question_is_ignored(self):
        result = classify("Welchen Broker выбрать для инвестиций?", source="telegram")
        self.assertEqual(result.kind, "ignore")
        self.assertFalse(result.direct_victim)

    def test_generic_german_money_back_phrase_is_ignored(self):
        result = classify("Wie bekomme ich mein Geld zurück? Welcher Broker ist seriös?", source="telegram")
        self.assertEqual(result.kind, "ignore")

    def test_german_direct_victim_is_lead(self):
        result = classify("Ich habe 12000 Euro verloren und kann mein Geld nicht auszahlen", source="telegram")
        self.assertEqual(result.kind, "lead")

    def test_qna_url_is_lead_when_personal(self):
        result = classify(
            "Ich habe 8000 Euro bei einem Broker verloren. Was kann ich tun?",
            "https://www.banki.ru/forum/topic/example",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "lead")
        self.assertEqual(result.source_kind, "user_generated")

    def test_unknown_external_site_is_not_a_lead(self):
        result = classify(
            "I lost 10000 euros to a broker and need help.",
            "https://example.com/story",
            source="gmail:google-alerts",
        )
        self.assertEqual(result.kind, "ignore")
        self.assertEqual(result.source_kind, "unknown")

    def test_repeated_alert_destination_source_types(self):
        self.assertEqual(source_kind("https://www.anwalt.de/rechtstipps/example"), "legal")
        self.assertEqual(source_kind("https://rus.postimees.ee/8566334/example"), "news")
        self.assertEqual(source_kind("https://www.banki.ru/forum/topic/example"), "user_generated")


if __name__ == "__main__":
    unittest.main()
