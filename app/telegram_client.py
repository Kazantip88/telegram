from __future__ import annotations

import asyncio
from telethon import TelegramClient, events

from .config import Settings
from .db import fingerprint, save_lead
from .detector import detect
from .emailer import build_message
from .scoring import score_lead


def category(signals) -> str:
    if signals.matched.get("investment"):
        if any(x in " ".join(signals.matched["investment"]) for x in ("crypto", "krypto", "bitcoin", "крипто", "биткоин")):
            return "CRYPTO"
        if any(x in " ".join(signals.matched["investment"]) for x in ("forex", "форекс")):
            return "FOREX"
        return "INVESTMENT_SCAM"
    return "OTHER"


async def run(settings: Settings) -> None:
    client = TelegramClient(settings.tg_session, settings.tg_api_id, settings.tg_api_hash)
    await client.start()
    print(f"Monitoring {len(settings.tg_sources)} authorized Telegram source(s)")

    @client.on(events.NewMessage(chats=list(settings.tg_sources)))
    async def handler(event):
        text = (event.raw_text or "").strip()
        if not text:
            return
        signals = detect(text)
        score = score_lead(signals)
        if score.total < settings.min_email_score:
            return

        sender = await event.get_sender()
        username = getattr(sender, "username", None)
        sender_id = str(getattr(sender, "id", "")) or None
        source = str(getattr(event.chat, "username", None) or event.chat_id)
        lead = {
            "fingerprint": fingerprint(source, sender_id, text),
            "telegram_message_id": event.id,
            "source": source,
            "sender_id": sender_id,
            "username": username,
            "language": signals.language,
            "amount": max(signals.amounts) if signals.amounts else None,
            "score": score.total,
            "priority": score.priority,
            "category": category(signals),
            "message": text,
            "reasons": score.reasons,
        }
        inserted = await save_lead(settings.db_path, lead)
        if not inserted:
            return

        msg = build_message(settings, lead)
        print("\n=== QUALIFIED LEAD ===")
        print(msg.as_string())
        print("=== END LEAD ===\n")

    await client.run_until_disconnected()
