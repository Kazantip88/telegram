from __future__ import annotations

import re
from dataclasses import dataclass, field

RU = {
    "loss": ["потерял", "потеряла", "потерял деньги", "украли", "обманули", "развели"],
    "fraud": ["мошенничество", "мошенники", "мошенник", "скам", "обман"],
    "withdrawal": ["не могу вывести", "не выводят", "заблокировали вывод", "вывод заблокирован", "не дают вывести"],
    "support": ["поддержка не отвечает", "брокер не отвечает", "не отвечает", "исчез", "пропал"],
    "evidence": ["скриншот", "скрины", "документы", "договор", "транзакци", "перевод", "выписка"],
    "investment": ["инвестировал", "инвестировала", "вложил", "вложила", "инвестиции", "брокер", "биржа", "форекс", "крипто", "bitcoin", "биткоин", "трейдинг"],
    "help": ["помогите вернуть", "вернуть деньги", "возврат денег", "юрист", "адвокат", "что делать", "помощь"],
}

DE = {
    "loss": ["geld verloren", "verloren", "bestohlen", "abgezockt", "betrogen"],
    "fraud": ["betrug", "betrüger", "scam", "anlagebetrug", "betrugsfall"],
    "withdrawal": ["kann nicht auszahlen", "auszahlung nicht möglich", "auszahlung blockiert", "auszahlung gesperrt", "kann mein geld nicht auszahlen"],
    "support": ["support antwortet nicht", "broker antwortet nicht", "keine antwort", "broker verschwunden", "verschwunden"],
    "evidence": ["screenshots", "beweise", "dokumente", "vertrag", "transaktion", "überweisung", "kontoauszug"],
    "investment": ["investiert", "investment", "investition", "broker", "börse", "forex", "krypto", "kryptowährung", "bitcoin", "trading"],
    "help": ["geld zurück", "geld zurückholen", "zurückbekommen", "anwalt", "rechtsanwalt", "rechtliche hilfe", "was kann ich tun", "hilfe"],
}

@dataclass
class Signals:
    language: str = "unknown"
    matched: dict[str, list[str]] = field(default_factory=dict)
    amounts: list[float] = field(default_factory=list)

    @property
    def has_loss(self) -> bool:
        return bool(self.matched.get("loss"))

    @property
    def has_fraud(self) -> bool:
        return bool(self.matched.get("fraud"))

    @property
    def has_withdrawal(self) -> bool:
        return bool(self.matched.get("withdrawal"))

    @property
    def has_evidence(self) -> bool:
        return bool(self.matched.get("evidence"))


def detect(text: str) -> Signals:
    t = text.lower().replace("ё", "е")
    ru_hits = sum(any(p in t for p in values) for values in RU.values())
    de_hits = sum(any(p in t for p in values) for values in DE.values())
    dictionary = RU if ru_hits >= de_hits else DE
    language = "ru" if dictionary is RU else "de"
    matched: dict[str, list[str]] = {}
    for category, phrases in dictionary.items():
        hits = [p for p in phrases if p in t]
        if hits:
            matched[category] = hits
    return Signals(language=language, matched=matched, amounts=extract_amounts(t))


def extract_amounts(text: str) -> list[float]:
    results: list[float] = []
    patterns = [
        r"(?:€|eur|euro)\s*([0-9]{1,3}(?:[.\s][0-9]{3})*(?:,[0-9]{1,2})?)",
        r"([0-9]{1,3}(?:[.\s][0-9]{3})*(?:,[0-9]{1,2})?)\s*(?:€|eur|euro)",
        r"€\s*([0-9]+(?:[.,][0-9]+)?)\s*k\b",
        r"\b([0-9]+(?:[.,][0-9]+)?)\s*k\b",
    ]
    for pattern in patterns:
        for raw in re.findall(pattern, text, flags=re.I):
            value = raw.replace(" ", "")
            if value.endswith("k"):
                value = value[:-1]
            if "," in value and "." in value:
                value = value.replace(".", "").replace(",", ".")
            elif value.count(".") == 1 and len(value.split(".")[-1]) == 3:
                value = value.replace(".", "")
            else:
                value = value.replace(",", ".")
            try:
                number = float(value)
                if pattern.endswith(r"\s*k\b"):
                    number *= 1000
                results.append(number)
            except ValueError:
                pass
    return sorted(set(results), reverse=True)
