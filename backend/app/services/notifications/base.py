"""Provider contract + the plain snapshots providers work on (no DB access)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AlertPayload:
    id: int
    region: str
    district: str
    level: str                      # moderate | high | severe
    title: str
    message: str                    # plain-text body
    flood_probability: float
    rain_probability: float | None
    rain_event_mm: float
    rain_duration_days: int
    villages: list[dict[str, Any]]  # [{name, band, probability, depth_m, reasons}]
    drivers: list[str]
    similar_incident: dict[str, Any] | None
    valid_until: datetime
    dashboard_url: str
    source: str = "monitor"
    why: list[dict[str, Any]] = field(default_factory=list)       # [{icon, text, modelled}]
    timeline: list[dict[str, Any]] = field(default_factory=list)  # [{offset_h, band, probability}]
    actions: list[dict[str, Any]] = field(default_factory=list)   # [{text, priority, owner}]
    confidence_label: str | None = None
    horizon_hours: int = 24
    data_mode: str | None = None

    @property
    def peak(self) -> dict[str, Any] | None:
        return max(self.timeline, key=lambda p: p["probability"]) if self.timeline else None


@dataclass(frozen=True)
class RecipientTarget:
    id: int | None
    name: str
    role: str
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    telegram_chat_id: str | None = None
    ack_url: str | None = None


@dataclass
class DeliveryResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None
    retryable: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


class NotificationProvider(ABC):
    """One outbound channel. `enabled()` is False until its credentials are set."""

    channel: str = ""
    display_name: str = ""
    cost_note: str = ""

    @abstractmethod
    def enabled(self) -> bool: ...

    @abstractmethod
    def target_for(self, recipient: RecipientTarget) -> str | None:
        """The address this channel would use for `recipient` (None = cannot reach)."""

    @abstractmethod
    async def send(self, target: str, alert: AlertPayload, recipient: RecipientTarget) -> DeliveryResult: ...

    def missing_config(self) -> list[str]:
        return []
