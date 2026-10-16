from __future__ import annotations

import base64
import html
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

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


def _extract_alert_items(text: str) -> list[tuple[str, str, str | None]]:
    """Extract individual Google Alert results from an alert email.

    Google Alerts is an aggregator: one email can contain several unrelated
    results. Each result must be scored independently so a useful phrase in
    one article cannot qualify an unrelated article in the same email.
    """
    urls = _links(text)
    if not urls:
        return [(text, text, None)]

    items: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()
    for url in urls:
        parsed = urlparse(url)
        if parsed.netloc.lower() in {"www.google.com", "google.com"}:
            # Google redirect URLs contain the actual destination in `url=`.
            from urllib.parse import parse_qs
            destination = parse_qs(parsed.query).get("url", [None])[0]
            if destination:
                url = destination
                parsed = urlparse(url)
        if not parsed.netloc:
            continue
        key = url.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)

        pos = text.find(url)
        start = max(0, pos - 700)
        end = min(len(text), pos + 1800)
        snippet = text[start:end].strip()
        items.append((snippet, snippet, url))

    return items or [(text, text, None)]


def _source_kind(url: str | None, item_text: str) -> str:
    if not url:
        return "unknown"
    host = urlparse(url).netloc.lower().removeprefix("www.")
    title = item_text.lower()

    blocked_hosts = {
        "banki.ru",
        "tass.ru",
        "ria.ru",
        "rbc.ru",
        "kommersant.ru",
        "lenta.ru",
        "gazeta.ru",
        "interfax.ru",
        "forbes.ru",
        "focus.de",
        "spiegel.de",
        "faz.net",
        "welt.de",
        "bild.de",
    }
    if host in blocked_hosts or any(x in title for x in ("news", "nachrichten", "новости", "статья")):
        return "news"

    qna_hosts = {"banki.ru", "stackoverflow.com", "quora.com", "gutefrage.net"}
    if host in qna_hosts or any(x in title for x in ("вопрос", "ответ", "frage", "antwort")):
        return "qna"

    return "public"


def _has_personal_victim_language(text: str) -> bool:
    """Require a first-person/direct-help signal for Gmail leads."""
    t = text.lower().replace("ё", "е")
    patterns = (
        r"\bя\s+(?:потерял|потеряла|вложил|вложила|инвестировал|инвестировала)\b",
        r"\bменя\s+(?:обманули|развели)\b",
        r"\bу\s+меня\s+(?:украли|заблокировали|не\s+выводят)\b",
        r"\bя\s+не\s+могу\s+вывести\b",
        r"\bпомогите\s+(?:вернуть|возвратить)\b",
        r"\bкак\s+вернуть\s+(?:мои\s+)?деньги\b",
        r"\bчто\s+делать\s+.*(?:деньг|брокер|мошенн)",
        r"\bich\s+(?:habe|hatte)\b.{0,80}\b(?:verloren|investiert|bezahlt|überwiesen)\b",
        r"\bich\s+wurde\s+betrogen\b",
        r"\bmir\s+wurde\b.{0,80}\b(?:geld|konto|auszahlung)\b",
        r"\bich\s+kann\s+(?:mein\s+)?geld\s+nicht\s+(?:auszahlen|abheben)\b",
        r"\bwie\s+bekomme\s+ich\s+mein\s+geld\s+zurück\b",
        r"\bich\s+brauche\s+(?:hilfe|einen\s+anwalt|rechtliche\s+hilfe)\b",
        r"\bwas\s+kann\s+ich\s+(?:tun|machen)\b",
    )
    return any(re.search(pattern, t, flags=re.I | re.S) for pattern in patterns)


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

    response = service.users().messages().list(
        userId=user_id, q=query, maxResults=max_messages
    ).execute()
    items = response.get("messages", []) or []

    qualified = hot = normal = 0
    for item in items:
        message_id = str(item["id"])
        full = service.users().messages().get(
            userId=user_id, id=message_id, format="full"
        ).execute()
        headers = _headers(full.get("payload", {}))
        text, sender = _build_text(headers, full.get("payload", {}))
        if not text:
            continue

        # IMPORTANT: Google Alert emails are aggregators. Score each result,
        # not the whole email, to prevent one matching phrase from qualifying
        # an unrelated article.
        for item_text, item_body, item_url in _extract_alert_items(text):
            kind = _source_kind(item_url, item_text)
            if kind in {"news", "qna"}:
                continue
            if not _has_personal_victim_language(item_body):
                continue

            signals = detect(item_body)
            result = score_lead(signals)
            if result.total < settings.min_email_score:
                continue

            source = "gmail:google-alerts"
            lead = {
                "fingerprint": fingerprint(source, message_id + "|" + (item_url or ""), item_body),
                "telegram_message_id": None,
                "source": source,
                "sender_id": message_id,
                "username": sender,
                "language": signals.language,
                "amount": max(signals.amounts) if signals.amounts else None,
                "score": result.total,
                "priority": result.priority,
                "category": _category(signals),
                "message": item_body,
                "reasons": list(result.reasons)
                + [f"gmail_message_id={message_id}"]
                + ([f"source_url={item_url}"] if item_url else []),
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
