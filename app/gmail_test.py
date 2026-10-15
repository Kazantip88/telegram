from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from .config import Settings
from .gmail_alerts import collect_once


async def main() -> None:
    load_dotenv()

    required = {
        "GMAIL_ENABLED": os.getenv("GMAIL_ENABLED", "true"),
        "GMAIL_CLIENT_SECRET_FILE": os.getenv(
            "GMAIL_CLIENT_SECRET_FILE", "data/google_client_secret.json"
        ),
    }
    print(f"GMAIL_ENABLED={required['GMAIL_ENABLED']}")
    print(f"OAuth JSON exists: {Path(required['GMAIL_CLIENT_SECRET_FILE']).exists()}")

    settings = Settings()
    stats = await collect_once(settings)
    print(
        "Gmail test complete: "
        f"messages={stats.messages}, qualified={stats.qualified}, "
        f"hot={stats.hot}, normal={stats.normal}"
    )


if __name__ == "__main__":
    asyncio.run(main())
