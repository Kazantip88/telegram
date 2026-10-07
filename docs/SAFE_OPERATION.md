# Safe operation profile

This project is intentionally designed for conservative, read-only monitoring. No implementation can guarantee that an account will never be restricted by Telegram.

## Before first login

- Use a separate, established Telegram account rather than a personal/main account.
- Use an API application created for this monitoring project and keep `api_id` / `api_hash` out of Git.
- Keep the Telethon `.session` file private; never commit or share it.
- Configure only public Telegram sources that you are authorized to monitor.

## Runtime rules

- Read-only: no DMs, replies, reactions, joins, invites, contact imports, or automated outreach.
- Do not use multiple sessions/accounts to bypass limits.
- Do not rotate accounts or IPs to evade restrictions.
- Do not attempt to bypass `FLOOD_WAIT` or other server-side limits.
- On a flood/rate-limit response, stop the worker and respect the server-provided wait period before any restart.
- Start with a small source set and conservative polling; increase coverage only after observing stable behavior.
- Prefer configured-source monitoring over global Telegram search.
- Keep request concurrency low and introduce deliberate delays between source/comment reads.
- Keep `DRY_RUN=true` until the monitoring behavior has been reviewed.

## Data handling

- Store only the minimum public message data required for lead triage and deduplication.
- Do not collect passwords, payment credentials, identity documents, authentication codes, or unrelated private information.
- Leads are triage signals only; a human lawyer must review them before any legal or commercial decision.

## Telegram terms

Telegram's current API terms prohibit using Telegram data to train, fine-tune, develop, enhance, or deploy AI/ML models. This project therefore uses deterministic rule-based detection/scoring and must not be turned into a training-data pipeline for Telegram content.

The Telegram API is monitored for abuse. There is no configuration that can guarantee immunity from restrictions or bans.

## Account placeholders

Keep these values empty until the dedicated monitoring account is ready:

```dotenv
TG_API_ID=
TG_API_HASH=
TG_SESSION=data/telegram_leads
TG_SOURCES=
```

Never put the Telegram login code or 2FA password in `.env`, source code, GitHub issues, or chat messages.
