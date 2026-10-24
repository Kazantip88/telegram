from __future__ import annotations

import asyncio
import base64
import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .config import load_settings
from .db import fingerprint, save_lead
from .detector import detect
from .emailer import build_message, send_message
from .scoring import score_lead


@dataclass(frozen=True)
class FacebookStats:
    queries: int = 0
    search_results: int = 0
    items: int = 0
    facebook: int = 0
    author: int = 0
    direct_posts: int = 0
    personal: int = 0
    qualified: int = 0
    duplicates: int = 0
    hot: int = 0
    normal: int = 0


_PERSONAL = (
    r"\bich\s+(?:habe|hatte)\b.{0,220}\b(?:geld|ersparnisse|euro|investition|investment|einzahlung|depot|konto)\b.{0,180}\b(?:verloren|weg|nicht\s+zurück|nicht\s+auszahlen|nicht\s+abheben|investiert|überwiesen|bezahlt)\b",
    r"\bich\s+wurde\s+(?:betrogen|abgezockt|getäuscht|beraubt)\b",
    r"\b(?:ich|wir)\s+(?:haben|habe)\b.{0,180}\b(?:geld|euro|krypto|bitcoin|trading)\b.{0,180}\b(?:verloren|weg|betrogen)\b",
    r"\bmir\s+wurde\b.{0,150}\b(?:geld|auszahlung|konto|einzahlung)\b",
    r"\bich\s+kann\s+mein\s+geld\s+nicht\s+(?:auszahlen|abheben|zurückbekommen)\b",
    r"\bich\s+bekomme\s+mein\s+geld\s+nicht\s+zurück\b",
    r"\bi\s+(?:lost|lose|have\s+lost)\b.{0,180}\b(?:money|funds|crypto|bitcoin|investment)\b",
    r"\bi\s+was\s+(?:scammed|defrauded)\b",
    r"\bmy\s+money\b.{0,120}\b(?:withdraw|withdrawal|back)\b",
    r"\bя\s+(?:потерял|потеряла|потеряли)\b.{0,180}\b(?:деньги|руб|евро|крипто|инвести)\b",
    r"\bменя\s+(?:обманули|обокрали)\b.{0,120}\b(?:брокер|крипто|инвест|деньги)\b",
    r"\bне\s+могу\s+(?:вывести|получить\s+назад)\b.{0,120}\b(?:деньги|средства|депозит)\b",
)

_EXPLICIT_LOSS = _PERSONAL
_BLOCKED_HOSTS = {"anwalt.de", "anwalt24.de", "banki.ru", "broker-betrug.de", "kryptoschaden.de", "betrugsopfer-hilfe.de", "telltrue.net", "fxidea.com", "finanzfrage.net"}
_BLOCKED_PATH_MARKERS = ("/ratgeber/", "/rechtstipps/", "/magazin/", "/news/", "/article/", "/reviews", "/review/", "/otzyv", "/otzyvy", "/warnung/", "/blog/", "/presse/", "/press/")
_DIRECT_FACEBOOK_MARKERS = ("/posts/", "/permalink/", "/story.php", "/permalink.php", "/photo.php", "/share/p/", "/share/v/", "/share/r/", "/share/")


def _clean(value: str) -> str:
    value = html.unescape(value or "")
    for _ in range(2):
        value = value.replace("\\\\/", "/").replace("\\/", "/")
        value = value.replace("\\\\u002F", "/").replace("\\u002F", "/")
        value = value.replace("\\\\u003A", ":").replace("\\u003A", ":")
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(value.split())


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _is_facebook(url: str) -> bool:
    host = _host(url)
    return host == "facebook.com" or host.endswith(".facebook.com")


def _blocked_source(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    return host in _BLOCKED_HOSTS or any(marker in parsed.path.lower() for marker in _BLOCKED_PATH_MARKERS)


def _direct_post(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if not _is_facebook(url):
        return False
    path = parsed.path.lower()
    query = parsed.query.lower()
    if "/groups/" in path:
        return "/posts/" in path or "/permalink" in path or "story_fbid=" in query
    return any(marker in path for marker in _DIRECT_FACEBOOK_MARKERS)


def _personal(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.I | re.S) for pattern in _PERSONAL)


def _explicit_loss(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.I | re.S) for pattern in _EXPLICIT_LOSS)


def _country(query: str) -> str:
    match = re.search(r"\[([A-Z]{2})\]", query.upper())
    return match.group(1) if match else "DE"


def _fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _query_urls(query: str) -> list[str]:
    country = _country(query)
    q = query.replace(f"[{country}]", "").strip()
    base = f"site:facebook.com ({q}) -site:anwalt.de -site:anwalt24.de -site:banki.ru"
    encoded = urllib.parse.quote_plus(base)
    return [
        f"https://www.bing.com/search?format=rss&q={encoded}&setlang=de",
        f"https://www.bing.com/search?q={encoded}&setlang=de",
        f"https://www.google.com/search?q={encoded}&hl=de&num=20",
        f"https://html.duckduckgo.com/html/?q={encoded}&kl=de-de",
    ]


