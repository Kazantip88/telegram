from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

LEGAL_HOSTS = {
    "anwalt.de", "anwalt24.de", "broker-betrug.de", "kryptoschaden.de", "betrugsopfer-hilfe.de",
}
NEWS_HOSTS = {
    "dw.com", "amp.dw.com", "postimees.ee", "rus.postimees.ee", "tass.ru", "ria.ru", "rbc.ru",
    "kommersant.ru", "lenta.ru", "gazeta.ru", "interfax.ru", "forbes.ru", "focus.de",
    "spiegel.de", "faz.net", "welt.de", "bild.de",
}
USER_GENERATED_HOSTS = {
    "quora.com", "gutefrage.net", "reddit.com", "pikabu.ru", "stackexchange.com",
    "stackexchange.com", "finanzfrage.net", "trustpilot.com",
}

@dataclass(frozen=True)
class CandidateClass:
    kind: str
    source_kind: str
    direct_victim: bool
    reasons: tuple[str, ...]


def _host(url: str | None) -> str:
    if not url:
        return ""
    return urlparse(url).netloc.lower().removeprefix("www.")


def source_kind(url: str | None, text: str = "") -> str:
    host = _host(url)
    path = urlparse(url).path.lower() if url else ""
    if host in LEGAL_HOSTS or "anwalt.de" in host or "anwalt24.de" in host or "/rechtstipps/" in path:
        return "legal"
    if host in NEWS_HOSTS:
        return "news"
    if host == "banki.ru" and path.startswith("/forum/"):
        return "user_generated"
    if host in USER_GENERATED_HOSTS:
        return "user_generated"
    if any(marker in path for marker in ("/news/", "/article/", "/reviews", "/review/", "/otzyv", "/otzyvy")):
        return "article"
    return "unknown"


PERSONAL_VICTIM_PATTERNS = (
    r"\bя\s+(?:потерял|потеряла)\b",
    r"\bя\s+(?:вложил|вложила|инвестировал|инвестировала)\b",
    r"\bя\s+(?:перевел|перевела|отправил|отправила)\b.{0,100}\b(?:деньги|средства|депозит|евро|доллар)\b",
    r"\bменя\s+(?:обманули|развели|кинули|обокрали)\b",
    r"\bу\s+меня\s+(?:украли|заблокировали|пропали)\b",
    r"\bу\s+меня\s+(?:не\s+выводят|заблокирован\s+вывод|заблокировали\s+вывод)\b",
    r"\bя\s+не\s+могу\s+вывести\b",
    r"\bмне\s+не\s+(?:дают|могут)\s+вывести\b",
    r"\bпомогите\s+(?:вернуть|забрать)\s+(?:мои\s+)?(?:деньги|средства)\b",
    r"\bich\s+(?:habe|hatte)\b.{0,100}\b(?:verloren|investiert|bezahlt|überwiesen)\b",
    r"\bich\s+wurde\s+(?:betrogen|abgezockt)\b",
    r"\bich\s+(?:habe|kann)\b.{0,100}\b(?:mein|meine)\s+(?:geld|auszahlung)\b",
    r"\bmir\s+wurde\b.{0,100}\b(?:geld|konto|auszahlung)\b",
    r"\bich\s+kann\s+(?:mein\s+)?geld\s+nicht\s+(?:auszahlen|abheben)\b",
    r"\bich\s+bekomme\s+mein\s+geld\s+nicht\s+zur[üu]ck\b",
    r"\bich\s+brauche\s+(?:hilfe|einen\s+anwalt|rechtliche\s+hilfe)\b",
    r"\bi\s+(?:lost|have\s+lost)\s+(?:my\s+)?(?:money|funds|savings)\b",
    r"\bi\s+(?:invested|transferred|sent)\b.{0,100}\b(?:money|funds|deposit)\b",
    r"\bi\s+was\s+(?:scammed|defrauded)\b",
    r"\bi\s+(?:can't|cannot|am\s+unable\s+to)\s+withdraw\b",
    r"\bi\s+(?:need|want)\b.{0,80}\b(?:get\s+my\s+money\s+back|legal\s+help|a\s+lawyer)\b",
)


def has_direct_victim_language(text: str) -> bool:
    normalized = text.lower().replace("ё", "е")
    return any(re.search(pattern, normalized, flags=re.I | re.S) for pattern in PERSONAL_VICTIM_PATTERNS)


def classify(text: str, url: str | None = None, source: str = "public") -> CandidateClass:
    kind = source_kind(url, text) if source == "gmail:google-alerts" else source
    direct = has_direct_victim_language(text)

    if kind in {"legal", "news", "article"}:
        return CandidateClass("intelligence", kind, direct, (f"non-user source: {kind}",))
    if kind == "unknown":
        return CandidateClass("ignore", kind, direct, ("source is not an approved user-generated channel",))
    if not direct:
        return CandidateClass("ignore", kind, False, ("no direct first-person victim signal",))
    return CandidateClass("lead", kind, True, ("direct first-person victim signal from user-generated source",))
