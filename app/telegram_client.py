from __future__ import annotations

import asyncio

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from .community_public import collect_once as collect_community_once
from .rss_leads import collect_once as collect_rss_once
from .telegram_search import search_once
from .x_leads import collect_once as collect_x_once


async def run(settings) -> None:
    telegram_enabled = bool(settings.tg_api_id and settings.tg_api_hash and settings.tg_search_queries)
    x_enabled = bool(settings.x_enabled and settings.x_api_bearer_token)
    client = None

    if telegram_enabled:
        client = TelegramClient(
            settings.tg_session,
            settings.tg_api_id,
            settings.tg_api_hash,
            sequential_updates=True,
        )
        await client.start()
        print(
            "Read-only Telegram monitoring: "
            f"global_queries={len(settings.tg_search_queries)} "
            f"configured_sources={len(settings.tg_sources)}"
        )
        print("No Telegram messages, reactions, joins, invites, or user outreach are performed.")
    else:
        print("Telegram monitoring disabled: API credentials/search queries are not configured.")

    print("Google Alerts/Gmail collector: removed from this application.")
    print(f"RSS public-feed collector: {len(settings.rss_feeds)} configured feed(s)")
    print("Community monitor: public Reddit search RSS + COMMUNITY_FEEDS")
    print("Facebook search-engine discovery: disabled; only a future authorized official API could enable it.")
    if x_enabled:
        print(
            "X API monitor enabled: "
            f"queries={len(settings.x_search_queries)} "
            f"max_results_per_query={settings.x_max_results} "
            f"interval={settings.x_poll_seconds}s"
        )
    else:
        print("X API monitor disabled: set X_API_BEARER_TOKEN and X_ENABLED=true to activate it.")

    loop = asyncio.get_running_loop()
    next_x_run = 0.0

    try:
        while True:
            if telegram_enabled and client is not None:
                try:
                    stats = await search_once(client, settings)
                    print(
                        "Telegram cycle: "
                        f"sources={stats.sources} messages={stats.messages} "
                        f"global_queries={stats.global_queries} global_results={stats.global_results} "
                        f"comments={stats.comments_checked} qualified={stats.qualified} "
                        f"hot={stats.hot} normal={stats.normal}"
                    )
                except FloodWaitError as exc:
                    print(f"Telegram FLOOD_WAIT received ({exc.seconds}s). Stopping Telegram safely.")
                    telegram_enabled = False
                except Exception as exc:
                    print(f"Telegram monitoring cycle failed: {exc}")

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
                community_stats = await collect_community_once(settings)
                print(
                    "Community public cycle: "
                    f"feeds={community_stats.feeds} items={community_stats.items} "
                    f"help_requests={community_stats.help_requests} "
                    f"qualified={community_stats.qualified} hot={community_stats.hot} "
                    f"normal={community_stats.normal}"
                )
            except Exception as exc:
                print(f"Community public collector failed: {exc}")

            if x_enabled and loop.time() >= next_x_run:
                try:
                    x_stats = await collect_x_once(settings)
                    print(
                        "X API cycle: "
                        f"queries={x_stats.queries} posts={x_stats.posts} "
                        f"personal={x_stats.personal_posts} qualified={x_stats.qualified} "
                        f"hot={x_stats.hot} normal={x_stats.normal}"
                    )
                except Exception as exc:
                    print(f"X API collector cycle failed: {exc}")
                next_x_run = loop.time() + settings.x_poll_seconds

            await asyncio.sleep(settings.poll_seconds)
    finally:
        if client is not None:
            await client.disconnect()
