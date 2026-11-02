# Public Victim-Help Lead Monitor

Read-only monitoring of public discussions where a person describes their own suspected investment/crypto/forex loss and explicitly asks for help, advice, or legal assistance. It is a triage aid for human review, not an automated legal assessment.

## What counts as a lead

A result must satisfy all of the following:

1. It comes from an approved public user-generated discussion, not a news site, law-firm page, broker review, marketing page, or search-results page.
2. The author speaks in the first person about their own loss, fraud, or blocked withdrawal.
3. The author explicitly asks for help, advice, a lawyer, or what to do next.
4. The text reaches the configured score threshold.

A news article quoting a victim is not a lead. A general question about brokers or investments is not a lead. A victim story without a request for assistance is kept out of the qualified-lead queue.

## Active sources

- Telegram: global search plus explicitly configured public groups. Top-level messages are considered only in public supergroups, not broadcast/news channels. Forwarded messages and bot-authored posts are skipped. For broadcast channels, only qualifying replies in an active linked public discussion are considered.
- Reddit: native public search RSS, sorted by newest, across Russian, German, English, and Dutch help-seeking phrases. Only direct Reddit post permalinks (/comments/) are accepted.
- Optional public RSS/Atom feeds: RSS_FEEDS and COMMUNITY_FEEDS can supply public forums/Q&A feeds. The item destination must still be an approved user-generated host and must pass the same first-person + help-request filter.

Approved user-generated hosts currently include Reddit, Quora, Gutefrage, Pikabu, StackExchange, Finanzfrage, and Banki.ru forum pages. This is a conservative allowlist; add other forums only after manual review.

## Sources intentionally disabled

- Google Alerts/Gmail is not part of the scheduled lead pipeline. Google Alerts results frequently resolve to editorial/news/legal pages and are not first-party requests.
- Facebook HTML scraping through Google, Bing, or DuckDuckGo search pages is not part of the scheduled pipeline. Search-engine result pages are not a reliable direct source of Facebook user posts. A future Facebook connector must use an authorized official API.

## Qualification and privacy

- First-person loss and explicit request-for-help checks run before scoring.
- RU, DE, EN, and NL phrase recognition is supported.
- Forwarded Telegram messages and bot-authored posts/replies are excluded.
- New records do not persist Telegram sender IDs or usernames. The public post permalink is retained for a reviewer.
- Only a short excerpt (up to 1,800 characters) is included in alerts.
- The application does not send DMs, follow people, join groups, react, or contact authors.
- A human must review every candidate and decide whether any lawful, appropriate response is warranted.

## Priority rules

- 80+ → HOT
- 50–79 → NORMAL
- Below 50 → ignored

The score is a triage signal only. Never treat it as proof of fraud, a legal conclusion, or consent to be contacted.

## Setup

1. Copy the example environment file to .env.
2. For Telegram, create an API application at my.telegram.org and set TG_API_ID and TG_API_HASH.
3. Set TG_SOURCES to public supergroups or public channels whose linked discussion groups you are authorized to monitor. The collector will ignore top-level broadcast-channel posts as lead candidates.
4. Optionally set COMMUNITY_FEEDS / RSS_FEEDS to public RSS/Atom feeds from approved user-generated forums. Unknown domains are rejected automatically.
5. Configure SMTP for notifications. Keep DRY_RUN=true for the first run.

Run the application with Python after installing requirements. The first Telethon run may ask for a phone number and Telegram login code. Keep the generated session file private and never commit it.

## Email destination

Default destination: info@lawlegal500.de.

An alert includes the post permalink, short public excerpt, language, category, scoring reasons, and priority. It does not include a stored author ID or username. A human reviewer must open the original public context before any further action.

## Tests

Run the unit-test discovery command from the repository root:
python -m unittest discover -s . -p "*_test.py" -v
