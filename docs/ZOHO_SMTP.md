# Zoho Mail SMTP setup

The project is prepared for the lawlegal500.de mailbox hosted on Zoho Mail.

## Recommended SMTP settings

For a business/domain mailbox, Zoho documents the outgoing server as:

- SMTP host: `smtppro.zoho.com`
- Port: `587`
- Security: STARTTLS/TLS
- Authentication: required
- Username: the full mailbox address, e.g. `info@lawlegal500.de`

Zoho also supports port `465` with SSL. Use the exact endpoint shown by Zoho for the organization if the account is assigned a region-specific server.

## Password

Do not put the normal Zoho account password in GitHub.

If MFA is enabled, create an application-specific password in Zoho Account → Security → App Passwords and use that value as `SMTP_PASSWORD`. Zoho states that the app-specific password is shown only once and can later be revoked.

## Local .env

Copy `.env.example` to `.env` and fill only locally:

```text
SMTP_HOST=smtppro.zoho.com
SMTP_PORT=587
SMTP_USER=info@lawlegal500.de
SMTP_PASSWORD=<Zoho app-specific password>
MAIL_FROM=info@lawlegal500.de
MAIL_TO=info@lawlegal500.de
SMTP_USE_TLS=true
```

Keep `DRY_RUN=true` for the first Telegram test cycles. In DRY_RUN mode the application builds and prints the email but does not send it.

## Security

Never commit `.env`, the Zoho password/app password, Telegram API hash, Telegram session file, login code, or 2FA password.
