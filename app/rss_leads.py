from __future__ import annotations

import asyncio
import html
import random
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlparse

from .db import fingerprint, save_lead
from .detector import detect
from .emailer import build_message, send_message
from .scoring import score_lead


@dataclass(frozen=True)
class RSSStats:
    feeds: int = 0
    items: int = 0
    personal_items: int = 0
    qualified: int = 0
    hot: int = 0
    normal: int = 0


_RU_PERSONAL = (
    r"\bя\s+(?:потерял|потеряла|вложил|вложила|инвестировал|инвестировала)\b",
    r"\bя\s+потерял(?:а)?\s+(?:деньги|сбережения|средства)\b",
    r"\bменя\s+(?:обманули|развели|обокрали)\b",
    r"\bу\s+меня\s+(?:украли|заблокировали|пропали|не\s+выводят)\b",
    r"\bу\s+меня\s+(?:заблокирован|заблокирована)\s+вывод\b",
    r"\bя\s+не\s+могу\s+вывести\s+(?:деньги|средства|свой\s+депозит|свои\s+деньги)\b",
)
_DE_PERSONAL = (
    r"\bich\s+(?:habe|hatte)\s+(?:mein(?:e|en)?\s+)?(?:geld|ersparnisse|mittel)\s+(?:verloren|investiert|bezahlt|überwiesen)\b",
    r"\bich\s+wurde\s+betrogen\b",
    r"\bmir\s+wurde\s+(?:geld|mein\s+konto|die\s+auszahlung)\b",
    r"\bich\s+kann\s+mein\s+geld\s+nicht\s+(?:auszahlen|abheben)\b",
    r"\bich\s+bekomme\s+mein\s+geld\s+nicht\s+zurück\b",
    r"\bich\s+brauche\s+(?:hilfe|einen\s+anwalt|rechtliche\s+hilfe)\b",
)
_EN_PERSONAL = (
    r"\bi\s+(?:lost|invested|deposited|transferred|paid)\b",
    r"\bi\s+(?:lost|invested)\s+(?:my\s+)?(?:money|savings|funds)\b",
    r"\bi\s+(?:was\s+)?scammed\b",
    r"\bi\s+was\s+defrauded\b",
    r"\bthey\s+(?:took|stole)\s+(?:my\s+)?money\b",
    r"\bi\s+(?:can't|cannot|can\s+not|am\s+unable\s+to)\s+(?:withdraw|cash\s*out)\b",
    r"\bmy\s+withdrawal\s+(?:is\s+)?blocked\b",
    r"\bi\s+(?:can't|cannot)\s+get\s+my\s+money\s+back\b",
    r"\bi\s+need\s+(?:a\s+lawyer|legal\s+help|help\s+getting\s+my\s+money\s+back)\b",
)


def _clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(value.split())


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return _clean("".join(el.itertext()))


def _first_child(parent: ET.Element, names: tuple[str, ...]) -> str:
    for child in list(parent):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag in names:
            if tag == "author":
                nested_name = _first_child(child, ("name",))
                if nested_name:
                    return nested_name
            return _text(child)
    return ""


def _link(item: ET.Element) -> str:
    for child in list(item):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag == "link":
            href = (child.attrib.get("href") or "").strip()
            if href:
                return href
            value = _text(child)
            if value:
                return value
    return ""


def _items(xml: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(xml)
    result: list[dict[str, str]] = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        if tag not in {"item", "entry"}:
            continue
        title = _first_child(node, ("title",))
        summary = _first_child(node, ("description", "summary", "content"))
        content = _first_child(node, ("content",))
        if content and content not in summary:
            summary = f"{summary} {content}".strip()
        link = _link(node)
        author = _first_child(node, ("author", "creator", "name"))
        if title or summary:
            result.append({"title": title, "summary": summary, "link": link, "author": author})
    return result


def _personal_victim_language(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in (*_RU_PERSONAL, *_DE_PERSONAL, *_EN_PERSONAL))


def _category(signals) -> str:
    investment = " ".join(signals.matched.get("investment", []))
    lowered = investment.lower()
    if any(x in lowered for x in ("crypto", "krypto", "bitcoin", "крипто", "биткоин")):
        return "CRYPTO"
    if any(x in lowered for x in ("forex", "форекс")):
        return "FOREX"
    if investment:
        return "INVESTMENT_SCAM"
    return "OTHER"


def _feed_label(url: str) -> str:
    parsed = urlparse(url)
    return f"rss:{parsed.netloc.lower()}" if parsed.netloc else "rss:unknown"


def _fetch_sync(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LawLegal-Public-Lead-Monitor/1.0 (+read-only RSS monitoring)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


async def _save_item(settings, feed_url: str, item: dict[str, str]):
    text = " — ".join(part for part in (item.get("title"), item.get("summary")) if part).strip()
    if not text or not _personal_victim_language(text):
        return None

    signals = detect(text)
    result = score_lead(signals)
    if result.total < settings.min_email_score:
        return None

    source = _feed_label(feed_url)
    source_url = item.get("link") or feed_url
    reasons = list(result.reasons)
    reasons.append(f"source_url={source_url}")
    if item.get("author"):
        reasons.append(f"public_author={item['author']}")

    lead = {
        "fingerprint": fingerprint(source, item.get("author") or None, text),
        "telegram_message_id": None,
        "source": source,
        "sender_id": None,
        "username": item.get("author") or None,
        "public_name": item.get("author") or None,
        "source_url": source_url,
        "language": signals.language,
        "amount": max(signals.amounts) if signals.amounts else None,
        "score": result.total,
        "priority": result.priority,
        "category": _category(signals),
        "message": text,
        "reasons": reasons,
    }
    inserted = await save_lead(settings.db_path, lead)
    if not inserted:
        return None

    msg = build_message(settings, lead)
    print("\n=== QUALIFIED RSS LEAD ===")
    print(msg.as_string())
    print("=== END RSS LEAD ===\n")
    await send_message(settings, msg)
    return result.priority


async def collect_once(settings) -> RSSStats:
    feeds = settings.rss_feeds
    if not feeds:
        return RSSStats()

    items = personal = qualified = hot = normal = 0
    for index, feed_url in enumerate(feeds):
        if index:
            delay = settings.rss_request_delay_seconds
            if settings.jitter_seconds:
                delay += random.uniform(0, settings.jitter_seconds)
            if delay > 0:
                await asyncio.sleep(delay)
        try:
            payload = await asyncio.to_thread(_fetch_sync, feed_url, settings.rss_timeout_seconds)
            feed_items = _items(payload)[: settings.rss_max_items]
            items += len(feed_items)
            for item in feed_items:
                text = " — ".join(part for part in (item.get("title"), item.get("summary")) if part).strip()
                if not _personal_victim_language(text):
                    continue
                personal += 1
                priority = await _save_item(settings, feed_url, item)
                if priority is None:
                    continue
                qualified += 1
                if priority == "HOT":
                    hot += 1
                else:
                    normal += 1
        except Exception as exc:
            print(f"RSS feed failed for {feed_url!r}: {exc}")

    return RSSStats(
        feeds=len(feeds),
        items=items,
        personal_items=personal,
        qualified=qualified,
        hot=hot,
        normal=normal,
    )
