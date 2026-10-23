from __future__ import annotations

import asyncio
import urllib.error

from .config import load_settings
from .facebook_public import _fetch, _query_urls, _search_links


async def main() -> None:
    settings = load_settings(require_telegram=False)
    queries = settings.facebook_queries[:3]
    print(f"Facebook probe: queries={len(queries)}")
    for query in queries:
        print(f"\nQUERY: {query}")
        for url in _query_urls(query):
            try:
                payload = await asyncio.to_thread(_fetch, url, settings.rss_timeout_seconds)
                items = _search_links(payload)
                print(f"OK bytes={len(payload)} results={len(items)} url={url}")
                if items:
                    for item in items[:3]:
                        print(f"  -> {item.get('link','')} | {item.get('title','')[:120]}")
            except urllib.error.HTTPError as exc:
                print(f"HTTP_ERROR status={exc.code} reason={exc.reason} url={url}")
            except urllib.error.URLError as exc:
                print(f"URL_ERROR reason={exc.reason} url={url}")
            except Exception as exc:
                print(f"ERROR type={type(exc).__name__} reason={exc} url={url}")


if __name__ == "__main__":
    asyncio.run(main())
