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
    global_queries: int = 0
    global_results: int = 0
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
    if any(x in lowered for x in ("crypto", "krypto", "bitcoin", "крипто", "биткоин", "crypt")):
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


async def _is_human_message(message) -> bool:
    """Fail closed for forwarded posts and bot-authored messages."""
    if getattr(message, "fwd_from", None) or getattr(message, "via_bot_id", None):
        return False
    sender = getattr(message, "sender", None)
    if sender is None:
        try:
            sender = await message.get_sender()
        except Exception:
            return False
    return sender is not None and not bool(getattr(sender, "bot", False))


async def _public_chat_info(message) -> tuple[str | None, str | None, bool]:
    try:
        chat = getattr(message, "chat", None) or await message.get_chat()
    except Exception:
        return None, None, False
    username = getattr(chat, "username", None)
    title = str(getattr(chat, "title", None) or username or "").strip() or None
    public_group = bool(
        username and (
            getattr(chat, "megagroup", False)
            or getattr(chat, "gigagroup", False)
        )
    )
    return (str(username).strip() if username else None), title, public_group


async def _save_candidate(
    settings,
    source: str,
    telegram_message_id: int,
    text: str,
    source_url: str,
    parent_id: int | None = None,
):
    # Telegram posts qualify only after first-person loss + explicit help request.
    classification = classify(text, source="telegram")
    if classification.kind != "lead":
        return None

    text = text.strip()[:1800]
    signals = detect(text)
    result = score_lead(signals)
    if result.total < settings.min_email_score:
        return None

    reasons = list(result.reasons) + list(classification.reasons)
    reasons.append(f"source_url={source_url}")
    if parent_id:
        reasons.append(f"discussion_parent={parent_id}")

    lead = {
        "fingerprint": fingerprint(source, str(telegram_message_id), text),
        "telegram_message_id": telegram_message_id,
        "source": source,
        # Do not persist Telegram user IDs or usernames. The public post URL is
        # enough for a human reviewer to open the original context.
        "sender_id": None,
        "username": None,
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
    print("\n=== QUALIFIED PUBLIC HELP REQUEST ===")
    print(msg.as_string())
    print("=== END HELP REQUEST ===\n")
    await send_message(settings, msg)
    return result.priority


async def _global_search_once(client: TelegramClient, settings) -> tuple[int, int, int, int, int]:
    """Search Telegram's public index, but only accept public group discussions."""
    results = qualified = hot = normal = 0
    seen: set[tuple[str, int]] = set()

    for query in settings.tg_search_queries:
        await _pause(settings)
        try:
            async for message in client.iter_messages(None, search=query, limit=settings.search_limit):
                results += 1
                text = (message.raw_text or "").strip()
                if not text or not await _is_human_message(message):
                    continue

                username, _title, is_public_group = await _public_chat_info(message)
                if not username or not is_public_group:
                    continue

                source_name = f"@{username}"
                key = (source_name, int(message.id))
                if key in seen:
                    continue
                seen.add(key)

                source_url = f"https://t.me/{username}/{message.id}"
                priority = await _save_candidate(
                    settings,
                    source_name,
                    message.id,
                    text,
                    source_url,
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
            print(f"Telegram public-group search failed for query {query!r}: {exc}")

    return len(settings.tg_search_queries), results, qualified, hot, normal


async def search_once(client: TelegramClient, settings) -> SearchStats:
    qualified = hot = normal = messages = 0
    global_queries = global_results = 0
    posts_without_comments = unavailable_discussions = inactive_discussions = comments_checked = 0

    global_queries, global_results, global_qualified, global_hot, global_normal = await _global_search_once(client, settings)
    qualified += global_qualified
    hot += global_hot
    normal += global_normal

    for source in settings.tg_sources:
        await _pause(settings)
        try:
            chat = await client.get_entity(source)
            username = getattr(chat, "username", None)
            source_name = f"@{username}" if username else str(getattr(chat, "title", None) or source)
            is_public_group = bool(
                username and (
                    getattr(chat, "megagroup", False)
                    or getattr(chat, "gigagroup", False)
                )
            )
            if not username:
                print(f"Skipping non-public Telegram source {source!r}: no public username/permalink.")
                continue

            comment_posts = 0
            async for message in client.iter_messages(chat, limit=settings.messages_per_source):
                messages += 1
                text = (message.raw_text or "").strip()
                replies = getattr(message, "replies", None)
                reply_count = int(getattr(replies, "replies", 0) or 0) if replies else 0
                source_url = f"https://t.me/{username}/{message.id}"

                # Top-level messages from channels are editorial content, not
                # user requests. Only original human posts in public groups pass.
                if is_public_group and text and await _is_human_message(message):
                    priority = await _save_candidate(
                        settings,
                        source_name,
                        message.id,
                        text,
                        source_url,
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

                # Comments are read as public discussion messages. Usernames/IDs
                # are intentionally not persisted in the lead record.
                for comment_text in discussion.comments:
                    priority = await _save_candidate(
                        settings,
                        source_name,
                        message.id,
                        comment_text,
                        source_url,
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
        global_queries=global_queries,
        global_results=global_results,
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
        print(f"Telegram one-cycle search: {len(settings.tg_sources)} configured source(s)")
        print(f"Telegram public-group queries: {len(settings.tg_search_queries)}")
        stats = await search_once(client, settings)
        print(
            "Telegram cycle: "
            f"sources={stats.sources} messages={stats.messages} "
            f"global_queries={stats.global_queries} global_results={stats.global_results} "
            f"comments={stats.comments_checked} qualified={stats.qualified} "
            f"hot={stats.hot} normal={stats.normal}"
        )
    except FloodWaitError as exc:
        print(f"Telegram FLOOD_WAIT received ({exc.seconds}s). Stopping safely.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
