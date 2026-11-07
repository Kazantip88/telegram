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
    "spiegel.de", "faz.net", "welt.de", "bild.de", "handelsblatt.com", "theguardian.com",
    "bbc.com", "bbc.co.uk", "cnn.com", "reuters.com", "apnews.com", "nytimes.com",
}
USER_GENERATED_HOSTS = {
    "quora.com", "gutefrage.net", "reddit.com", "pikabu.ru", "stackexchange.com",
    "finanzfrage.net", "x.com", "twitter.com",
}


@dataclass(frozen=True)
class CandidateClass:
    kind: str
    source_kind: str
    direct_victim: bool
    financial_context: bool
    help_request: bool
    reasons: tuple[str, ...]


def _host(url: str | None) -> str:
    if not url:
        return ""
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _is_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def source_kind(url: str | None, text: str = "") -> str:
    host = _host(url)
    path = urlparse(url).path.lower() if url else ""
    if any(_is_domain(host, domain) for domain in LEGAL_HOSTS) or "/rechtstipps/" in path:
        return "legal"
    if any(_is_domain(host, domain) for domain in NEWS_HOSTS):
        return "news"
    if any(_is_domain(host, domain) for domain in ("x.com", "twitter.com")):
        return "user_generated" if re.search(r"/status/\d+(?:/|$)", path) else "unknown"
    if _is_domain(host, "banki.ru") and path.startswith("/forum/"):
        return "user_generated"
    if any(_is_domain(host, domain) for domain in USER_GENERATED_HOSTS):
        return "user_generated"
    if any(marker in path for marker in ("/news/", "/article/", "/reviews", "/review/", "/otzyv", "/otzyvy", "/press/")):
        return "article"
    return "unknown"


PERSONAL_VICTIM_PATTERNS = (
    r"\bя\s+(?:потерял|потеряла)\b",
    r"\bя\s+(?:вложил|вложила|инвестировал|инвестировала|перевел|перевела|отправил|отправила)\b.{0,140}\b(?:деньги|средства|депозит|евро|доллар|крипто|руб)",
    r"\bменя\s+(?:обманули|развели|кинули|обокрали)\b",
    r"\bу\s+меня\s+(?:украли|заблокировали|пропали|не\s+выводят)\b",
    r"\bя\s+не\s+могу\s+вывести\b",
    r"\bмне\s+не\s+(?:дают|могут)\s+вывести\b",
    r"\bich\s+(?:habe|hatte)\b.{0,140}\b(?:geld|ersparnisse|euro|investment|einzahlung|konto)\b.{0,140}\b(?:verloren|investiert|bezahlt|überwiesen|weg)\b",
    r"\bich\s+wurde\s+(?:betrogen|abgezockt|getäuscht)\b",
    r"\bich\s+kann\s+(?:mein\s+)?geld\s+nicht\s+(?:auszahlen|abheben)\b",
    r"\bich\s+bekomme\s+mein\s+geld\s+nicht\s+zurück\b",
    r"\bmir\s+wurde\b.{0,120}\b(?:geld|konto|auszahlung)\b",
    r"\bi\s+(?:lost|have\s+lost)\s+(?:my\s+)?(?:money|funds|savings|investment)\b",
    r"\bi\s+(?:invested|transferred|sent|paid)\b.{0,140}\b(?:money|funds|deposit|crypto)\b",
    r"\bi\s+(?:was\s+)?(?:scammed|defrauded)\b",
    r"\bthey\s+(?:stole|took)\s+(?:my\s+)?(?:money|savings|funds)\b",
    r"\bi\s+(?:can't|cannot|am\s+unable\s+to)\s+withdraw\b",
    r"\bmy\s+withdrawal\s+(?:is\s+)?blocked\b",
    r"\bik\s+(?:ben|werd)\s+opgelicht\b",
    r"\bik\s+heb\b.{0,100}\b(?:geld|spaargeld|belegging)\b.{0,100}\b(?:verloren|overgemaakt|betaald)\b",
    r"\bik\s+kan\s+mijn\s+geld\s+niet\s+(?:opnemen|terugkrijgen)\b",
    r"\bmijn\s+(?:geld|opname)\s+is\s+(?:weg|geblokkeerd)\b",
    r"\bze\s+hebben\s+mijn\s+geld\s+gestolen\b",
)

