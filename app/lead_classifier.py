from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


# Google Alerts frequently surfaces legal SEO pages and news articles that contain
# exactly the same words as a real victim. Source classification MUST happen
# before lead scoring.
LEGAL_HOSTS = {
    "anwalt.de",
    "anwalt24.de",
    "broker-betrug.de",
    "kryptoschaden.de",
    "betrugsopfer-hilfe.de",
}

NEWS_HOSTS = {
    "dw.com",
    "amp.dw.com",
    "postimees.ee",
    "rus.postimees.ee",
    "tass.ru",
    "ria.ru",
    "rbc.ru",
    "kommersant.ru",
    "lenta.ru",
    "gazeta.ru",
    "interfax.ru",
    "forbes.ru",
    "focus.de",
    "spiegel.de",
    "faz.net",
    "welt.de",
    "bild.de",
}

LEGAL_MARKERS = (
    "anwalt",
    "rechtsanwalt",
    "rechtsberatung",
    "rechtstipp",
    "kostenfreie ersteinschätzung",
    "kostenlose ersteinschätzung",
    "rechtliche hilfe",
    "juristische hilfe",
    "ansprüche",
    "anspruchsgegner",
    "kanzlei",
)

NEWS_MARKERS = (
    "nachrichten",
    "news",
    "колл-цент",
    "жертва может",
    "объясняет",
    "сообщает",
)


@dataclass(frozen=True)
class CandidateClass:
    # lead: eligible for normal lead scoring
    # intelligence: useful scam/news/legal information, but not a client lead
    # ignore: no reliable victim intent
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
    lowered = text.lower()

    if host in LEGAL_HOSTS or "/rechtstipps/" in path or "anwalt.de" in host or "anwalt24.de" in host:
        return "legal"
    if host in NEWS_HOSTS or any(marker in lowered for marker in NEWS_MARKERS):
        return "news"
    if any(marker in lowered for marker in LEGAL_MARKERS):
        return "legal"
    if any(marker in path for marker in ("/news/", "/article/", "/reviews", "/review/", "/otzyv", "/otzyvy")):
        return "article"
    return "public"


# These patterns are intentionally about the speaker's own experience.
# Generic phrases such as "victims lost money" or "people want their money back"
# do NOT qualify.
PERSONAL_VICTIM_PATTERNS = (
    # Russian
    r"\bя\s+(?:потерял|потеряла)\b",
    r"\bя\s+(?:вложил|вложила|инвестировал|инвестировала)\b",
    r"\bя\s+(?:перевел|перевела|отправил|отправила)\b.{0,100}\b(?:деньги|средства|депозит|евро|доллар)",
    r"\bменя\s+(?:обманули|развели|кинули|обокрали)\b",
    r"\bу\s+меня\s+(?:украли|заблокировали|пропали)\b",
    r"\bу\s+меня\s+(?:не\s+выводят|заблокирован\s+вывод|заблокировали\s+вывод)\b",
    r"\bя\s+не\s+могу\s+вывести\b",
    r"\bмне\s+не\s+(?:дают|могут)\s+вывести\b",
    r"\bпомогите\s+(?:вернуть|забрать)\s+(?:мои\s+)?(?:деньги|средства)\b",
    # German
    r"\bich\s+(?:habe|hatte)\b.{0,100}\b(?:verloren|investiert|bezahlt|überwiesen)\b",
    r"\bich\s+wurde\s+(?:betrogen|abgezockt)\b",
    r"\bich\s+(?:habe|kann)\b.{0,100}\b(?:mein|meine)\s+(?:geld|auszahlung)\b",
    r"\bmir\s+wurde\b.{0,100}\b(?:geld|konto|auszahlung)\b",
    r"\bich\s+kann\s+(?:mein\s+)?geld\s+nicht\s+(?:auszahlen|abheben)\b",
    r"\bich\s+bekomme\s+mein\s+geld\s+nicht\s+zur[üu]ck\b",
    r"\bich\s+brauche\s+(?:hilfe|einen\s+anwalt|rechtliche\s+hilfe)\b",
    # English
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
    kind = source_kind(url, text) if source == "gmail:google-alerts" or url else source
    direct = has_direct_victim_language(text)

    if kind in {"legal", "news", "article"}:
        return CandidateClass(
            kind="intelligence",
            source_kind=kind,
            direct_victim=direct,
            reasons=(f"non-lead source: {kind}",),
        )

    if not direct:
        return CandidateClass(
            kind="ignore",
            source_kind=kind,
            direct_victim=False,
            reasons=("no direct first-person victim signal",),
        )

    return CandidateClass(
        kind="lead",
        source_kind=kind,
        direct_victim=True,
        reasons=("direct first-person victim signal",),
    )
