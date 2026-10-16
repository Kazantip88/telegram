from __future__ import annotations

import base64
import html
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

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
        raise RuntimeError(f"Gmail OAuth client file not found: {client_file}")
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
        data = (part.get("body", {}) or {}).get("data")
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
    return {str(x.get("name", "")).lower(): str(x.get("value", "")) for x in payload.get("headers", []) or []}

def _links(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>\"']+", text)

def _unwrap_google_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.lower() in {"www.google.com", "google.com"}:
        target = parse_qs(parsed.query).get("url", [None])[0]
        if target:
            return unquote(target)
    return url

def _build_text(headers: dict[str, str], payload: dict) -> tuple[str, str | None]:
    plain, html_body = _parts(payload)
    body = plain or _strip_html(html_body)
    subject = headers.get("subject", "").strip()
    sender = headers.get("from", "").strip()
    return "\n\n".join(x for x in (subject, body) if x).strip(), sender or None

def _extract_alert_items(text: str) -> list[tuple[str, str | None]]:
    """Split Google Alerts into separate result segments using URL boundaries."""
    matches = list(re.finditer(r"https?://[^\s<>\"']+", text))
    unique: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for match in matches:
        raw = match.group(0).rstrip(".,)")
        destination = _unwrap_google_url(raw)
        parsed = urlparse(destination)
        host = parsed.netloc.lower().removeprefix("www.")
        if not host or host.endswith("google.com") or host.endswith("googleusercontent.com"):
            continue
        key = destination.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        unique.append((match.start(), match.end(), destination))
    if not unique:
        return [(text, None)]

    items: list[tuple[str, str | None]] = []
    for i, (url_start, url_end, destination) in enumerate(unique):
        start = unique[i - 1][1] if i else 0
        segment = text[start:url_start].strip()
        if i == 0:
            # Drop Google Alert subject/header boilerplate before the first result.
            marker = re.search(r"===\s*Web\s*-\s*\d+\s+new results.*?===", segment, re.I | re.S)
            if marker:
                segment = segment[marker.end():].strip()
        segment = re.sub(r"(?is)Links:\s*.*$", "", segment).strip()
        if segment:
            items.append((segment, destination))
    return items or [(text, None)]

def _source_kind(url: str | None, item_text: str) -> str:
    if not url:
        return "unknown"
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    title = item_text.lower()
    news_hosts = {"tass.ru", "ria.ru", "rbc.ru", "kommersant.ru", "lenta.ru", "gazeta.ru", "interfax.ru", "forbes.ru", "focus.de", "spiegel.de", "faz.net", "welt.de", "bild.de"}
    qna_hosts = {"banki.ru", "stackoverflow.com", "quora.com", "gutefrage.net"}
    if host in qna_hosts:
        return "qna"
    if host in news_hosts or any(x in title for x in ("новости", "nachrichten")):
        return "news"
    if any(x in path for x in ("/otzyv", "/otzyvy", "/reviews", "/review/", "/news/", "/article/")):
        return "article"
    return "public"

def _has_personal_victim_language(text: str) -> bool:
    """Strong first-person/direct-victim signal only; generic article phrases do not qualify."""
    t = text.lower().replace("ё", "е")
    patterns = (
        r"\bя\s+(?:потерял|потеряла|вложил|вложила|инвестировал|инвестировала)\b",
        r"\bя\s+(?:потерял|потеряла)\s+(?:деньги|сбережения|средства)\b",
        r"\bменя\s+(?:обманули|развели|обокрали)\b",
        r"\bу\s+меня\s+(?:украли|заблокировали|пропали)\b",
        r"\bу\s+меня\s+(?:не\s+выводят|заблокирован\s+вывод|заблокировали\s+вывод)\b",
        r"\bя\s+не\s+могу\s+вывести\s+(?:деньги|средства|свой\s+депозит|свои\s+деньги)\b",
        r"\bich\s+(?:habe|hatte)\b.{0,80}\b(?:verloren|investiert|bezahlt|überwiesen)\b",
        r"\bich\s+wurde\s+betrogen\b",
        r"\bmir\s+wurde\b.{0,80}\b(?:geld|konto|auszahlung)\b",
        r"\bich\s+kann\s+(?:mein\s+)?geld\s+nicht\s+(?:auszahlen|abheben)\b",
        r"\bich\s+bekomme\s+mein\s+geld\s+nicht\s+zur[üu]ck\b",
        r"\bich\s+brauche\s+(?:hilfe|einen\s+anwalt|rechtliche\s+hilfe)\b",
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
    response = service.users().messages().list(userId="me", q=_setting("GMAIL_QUERY", ""), maxResults=max(1, int(_setting("GMAIL_MAX_MESSAGES", "50")))).execute()
    items = response.get("messages", []) or []
    qualified = hot = normal = 0
    for item in items:
        message_id = str(item["id"])
        full = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        headers = _headers(full.get("payload", {}))
        text, sender = _build_text(headers, full.get("payload", {}))
        if not text:
            continue
        for item_text, item_url in _extract_alert_items(text):
            kind = _source_kind(item_url, item_text)
            if kind in {"news", "qna", "article"} or not _has_personal_victim_language(item_text):
                continue
            signals = detect(item_text)
            result = score_lead(signals)
            if result.total < settings.min_email_score:
                continue
            source = "gmail:google-alerts"
            lead = {
                "fingerprint": fingerprint(source, message_id + "|" + (item_url or ""), item_text),
                "telegram_message_id": None,
                "source": source,
                "sender_id": message_id,
                "username": sender,
                "language": signals.language,
                "amount": max(signals.amounts) if signals.amounts else None,
                "score": result.total,
                "priority": result.priority,
                "category": _category(signals),
                "message": item_text,
                "reasons": list(result.reasons) + [f"gmail_message_id={message_id}"] + ([f"source_url={item_url}"] if item_url else []),
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