def _extract_author(text: str) -> str:
    text = _clean(text)
    for pattern in (r"^(.{2,80}?)\s*[|–—-]\s*Facebook", r"^(.{2,80}?)\s+on\s+Facebook"):
        match = re.search(pattern, text, flags=re.I)
        if match:
            candidate = _clean(match.group(1))
            lowered = candidate.lower()
            blocked = ("betrüger", "betrug", "scam", "fraud", "community", "gruppe", "group", "warnung", "hilfe", "marketplace", "kleinanzeigen")
            if candidate and not lowered.startswith(("www.", "http", "site:")) and not any(term in lowered for term in blocked):
                return candidate
    return ""


def _decode_result_url(raw: str) -> str:
    candidate = _clean(raw).strip(" '\"")
    for _ in range(4):
        parsed = urllib.parse.urlparse(candidate)
        host = parsed.netloc.lower()
        if candidate.startswith("//"):
            candidate = "https:" + candidate
            continue
        if parsed.path == "/url":
            values = urllib.parse.parse_qs(parsed.query)
            candidate = values.get("q", values.get("url", [candidate]))[0]
            continue
        if host.endswith("duckduckgo.com"):
            candidate = urllib.parse.parse_qs(parsed.query).get("uddg", [candidate])[0]
            continue
        if host.endswith("bing.com") and parsed.path.startswith("/ck/a"):
            encoded = urllib.parse.parse_qs(parsed.query).get("u", [""])[0]
            if encoded.startswith("a1"):
                try:
                    padded = encoded[2:] + "=" * (-len(encoded[2:]) % 4)
                    candidate = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
                    continue
                except Exception:
                    pass
            candidate = urllib.parse.parse_qs(parsed.query).get("url", [candidate])[0]
            continue
        break
    return _clean(urllib.parse.unquote(candidate))


def _append_result(result: list[dict[str, str]], seen: set[str], link: str, title: str, summary: str) -> None:
    candidate = _decode_result_url(link)
    if not _is_facebook(candidate):
        return
    canonical = candidate.split("#", 1)[0].rstrip("/").lower()
    if canonical in seen:
        return
    seen.add(canonical)
    clean_title = _clean(title) or "Facebook public result"
    result.append({"title": clean_title, "summary": _clean(summary)[:1600], "author": _extract_author(clean_title), "link": candidate})


def _search_links(payload: bytes) -> list[dict[str, str]]:
    text = html.unescape(payload.decode("utf-8", errors="ignore"))
    for _ in range(2):
        text = text.replace("\\\\/", "/").replace("\\/", "/")
        text = text.replace("\\\\u002F", "/").replace("\\u002F", "/")
        text = text.replace("\\\\u003A", ":").replace("\\u003A", ":")
    result: list[dict[str, str]] = []
    seen: set[str] = set()

    # RSS result items.
    if "<item>" in text.lower() and ("<rss" in text.lower() or "<channel" in text.lower()):
        for match in re.finditer(r"<item>(.*?)</item>", text, flags=re.I | re.S):
            item = match.group(1)
            link = re.search(r"<link>(.*?)</link>", item, flags=re.I | re.S)
            if not link:
                continue
            title = re.search(r"<title>(.*?)</title>", item, flags=re.I | re.S)
            desc = re.search(r"<description>(.*?)</description>", item, flags=re.I | re.S)
            _append_result(result, seen, link.group(1), title.group(1) if title else "Facebook public result", desc.group(1) if desc else "")

    # Search-engine result anchors (Bing b_algo, Google, DuckDuckGo).
    for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, flags=re.I | re.S):
        raw, title_html = match.groups()
        _append_result(result, seen, raw, title_html, text[match.end():match.end() + 3500])

    # data-href/data-url targets.
    for match in re.finditer(r'(?:data-href|data-url)=["\']([^"\']+)["\']', text, flags=re.I):
        _append_result(result, seen, match.group(1), "Facebook public result", text[max(0, match.start() - 800):match.end() + 2200])

    # Facebook URLs embedded in JSON/script. Stop only at JSON/string delimiters, not at '/'.
    for match in re.finditer(r'https?://(?:www\.)?facebook\.com/[A-Za-z0-9_./?=&%+\-]+', text, flags=re.I):
        _append_result(result, seen, match.group(0), "Facebook public result", text[max(0, match.start() - 800):match.end() + 1600])

    return result


