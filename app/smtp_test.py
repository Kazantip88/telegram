from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    mail_from = os.getenv("MAIL_FROM", user).strip()
    mail_to = os.getenv("MAIL_TO", "").strip()
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "y", "on"}

    missing = [
        name
        for name, value in {
            "SMTP_HOST": host,
            "SMTP_USER": user,
            "SMTP_PASSWORD": password,
            "MAIL_FROM": mail_from,
            "MAIL_TO": mail_to,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit("Missing SMTP settings: " + ", ".join(missing))

    message = EmailMessage()
    message["Subject"] = "Telegram Lead Monitor — SMTP test"
    message["From"] = mail_from
    message["To"] = mail_to
    message.set_content(
        "SMTP test successful. This message confirms that the Telegram Lead Monitor can authenticate and send through Zoho SMTP."
    )

    print(f"Connecting to {host}:{port} (TLS={use_tls})...")
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(user, password)
        smtp.send_message(message)

    print(f"Test email sent to {mail_to}")


if __name__ == "__main__":
    main()
