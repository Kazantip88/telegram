from __future__ import annotations

import unittest

from app.detector import detect
from app.scoring import score_lead


class DutchDetectionTests(unittest.TestCase):
    def test_russian_kicked_out_victim_scores_as_candidate(self):
        signals = detect("Меня кинули на 20000 евро у брокера. Помогите, что делать?")
        self.assertEqual(signals.language, "ru")
        self.assertGreaterEqual(score_lead(signals).total, 50)

    def test_dutch_help_request_scores_as_candidate(self):
        signals = detect("Ik ben opgelicht door een crypto broker, mijn spaargeld is weg. Ik heb hulp nodig.")
        self.assertEqual(signals.language, "nl")
        score = score_lead(signals)
        self.assertGreaterEqual(score.total, 50)


if __name__ == "__main__":
    unittest.main()
