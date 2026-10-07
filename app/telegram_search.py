from __future__ import annotations

import asyncio
from dataclasses import dataclass

from telethon import TelegramClient

from .db import fingerprint, save_lead
from .detector import detect
from .discussion_filter import inspect_discussion
from .emailer import build_message
from .scoring import score_lead


SEARCH_QUERIES: tuple[str, ...] = (
    # Russian
    "потерял деньги брокер", "потеряла деньги брокер", "мошенничество брокер",
    "мошенники брокер", "не могу вывести деньги", "не выводят деньги",
    "заблокировали вывод", "вернуть деньги брокер", "потерял деньги крипто",
    "обманули инвестиции", "скам инвестиции", "форекс мошенничество",
    # German
    "Geld verloren Broker", "Betrug Broker", "Betrüger Broker", "Anlagebetrug",
    "Investment Betrug", "kann nicht auszahlen", "Auszahlung blockiert",
    "Geld zurück Broker", "Geld verloren Krypto", "Forex Betrug", "Broker verschwunden",
)


@dataclass(frozen=True)
class SearchStats:
    queries: int = 0
    messages: int = 0
    posts_without_comments: int = 0
    unavailable_discussions: int = 0
    inactive_discussions: int = 0
    comments_checked: int = 0
    qualified: int = 0
    hot: int = 0
    normal: int = 0


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


async def search_once(client: TelegramClient, settings) -> SearchStats:
    qualified = hot = normal = messages = 0
    posts_without_comments = unavailable_discussions = inactive_discussions = comments_checked = 0

    for query in SEARCH_QUERIES:
        try:
            async for message in client.iter_messages(None, search=query, limit=settings.search_limit):
                messages += 1
                text = (message.raw_text or "").strip()
                if not text:
                    continue

                # First gate: Telegram's replies metadata. No comments means no
                # discussion fetch and therefore no wasted requests.
                replies = getattr(message, "replies", None)
                reply_count = int(getattr(replies, "replies", 0) or 0) if replies else 0
                if reply_count <= 0:
                    posts_without_comments += 1
                    continue

                discussion = await inspect_discussion(
                    message,
                    limit=settings.comments_limit,
                    active_days=settings.comments_active_days,
                )
                comments_checked += discussion.comments_checked

                if not discussion.available:
                    unavailable_discussions += 1
                    continue
                if not discussion.active:
                    inactive_discussions += 1
                    continue

                chat = await message.get_chat()
                source = str(
                    getattr(chat, "username", None)
                    or getattr(chat, "title", None)
                    or message.chat_id
                )

                # Analyze the post and each recent comment separately. A generic
                # post can hide a strong victim signal in its discussion.
                candidates = [(message, text, None)]
                candidates.extend(
                    (None, comment_text, message.id)
                    for comment_text in discussion.comments
                )

                for candidate_message, candidate_text, parent_id in candidates:
                    signals = detect(candidate_text)
                    result = score_lead(signals)
                    if result.total < settings.min_email_score:
                        continue

                    sender_id = None
                    telegram_message_id = message.id
                    if candidate_message is not None:
                        telegram_message_id = candidate_message.id
                        sender_id = str(candidate_message.sender_id) if candidate_message.sender_id else None

                    reasons = list(result.reasons)
                    if parent_id:
                        reasons.append(f"discussion_parent={parent_id}")

                    lead = {
                        "fingerprint": fingerprint(source, sender_id, candidate_text),
                        "telegram_message_id": telegram_message_id,
                        "source": source,
                        "sender_id": sender_id,
                        "username": None,
                        "language": signals.language,
                        "amount": max(signals.amounts) if signals.amounts else None,
                        "score": result.total,
                        "priority": result.priority,
                        "category": _category(signals),
                        "message": candidate_text,
                        "reasons": reasons,
                    }
                    inserted = await save_lead(settings.db_path, lead)
                    if not inserted:
                        continue

                    qualified += 1
                    if result.priority == "HOT":
                        hot += 1
                    else:
                        normal += 1

                    msg = build_message(settings, lead)
                    print("\n=== QUALIFIED LEAD ===")
                    print(msg.as_string())
                    print("=== END LEAD ===\n")

        except Exception as exc:
            print(f"Search failed for query {query!r}: {exc}")

        await asyncio.sleep(0)

    return SearchStats(
        queries=len(SEARCH_QUERIES),
        messages=messages,
        posts_without_comments=posts_without_comments,
        unavailable_discussions=unavailable_discussions,
        inactive_discussions=inactive_discussions,
        comments_checked=comments_checked,
        qualified=qualified,
        hot=hot,
        normal=normal,
    )
