# Lead pipeline after Google Alerts false-positive review

## Principle

Keyword scoring is not the first decision anymore.

The pipeline is now:

1. Parse the source/result.
2. Classify the source type.
3. Require a direct first-person victim signal for a lead.
4. Only then run the existing score.
5. Email only candidates that pass both classification and score threshold.

## Result classes

- `lead` — direct first-person victim signal; eligible for scoring.
- `intelligence` — useful broker/scam/news/legal information, but not a client lead.
- `ignore` — no reliable direct victim intent.

## Google Alerts source classes

- `legal` — Anwalt.de, Anwalt24, broker-betrug.de, kryptoschaden.de, betrugsopfer-hilfe.de and legal article paths.
- `news` — known news publishers such as DW and Postimees.
- `article` — generic article/review/news URL paths not otherwise classified.
- `public` — everything else, including public Q&A pages.

Legal/news/article results never enter lead scoring, even when they contain phrases such as `Geld zurück`, `Betrug`, `Opfer`, `Anlagebetrug`, `Betroffene` or large loss amounts.

## Direct victim signal

The classifier looks for first-person statements such as:

- RU: `я потерял`, `меня обманули`, `меня кинули`, `у меня украли`, `я не могу вывести`, `помогите вернуть мои деньги`.
- DE: `ich habe ... verloren`, `ich wurde betrogen`, `ich kann mein Geld nicht auszahlen`, `ich bekomme mein Geld nicht zurück`.
- EN: `I lost my money`, `I was scammed`, `I cannot withdraw`, `get my money back`.

Third-person phrases such as `жертва потеряла деньги`, `Geld verloren haben`, `Opfer` or `Betroffene` are not direct victim signals.

## Why this fixes the reviewed alerts

The 12 manually reviewed Google Alert emails showed that the main false-positive source was not arithmetic scoring. It was context:

- legal SEO pages repeated all target keywords;
- news articles described victims without being written by the victim;
- broker warning pages used `Betrug`, `Geld zurück`, `Opfer` and similar terms as article content or CTA;
- the same broker/entity appeared across several Alert queries;
- a large number in an article was not necessarily the victim's loss;
- `kostenfreie Ersteinschätzung` was a law-firm CTA, not a user's request for legal help.

The classifier therefore runs before scoring.

## Deduplication

Gmail lead fingerprints now use the destination URL when available, so the same Alert result repeated across different Alert emails can collapse to one lead candidate.

## Telegram

Telegram public posts/comments also pass through the direct-victim gate. This prevents generic investment questions and third-person stories from becoming leads merely because they contain broker/fraud keywords.

## Tests

Regression cases for the reviewed false-positive patterns are in `app/lead_classifier_test.py`.

Run locally from the repository root:

```bash
python3 -m unittest app.lead_classifier_test
```

The test suite is intentionally separate from the live Gmail collector and does not send email or modify the lead database.
