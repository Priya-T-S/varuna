"""
Alert fan-out: resolve who should hear about an alert, send on every channel
they subscribed to (concurrently, with retry + backoff), and record each
attempt as an AlertDelivery row for the audit trail.

Escalation: each recipient has a `min_level` tier - e.g. the District
Collector gets `high` and above, the State EOC only `severe`.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from dataclasses import dataclass

from sqlalchemy import select

from app.core.config import Settings, settings as default_settings
from app.db.models import AlertDelivery, AlertEvent, FloodAlert, Recipient
from app.db.session import session_scope
from app.services import system_state
from app.services.notifications.base import (
    AlertPayload,
    DeliveryResult,
    NotificationProvider,
    RecipientTarget,
)
from app.services.notifications.broadcaster import broadcaster
from app.services.notifications.providers import build_providers

logger = logging.getLogger(__name__)

LEVELS = {"low": 0, "moderate": 1, "high": 2, "severe": 3}
BROADCAST_CHANNELS = ("inapp", "console")


def ack_token(alert_id: int, recipient_id: int | None, secret: str | None = None) -> str:
    key = (secret or default_settings.SECRET_KEY).encode()
    return hmac.new(key, f"{alert_id}:{recipient_id or 0}".encode(), hashlib.sha256).hexdigest()[:24]


def ack_url(alert_id: int, recipient_id: int | None, s: Settings | None = None) -> str:
    s = s or default_settings
    return (
        f"{s.PUBLIC_BASE_URL.rstrip('/')}{s.API_V1_PREFIX}/alerts/{alert_id}/ack"
        f"?r={recipient_id or 0}&token={ack_token(alert_id, recipient_id, s.SECRET_KEY)}"
    )


def alert_payload(alert: FloodAlert, s: Settings | None = None) -> AlertPayload:
    s = s or default_settings
    return AlertPayload(
        id=alert.id,
        region=alert.region,
        district=alert.district,
        level=alert.level,
        title=alert.title,
        message=alert.message,
        flood_probability=alert.flood_probability,
        rain_probability=alert.rain_probability,
        rain_event_mm=alert.rain_event_mm,
        rain_duration_days=alert.rain_duration_days,
        villages=list(alert.affected_villages or []),
        drivers=list(alert.top_drivers or []),
        similar_incident=alert.similar_incident,
        valid_until=alert.valid_until,
        dashboard_url=f"{s.DASHBOARD_URL.rstrip('/')}/alerts",
        source=alert.source,
        why=list(alert.why or []),
        timeline=list(alert.timeline or []),
        actions=list(alert.actions or []),
        confidence_label=alert.confidence_label,
        horizon_hours=alert.horizon_hours or 24,
        data_mode=alert.data_mode,
    )


def _target(r: Recipient, alert_id: int, s: Settings) -> RecipientTarget:
    return RecipientTarget(
        id=r.id, name=r.name, role=r.role, phone=r.phone, whatsapp=r.whatsapp, email=r.email,
        telegram_chat_id=r.telegram_chat_id, ack_url=ack_url(alert_id, r.id, s),
    )


@dataclass
class _Job:
    recipient: RecipientTarget
    channel: str
    target: str | None
    provider: NotificationProvider | None


class AlertDispatcher:
    def __init__(
        self,
        providers: dict[str, NotificationProvider] | None = None,
        settings: Settings | None = None,
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.settings = settings or default_settings
        self.providers = providers if providers is not None else build_providers(self.settings)
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds

    # ------------------------------------------------------------------
    def provider_status(self) -> list[dict]:
        return [
            {
                "channel": p.channel,
                "name": p.display_name,
                "enabled": p.enabled(),
                "cost": p.cost_note,
                "missing_config": p.missing_config(),
            }
            for p in self.providers.values()
        ]

    def matching_recipients(self, db, alert: FloodAlert) -> list[Recipient]:
        rows = db.scalars(select(Recipient).where(Recipient.active.is_(True))).all()
        level = LEVELS.get(alert.level, 0)
        return [
            r for r in rows
            if r.region.lower() == alert.region.lower()
            and (r.district is None or r.district.lower() == alert.district.lower())
            and LEVELS.get(r.min_level, 2) <= level
        ]

    # ------------------------------------------------------------------
    async def dispatch(
        self,
        alert_id: int,
        *,
        recipient_ids: list[int] | None = None,
        channels: list[str] | None = None,
        include_broadcast: bool = True,
    ) -> list[dict]:
        with session_scope() as db:
            alert = db.get(FloodAlert, alert_id)
            if alert is None:
                raise ValueError(f"Alert {alert_id} not found")
            payload = alert_payload(alert, self.settings)
            if recipient_ids is not None:
                recipients = db.scalars(select(Recipient).where(Recipient.id.in_(recipient_ids))).all()
            else:
                recipients = self.matching_recipients(db, alert)
            targets = [(_target(r, alert_id, self.settings), list(r.channels or [])) for r in recipients]

        jobs = self._plan(alert_id, targets, channels, include_broadcast)
        results = await asyncio.gather(*(self._deliver(job, payload) for job in jobs))

        with session_scope() as db:
            rows = [
                AlertDelivery(
                    alert_id=alert_id,
                    recipient_id=job.recipient.id,
                    recipient_name=job.recipient.name,
                    channel=job.channel,
                    target=_mask(job.target),
                    status=status,
                    provider_message_id=result.provider_message_id if result else None,
                    error=(result.error if result else skip_reason),
                    attempts=attempts,
                )
                for job, (status, result, attempts, skip_reason) in zip(jobs, results)
            ]
            db.add_all(rows)
            db.flush()
            summary = [
                {"channel": r.channel, "recipient": r.recipient_name, "status": r.status, "error": r.error}
                for r in rows
            ]
            counts = {s: sum(1 for r in rows if r.status == s) for s in ("sent", "failed", "skipped")}
            people = sorted({r.recipient_name for r in rows if r.channel not in BROADCAST_CHANNELS})
            channels = sorted({r.channel for r in rows if r.status == "sent"})
            db.add(AlertEvent(
                alert_id=alert_id,
                stage="sent",
                actor="system",
                detail=(
                    (
                        f"Sent to {len(people)} recipient(s) ({', '.join(people[:4])}{'…' if len(people) > 4 else ''}): "
                        f"{counts['sent']} delivered, {counts['failed']} failed, {counts['skipped']} skipped"
                        + (f" via {', '.join(channels)}." if channels else ".")
                    )
                    if people else
                    "Shown on the dashboard live feed and logged. No recipient with contact details is set up for this district."
                ),
                data={"counts": counts, "deliveries": summary},
            ))

        broadcaster.publish({"type": "deliveries", "alert_id": alert_id, "deliveries": summary})
        sent = sum(1 for s in summary if s["status"] == "sent")
        logger.info("Alert #%s dispatched: %d/%d deliveries sent", alert_id, sent, len(summary))
        return summary

    # ------------------------------------------------------------------
    def _plan(
        self,
        alert_id: int,
        targets: list[tuple[RecipientTarget, list[str]]],
        channels: list[str] | None,
        include_broadcast: bool,
    ) -> list[_Job]:
        wanted = set(channels) if channels else None
        jobs: list[_Job] = []
        seen: set[tuple[str, str]] = set()

        def add(recipient: RecipientTarget, channel: str) -> None:
            provider = self.providers.get(channel)
            target = provider.target_for(recipient) if provider else None
            key = (channel, target or f"none:{recipient.id}")
            if key in seen:
                return
            seen.add(key)
            jobs.append(_Job(recipient, channel, target, provider))

        for recipient, subscribed in targets:
            for channel in subscribed:
                if wanted is None or channel in wanted:
                    add(recipient, channel)

        s = self.settings
        telegram = self.providers.get("telegram")
        if s.TELEGRAM_DEFAULT_CHAT_ID and telegram and telegram.enabled() and (wanted is None or "telegram" in wanted):
            add(
                RecipientTarget(
                    id=None, name="Control room (Telegram group)", role="control_room",
                    telegram_chat_id=s.TELEGRAM_DEFAULT_CHAT_ID, ack_url=ack_url(alert_id, None, s),
                ),
                "telegram",
            )
        if include_broadcast:
            dashboard = RecipientTarget(id=None, name="Dashboard", role="system", ack_url=ack_url(alert_id, None, s))
            for channel in BROADCAST_CHANNELS:
                add(dashboard, channel)
        return jobs

    async def _deliver(
        self, job: _Job, payload: AlertPayload
    ) -> tuple[str, DeliveryResult | None, int, str | None]:
        if job.provider is None:
            return "skipped", None, 0, f"Unknown channel '{job.channel}'"
        if not job.provider.enabled():
            missing = ", ".join(job.provider.missing_config()) or "credentials"
            return "skipped", None, 0, f"{job.provider.display_name} not configured (set {missing})"
        if not job.target:
            return "skipped", None, 0, f"No {job.channel} address for {job.recipient.name}"
        if system_state.state.faults["notifications"] and job.channel not in BROADCAST_CHANNELS:
            return "failed", DeliveryResult(ok=False, error="Provider unreachable (simulated outage)"), 1, None

        result: DeliveryResult | None = None
        attempts = 0
        for attempt in range(1, self.max_attempts + 1):
            attempts = attempt
            try:
                result = await job.provider.send(job.target, payload, job.recipient)
            except Exception as exc:  # network errors, timeouts
                logger.warning("%s delivery attempt %d failed: %s", job.channel, attempt, exc)
                result = DeliveryResult(ok=False, error=f"{type(exc).__name__}: {exc}")
            if result.ok or not result.retryable:
                break
            if attempt < self.max_attempts:
                await asyncio.sleep(self.backoff_seconds * 2 ** (attempt - 1))
        return ("sent" if result and result.ok else "failed"), result, attempts, None


def _mask(target: str | None) -> str | None:
    """Keep audit rows useful without storing full phone numbers / e-mails in the clear."""
    if not target or target in ("dashboard", "log"):
        return target
    if "@" in target:
        user, _, domain = target.partition("@")
        return f"{user[:2]}***@{domain}"
    digits = target.replace("whatsapp:", "")
    return (("whatsapp:" if target.startswith("whatsapp:") else "") + digits[:3] + "****" + digits[-3:]) if len(digits) > 6 else target


_dispatcher: AlertDispatcher | None = None


def get_dispatcher() -> AlertDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AlertDispatcher()
    return _dispatcher


def set_dispatcher(dispatcher: AlertDispatcher | None) -> None:
    """Test hook: swap in a dispatcher with fake providers."""
    global _dispatcher
    _dispatcher = dispatcher
