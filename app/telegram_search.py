from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from telethon import TelegramClient

from .db import fingerprint, save_lead
from .detector import detect
from .emailer import build_message
from .scoring import score_lead


SEARCH_QUERIES: tuple[str, ...] = (
    # Russian
    "потерял деньги брокер",
    "потеряла деньги брокер",
    "мошенничество брокер",
    "мошенники брокер",
    "не могу вывести деньги",
    "не выводят деньги",
    "заблокировали вывод",
    "вернуть деньги брокер",
    "потерял деньги крипто",
    "обманули инвестиции",
    "скам инвестиции",
    "форекс мошенничество",
    # German
    "Geld verloren Broker",
    "Betrug Broker",
    "Betrüger Broker",
    "Anlagebetrug",
    "Investment Betrug",
    "kann nicht auszahlen",
    "Auszahlung blockiert",
    "Geld zurück Broker",
    "Geld verloren Krypto",
    "Forex Betrug",
    "Broker verschwunden",
)


@dataclass(frozen=True)
class SearchStats:
    queries: int = 0
    messages: int = 0
    posts_without_comments: int = 0
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


def _has_comments(message) -> bool:
    """Cheap gate: do not request a discussion thread if Telegram says there are no comments."""
    replies = getattr(message, "replies", None)
    if replies is None:
        return False
    count = int(getattr(replies, "replies", 0) or 0)
    comments_enabled = getattr(replies, "comments", None)
    if comments_enabled is False:
        return False
    return count > 0


async def _active_comments(client: TelegramClient, message, settings):
    """Return recent comments only when the post has an accessible active discussion."""
    if not _has_comments(message):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.comments_active_days)
    comments = []
    try:
        # Telegram exposes channel comments as replies in the linked discussion group.
        # If the discussion is inaccessible, fail closed: skip it rather than spending
        # time retrying or trying to join anything.
        async for comment in client.iter_messages(
            message.chat_id,
            reply_to=message.id,
            limit=settings.comments_limit,
        ):
            comment_date = comment.date
            if comment_date is not None:
                if comment_date.tzinfo is None:
                    comment_date = comment_date.replace(tzinfo=timezone.utc)
                if comment_date < cutoff:
                    break
            if (comment.raw_text or "").strip():
                comments.append(comment)
    except Exception:
        return []

    return comments


async def _save_candidate(settings, source, message, text, signals, sender_id=None, parent_id=None):
    result = score_lead(signals)
    if result.total < settings.min_email_score:
        return False, None

    lead = {
        "fingerprint": fingerprint(source, sender_id, text),
        "telegram_message_id": message.id,
        "source": source,
        "sender_id": sender_id,
        "username": None,
        "language": signals.language,
        "amount": max(signals.amounts) if signals.amounts else None,
        "score": result.total,
        "priority": result.priority,
        "category": _category(signals),
        "message": text,
        "reasons": result.reasons + ([f"discussion_parent={parent_id}"] if parent_id else []),
    }
    inserted = await save_lead(settings.db_path, lead)
    return inserted, lead


async def search_once(client: TelegramClient, settings) -> SearchStats:
    qualified = 0
    hot = 0
    normal = 0
    messages = 0
    posts_without_comments = 0
    inactive_discussions = 0
    comments_checked = 0

    for query in SEARCH_QUERIES:
        try:
            async for message in client.iter_messages(None, search=query, limit=settings.search_limit):
                messages += 1
                text = (message.raw_text or "").strip()
                if not text:
                    continue

                # Important performance rule: first inspect Telegram's cheap replies
                # metadata. Posts without comments are ignored immediately.
                if not _has_comments(message):
                    posts_without_comments += 1
                    continue

                comments = await _active_comments(client, message, settings)
                if not comments:
                    inactive_discussions += 1
                    continue
                comments_checked += len(comments)

                chat = await message.get_chat()
                source = str(
                    getattr(chat, "username", None)
                    or getattr(chat, "title", None)
                    or message.chat_id
                )

                # Check the post itself, but only after confirming that its discussion
                # is active. More importantly, inspect the comments: victim details are
                # often written in replies while the channel post is generic.
                candidates = [(message, text, message.id)]
                candidates.extend(
                    (comment, (comment.raw_text or "").strip(), message.id)
                    for comment in comments
                )

                for candidate_message, candidate_text, parent_id in candidates:
                    if not candidate_text:
                        continue
                    signals = detect(candidate_text)
                    sender_id = str(candidate_message.sender_id) if candidate_message.sender_id else None
                    inserted, lead = await _save_candidate(
                        settings,
                        source,
                        candidate_message,
                        candidate_text,
                        signals,
                        sender_id=sender_id,
                        parent_id=parent_id if candidate_message.id != message.id else None,
                    )
                    if not inserted:
                        continue

                    qualified += 1
                    if lead["priority"] == "HOT":
                        hot += 1
                    else:
                        normal += 1

                    # Email is intentionally rendered here for human review. The
                    # current MVP does not send messages automatically.
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
        inactive_discussions=inactive_discussions,
        comments_checked=comments_checked,
        qualified=qualified,
        hot=hot,
        normal=normal,
    )
