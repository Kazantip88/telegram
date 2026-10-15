# Gmail Alerts setup

The collector uses the Gmail API with the readonly scope:

`https://www.googleapis.com/auth/gmail.readonly`

## Local credential files

Do **not** commit the Google OAuth client JSON or Gmail token. Google explicitly recommends keeping `client_secret.json` outside a public source tree.

Place the downloaded Desktop OAuth JSON at:

`data/google_client_secret.json`

The first local run opens Google's OAuth consent flow. After approval, the refresh token is saved to:

`data/gmail_token.json`

Both files are ignored by Git.

## Google Alerts

The collector reads Gmail messages, runs the existing RU/DE detector and lead scorer, deduplicates through the existing SQLite lead store, and sends qualified leads through the existing emailer. It does not mark Gmail messages as read.

Keep `DRY_RUN=true` until the first end-to-end cycle has been reviewed by a human.
