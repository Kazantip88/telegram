from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from .config import Settings


def build_subject(lead: dict) -> str:
    icon = "HOT" if lead["priority"] == "HOT" else "NORMAL"
    amount = f"EUR {lead['amount']:,.0f}" if lead.get("amount") else "amount unknown"
    return f"[{icon}] Fraud-recovery lead — {amount} — {lead.get('category', 'Unknown')}"


def build_body(lead: dict) -> str:
    reasons = "\n".join(f"- {r}" for r in lead.get("reasons", [])) or "- none"
    amount = f"EUR {lead['amount']:,.0f}" if lead.get("amount") else "Not detected"
    return f"""New Telegram lead\n\nPriority: {lead['priority']}\nScore: {lead['score']}/100\nLanguage: {lead.get('language', 'unknown')}\nCategory: {lead.get('category', 'Unknown')}\nPotential loss: {amount}\nSource: {lead['source']}\nUsername: {lead.get('username') or 'not available'}\nMessage ID: {lead.get('telegram_message_id') or 'n/a'}\n\nScoring reasons:\n{reasons}\n\nOriginal public message:\n{lead['message']}\n\nHuman review is required before any legal or commercial decision.\n"""


def build_message(settings: Settings, lead: dict) -> EmailMessage:
    if not settings.mail_to:
        raise RuntimeError("MAIL_TO is required")
    msg = EmailMessage()
    msg["Subject"] = build_subject(lead)
    msg["From"] = settings.mail_from or settings.mail_to
    msg["To"] = settings.mail_to
    msg.set_content(build_body(lead))
    return msg


def _send_sync(settings: Settings, message: EmailMessage) -> None:
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is required when DRY_RUN=false")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


async def send_message(settings: Settings, message: EmailMessage) -> None:
    if settings.dry_run:
        print("DRY_RUN=true: email not sent")
        return
    await asyncio.to_thread(_send_sync, settings, message)
