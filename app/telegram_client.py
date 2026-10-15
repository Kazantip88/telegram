from __future__ import annotations

import asyncio

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from .config import Settings
from .gmail_alerts import collect_once
from .telegram_search import search_once


async def run(settings: Settings) -> None:
    client = TelegramClient(
        settings.tg_session,
        settings.tg_api_id,
        settings.tg_api_hash,
        sequential_updates=True,
    )

    await client.start()
    print(f"Read-only Telegram monitoring: {len(settings.tg_sources)} configured public source(s)")
    print("No Telegram messages, reactions, joins, invites, or user outreach are performed.")
    print("Gmail collector uses readonly OAuth and does not mark messages as read.")

    try:
        while True:
            try:
                stats = await search_once(client, settings)
                print(
                    "Telegram cycle: "
                    f"sources={stats.sources} messages={stats.messages} "
                    f"comments={stats.comments_checked} qualified={stats.qualified} "
                    f"hot={stats.hot} normal={stats.normal}"
                )
            except FloodWaitError as exc:
                # Deliberately stop instead of retrying/working around a server limit.
                print(f"Telegram FLOOD_WAIT received ({exc.seconds}s). Stopping monitor safely.")
                break
            except Exception as exc:
                print(f"Telegram monitoring cycle failed: {exc}")

            try:
                gmail_stats = await collect_once(settings)
                print(
                    "Gmail Alerts cycle: "
                    f"messages={gmail_stats.messages} qualified={gmail_stats.qualified} "
                    f"hot={gmail_stats.hot} normal={gmail_stats.normal}"
                )
            except Exception as exc:
                print(f"Gmail collector cycle failed: {exc}")

            await asyncio.sleep(settings.poll_seconds)
    finally:
        await client.disconnect()
