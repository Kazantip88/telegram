from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from .db import fingerprint, save_lead
from .detector import detect
from .discussion_filter import inspect_discussion
from .emailer import build_message
from .scoring import score_lead


@dataclass(frozen=True)
class SearchStats:
    sources: int = 0
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


async def _pause(settings) -> None:
    delay = settings.request_delay_seconds
    if settings.jitter_seconds:
        delay += random.uniform(0, settings.jitter_seconds)
    if delay > 0:
        await asyncio.sleep(delay)


async def _save_candidate(settings, source: str, telegram_message_id: int, text: str, sender_id: str | None, parent_id: int | None = None):
    signals = detect(text)
    result = score_lead(signals)
    if result.total < settings.min_email_score:
        return None

    reasons = list(result.reasons)
    if parent_id:
        reasons.append(f"discussion_parent={parent_id}")

    lead = {
        "fingerprint": fingerprint(source, sender_id, text),
        "telegram_message_id": telegram_message_id,
        "source": source,
        "sender_id": sender_id,
        "username": None,
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
    print("\n=== QUALIFIED LEAD ===")
    print(msg.as_string())
    print("=== END LEAD ===\n")
    return result.priority


async def search_once(client: TelegramClient, settings) -> SearchStats:
    qualified = hot = normal = messages = 0
    posts_without_comments = unavailable_discussions = inactive_discussions = comments_checked = 0

    # Deliberately avoid global Telegram search. Only explicitly configured,
    # authorized public sources are read.
    for source in settings.tg_sources:
        await _pause(settings)
        try:
            chat = await client.get_entity(source)
            source_name = str(getattr(chat, "username", None) or getattr(chat, "title", None) or source)

            comment_posts = 0
            async for message in client.iter_messages(chat, limit=settings.messages_per_source):
                messages += 1
                text = (message.raw_text or "").strip()
                if not text:
                    continue

                replies = getattr(message, "replies", None)
                reply_count = int(getattr(replies, "replies", 0) or 0) if replies else 0
                if reply_count <= 0:
                    posts_without_comments += 1
                    continue

                # Discussion reads are deliberately capped per source per cycle.
                if comment_posts >= settings.comment_posts_per_source:
                    continue

                await _pause(settings)
                discussion = await inspect_discussion(
                    message,
                    limit=settings.comments_limit,
                    active_days=settings.comments_active_days,
                )
                comment_posts += 1
                comments_checked += discussion.comments_checked

                if not discussion.available:
                    unavailable_discussions += 1
                    continue
                if not discussion.active:
                    inactive_discussions += 1
                    continue

                candidates = [(message.id, text, str(message.sender_id) if message.sender_id else None, None)]
                candidates.extend(
                    (message.id, comment_text, None, message.id)
                    for comment_text in discussion.comments
                )

                for message_id, candidate_text, sender_id, parent_id in candidates:
                    priority = await _save_candidate(
                        settings,
                        source_name,
                        message_id,
                        candidate_text,
                        sender_id,
                        parent_id,
                    )
                    if priority is None:
                        continue
                    qualified += 1
                    if priority == "HOT":
                        hot += 1
                    else:
                        normal += 1

        except FloodWaitError:
            # Never retry or work around a Telegram flood limit automatically.
            raise
        except Exception as exc:
            print(f"Source failed for {source!r}: {exc}")

    return SearchStats(
        sources=len(settings.tg_sources),
        messages=messages,
        posts_without_comments=posts_without_comments,
        unavailable_discussions=unavailable_discussions,
        inactive_discussions=inactive_discussions,
        comments_checked=comments_checked,
        qualified=qualified,
        hot=hot,
        normal=normal,
    )