async def collect_once(settings) -> FacebookStats:
    if not settings.facebook_enabled or not settings.facebook_queries:
        return FacebookStats()
    stats = FacebookStats(queries=len(settings.facebook_queries))
    seen_urls: set[str] = set()
    for query in settings.facebook_queries:
        for query_url in _query_urls(query):
            try:
                payload = await asyncio.to_thread(_fetch, query_url, settings.rss_timeout_seconds)
                items = _search_links(payload)[: settings.facebook_max_items]
                stats = FacebookStats(stats.queries, stats.search_results + len(items), stats.items + len(items), stats.facebook, stats.author, stats.direct_posts, stats.personal, stats.qualified, stats.duplicates, stats.hot, stats.normal)
                for item in items:
                    source_url = item.get("link", "")
                    if not source_url or source_url in seen_urls or _blocked_source(source_url):
                        continue
                    seen_urls.add(source_url)
                    stats = FacebookStats(stats.queries, stats.search_results, stats.items, stats.facebook + 1, stats.author, stats.direct_posts, stats.personal, stats.qualified, stats.duplicates, stats.hot, stats.normal)
                    public_author = item.get("author", "").strip()
                    if public_author:
                        stats = FacebookStats(stats.queries, stats.search_results, stats.items, stats.facebook, stats.author + 1, stats.direct_posts, stats.personal, stats.qualified, stats.duplicates, stats.hot, stats.normal)
                    if not _direct_post(source_url):
                        continue
                    stats = FacebookStats(stats.queries, stats.search_results, stats.items, stats.facebook, stats.author, stats.direct_posts + 1, stats.personal, stats.qualified, stats.duplicates, stats.hot, stats.normal)
                    text = " — ".join(x for x in (item.get("title"), item.get("summary")) if x).strip()
                    if not _personal(text) or not _explicit_loss(text):
                        continue
                    stats = FacebookStats(stats.queries, stats.search_results, stats.items, stats.facebook, stats.author, stats.direct_posts, stats.personal + 1, stats.qualified, stats.duplicates, stats.hot, stats.normal)
                    signals = detect(text)
                    score = score_lead(signals)
                    if score.total < settings.min_email_score:
                        print(f"Facebook candidate held for review: score={score.total} below threshold={settings.min_email_score} url={source_url}")
                        continue
                    reasons = list(score.reasons) + [f"source_url={source_url}", f"facebook_target_country={_country(query)}", f"public_author={public_author or 'not exposed in search result'}"]
                    lead = {
                        "fingerprint": fingerprint("facebook:public", source_url, text),
                        "telegram_message_id": None, "source": "facebook:public", "sender_id": None,
                        "public_id": None, "public_name": public_author or None, "username": public_author or None,
                        "source_url": source_url, "language": signals.language,
                        "amount": max(signals.amounts) if signals.amounts else None,
                        "score": score.total, "priority": score.priority,
                        "category": "CRYPTO" if any(x in text.lower() for x in ("krypto", "bitcoin", "btc", "crypto")) else "INVESTMENT_SCAM",
                        "message": text, "reasons": reasons,
                    }
                    saved = await save_lead(settings.db_path, lead)
                    print(f"Facebook personal candidate: author={public_author!r} score={score.total} priority={score.priority} duplicate={'no' if saved else 'yes'} url={source_url}")
                    if not saved:
                        stats = FacebookStats(stats.queries, stats.search_results, stats.items, stats.facebook, stats.author, stats.direct_posts, stats.personal, stats.qualified, stats.duplicates + 1, stats.hot, stats.normal)
                        continue
                    await send_message(settings, build_message(settings, lead))
                    if score.priority == "HOT":
                        stats = FacebookStats(stats.queries, stats.search_results, stats.items, stats.facebook, stats.author, stats.direct_posts, stats.personal, stats.qualified + 1, stats.duplicates, stats.hot + 1, stats.normal)
                    else:
                        stats = FacebookStats(stats.queries, stats.search_results, stats.items, stats.facebook, stats.author, stats.direct_posts, stats.personal, stats.qualified + 1, stats.duplicates, stats.hot, stats.normal + 1)
            except Exception as exc:
                print(f"Facebook public search failed for {query_url!r}: {exc}")
    print(f"Facebook search diagnostics: queries={stats.queries} search_results={stats.search_results} facebook_urls={stats.facebook} direct_posts={stats.direct_posts} personal={stats.personal} qualified={stats.qualified}")
    return stats


async def main() -> None:
    settings = load_settings(require_telegram=False)
    stats = await collect_once(settings)
    print(f"Facebook public test: queries={stats.queries} search_results={stats.search_results} items={stats.items} facebook={stats.facebook} author={stats.author} direct_posts={stats.direct_posts} personal={stats.personal} qualified={stats.qualified} duplicates={stats.duplicates} hot={stats.hot} normal={stats.normal}")


if __name__ == "__main__":
    asyncio.run(main())
