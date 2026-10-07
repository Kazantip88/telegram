# Telegram Law Lead Monitor

RU/DE Telegram monitoring MVP for identifying public messages that may indicate fraud-related financial losses and routing qualified leads to a law-firm inbox.

## Priority rules

- **80+** → 🔴 HOT
- **50–79** → 🟠 NORMAL
- **<50** → ignored

The score is a triage signal only. A human must review every lead before any legal or commercial decision.

## Flow

```text
Authorized public Telegram sources
              ↓
          RU / DE detection
              ↓
       fraud / loss signals
              ↓
          score 0–100
          /         \
       <50          50+
     IGNORE          ↓
                ┌────┴────┐
             50–79       80+
             NORMAL      HOT
                └────┬────┘
                     ↓
                 SQLite dedup
                     ↓
              email to law firm
                     ↓
              human lawyer review
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
- Email message generation for the law-firm inbox
- Dry-run mode for safe testing
- No automatic Telegram outreach to users

## Source model

The MVP monitors **public Telegram sources that are explicitly configured and authorized** in `TG_SOURCES`. Telegram does not expose an API that guarantees a complete inventory of every public Telegram channel/group, so a claim of scanning 100% of Telegram would be misleading.

For broader coverage, maintain a large registry of public RU/DE sources in `config/public_sources.example.txt` and periodically review/expand it. The monitor can then process the configured sources continuously without contacting their members.

## Setup

1. Copy `.env.example` to `.env`.
2. Create a Telegram API application at `my.telegram.org` and put `TG_API_ID` and `TG_API_HASH` in `.env`.
3. Add public channels/groups you are authorized to monitor to `TG_SOURCES` (comma-separated usernames or public links).
4. Configure the SMTP provider used by the law firm.
5. Start with `DRY_RUN=true` and review the generated messages before enabling any production mail transport.

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

The email contains the priority, score, language, category, detected loss amount, source, message ID, scoring reasons and the public message text. Lawyers decide whether and how to contact the person; the monitor does not send Telegram DMs.

## Safety / privacy

Only monitor Telegram sources you are authorized to monitor and comply with Telegram terms and applicable privacy/data-protection law. Store the minimum data necessary. Do not collect passwords, payment credentials, identity documents, or other unnecessary sensitive information. The application is for lead triage, not legal advice and not an automated legal eligibility decision.
