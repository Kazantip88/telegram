from __future__ import annotations

import asyncio
import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .db import fingerprint, save_lead
from .detector import detect
from .emailer import build_message, send_message
from .scoring import score_lead


@dataclass(frozen=True)
class FacebookStats:
    queries: int = 0
    items: int = 0
    personal: int = 0
    qualified: int = 0
    hot: int = 0
    normal: int = 0


_PERSONAL = (
    r"\bich\s+(?:habe|hatte)\s+(?:mein(?:e|en)?\s+)?(?:geld|ersparnisse|mittel)\s+(?:verloren|investiert|überwiesen|bezahlt)\b",
    r"\bich\s+wurde\s+betrogen\b",
    r"\bich\s+kann\s+mein\s+geld\s+nicht\s+(?:auszahlen|abheben)\b",
    r"\bich\s+bekomme\s+mein\s+geld\s+nicht\s+zurück\b",
    r"\bich\s+brauche\s+(?:hilfe|einen\s+anwalt|rechtliche\s+hilfe)\b",
)

_COUNTRY_HINTS = {
    "DE": ("Deutschland", "Germany"),
    "AT": ("Österreich", "Austria"),
    "CH": ("Schweiz", "Switzerland"),
    "LU": ("Luxemburg", "Luxembourg"),
    "BE": ("Belgien", "Belgium"),
    "NL": ("Niederlande", "Netherlands"),
}


def _clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(value.split())


def _child(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag in names:
            return _clean("".join(child.itertext()))
    return ""


def _link(node: ET.Element) -> str:
    for child in list(node):
        if child.tag.rsplit("}", 1)[-1].lower() == "link":
            return (child.attrib.get("href") or _clean("".join(child.itertext()))).strip()
    return ""


def _items(payload: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(payload)
    result: list[dict[str, str]] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() not in {"item", "entry"}:
            continue
        title = _child(node, ("title",))
        summary = _child(node, ("description", "summary", "content"))
        author = _child(node, ("author", "creator", "name"))
        link = _link(node)
        if title or summary:
            result.append({"title": title, "summary": summary, "author": author, "link": link})
    return result


def _is_facebook(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    return host in {"facebook.com", "m.facebook.com"} or host.endswith(".facebook.com")


def _personal(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in _PERSONAL)


def _public_profile_id(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    value = params.get("id", [""])[0]
    return value if value.isdigit() else None


def _country(query: str) -> str:
    upper = query.upper()
    for code in _COUNTRY_HINTS:
        if f"[{code}]" in upper:
            return code
    return "DE"


def _fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LawLegal-Public-Lead-Monitor/1.0 (read-only public search)",
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _query_url(query: str) -> str:
    country = _country(query)
    gl = country if country in {"DE", "AT", "CH", "BE", "NL"} else "LU"
    q = query.replace(f"[{country}]", "").strip()
    params = urllib.parse.urlencode({"q": f"site:facebook.com {q}", "hl": "de", "gl": gl, "ceid": f"{gl}:de"})
    return f"https://news.google.com/rss/search?{params}"


async def collect_once(settings) -> FacebookStats:
    if not settings.facebook_enabled or not settings.facebook_queries:
        return FacebookStats()

    stats = FacebookStats(queries=len(settings.facebook_queries))
    for query in settings.facebook_queries:
        try:
            payload = await asyncio.to_thread(_fetch, _query_url(query), settings.rss_timeout_seconds)
            items = _items(payload)[: settings.facebook_max_items]
            stats = FacebookStats(stats.queries, stats.items + len(items), stats.personal, stats.qualified, stats.hot, stats.normal)
            for item in items:
                if not _is_facebook(item.get("link", "")):
                    continue
                text = " — ".join(x for x in (item.get("title"), item.get("summary")) if x).strip()
                if not _personal(text):
                    continue
                stats = FacebookStats(stats.queries, stats.items, stats.personal + 1, stats.qualified, stats.hot, stats.normal)
                signals = detect(text)
                result = score_lead(signals)
                if result.total < settings.min_email_score:
                    continue

                source_url = item.get("link") or _query_url(query)
                profile_id = _public_profile_id(source_url)
                public_name = item.get("author") or None
                reasons = list(result.reasons)
                reasons.append(f"source_url={source_url}")
                reasons.append(f"facebook_target_country={_country(query)}")
                if public_name:
                    reasons.append(f"public_name={public_name}")
                if profile_id:
                    reasons.append(f"public_facebook_id={profile_id}")

                lead = {
                    "fingerprint": fingerprint("facebook:public", source_url, text),
                    "telegram_message_id": None,
                    "source": "facebook:public",
                    "sender_id": profile_id,
                    "public_id": profile_id,
                    "public_name": public_name,
                    "username": public_name,
                    "source_url": source_url,
                    "language": signals.language,
                    "amount": max(signals.amounts) if signals.amounts else None,
                    "score": result.total,
                    "priority": result.priority,
                    "category": "CRYPTO" if any(x in text.lower() for x in ("krypto", "bitcoin")) else "INVESTMENT_SCAM",
                    "message": text,
                    "reasons": reasons,
                }
                if not await save_lead(settings.db_path, lead):
                    continue
                await send_message(settings, build_message(settings, lead))
                if result.priority == "HOT":
                    stats = FacebookStats(stats.queries, stats.items, stats.personal, stats.qualified + 1, stats.hot + 1, stats.normal)
                else:
                    stats = FacebookStats(stats.queries, stats.items, stats.personal, stats.qualified + 1, stats.hot, stats.normal + 1)
        except Exception as exc:
            print(f"Facebook public search failed for {query!r}: {exc}")

    return stats
