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


_DEFAULT_FACEBOOK_QUERIES = (
    "[DE] \"ich habe Geld verloren\" Broker",
    "[DE] \"ich wurde betrogen\" Broker",
    "[DE] \"mein Geld\" \"nicht zurück\" Trading",
    "[DE] \"Auszahlung\" \"verweigert\" Broker",
    "[DE] \"Auszahlung\" \"blockiert\" Krypto",
    "[DE] \"Geld verloren\" Trading Betrug",
    "[DE] \"Geld verloren\" Krypto Betrug",
    "[DE] \"ich brauche Hilfe\" Broker Betrug",
    "[DE] \"ich brauche einen Anwalt\" Trading",
    "[DE] \"welcher Anwalt\" Broker Betrug",
    "[AT] \"ich wurde betrogen\" Broker",
    "[CH] \"ich wurde betrogen\" Broker",
    "[NL] \"I lost money\" broker scam",
    "[EN] \"I was scammed\" broker withdrawal",
    "[EN] \"my money\" \"cannot withdraw\" crypto",
    "[RU] \"я потерял деньги\" брокер мошенники",
    "[RU] \"не могу вывести\" деньги брокер",
    "[RU] \"меня обманули\" брокер крипто",
)


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
    rss_feeds: tuple[str, ...]
    rss_max_items: int
    rss_timeout_seconds: int
    rss_request_delay_seconds: float
    facebook_enabled: bool
    facebook_queries: tuple[str, ...]
    facebook_max_items: int


def load_settings(require_telegram: bool = True) -> Settings:
    api_id = os.getenv("TG_API_ID", "").strip()
    api_hash = os.getenv("TG_API_HASH", "").strip()
    if require_telegram and (not api_id or not api_hash):
        raise RuntimeError("TG_API_ID and TG_API_HASH are required")

    sources = tuple(s.strip() for s in os.getenv("TG_SOURCES", "").split(",") if s.strip())
    if require_telegram and not sources:
        raise RuntimeError("TG_SOURCES must contain at least one authorized public source")

    rss_feeds = tuple(s.strip() for s in os.getenv("RSS_FEEDS", "").split(",") if s.strip())
    facebook_queries_env = tuple(s.strip() for s in os.getenv("FACEBOOK_QUERIES", "").split("|") if s.strip())
    facebook_queries = facebook_queries_env or _DEFAULT_FACEBOOK_QUERIES

    db_path = Path(os.getenv("DB_PATH", "data/leads.sqlite3"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        tg_api_id=int(api_id or "0"),
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
        rss_feeds=rss_feeds,
        rss_max_items=max(1, int(os.getenv("RSS_MAX_ITEMS", "50"))),
        rss_timeout_seconds=max(5, int(os.getenv("RSS_TIMEOUT_SECONDS", "20"))),
        rss_request_delay_seconds=max(0.0, float(os.getenv("RSS_REQUEST_DELAY_SECONDS", "2"))),
        facebook_enabled=_bool("FACEBOOK_ENABLED", True),
        facebook_queries=facebook_queries,
        facebook_max_items=max(1, int(os.getenv("FACEBOOK_MAX_ITEMS", "50"))),
    )
