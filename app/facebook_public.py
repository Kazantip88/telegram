from __future__ import annotations

import asyncio
import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .config import load_settings
from .db import fingerprint, save_lead
from .detector import detect
from .emailer import build_message, send_message
from .scoring import score_lead


@dataclass(frozen=True)
class FacebookStats:
    queries: int = 0
    items: int = 0
    facebook: int = 0
    author: int = 0
    direct_posts: int = 0
    personal: int = 0
    qualified: int = 0
    hot: int = 0
    normal: int = 0


# Very narrow: first-person victim language only.
_PERSONAL = (
    r"\bich\s+(?:habe|hatte)\b.{0,160}\b(?:geld|ersparnisse|euro|€|investition|investment|einzahlung|depot)\b.{0,120}\b(?:verloren|weg|nicht\s+zurück|nicht\s+auszahlen|nicht\s+abheben|investiert|überwiesen|bezahlt)\b",
    r"\bich\s+wurde\s+(?:betrogen|abgezockt|getäuscht)\b",
    r"\bmir\s+wurde\b.{0,120}\b(?:geld|auszahlung|konto)\b",
    r"\bich\s+kann\s+mein\s+geld\s+nicht\s+(?:auszahlen|abheben|zurückbekommen)\b",
    r"\bich\s+bekomme\s+mein\s+geld\s+nicht\s+zurück\b",
    r"\bich\s+brauche\s+(?:hilfe|einen\s+anwalt|rechtliche\s+hilfe)\b.{0,120}\b(?:broker|geld|invest|krypto|trading)\b",
)

# Hard blacklist. These are never leads, even if they quote a real victim.
_BLOCKED_HOSTS = {
    "anwalt.de", "anwalt24.de", "banki.ru", "broker-betrug.de",
    "kryptoschaden.de", "betrugsopfer-hilfe.de", "telltrue.net",
    "fxidea.com", "finanzfrage.net",
}
_BLOCKED_PATH_MARKERS = (
    "/ratgeber/", "/rechtstipps/", "/magazin/", "/news/", "/article/",
    "/reviews", "/review/", "/otzyv", "/otzyvy", "/warnung/",
    "/blog/", "/presse/", "/press/",
)

# Only these Facebook URL shapes are accepted as a direct user post.
# Group/page/profile landing pages are rejected because they are not the
# original user message.
_DIRECT_FACEBOOK_MARKERS = (
    "/posts/", "/permalink/", "/groups/", "/story.php", "/photo.php",
)

_COUNTRY_HINTS = {"DE", "AT", "CH", "LU", "BE", "NL"}


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


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _is_facebook(url: str) -> bool:
    host = _host(url)
    return host == "facebook.com" or host.endswith(".facebook.com")


def _blocked_source(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    return host in _BLOCKED_HOSTS or any(marker in path for marker in _BLOCKED_PATH_MARKERS)


def _direct_post(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    return _is_facebook(url) and any(marker in path or marker in parsed.query.lower() for marker in _DIRECT_FACEBOOK_MARKERS)


def _personal(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.I | re.S) for pattern in _PERSONAL)


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
    # Search specifically for Facebook post URLs and exclude known article/SEO
    # domains. Google supports site: and -site: operators.
    q = (
        f"site:facebook.com ({q}) "
        "(post OR permalink OR \"story.php\") "
        "-site:anwalt24.de -site:anwalt.de -site:banki.ru "
        "-site:broker-betrug.de -site:telltrue.net -site:fxidea.com"
    )
    params = urllib.parse.urlencode({
        "q": q,
        "hl": "de",
        "gl": gl,
        "ceid": f"{gl}:de",
    })
    return f"https://news.google.com/rss/search?{params}"


async def collect_once(settings) -> FacebookStats:
    if not settings.facebook_enabled or not settings.facebook_queries:
        return FacebookStats()

    stats = FacebookStats(queries=len(settings.facebook_queries))
    for query in settings.facebook_queries:
        try:
            payload = await asyncio.to_thread(_fetch, _query_url(query), settings.rss_timeout_seconds)
            items = _items(payload)[: settings.facebook_max_items]
            stats = FacebookStats(
                stats.queries, stats.items + len(items), stats.facebook,
                stats.author, stats.direct_posts, stats.personal,
                stats.qualified, stats.hot, stats.normal,
            )
            for item in items:
                source_url = item.get("link", "")
                if _blocked_source(source_url):
                    continue
                if not _is_facebook(source_url):
                    continue
                stats = FacebookStats(
                    stats.queries, stats.items, stats.facebook + 1,
                    stats.author, stats.direct_posts, stats.personal,
                    stats.qualified, stats.hot, stats.normal,
                )

                # A result without a public author is not a lead.
                public_author = item.get("author", "").strip()
                if not public_author:
                    continue
                stats = FacebookStats(
                    stats.queries, stats.items, stats.facebook,
                    stats.author + 1, stats.direct_posts, stats.personal,
                    stats.qualified, stats.hot, stats.normal,
                )

                if not _direct_post(source_url):
                    continue
                stats = FacebookStats(
                    stats.queries, stats.items, stats.facebook,
                    stats.author, stats.direct_posts + 1, stats.personal,
                    stats.qualified, stats.hot, stats.normal,
                )

                text = " — ".join(x for x in (item.get("title"), item.get("summary")) if x).strip()
                if not _personal(text):
                    continue
                stats = FacebookStats(
                    stats.queries, stats.items, stats.facebook,
                    stats.author, stats.direct_posts, stats.personal + 1,
                    stats.qualified, stats.hot, stats.normal,
                )

                signals = detect(text)
                result = score_lead(signals)
                if result.total < settings.min_email_score:
                    continue

                reasons = list(result.reasons)
                reasons.append(f"source_url={source_url}")
                reasons.append(f"facebook_target_country={_country(query)}")
                reasons.append(f"public_author={public_author}")

                lead = {
                    "fingerprint": fingerprint("facebook:public", source_url, text),
                    "telegram_message_id": None,
                    "source": "facebook:public",
                    "sender_id": None,
                    "public_id": None,
                    "public_name": public_author,
                    "username": public_author,
                    "source_url": source_url,
                    "language": signals.language,
                    "amount": max(signals.amounts) if signals.amounts else None,
                    "score": result.total,
                    "priority": result.priority,
                    "category": "CRYPTO" if any(x in text.lower() for x in ("krypto", "bitcoin", "btc")) else "INVESTMENT_SCAM",
                    "message": text,
                    "reasons": reasons,
                }
                if not await save_lead(settings.db_path, lead):
                    continue
                await send_message(settings, build_message(settings, lead))
                if result.priority == "HOT":
                    stats = FacebookStats(stats.queries, stats.items, stats.facebook, stats.author, stats.direct_posts, stats.personal, stats.qualified + 1, stats.hot + 1, stats.normal)
                else:
                    stats = FacebookStats(stats.queries, stats.items, stats.facebook, stats.author, stats.direct_posts, stats.personal, stats.qualified + 1, stats.hot, stats.normal + 1)
        except Exception as exc:
            print(f"Facebook public search failed for {query!r}: {exc}")

    return stats


async def main() -> None:
    settings = load_settings(require_telegram=False)
    stats = await collect_once(settings)
    print(
        "Facebook public test: "
        f"queries={stats.queries} items={stats.items} facebook={stats.facebook} "
        f"author={stats.author} direct_posts={stats.direct_posts} personal={stats.personal} "
        f"qualified={stats.qualified} hot={stats.hot} normal={stats.normal}"
    )


if __name__ == "__main__":
    asyncio.run(main())
