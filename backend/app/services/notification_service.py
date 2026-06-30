"""
Outbound notifications: email (SMTP), Slack webhooks.

Config via .env (all optional — features are silently skipped when not set):
    SMTP_HOST       = smtp.gmail.com
    SMTP_PORT       = 587
    SMTP_USER       = you@gmail.com
    SMTP_PASSWORD   = your-app-password
    ALERT_EMAIL_TO  = admin@company.com,security@company.com
    SLACK_WEBHOOK_URL = https://hooks.slack.com/...
"""
import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from concurrent.futures import ThreadPoolExecutor

import httpx

log = logging.getLogger(__name__)

_MAIL_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="smtp")


def _send_smtp_sync(host: str, port: int, user: str, password: str,
                    recipients: list[str], subject: str, body_html: str,
                    body_text: str) -> None:
    """Blocking SMTP send — runs in a thread pool so the async loop is not blocked."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=10) as server:
        server.ehlo()
        if port != 465:
            server.starttls(context=context)
            server.ehlo()
        server.login(user, password)
        server.sendmail(user, recipients, msg.as_string())


class NotificationService:
    """
    Sends alerts via email and/or Slack webhooks.
    All config is read lazily from app settings so callers don't need to pass it.
    """

    def __init__(self, webhook_urls: list[str] | None = None):
        self.webhook_urls = webhook_urls or []
        # Lazy-import settings to avoid circular import
        self._settings = None

    def _cfg(self):
        if self._settings is None:
            from ..config import settings
            self._settings = settings
        return self._settings

    # ── Public alert methods ──────────────────────────────────────────────────
    async def notify_spoof(self, camera_id: str, snapshot_url: str | None = None):
        cfg = self._cfg()
        subject = "[ALERT] Spoof attempt detected"
        body_text = (
            f"A spoof (fake face) attempt was detected on camera: {camera_id}\n"
            f"Snapshot: {snapshot_url or 'N/A'}\n\n"
            "Check the dashboard for details."
        )
        body_html = _html_alert(
            title="Spoof Attempt Detected",
            color="#cc0000",
            lines=[
                f"<b>Camera:</b> {camera_id}",
                f"<b>Snapshot:</b> {snapshot_url or 'N/A'}",
                "Check the dashboard for live details.",
            ],
        )
        await self._send_all(subject, body_text, body_html)

    async def notify_intruder(self, camera_id: str, snapshot_url: str | None = None):
        subject = "[ALERT] Intruder detected outside business hours"
        body_text = (
            f"An unknown person was detected outside business hours on camera: {camera_id}\n"
            f"Snapshot: {snapshot_url or 'N/A'}"
        )
        body_html = _html_alert(
            title="Intruder Alert",
            color="#8b0000",
            lines=[
                f"<b>Camera:</b> {camera_id}",
                f"<b>Snapshot:</b> {snapshot_url or 'N/A'}",
                "Detected outside normal business hours (07:00–20:00 UTC).",
            ],
        )
        await self._send_all(subject, body_text, body_html)

    async def notify_blacklist(self, employee_name: str, camera_id: str,
                               snapshot_url: str | None = None):
        subject = f"[ALERT] Blacklisted employee detected: {employee_name}"
        body_text = (
            f"Blacklisted employee '{employee_name}' was detected on camera {camera_id}.\n"
            f"Snapshot: {snapshot_url or 'N/A'}"
        )
        body_html = _html_alert(
            title="Blacklisted Employee Detected",
            color="#8b0000",
            lines=[
                f"<b>Employee:</b> {employee_name}",
                f"<b>Camera:</b> {camera_id}",
                f"<b>Snapshot:</b> {snapshot_url or 'N/A'}",
            ],
        )
        await self._send_all(subject, body_text, body_html)

    async def notify_late(self, employee_name: str, late_by_min: int):
        subject = f"[INFO] Late arrival: {employee_name} ({late_by_min} min)"
        body_text = f"{employee_name} arrived {late_by_min} minute(s) late."
        body_html = _html_alert(
            title="Late Arrival",
            color="#e67e00",
            lines=[f"<b>{employee_name}</b> arrived <b>{late_by_min} min</b> late."],
        )
        await self._send_all(subject, body_text, body_html)

    async def notify_after_hours(self, employee_name: str, camera_id: str):
        subject = f"[ALERT] After-hours detection: {employee_name}"
        body_text = (
            f"{employee_name} was detected outside their shift window on camera {camera_id}."
        )
        body_html = _html_alert(
            title="After-Hours Detection",
            color="#c47c00",
            lines=[
                f"<b>Employee:</b> {employee_name}",
                f"<b>Camera:</b> {camera_id}",
                "This person was seen outside their scheduled shift window.",
            ],
        )
        await self._send_all(subject, body_text, body_html)

    async def notify_digest(self, date_str: str, total: int, present: int,
                            absent: int, late: int) -> None:
        """Daily attendance digest email."""
        rate = round(present / total * 100, 1) if total else 0.0
        subject = f"[Attendance] Daily report — {date_str}"
        body_text = (
            f"Attendance digest for {date_str}\n"
            f"  Present: {present}/{total}  ({rate}%)\n"
            f"  Absent : {absent}\n"
            f"  Late   : {late}"
        )
        body_html = _html_alert(
            title=f"Daily Attendance Report — {date_str}",
            color="#2a7ae2",
            lines=[
                f"<b>Present:</b> {present} / {total} ({rate}%)",
                f"<b>Absent:</b>  {absent}",
                f"<b>Late:</b>    {late}",
            ],
        )
        await self._email(subject, body_text, body_html)

    async def send_generic_webhook(self, payload: dict) -> None:
        await self._fire_webhooks(payload)

    # ── Internal send helpers ─────────────────────────────────────────────────
    async def _send_all(self, subject: str, body_text: str, body_html: str) -> None:
        await asyncio.gather(
            self._email(subject, body_text, body_html),
            self._fire_webhooks({"subject": subject, "body": body_text}),
            return_exceptions=True,
        )

    async def _email(self, subject: str, body_text: str, body_html: str) -> None:
        cfg = self._cfg()
        if not (cfg.SMTP_HOST and cfg.SMTP_USER and cfg.SMTP_PASSWORD and cfg.ALERT_EMAIL_TO):
            return  # SMTP not configured — skip silently
        recipients = [r.strip() for r in cfg.ALERT_EMAIL_TO.split(",") if r.strip()]
        if not recipients:
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                _MAIL_POOL, _send_smtp_sync,
                cfg.SMTP_HOST, cfg.SMTP_PORT, cfg.SMTP_USER, cfg.SMTP_PASSWORD,
                recipients, subject, body_html, body_text,
            )
            log.info("Email sent: %s → %s", subject, recipients)
        except Exception as e:
            log.error("SMTP error sending %r: %s", subject, e)

    async def _fire_webhooks(self, payload: dict) -> None:
        if not self.webhook_urls:
            return
        async with httpx.AsyncClient(timeout=5) as client:
            for url in self.webhook_urls:
                try:
                    await client.post(url, json=payload)
                except Exception as e:
                    log.warning("Webhook %s failed: %s", url, e)


# ── HTML email template ───────────────────────────────────────────────────────
def _html_alert(title: str, color: str, lines: list[str]) -> str:
    items = "".join(f"<p style='margin:4px 0'>{l}</p>" for l in lines)
    return f"""
<html><body style='font-family:sans-serif;background:#f4f4f4;padding:20px'>
<div style='max-width:520px;margin:auto;background:#fff;border-radius:8px;
            overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.12)'>
  <div style='background:{color};padding:18px 24px'>
    <h2 style='color:#fff;margin:0'>{title}</h2>
  </div>
  <div style='padding:20px 24px;color:#333;line-height:1.6'>{items}</div>
  <div style='background:#f4f4f4;padding:10px 24px;font-size:11px;color:#888'>
    Smart AI Attendance System
  </div>
</div>
</body></html>
"""
