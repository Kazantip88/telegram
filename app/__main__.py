import asyncio

from .config import load_settings
from .db import init_db
from .telegram_client import run


def main() -> None:
    settings = load_settings()
    asyncio.run(init_db(settings.db_path))
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
