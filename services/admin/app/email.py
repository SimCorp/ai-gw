"""
Minimal SMTP email sender. All sends are no-ops when SMTP_HOST is not set.
Uses asyncio.to_thread to avoid blocking the event loop.
"""
import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)


def _get_smtp_settings():
    """Read SMTP config from env at send time (not import time)."""
    import os
    return {
        "host": os.getenv("SMTP_HOST", ""),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from_addr": os.getenv("SMTP_FROM", "AI Gateway <noreply@simcorp.com>"),
        "portal_url": os.getenv("PORTAL_BASE_URL", "http://localhost:3001"),
    }


def _send_sync(to: str, subject: str, html: str, cfg: dict) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
        s.ehlo()
        s.starttls(context=ctx)
        s.login(cfg["user"], cfg["password"])
        s.sendmail(cfg["from_addr"], [to], msg.as_string())


async def send_email(to: str, subject: str, html: str) -> None:
    cfg = _get_smtp_settings()
    if not cfg["host"]:
        log.info("SMTP not configured — skipping email to %s: %s", to, subject)
        return
    try:
        await asyncio.to_thread(_send_sync, to, subject, html, cfg)
        log.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        log.error("Failed to send email to %s: %s — %s", to, subject, exc)


def password_reset_html(portal_url: str, reset_url: str, display_name: str) -> str:
    return f"""
<html><body style="font-family:sans-serif;color:#1a1a2e;max-width:560px;margin:auto">
<h2>Reset your AI Gateway password</h2>
<p>Hi {display_name},</p>
<p>Someone requested a password reset for your account. Click below to set a new password.
This link expires in <strong>1 hour</strong>.</p>
<p><a href="{reset_url}" style="background:#0A7BD7;color:#fff;padding:10px 20px;
border-radius:6px;text-decoration:none;display:inline-block">Reset password</a></p>
<p style="color:#888;font-size:12px">If you didn't request this, you can ignore this email.
Your password will not change.</p>
</body></html>"""


def password_changed_html(portal_url: str, display_name: str) -> str:
    return f"""
<html><body style="font-family:sans-serif;color:#1a1a2e;max-width:560px;margin:auto">
<h2>Your AI Gateway password was changed</h2>
<p>Hi {display_name},</p>
<p>Your password was just changed. If this was you, no action is needed.</p>
<p>If you didn't make this change, <a href="{portal_url}/login">sign in</a> immediately
and contact your administrator.</p>
</body></html>"""


def team_assignment_html(portal_url: str, display_name: str, team_name: str, assigner: str) -> str:
    return f"""
<html><body style="font-family:sans-serif;color:#1a1a2e;max-width:560px;margin:auto">
<h2>You've been added to a team</h2>
<p>Hi {display_name},</p>
<p><strong>{assigner}</strong> has added you to the <strong>{team_name}</strong> team
on the AI Gateway.</p>
<p><a href="{portal_url}" style="background:#0A7BD7;color:#fff;padding:10px 20px;
border-radius:6px;text-decoration:none;display:inline-block">Open portal</a></p>
</body></html>"""
