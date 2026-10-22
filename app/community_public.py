from __future__ import annotations

import asyncio
import os
import random
import re
import urllib.parse
from dataclasses import dataclass

from .rss_leads import _fetch_sync, _items, _save_item, _personal_victim_language


@dataclass(frozen=True)
class CommunityStats:
    feeds: int = 0
    items: int = 0
    direct_loss: int = 0
    qualified: int = 0
    hot: int = 0
    normal: int = 0


# Reddit's public RSS search endpoint; no account, login, private data, or DMs.
# Search queries intentionally target first-person loss/withdrawal reports.
_REDDIT_QUERIES = (
    '"I lost money" broker scam',
    '"cannot withdraw" crypto broker',
    '"I was scammed" investment',
    '"ich habe Geld verloren" Broker',
    '"Auszahlung" "verweigert" Broker',
    '"я потерял деньги" брокер',
    '"не могу вывести" деньги брокер',
)


def _default_feeds() -> tuple[str, ...]:
    feeds = []
    for query in _REDDIT_QUERIES:
        feeds.append(
            "https://www.reddit.com/search.rss?"
            + urllib.parse.urlencode({"q": query, "sort": "new", "t": "month"})
        )
    extra = tuple(
        item.strip()
        for item in os.getenv("COMMUNITY_FEEDS", "").split(",")
        if item.strip()
    )
    return tuple(feeds) + extra


def _explicit_loss(text: str) -> bool:
    lowered = text.lower().replace("ё", "е")
    patterns = (
        r"\bя\s+(?:потерял|потеряла|потеряли)\b.{0,180}\b(?:деньги|средства|руб|евро|доллар|крипто|инвести)",
        r"\bя\s+(?:вложил|вложила|перевел|перевела|отправил|отправила)\b.{0,160}\b(?:деньги|средства|депозит|евро|доллар|крипто)",
        r"\bменя\s+(?:обманули|развели|кинули|обокрали)\b",
        r"\b(?:не могу|не получается)\s+(?:вывести|забрать)\b.{0,100}\b(?:деньги|средства|депозит|крипто)",
        r"\bich\s+(?:habe|hatte)\b.{0,180}\b(?:geld|ersparnisse|euro|investment|einzahlung)\b.{0,180}\b(?:verloren|überwiesen|bezahlt|investiert)",
        r"\bich\s+wurde\s+(?:betrogen|abgezockt|getäuscht)\b",
        r"\bich\s+kann\s+mein\s+geld\s+nicht\s+(?:auszahlen|abheben|zurückbekommen)\b",
        r"\bi\s+(?:lost|have\s+lost)\b.{0,160}\b(?:money|funds|savings|crypto|investment)",
        r"\bi\s+(?:was\s+scammed|was\s+defrauded)\b",
        r"\bi\s+(?:cannot|can't|am unable to)\s+withdraw\b",
        r"\bmy\s+withdrawal\s+(?:is\s+)?blocked\b",
    )
    return any(re.search(pattern, lowered, flags=re.I | re.S) for pattern in patterns)


_PROMO_PATTERNS = (
    r"\baffiliate\b", r"\bdiscount codes?\b", r"\bpromo codes?\b",
    r"\bnot affiliated\b", r"\bleave (?:a|your) review\b",
    r"\bcomparison site\b", r"\bverified reviews?\b",
    r"\bmy workflow\b", r"\bcheck out (?:this|the) site\b",
    r"\beducation hub\b", r"\buse my code\b",
)
_CLEAR_COMPLAINT_TITLE = (
    r"\b(?:denied|blocked|refused|stolen|scammed|fraud|withdrawal|payout|lost my money)\b",
    r"\b(?:betrogen|abgezockt|auszahlung|geld verloren|betrug|nicht auszahlen)\b",
    r"\b(?:обманули|мошенник|не могу вывести|потерял деньги|украли)\b",
)


def _likely_promo_or_seo(text: str, title: str) -> bool:
    lowered = text.lower()
    if len(text) > 5000 and any(re.search(p, lowered, re.I) for p in _PROMO_PATTERNS):
        return True
    if sum(1 for p in _PROMO_PATTERNS if re.search(p, lowered, re.I)) >= 2:
        return True
    # Long generic trading/review articles often mention losses as anecdotes.
    # Require the title itself to indicate a complaint before treating them as leads.
    if len(text) > 2500 and not any(re.search(p, title.lower(), re.I) for p in _CLEAR_COMPLAINT_TITLE):
        return True
    return False


async def collect_once(settings) -> CommunityStats:
    feeds = _default_feeds()
    items_count = direct_loss = qualified = hot = normal = 0
    reddit_failed = False
    for index, feed_url in enumerate(feeds):
        is_reddit_search = "reddit.com/search.rss" in feed_url
        if is_reddit_search and reddit_failed:
            continue
        if index:
            delay = max(1.0, settings.rss_request_delay_seconds)
            if settings.jitter_seconds:
                delay += random.uniform(0, settings.jitter_seconds)
            await asyncio.sleep(delay)
        try:
            payload = await asyncio.to_thread(
                _fetch_sync, feed_url, settings.rss_timeout_seconds
            )
            items = _items(payload)[: settings.rss_max_items]
            items_count += len(items)
            for item in items:
                title = item.get("title", "").strip()
                summary = item.get("summary", "").strip()
                text = " — ".join(part for part in (title, summary) if part).strip()
                if not text or not _personal_victim_language(text) or not _explicit_loss(text):
                    continue
                if _likely_promo_or_seo(text, title):
                    print(f"Community candidate rejected as promotional/article content: {item.get('link', '')}")
                    continue
                if is_reddit_search:
                    link = item.get("link", "")
                    if "reddit.com/" not in link or "/comments/" not in link:
                        continue
                # Never score an unlimited full post body. It can contain unrelated
                # amounts, quoted stories, and promotional copy far from the title.
                bounded_item = dict(item)
                bounded_item["summary"] = summary[:2500]
                direct_loss += 1
                priority = await _save_item(settings, feed_url, bounded_item)
                if priority is None:
                    continue
                qualified += 1
                if priority == "HOT":
                    hot += 1
                else:
                    normal += 1
        except Exception as exc:
            print(f"Community public feed failed for {feed_url!r}: {exc}")
            if is_reddit_search and any(code in str(exc) for code in ("429", "403", "535")):
                reddit_failed = True
                print("Reddit search is rate-limited or blocked; skipping remaining Reddit queries this cycle.")
    return CommunityStats(
        feeds=len(feeds),
        items=items_count,
        direct_loss=direct_loss,
        qualified=qualified,
        hot=hot,
        normal=normal,
    )


async def main() -> None:
    from .config import load_settings

    settings = load_settings(require_telegram=False)
    stats = await collect_once(settings)
    print(
        "Community public test: "
        f"feeds={stats.feeds} items={stats.items} direct_loss={stats.direct_loss} "
        f"qualified={stats.qualified} hot={stats.hot} normal={stats.normal}"
    )


if __name__ == "__main__":
    asyncio.run(main())
