from __future__ import annotations

import asyncio
import hashlib
import json
import random
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .db import fingerprint, get_collector_cursor, save_lead, set_collector_cursor
from .detector import detect
from .emailer import build_message, send_message
from .lead_classifier import classify, has_direct_victim_language
from .scoring import score_lead

X_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


@dataclass(frozen=True)
class XStats:
    queries: int = 0
    posts: int = 0
    personal_posts: int = 0
    qualified: int = 0
    hot: int = 0
    normal: int = 0


def _query_key(query: str) -> str:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:20]
    return f"x:recent:{digest}"


def _parse_payload(payload: dict) -> tuple[list[dict[str, str]], str | None]:
    rows: list[dict[str, str]] = []
    for post in payload.get("data", []) or []:
        post_id = str(post.get("id", "")).strip()
        text = str(post.get("text", "")).strip()
        if not post_id.isdigit() or not text:
            continue
        rows.append({
            "id": post_id,
            "text": text,
            "lang": str(post.get("lang", "")).strip(),
        })
    meta = payload.get("meta", {}) or {}
    newest_id = str(meta.get("newest_id", "")).strip() or None
    return rows, newest_id


def _fetch_sync(token: str, query: str, max_results: int, timeout: int, since_id: str | None = None) -> dict:
    params = {
        "query": query,
        "max_results": str(max_results),
        "sort_order": "recency",
        "post.fields": "created_at,lang",
    }
    if since_id and since_id.isdigit():
        params["since_id"] = since_id
    url = f"{X_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "Public-Help-Lead-Monitor/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"X API HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"X API request failed: {exc}") from exc


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


async def _save_post(settings, post: dict[str, str]) -> str | None:
    text = post["text"]
    source_url = f"https://x.com/i/web/status/{post['id']}"

    classification = classify(text, source_url, source="x:api")
    if classification.kind != "lead":
        return None

    excerpt = text[:1800]
    signals = detect(excerpt)
    result = score_lead(signals)
    if result.total < settings.min_email_score:
        return None

    source = "x:api"
    reasons = list(result.reasons) + list(classification.reasons)
    reasons.append(f"source_url={source_url}")
    if post.get("lang"):
        reasons.append(f"x_language={post['lang']}")

    lead = {
        "fingerprint": fingerprint(source, source_url, excerpt),
        "telegram_message_id": None,
        "source": source,
        "sender_id": None,
        "username": None,
        "source_url": source_url,
        "language": post.get("lang") or signals.language,
        "amount": max(signals.amounts) if signals.amounts else None,
        "score": result.total,
        "priority": result.priority,
        "category": _category(signals),
        "message": excerpt,
        "reasons": reasons,
    }
    if not await save_lead(settings.db_path, lead):
        return None

    message = build_message(settings, lead)
    print("\n=== QUALIFIED X LEAD ===")
    print(message.as_string())
    print("=== END X LEAD ===\n")
    await send_message(settings, message)
    return result.priority


async def collect_once(settings) -> XStats:
    if not settings.x_enabled or not settings.x_api_bearer_token:
        return XStats()

    totals = {"posts": 0, "personal_posts": 0, "qualified": 0, "hot": 0, "normal": 0}
    successful_queries = 0

    for index, query in enumerate(settings.x_search_queries):
        if index:
            await asyncio.sleep(random.uniform(0.5, 1.5))
        state_key = _query_key(query)
        cursor = await get_collector_cursor(settings.db_path, state_key)
        try:
            payload = await asyncio.to_thread(
                _fetch_sync,
                settings.x_api_bearer_token,
                query,
                settings.x_max_results,
                settings.x_timeout_seconds,
                cursor,
            )
            posts, newest_id = _parse_payload(payload)
            successful_queries += 1
            totals["posts"] += len(posts)

            for post in posts:
                if has_direct_victim_language(post["text"]):
                    totals["personal_posts"] += 1
                priority = await _save_post(settings, post)
                if priority is None:
                    continue
                totals["qualified"] += 1
                if priority == "HOT":
                    totals["hot"] += 1
                else:
                    totals["normal"] += 1

            # Advance only after all returned posts have been processed.
            # This prevents repeated reads of old results and reduces API spend.
            if newest_id:
                await set_collector_cursor(settings.db_path, state_key, newest_id)
        except Exception as exc:
            print(f"X API query failed ({query[:90]!r}): {exc}")

    return XStats(queries=successful_queries, **totals)
