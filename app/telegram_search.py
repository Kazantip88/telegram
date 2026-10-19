from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from .config import load_settings
from .db import fingerprint, init_db, save_lead
from .detector import detect
from .discussion_filter import inspect_discussion
from .emailer import build_message, send_message
from .lead_classifier import classify
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


async def _save_candidate(
    settings,
    source: str,
    telegram_message_id: int,
    text: str,
    sender_id: str | None,
    username: str | None = None,
    parent_id: int | None = None,
):
    # Telegram posts/comments are user-generated public content, so they do not
    # need the URL/source classification used by Google Alerts. They do need the
    # same direct-victim gate: generic investment questions and third-person
    # stories must not become client leads just because they contain keywords.
    classification = classify(text, source=source)
    if classification.kind != "lead":
        return None

    signals = detect(text)
    result = score_lead(signals)
    if result.total < settings.min_email_score:
        return None

    reasons = list(result.reasons) + list(classification.reasons)
    if parent_id:
        reasons.append(f"discussion_parent={parent_id}")
    if username:
        reasons.append(f"public_username=@{username}")
        reasons.append(f"profile_url=https://t.me/{username}")

    lead = {
        "fingerprint": fingerprint(source, sender_id, text),
        "telegram_message_id": telegram_message_id,
        "source": source,
        "sender_id": sender_id,
        "username": username,
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
    await send_message(settings, msg)
    return result.priority


async def _public_username(message) -> str | None:
    sender = getattr(message, "sender", None)
    if sender is None:
        try:
            sender = await message.get_sender()
        except Exception:
            return None
    username = getattr(sender, "username", None)
    return str(username).strip() if username else None


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

                priority = await _save_candidate(
                    settings,
                    source_name,
                    message.id,
                    text,
                    str(message.sender_id) if message.sender_id else None,
                    None,
                    None,
                )
                if priority is not None:
                    qualified += 1
                    if priority == "HOT":
                        hot += 1
                    else:
                        normal += 1

                if reply_count <= 0:
                    posts_without_comments += 1
                    continue

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

                for comment_text, username in zip(discussion.comments, discussion.authors):
                    priority = await _save_candidate(
                        settings,
                        source_name,
                        message.id,
                        comment_text,
                        None,
                        username,
                        message.id,
                    )
                    if priority is None:
                        continue
                    qualified += 1
                    if priority == "HOT":
                        hot += 1
                    else:
                        normal += 1

        except FloodWaitError:
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


async def main() -> None:
    settings = load_settings()
    await init_db(settings.db_path)
    client = TelegramClient(
        settings.tg_session,
        settings.tg_api_id,
        settings.tg_api_hash,
        sequential_updates=True,
    )
    await client.start()
    try:
        print(f"Telegram one-cycle search: {len(settings.tg_sources)} source(s)")
        stats = await search_once(client, settings)
        print(
            "Telegram cycle: "
            f"sources={stats.sources} messages={stats.messages} "
            f"comments={stats.comments_checked} qualified={stats.qualified} "
            f"hot={stats.hot} normal={stats.normal}"
        )
    except FloodWaitError as exc:
        print(f"Telegram FLOOD_WAIT received ({exc.seconds}s). Stopping safely.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
