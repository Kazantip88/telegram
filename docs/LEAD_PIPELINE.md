# Lead pipeline: direct public requests for help

## Qualification rule

A candidate is eligible only when all three gates pass:

1. Source gate: the destination is an approved user-generated discussion. News publishers, legal/SEO pages, company pages, broker reviews, marketing pages, unknown domains, search result pages, and article pages are not lead sources.
2. Personal-experience gate: the author uses first-person language describing their own financial loss, suspected fraud, or blocked withdrawal.
3. Help-intent gate: the author explicitly asks for help, advice, a lawyer, legal assistance, or what to do next.

Only after all gates pass does the existing score run. The candidate must then meet MIN_EMAIL_SCORE.

## Active source paths

- Reddit native public search RSS, sorted by newest, with RU/DE/EN/NL phrases. A Reddit result must link to a direct post permalink under /comments/.
- Public Telegram supergroups: original human-authored messages only. Broadcast channels are not treated as people. For broadcast channels, only qualifying messages in linked public discussions may pass.
- Optional RSS/Atom feeds: the feed transports discovery items, but each item's final link is independently checked against the user-generated host allowlist.

The current host allowlist includes Reddit, Quora, Gutefrage, Pikabu, StackExchange, Finanzfrage, and Banki.ru forum pages. Unknown hosts are rejected until reviewed and added deliberately.

## Disabled discovery methods

- Google Alerts/Gmail is not called by the scheduled pipeline.
- Facebook search-engine HTML scraping (Google/Bing/DuckDuckGo result pages) is not called by the scheduled pipeline.
- No search-engine result page is ever considered a direct user post.

These choices intentionally reduce volume to improve precision. They do not guarantee that every person in need will be found; public-platform search, indexing, privacy settings, and rate limits restrict coverage.

## Lead classes

- lead — first-person loss report + explicit help request from an approved user-generated source; eligible for scoring.
- intelligence — editorial/news/legal context; never a client lead.
- ignore — no direct personal-loss signal, no explicit help request, or unsupported source.

## Privacy and handling

- No DMs, unsolicited contact, reactions, joining groups, or profile enrichment.
- Telegram sender IDs and usernames are not persisted in new lead records.
- Public post permalink and a short excerpt (up to 1,800 characters) are retained for human verification.
- Human review is mandatory before any legal or commercial decision.
