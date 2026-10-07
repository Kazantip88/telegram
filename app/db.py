from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT UNIQUE NOT NULL,
    telegram_message_id INTEGER,
    source TEXT NOT NULL,
    sender_id TEXT,
    username TEXT,
    language TEXT,
    amount REAL,
    score INTEGER NOT NULL,
    priority TEXT NOT NULL,
    category TEXT,
    message TEXT NOT NULL,
    reasons TEXT NOT NULL,
    created_at TEXT NOT NULL,
    emailed_at TEXT
);
"""


def fingerprint(source: str, sender_id: str | None, message: str) -> str:
    normalized = " ".join(message.lower().split())
    raw = f"{source}|{sender_id or ''}|{normalized}".encode()
    return hashlib.sha256(raw).hexdigest()


async def init_db(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def save_lead(path: Path, lead: dict) -> bool:
    try:
        async with aiosqlite.connect(path) as db:
            await db.execute(
                """INSERT INTO leads
                (fingerprint, telegram_message_id, source, sender_id, username, language,
                 amount, score, priority, category, message, reasons, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lead["fingerprint"], lead.get("telegram_message_id"), lead["source"],
                    lead.get("sender_id"), lead.get("username"), lead.get("language"),
                    lead.get("amount"), lead["score"], lead["priority"], lead.get("category"),
                    lead["message"], json.dumps(lead.get("reasons", []), ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
            return True
    except aiosqlite.IntegrityError:
        return False


async def mark_emailed(path: Path, fingerprint_value: str) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "UPDATE leads SET emailed_at=? WHERE fingerprint=?",
            (datetime.now(timezone.utc).isoformat(), fingerprint_value),
        )
        await db.commit()
