from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    tg_api_id: int
    tg_api_hash: str
    tg_session: str
    tg_sources: tuple[str, ...]
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    mail_from: str
    mail_to: str
    smtp_use_tls: bool
    db_path: Path
    dry_run: bool
    min_email_score: int
    hot_score: int
    poll_seconds: int
    search_limit: int
    comments_limit: int
    comments_active_days: int
    messages_per_source: int
    comment_posts_per_source: int
    request_delay_seconds: float
    jitter_seconds: float


def load_settings() -> Settings:
    api_id = os.getenv("TG_API_ID", "").strip()
    api_hash = os.getenv("TG_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise RuntimeError("TG_API_ID and TG_API_HASH are required")

    sources = tuple(s.strip() for s in os.getenv("TG_SOURCES", "").split(",") if s.strip())
    if not sources:
        raise RuntimeError("TG_SOURCES must contain at least one authorized public source")

    db_path = Path(os.getenv("DB_PATH", "data/leads.sqlite3"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        tg_api_id=int(api_id),
        tg_api_hash=api_hash,
        tg_session=os.getenv("TG_SESSION", "data/telegram_leads"),
        tg_sources=sources,
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        mail_from=os.getenv("MAIL_FROM", ""),
        mail_to=os.getenv("MAIL_TO", "info@lawlegal500.de"),
        smtp_use_tls=_bool("SMTP_USE_TLS", True),
        db_path=db_path,
        dry_run=_bool("DRY_RUN", True),
        min_email_score=int(os.getenv("MIN_EMAIL_SCORE", "50")),
        hot_score=int(os.getenv("HOT_SCORE", "80")),
        poll_seconds=max(60, int(os.getenv("POLL_SECONDS", "900"))),
        search_limit=max(1, int(os.getenv("SEARCH_LIMIT", "25"))),
        comments_limit=max(1, int(os.getenv("COMMENTS_LIMIT", "5"))),
        comments_active_days=max(1, int(os.getenv("COMMENTS_ACTIVE_DAYS", "30"))),
        messages_per_source=max(1, int(os.getenv("MESSAGES_PER_SOURCE", "50"))),
        comment_posts_per_source=max(0, int(os.getenv("COMMENT_POSTS_PER_SOURCE", "5"))),
        request_delay_seconds=max(0.0, float(os.getenv("REQUEST_DELAY_SECONDS", "3"))),
        jitter_seconds=max(0.0, float(os.getenv("JITTER_SECONDS", "2"))),
    )