FINANCIAL_CONTEXT_PATTERNS = (
    r"\b(?:деньг|средств|руб|евро|доллар|депозит|брокер|бирж|инвест|крипто|биткоин|форекс|трейд|вывод|банк|карт|перевод)\w*\b",
    r"\b(?:geld|ersparnis|euro|dollar|konto|broker|börse|investment|anlage|krypto|bitcoin|forex|trading|auszahlung|bank|überweisung)\w*\b",
    r"\b(?:money|funds|savings|deposit|broker|exchange|investment|crypto|bitcoin|forex|trading|withdraw|bank|transfer|card|payment|dollars|euros)\b",
    r"\b(?:geld|spaargeld|euro|rekening|broker|belegging|crypto|bitcoin|forex|trading|opname|uitbetaling|bank|overboeking|betaling)\b",
)

HELP_REQUEST_PATTERNS = (
    r"\b(?:помогите|нужна\s+помощь|ищу\s+помощь|подскажите|что\s+(?:мне\s+)?делать|куда\s+обращаться|кто\s+может\s+помочь|посоветуйте)\b",
    r"\b(?:нужен|ищу)\s+(?:юрист|адвокат)\b",
    r"\bкак\s+(?:вернуть|взыскать)\s+(?:мои\s+)?(?:деньги|средства)\b",
    r"\b(?:ich\s+brauche\s+hilfe|ich\s+suche\s+(?:einen\s+)?anwalt|was\s+kann\s+ich\s+tun|kann\s+mir\s+jemand\s+helfen|bitte\s+um\s+rat|wer\s+kann\s+helfen|anwalt\s+empfehlen|rechtliche\s+hilfe)\b",
    r"\b(?:i\s+need\s+help|please\s+help|need\s+a\s+lawyer|looking\s+for\s+a\s+lawyer|what\s+can\s+i\s+do|any\s+advice|can\s+anyone\s+help|seeking\s+legal\s+advice|recommend\s+a\s+lawyer|who\s+can\s+help|how\s+can\s+i\s+recover)\b",
    r"\b(?:ik\s+heb\s+hulp\s+nodig|ik\s+zoek\s+(?:een\s+)?advocaat|wat\s+kan\s+ik\s+doen|kan\s+iemand\s+mij\s+helpen|advies\s+gevraagd|juridische\s+hulp|hoe\s+krijg\s+ik\s+mijn\s+geld\s+terug)\b",
)


def has_direct_victim_language(text: str) -> bool:
    normalized = text.lower().replace("ё", "е")
    return any(re.search(pattern, normalized, flags=re.I | re.S) for pattern in PERSONAL_VICTIM_PATTERNS)


def has_help_request(text: str) -> bool:
    normalized = text.lower().replace("ё", "е")
    return any(re.search(pattern, normalized, flags=re.I | re.S) for pattern in HELP_REQUEST_PATTERNS)


def has_financial_context(text: str) -> bool:
    normalized = text.lower().replace("ё", "е")
    return any(re.search(pattern, normalized, flags=re.I | re.S) for pattern in FINANCIAL_CONTEXT_PATTERNS)


def classify(text: str, url: str | None = None, source: str = "public") -> CandidateClass:
    kind = source_kind(url, text) if source in {"gmail:google-alerts", "rss:public", "x:api"} else source
    direct = has_direct_victim_language(text)
    financial = has_financial_context(text)
    asks_for_help = has_help_request(text)

    if kind in {"legal", "news", "article"}:
        return CandidateClass("intelligence", kind, direct, financial, asks_for_help, (f"non-user source: {kind}",))
    if kind not in {"user_generated", "telegram"}:
        return CandidateClass("ignore", kind, direct, financial, asks_for_help, ("source is not an approved public user-generated discussion",))

    host = _host(url)
    path = urlparse(url).path.lower() if url else ""
    if _is_domain(host, "reddit.com") and "/comments/" not in path:
        return CandidateClass("ignore", kind, direct, financial, asks_for_help, ("Reddit result is not a direct post permalink",))
    if (_is_domain(host, "x.com") or _is_domain(host, "twitter.com")) and not re.search(r"/status/\d+(?:/|$)", path):
        return CandidateClass("ignore", kind, direct, financial, asks_for_help, ("X result is not a direct public post permalink",))
    if not direct:
        return CandidateClass("ignore", kind, False, financial, asks_for_help, ("no first-person report of the author's own loss",))
    if not financial:
        return CandidateClass("ignore", kind, True, False, asks_for_help, ("no explicit financial-loss context",))
    if not asks_for_help:
        return CandidateClass("ignore", kind, True, True, False, ("no explicit request for help, advice, or legal assistance",))
    return CandidateClass(
        "lead",
        kind,
        True,
        True,
        True,
        ("first-person financial-loss report", "explicit request for help/advice"),
    )
