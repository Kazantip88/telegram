# Lead pipeline after Google Alerts false-positive review

## Principle

The system is looking for personal public appeals from people who report their own fraud/investment loss. It is not a news monitor and it is not a legal-article monitor.

The pipeline is:

1. Parse the source/result.
2. Classify the source type.
3. For external Google Alert results, allow only approved user-generated discussion/Q&A sources.
4. Require a direct first-person victim signal for a lead.
5. Only then run the existing score.
6. Email only candidates that pass both classification and score threshold.

## Result classes

- `lead` — direct first-person victim signal from an approved user-generated source; eligible for scoring.
- `intelligence` — useful broker/scam/news/legal information, but never a client lead.
- `ignore` — unsupported source or no reliable direct victim intent.

## Google Alerts source policy

Google Alerts is used only as a discovery mechanism. A result is lead-capable only when its destination is an explicitly approved user-generated discussion/Q&A source.

Approved user-generated sources currently include:

- Banki.ru forum (`/forum/` only)
- Quora
- Gutefrage
- Reddit
- Pikabu

Explicitly rejected as client-lead sources:

- news publishers;
- legal/SEO pages;
- generic articles, reviews and broker-warning pages;
- arbitrary or unknown domains;
- any page where the first-person wording is merely a quote inside an article.

For example, `bankstoday.net/.../zalarium-com-obzor` containing `Я уже потерял деньги...` is still rejected because the destination is not an approved user-generated discussion source.

## Direct victim signal

The classifier looks for first-person statements such as:

- RU: `я потерял`, `меня обманули`, `меня кинули`, `у меня украли`, `я не могу вывести`, `помогите вернуть мои деньги`.
- DE: `ich habe ... verloren`, `ich wurde betrogen`, `ich kann mein Geld nicht auszahlen`, `ich bekomme mein Geld nicht zurück`.
- EN: `I lost my money`, `I was scammed`, `I cannot withdraw`, `get my money back`.

Third-person phrases such as `жертва потеряла деньги`, `Geld verloren haben`, `Opfer` or `Betroffene` are not direct victim signals. First-person quotes inside rejected article/news sources are not leads either.

## Why this fixes the reviewed alerts

The reviewed Google Alert emails showed that the main false-positive source was context:

- legal SEO pages repeated all target keywords;
- news articles described victims without being written by the victim;
- broker warning pages used `Betrug`, `Geld zurück`, `Opfer` and similar terms as article content or CTA;
- the same broker/entity appeared across several Alert queries;
- a large number in an article was not necessarily the victim's loss;
- `kostenfreie Ersteinschätzung` was a law-firm CTA, not a user's request for legal help.

The classifier therefore rejects the source before scoring.

## Deduplication

Gmail lead fingerprints use the destination URL when available, so the same Alert result repeated across different Alert emails can collapse to one lead candidate.

## Telegram

Telegram public posts/comments also pass through the direct-victim gate. Telegram does not use the Google Alert source allowlist; its configured source is already a user-generated public channel/post stream.

## Tests

Regression cases for the reviewed false-positive patterns are in `app/lead_classifier_test.py`, including a Banki Today-style article with a first-person quote and unknown external sites.

Run locally from the repository root:

```bash
python3 -m unittest app.lead_classifier_test
```

The test suite is intentionally separate from the live Gmail collector and does not send email or modify the lead database.
