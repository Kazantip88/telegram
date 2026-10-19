from __future__ import annotations

import asyncio

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from .facebook_public import collect_once as collect_facebook_once
from .gmail_alerts import collect_once as collect_gmail_once
from .rss_leads import collect_once as collect_rss_once
from .telegram_search import search_once


async def run(settings) -> None:
    telegram_enabled = bool(settings.tg_api_id and settings.tg_api_hash and settings.tg_sources)
    client = None

    if telegram_enabled:
        client = TelegramClient(
            settings.tg_session,
            settings.tg_api_id,
            settings.tg_api_hash,
            sequential_updates=True,
        )
        await client.start()
        print(f"Read-only Telegram monitoring: {len(settings.tg_sources)} configured public source(s)")
        print("No Telegram messages, reactions, joins, invites, or user outreach are performed.")
    else:
        print("Telegram monitoring disabled: API credentials/sources are not configured.")

    print("Gmail collector uses readonly OAuth and does not mark messages as read.")
    print(f"RSS public-feed collector: {len(settings.rss_feeds)} configured feed(s)")
    print(f"Facebook public monitor: {'enabled' if settings.facebook_enabled else 'disabled'}")

    try:
        while True:
            if telegram_enabled and client is not None:
                try:
                    stats = await search_once(client, settings)
                    print(
                        "Telegram cycle: "
                        f"sources={stats.sources} messages={stats.messages} "
                        f"comments={stats.comments_checked} qualified={stats.qualified} "
                        f"hot={stats.hot} normal={stats.normal}"
                    )
                except FloodWaitError as exc:
                    print(f"Telegram FLOOD_WAIT received ({exc.seconds}s). Stopping Telegram safely.")
                    telegram_enabled = False
                except Exception as exc:
                    print(f"Telegram monitoring cycle failed: {exc}")

            try:
                gmail_stats = await collect_gmail_once(settings)
                print(
                    "Gmail Alerts cycle: "
                    f"messages={gmail_stats.messages} qualified={gmail_stats.qualified} "
                    f"hot={gmail_stats.hot} normal={gmail_stats.normal}"
                )
            except Exception as exc:
                print(f"Gmail collector cycle failed: {exc}")

            try:
                rss_stats = await collect_rss_once(settings)
                print(
                    "RSS cycle: "
                    f"feeds={rss_stats.feeds} items={rss_stats.items} "
                    f"personal={rss_stats.personal_items} qualified={rss_stats.qualified} "
                    f"hot={rss_stats.hot} normal={rss_stats.normal}"
                )
            except Exception as exc:
                print(f"RSS collector cycle failed: {exc}")

            try:
                facebook_stats = await collect_facebook_once(settings)
                print(
                    "Facebook public cycle: "
                    f"queries={facebook_stats.queries} items={facebook_stats.items} "
                    f"personal={facebook_stats.personal} qualified={facebook_stats.qualified} "
                    f"hot={facebook_stats.hot} normal={facebook_stats.normal}"
                )
            except Exception as exc:
                print(f"Facebook collector cycle failed: {exc}")

            await asyncio.sleep(settings.poll_seconds)
    finally:
        if client is not None:
            await client.disconnect()
