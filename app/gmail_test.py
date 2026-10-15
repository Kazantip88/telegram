from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

from .gmail_alerts import collect_once


async def main() -> None:
    load_dotenv()

    client_file = os.getenv(
        "GMAIL_CLIENT_SECRET_FILE", "data/google_client_secret.json"
    )
    print(f"GMAIL_ENABLED={os.getenv('GMAIL_ENABLED', 'true')}")
    print(f"OAuth JSON exists: {Path(client_file).exists()}")

    settings = SimpleNamespace(
        db_path=Path(os.getenv("DB_PATH", "data/leads.sqlite3")),
        min_email_score=int(os.getenv("MIN_EMAIL_SCORE", "50")),
        dry_run=os.getenv("DRY_RUN", "true").strip().lower()
        in {"1", "true", "yes", "y", "on"},
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        mail_from=os.getenv("MAIL_FROM", ""),
        mail_to=os.getenv("MAIL_TO", ""),
        smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").strip().lower()
        in {"1", "true", "yes", "y", "on"},
    )
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)

    stats = await collect_once(settings)
    print(
        "Gmail test complete: "
        f"messages={stats.messages}, qualified={stats.qualified}, "
        f"hot={stats.hot}, normal={stats.normal}"
    )


if __name__ == "__main__":
    asyncio.run(main())
