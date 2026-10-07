from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from telethon.errors import RPCError


@dataclass(frozen=True)
class DiscussionResult:
    available: bool
    active: bool
    replies: int
    comments_checked: int
    comments: tuple[str, ...]
    reason: str


async def inspect_discussion(message, *, limit: int = 10, active_days: int = 30) -> DiscussionResult:
    """Cheaply decide whether a channel post is worth reading for comments.

    Telegram exposes comment metadata on the post itself. We use that metadata
    as the first gate, then fetch only a small number of recent replies.
    """
    replies = getattr(message, "replies", None)
    if replies is None:
        return DiscussionResult(False, False, 0, 0, (), "no_discussion_metadata")

    total = int(getattr(replies, "replies", 0) or 0)
    channel_id = getattr(replies, "channel_id", None)
    if total <= 0 or not channel_id:
        return DiscussionResult(False, False, total, 0, (), "no_comments")

    try:
        # Telethon's reply_to support retrieves the thread in the linked
        # discussion group. We intentionally inspect only recent comments.
        comments = []
        async for reply in message.client.iter_messages(
            channel_id,
            reply_to=message.id,
            limit=limit,
        ):
            text = (reply.raw_text or "").strip()
            if text:
                comments.append(text)

        if not comments:
            return DiscussionResult(False, False, total, 0, (), "discussion_unreadable")

        # The iterator is reverse chronological in Telegram/Telethon usage;
        # use the newest fetched message date as the activity signal.
        newest = None
        async for reply in message.client.iter_messages(
            channel_id,
            reply_to=message.id,
            limit=1,
        ):
            newest = getattr(reply, "date", None)
            break

        if newest is None:
            return DiscussionResult(False, False, total, len(comments), tuple(comments), "no_comment_date")

        if newest.tzinfo is None:
            newest = newest.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=active_days)
        active = newest >= cutoff
        return DiscussionResult(
            True,
            active,
            total,
            len(comments),
            tuple(comments),
            "active" if active else "inactive",
        )
    except (RPCError, ValueError, TypeError) as exc:
        return DiscussionResult(False, False, total, 0, (), f"discussion_error:{type(exc).__name__}")
