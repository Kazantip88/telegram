from __future__ import annotations

import asyncio

from .config import load_settings
from .rss_leads import collect_once


async def main() -> None:
    settings = load_settings(require_telegram=False)
    stats = await collect_once(settings)
    print(
        "RSS test complete: "
        f"feeds={stats.feeds}, "
        f"items={stats.items}, "
        f"personal={stats.personal_items}, "
        f"qualified={stats.qualified}, "
        f"hot={stats.hot}, "
        f"normal={stats.normal}"
    )


if __name__ == "__main__":
    asyncio.run(main())
