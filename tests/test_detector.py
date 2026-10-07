from app.detector import detect, extract_amounts


def test_euro_formats():
    assert 18500 in extract_amounts("18.500 EUR")
    assert 8500 in extract_amounts("€8500")
    assert 15000 in extract_amounts("15k EUR")


def test_bilingual_detection():
    ru = detect("Потерял €8500, брокер заблокировал вывод, есть скриншоты")
    de = detect("Ich habe 8500 EUR verloren, Auszahlung blockiert, Screenshots vorhanden")
    assert ru.language == "ru"
    assert de.language == "de"
    assert ru.has_withdrawal and de.has_withdrawal
