from __future__ import annotations

import base64
import html
import os
import re
from dataclasses import dataclass
from email.message import Message
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .db import fingerprint, save_lead
from .detector import detect
from .emailer import build_message, send_message
from .scoring import score_lead

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@dataclass(frozen=True)
class GmailStats:
    messages: int = 0
    qualified: int = 0
    hot: int = 0
    normal: int = 0


def _setting(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _credentials() -> Credentials:
    client_file = Path(_setting("GMAIL_CLIENT_SECRET_FILE", "data/google_client_secret.json"))
    token_file = Path(_setting("GMAIL_TOKEN_FILE", "data/gmail_token.json"))
    if not client_file.exists():
        raise RuntimeError(
            f"Gmail OAuth client file not found: {client_file}. "
            "Download the Desktop OAuth JSON from Google Cloud and place it there."
        )

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
        creds = flow.run_local_server(port=0)

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _decode(data: str) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode()).decode("utf-8", errors="replace")


def _strip_html(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def _parts(payload: dict) -> tuple[str, str]:
    plain: list[str] = []
    html_parts: list[str] = []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        body = part.get("body", {}) or {}
        data = body.get("data")
        if data:
            text = _decode(data)
            if mime == "text/plain":
                plain.append(text)
            elif mime == "text/html":
                html_parts.append(text)
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    return "\n".join(plain).strip(), "\n".join(html_parts).strip()


def _headers(payload: dict) -> dict[str, str]:
    return {
        str(item.get("name", "")).lower(): str(item.get("value", ""))
        for item in payload.get("headers", []) or []
    }


def _links(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>\"']+", text)


def _build_text(headers: dict[str, str], payload: dict) -> tuple[str, str | None]:
    plain, html_body = _parts(payload)
    body = plain or _strip_html(html_body)
    subject = headers.get("subject", "").strip()
    sender = headers.get("from", "").strip()
    links = _links(plain + " " + html_body)

    chunks = [x for x in (subject, body) if x]
    if links:
        chunks.append("Links: " + " ".join(links[:10]))
    text = "\n\n".join(chunks).strip()
    return text, sender or None


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


async def collect_once(settings) -> GmailStats:
    if _setting("GMAIL_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        return GmailStats()

    creds = _credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    user_id = "me"
    query = _setting("GMAIL_QUERY", "")
    max_messages = max(1, int(_setting("GMAIL_MAX_MESSAGES", "50")))

    request = service.users().messages().list(userId=user_id, q=query, maxResults=max_messages)
    response = request.execute()
    items = response.get("messages", []) or []

    qualified = hot = normal = 0
    for item in items:
        message_id = str(item["id"])
        full = service.users().messages().get(userId=user_id, id=message_id, format="full").execute()
        headers = _headers(full.get("payload", {}))
        text, sender = _build_text(headers, full.get("payload", {}))
        if not text:
            continue

        signals = detect(text)
        result = score_lead(signals)
        if result.total < settings.min_email_score:
            continue

        source = "gmail:google-alerts"
        lead = {
            "fingerprint": fingerprint(source, message_id, text),
            "telegram_message_id": None,
            "source": source,
            "sender_id": message_id,
            "username": sender,
            "language": signals.language,
            "amount": max(signals.amounts) if signals.amounts else None,
            "score": result.total,
            "priority": result.priority,
            "category": _category(signals),
            "message": text,
            "reasons": list(result.reasons) + [f"gmail_message_id={message_id}"],
        }
        inserted = await save_lead(settings.db_path, lead)
        if not inserted:
            continue

        msg = build_message(settings, lead)
        print("\n=== GMAIL QUALIFIED LEAD ===")
        print(msg.as_string())
        print("=== END GMAIL LEAD ===\n")
        await send_message(settings, msg)

        qualified += 1
        if result.priority == "HOT":
            hot += 1
        else:
            normal += 1

    return GmailStats(messages=len(items), qualified=qualified, hot=hot, normal=normal)
