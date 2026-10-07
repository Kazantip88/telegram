from __future__ import annotations

import asyncio

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from .config import Settings
from .telegram_search import search_once


async def run(settings: Settings) -> None:
    client = TelegramClient(
        settings.tg_session,
        settings.tg_api_id,
        settings.tg_api_hash,
        sequential_updates=True,
    )

    await client.start()
    print(f"Read-only monitoring: {len(settings.tg_sources)} configured public source(s)")
    print("No Telegram messages, reactions, joins, invites, or user outreach are performed.")

    try:
        while True:
            try:
                stats = await search_once(client, settings)
                print(
                    "Cycle: "
                    f"sources={stats.sources} messages={stats.messages} "
                    f"comments={stats.comments_checked} qualified={stats.qualified} "
                    f"hot={stats.hot} normal={stats.normal}"
                )
            except FloodWaitError as exc:
                # Deliberately stop instead of retrying/working around a server limit.
                print(f"Telegram FLOOD_WAIT received ({exc.seconds}s). Stopping monitor safely.")
                break
            except Exception as exc:
                print(f"Monitoring cycle failed: {exc}")

            await asyncio.sleep(settings.poll_seconds)
    finally:
        await client.disconnect()
