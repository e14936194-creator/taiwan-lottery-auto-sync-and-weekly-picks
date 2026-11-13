"""Optional notification helpers (SMTP email or generic JSON webhook)."""

from __future__ import annotations

from email.message import EmailMessage
import json
import os
import smtplib
import urllib.request


def send_email_if_configured(subject: str, body: str) -> bool:
    """Send plain-text email when SMTP environment variables are provided."""
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("SMTP_TO")
    if not all([host, user, password, to_addr]):
        return False

    port = int(os.environ.get("SMTP_PORT", "587"))
    from_addr = os.environ.get("SMTP_FROM", user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)
    return True


def send_webhook_if_configured(body: str) -> bool:
    """Post report text to a JSON webhook (Discord/Slack/Google Chat compatible)."""
    webhook_url = os.environ.get("LOTTERY_WEBHOOK_URL")
    if not webhook_url:
        return False

    # Support both Slack/Google Chat ('text') and Discord ('content') payloads.
    payload = json.dumps({"text": body[:3900], "content": body[:1900]}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return 200 <= resp.status < 300
