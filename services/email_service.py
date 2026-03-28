"""Email notification service via Gmail SMTP."""

from __future__ import annotations

import logging

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

import aiosmtplib

from config import Config

logger = logging.getLogger(__name__)


async def send_email(
    subject: str,
    body: str,
    *,
    attachment_path: Path | None = None,
    html: bool = False,
) -> bool:
    if not Config.GMAIL_ADDRESS or not Config.GMAIL_APP_PASSWORD:
        logger.warning("Gmail not configured, skipping email")
        return False

    msg = MIMEMultipart()
    msg["From"] = Config.GMAIL_ADDRESS
    msg["To"] = Config.NOTIFICATION_EMAIL or Config.GMAIL_ADDRESS
    msg["Subject"] = subject

    content_type = "html" if html else "plain"
    msg.attach(MIMEText(body, content_type))

    if attachment_path and attachment_path.exists():
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment_path.read_bytes())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={attachment_path.name}",
        )
        msg.attach(part)

    try:
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=Config.GMAIL_ADDRESS,
            password=Config.GMAIL_APP_PASSWORD,
        )
        logger.info("Email sent: %s", subject)
        return True
    except Exception:
        logger.exception("Failed to send email: %s", subject)
        return False


async def send_daily_summary(summary_text: str) -> bool:
    from datetime import date
    subject = f"📊 Daily Tracker Summary — {date.today().isoformat()}"
    return await send_email(subject, summary_text)


async def send_weekly_summary(summary_text: str, excel_path: Path | None = None) -> bool:
    from datetime import date
    subject = f"📊 Weekly Tracker Report — {date.today().isoformat()}"
    return await send_email(subject, summary_text, attachment_path=excel_path)
