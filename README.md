# Telegram Law Lead Monitor

RU/DE Telegram monitoring MVP for identifying public messages that may indicate fraud-related financial losses and routing qualified leads to a law-firm inbox.

## Priority rules

- **80+** → 🔴 HOT
- **50–79** → 🟠 NORMAL
- **<50** → ignored

The score is a triage signal only. A human must review every lead before any legal or commercial decision.

## Flow

```text
Telegram public sources
        ↓
RU/DE keyword detection
        ↓
Fraud / loss signal extraction
        ↓
Lead scoring
        ↓
80+ HOT ───────┐
50–79 NORMAL ──┼→ email
<50 IGNORE     │
        ↓      │
SQLite dedup ──┘
```

## Features

- German + Russian keyword dictionaries
- Fraud/investment context detection
- EUR amount extraction (`€18,500`, `18.500 EUR`, `15k`)
- Broker/exchange/platform hints
- Withdrawal-blocked / support-unresponsive signals
- Evidence/document signals
- Duplicate suppression
- SQLite storage
- SMTP email delivery
- Dry-run mode for safe testing
- No automatic Telegram outreach to users

## Setup

1. Copy `.env.example` to `.env`.
2. Create a Telegram API application at `my.telegram.org` and put `TG_API_ID` and `TG_API_HASH` in `.env`.
3. Add Telegram public channels/groups you are authorized to monitor to `TG_SOURCES` (comma-separated usernames or public links).
4. Configure SMTP.
5. Start with `DRY_RUN=true`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app
```

The first Telethon run may ask for a phone number and Telegram login code. Keep the generated session file private and never commit it.

## Email destination

Default destination:

`info@lawlegal500.de`

## Safety / privacy

Only monitor Telegram sources you are authorized to monitor and comply with Telegram terms and applicable privacy/data-protection law. Store the minimum data necessary. Do not collect passwords, payment credentials, identity documents, or other unnecessary sensitive information. The application is for lead triage, not legal advice and not an automated legal eligibility decision.
