from app.detector import detect
from app.scoring import score_lead


def test_hot_german_lead():
    text = "Ich habe 18.500 EUR bei einem Broker investiert, kann nicht auszahlen, Support antwortet nicht. Screenshots und Überweisungen vorhanden."
    score = score_lead(detect(text))
    assert score.priority == "HOT"
    assert score.total >= 80


def test_ignore_investment_question():
    text = "Welcher Broker ist gut für Forex Trading? Ich möchte anfangen."
    score = score_lead(detect(text))
    assert score.priority == "IGNORE"
    assert score.total < 50


def test_normal_russian_case():
    text = "Вложил деньги в крипто платформу, теперь не могу вывести. Что делать?"
    score = score_lead(detect(text))
    assert score.priority in {"NORMAL", "HOT"}
    assert score.total >= 50
