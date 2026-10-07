from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

from telethon import TelegramClient

from .db import fingerprint, save_lead
from .detector import detect
from .emailer import build_message
from .scoring import score_lead


SEARCH_QUERIES: tuple[str, ...] = (
    # Russian
    "потерял деньги брокер",
    "потеряла деньги брокер",
    "мошенничество брокер",
    "мошенники брокер",
    "не могу вывести деньги",
    "не выводят деньги",
    "заблокировали вывод",
    "вернуть деньги брокер",
    "потерял деньги крипто",
    "обманули инвестиции",
    "скам инвестиции",
    "форекс мошенничество",
    # German
    "Geld verloren Broker",
    "Betrug Broker",
    "Betrüger Broker",
    "Anlagebetrug",
    "Investment Betrug",
    "kann nicht auszahlen",
    "Auszahlung blockiert",
    "Geld zurück Broker",
    "Geld verloren Krypto",
    "Forex Betrug",
    "Broker verschwunden",
)


@dataclass(frozen=True)
class SearchStats:
    queries: int = 0
    messages: int = 0
    qualified: int = 0
    hot: int = 0
    normal: int = 0


def _category(signals) -> str:
    investment = " ".join(signals.matched.get("investment", []))
    lowered = investment.lower()
    if any(x in lowered for x in ("crypto", "krypto", "bitcoin", "крипто", "биткоин")):
        return "CRYPTO"
    if any(x in lowered for x in ("forex", "форекс")):
        return "FOREX"
    if investment:
        return "INVESTMENT_SCAM"
    return "OTHER"


async def search_once(client: TelegramClient, settings) -> SearchStats:
    qualified = 0
    hot = 0
    normal = 0
    messages = 0

    for query in SEARCH_QUERIES:
        try:
            async for message in client.iter_messages(None, search=query, limit=100):
                messages += 1
                text = (message.raw_text or "").strip()
                if not text:
                    continue

                signals = detect(text)
                result = score_lead(signals)
                if result.total < settings.min_email_score:
                    continue

                chat = await message.get_chat()
                source = str(
                    getattr(chat, "username", None)
                    or getattr(chat, "title", None)
                    or message.chat_id
                )
                sender_id = str(message.sender_id) if message.sender_id else None

                lead = {
                    "fingerprint": fingerprint(source, sender_id, text),
                    "telegram_message_id": message.id,
                    "source": source,
                    "sender_id": sender_id,
                    "username": None,
                    "language": signals.language,
                    "amount": max(signals.amounts) if signals.amounts else None,
                    "score": result.total,
                    "priority": result.priority,
                    "category": _category(signals),
                    "message": text,
                    "reasons": result.reasons,
                }
                inserted = await save_lead(settings.db_path, lead)
                if not inserted:
                    continue

                qualified += 1
                if result.priority == "HOT":
                    hot += 1
                else:
                    normal += 1

                # Email is intentionally rendered here for human review. The
                # current MVP does not send messages automatically.
                msg = build_message(settings, lead)
                print("\n=== QUALIFIED LEAD ===")
                print(msg.as_string())
                print("=== END LEAD ===\n")

        except Exception as exc:
            print(f"Search failed for query {query!r}: {exc}")

        await asyncio.sleep(0)

    return SearchStats(
        queries=len(SEARCH_QUERIES),
        messages=messages,
        qualified=qualified,
        hot=hot,
        normal=normal,
    )
