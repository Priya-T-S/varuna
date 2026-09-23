"""
Channel implementations.

  telegram   Telegram Bot API (free, instant, rich HTML + buttons, group broadcast)
  email      SMTP (free with Gmail App Password), HTML report
  sms        Twilio Programmable SMS (free trial credit, verified numbers)
  whatsapp   Twilio WhatsApp (free sandbox)
  inapp      Live dashboard feed over Server-Sent Events (always on)
  console    Structured log line (always on - dry-run / audit)

All HTTP calls use httpx directly (no vendor SDKs). A provider reports
itself disabled until its credentials are present in the environment.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app.core.config import Settings
from app.services.notifications import formatting
from app.services.notifications.base import (
    AlertPayload,
    DeliveryResult,
    NotificationProvider,
    RecipientTarget,
)
from app.services.notifications.broadcaster import broadcaster

logger = logging.getLogger("varuna.alerts")

_HTTP_TIMEOUT = httpx.Timeout(15.0)


def _http_result(resp: httpx.Response, id_key: str) -> DeliveryResult:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.is_success:
        return DeliveryResult(ok=True, provider_message_id=str(_dig(body, id_key) or ""))
    message = body.get("description") or body.get("message") or resp.text[:300]
    # 4xx (bad number, bad token) will not fix itself on retry; 429/5xx might.
    retryable = resp.status_code == 429 or resp.status_code >= 500
    return DeliveryResult(ok=False, error=f"HTTP {resp.status_code}: {message}", retryable=retryable)


def _dig(body: dict, dotted: str):
    cur = body
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


# ---------------------------------------------------------------------------
class TelegramProvider(NotificationProvider):
    channel = "telegram"
    display_name = "Telegram Bot"
    cost_note = "Free"

    def __init__(self, settings: Settings) -> None:
        self.token = settings.TELEGRAM_BOT_TOKEN

    def enabled(self) -> bool:
        return bool(self.token)

    def missing_config(self) -> list[str]:
        return [] if self.token else ["TELEGRAM_BOT_TOKEN"]

    def target_for(self, recipient: RecipientTarget) -> str | None:
        return recipient.telegram_chat_id

    async def send(self, target: str, alert: AlertPayload, recipient: RecipientTarget) -> DeliveryResult:
        payload = {
            "chat_id": target,
            "text": formatting.telegram_html(alert, recipient),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        buttons = formatting.telegram_buttons(alert, recipient)
        if buttons:
            payload["reply_markup"] = buttons
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(f"https://api.telegram.org/bot{self.token}/sendMessage", json=payload)
        return _http_result(resp, "result.message_id")


# ---------------------------------------------------------------------------
class EmailProvider(NotificationProvider):
    channel = "email"
    display_name = "E-mail (SMTP)"
    cost_note = "Free (Gmail App Password)"

    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def enabled(self) -> bool:
        return bool(self.s.SMTP_HOST and self.s.SMTP_USER and self.s.SMTP_PASSWORD)

    def missing_config(self) -> list[str]:
        return [k for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD") if not getattr(self.s, k)]

    def target_for(self, recipient: RecipientTarget) -> str | None:
        return recipient.email

    async def send(self, target: str, alert: AlertPayload, recipient: RecipientTarget) -> DeliveryResult:
        msg = EmailMessage()
        msg["Subject"] = formatting.email_subject(alert)
        msg["From"] = self.s.SMTP_FROM or self.s.SMTP_USER
        msg["To"] = target
        msg.set_content(formatting.whatsapp_text(alert, recipient).replace("*", ""))
        msg.add_alternative(formatting.email_html(alert, recipient), subtype="html")

        def _send() -> None:
            context = ssl.create_default_context()
            if self.s.SMTP_PORT == 465:
                with smtplib.SMTP_SSL(self.s.SMTP_HOST, self.s.SMTP_PORT, context=context, timeout=20) as smtp:
                    smtp.login(self.s.SMTP_USER, self.s.SMTP_PASSWORD)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(self.s.SMTP_HOST, self.s.SMTP_PORT, timeout=20) as smtp:
                    if self.s.SMTP_USE_TLS:
                        smtp.starttls(context=context)
                    smtp.login(self.s.SMTP_USER, self.s.SMTP_PASSWORD)
                    smtp.send_message(msg)

        try:
            await asyncio.to_thread(_send)
            return DeliveryResult(ok=True, provider_message_id=msg.get("Message-ID"))
        except smtplib.SMTPAuthenticationError as exc:
            return DeliveryResult(ok=False, error=f"SMTP authentication failed: {exc.smtp_error!r}", retryable=False)
        except smtplib.SMTPRecipientsRefused as exc:
            return DeliveryResult(ok=False, error=f"Recipient refused: {exc.recipients}", retryable=False)
        except (smtplib.SMTPException, OSError) as exc:
            return DeliveryResult(ok=False, error=f"SMTP error: {exc}")


# ---------------------------------------------------------------------------
class _TwilioBase(NotificationProvider):
    def __init__(self, settings: Settings) -> None:
        self.sid = settings.TWILIO_ACCOUNT_SID
        self.token = settings.TWILIO_AUTH_TOKEN

    async def _post(self, sender: str, to: str, body: str) -> DeliveryResult:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, auth=(self.sid, self.token)) as client:
            resp = await client.post(url, data={"From": sender, "To": to, "Body": body})
        return _http_result(resp, "sid")


class TwilioSmsProvider(_TwilioBase):
    channel = "sms"
    display_name = "SMS (Twilio)"
    cost_note = "Free trial credit"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.sender = settings.TWILIO_SMS_FROM

    def enabled(self) -> bool:
        return bool(self.sid and self.token and self.sender)

    def missing_config(self) -> list[str]:
        return [k for k, v in (("TWILIO_ACCOUNT_SID", self.sid), ("TWILIO_AUTH_TOKEN", self.token),
                               ("TWILIO_SMS_FROM", self.sender)) if not v]

    def target_for(self, recipient: RecipientTarget) -> str | None:
        return recipient.phone

    async def send(self, target: str, alert: AlertPayload, recipient: RecipientTarget) -> DeliveryResult:
        return await self._post(self.sender, target, formatting.sms_text(alert, recipient))


class TwilioWhatsAppProvider(_TwilioBase):
    channel = "whatsapp"
    display_name = "WhatsApp (Twilio)"
    cost_note = "Free sandbox"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        sender = settings.TWILIO_WHATSAPP_FROM
        self.sender = (sender if sender.startswith("whatsapp:") else f"whatsapp:{sender}") if sender else None

    def enabled(self) -> bool:
        return bool(self.sid and self.token and self.sender)

    def missing_config(self) -> list[str]:
        return [k for k, v in (("TWILIO_ACCOUNT_SID", self.sid), ("TWILIO_AUTH_TOKEN", self.token),
                               ("TWILIO_WHATSAPP_FROM", self.sender)) if not v]

    def target_for(self, recipient: RecipientTarget) -> str | None:
        number = recipient.whatsapp or recipient.phone
        return f"whatsapp:{number}" if number and not number.startswith("whatsapp:") else number

    async def send(self, target: str, alert: AlertPayload, recipient: RecipientTarget) -> DeliveryResult:
        return await self._post(self.sender, target, formatting.whatsapp_text(alert, recipient))


# ---------------------------------------------------------------------------
class InAppProvider(NotificationProvider):
    channel = "inapp"
    display_name = "Dashboard live feed"
    cost_note = "Built-in"

    def enabled(self) -> bool:
        return True

    def target_for(self, recipient: RecipientTarget) -> str | None:
        return "dashboard"

    async def send(self, target: str, alert: AlertPayload, recipient: RecipientTarget) -> DeliveryResult:
        delivered = broadcaster.publish(
            {
                "type": "alert",
                "alert_id": alert.id,
                "level": alert.level,
                "title": alert.title,
                "district": alert.district,
                "region": alert.region,
                "message": alert.message,
            }
        )
        return DeliveryResult(ok=True, provider_message_id=f"{delivered} live viewer(s)")


class ConsoleProvider(NotificationProvider):
    channel = "console"
    display_name = "Server log"
    cost_note = "Built-in"

    def enabled(self) -> bool:
        return True

    def target_for(self, recipient: RecipientTarget) -> str | None:
        return "log"

    async def send(self, target: str, alert: AlertPayload, recipient: RecipientTarget) -> DeliveryResult:
        logger.warning(
            "ALERT #%s [%s] %s/%s p=%.2f rain=%.0fmm - %s",
            alert.id, alert.level.upper(), alert.region, alert.district,
            alert.flood_probability, alert.rain_event_mm, alert.title,
        )
        return DeliveryResult(ok=True, provider_message_id="logged")


# ---------------------------------------------------------------------------
def build_providers(settings: Settings) -> dict[str, NotificationProvider]:
    providers: list[NotificationProvider] = [
        TelegramProvider(settings),
        EmailProvider(settings),
        TwilioSmsProvider(settings),
        TwilioWhatsAppProvider(settings),
        InAppProvider(),
        ConsoleProvider(),
    ]
    return {p.channel: p for p in providers}
