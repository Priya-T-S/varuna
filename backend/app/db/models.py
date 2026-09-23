"""
ORM models for alerting and the what-if assistant.

Portable across SQLite (default, zero-setup) and PostgreSQL. Table names are
distinct from database/schema.sql's `alerts` table, which models the older
prediction-linked design.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Recipient(Base):
    """A district official who receives alerts (collector, ADM, SDMA officer...)."""

    __tablename__ = "alert_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40), default="collector")  # collector | adm | sdma | control_room
    region: Mapped[str] = mapped_column(String(40), index=True)
    district: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)  # None = whole region
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channels: Mapped[list] = mapped_column(JSON, default=list)  # ["telegram","email","sms","whatsapp"]
    min_level: Mapped[str] = mapped_column(String(16), default="high")  # escalation tier
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AlertRule(Base):
    """Threshold + cooldown policy. region/district None = applies everywhere."""

    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region: Mapped[str | None] = mapped_column(String(40), nullable=True)
    district: Mapped[str | None] = mapped_column(String(80), nullable=True)
    min_level: Mapped[str] = mapped_column(String(16), default="high")
    min_probability: Mapped[float] = mapped_column(Float, default=0.0)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=180)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class FloodAlert(Base):
    __tablename__ = "flood_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region: Mapped[str] = mapped_column(String(40), index=True)
    district: Mapped[str] = mapped_column(String(80), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(16))           # moderate | high | severe
    flood_probability: Mapped[float] = mapped_column(Float)  # max village probability in district
    rain_probability: Mapped[float | None] = mapped_column(Float, nullable=True)  # fusion model
    rain_event_mm: Mapped[float] = mapped_column(Float)
    rain_duration_days: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    top_drivers: Mapped[list] = mapped_column(JSON, default=list)
    affected_villages: Mapped[list] = mapped_column(JSON, default=list)
    similar_incident: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="monitor")  # monitor | manual | scenario | test
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # --- explainability & operational metadata (all nullable: added by migration) ---
    status: Mapped[str | None] = mapped_column(String(16), nullable=True, default="active")  # active | acknowledged | resolved
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supersedes_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    why: Mapped[list | None] = mapped_column(JSON, nullable=True)            # [{icon, text}]
    model_drivers: Mapped[list | None] = mapped_column(JSON, nullable=True)  # SHAP top features
    timeline: Mapped[list | None] = mapped_column(JSON, nullable=True)       # [{offset_h, band, probability}]
    actions: Mapped[list | None] = mapped_column(JSON, nullable=True)        # [{text, priority, owner}]
    confidence_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    horizon_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)  # observed | climatology | demo | scenario | test
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance: Mapped[list | None] = mapped_column(JSON, nullable=True)     # which components ran / were estimated

    deliveries: Mapped[list["AlertDelivery"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan", order_by="AlertDelivery.id"
    )
    events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan", order_by="AlertEvent.id"
    )


class AlertEvent(Base):
    """Audit trail: every lifecycle step, who did it and when."""

    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("flood_alerts.id", ondelete="CASCADE"), index=True)
    # detected | generated | reviewed | sent | acknowledged | severity_changed | note | resolved
    stage: Mapped[str] = mapped_column(String(24))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    detail: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    alert: Mapped[FloodAlert] = relationship(back_populates="events")


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("flood_alerts.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[int | None] = mapped_column(ForeignKey("alert_recipients.id", ondelete="SET NULL"), nullable=True)
    recipient_name: Mapped[str] = mapped_column(String(120))
    channel: Mapped[str] = mapped_column(String(16))   # telegram | email | sms | whatsapp | inapp | console
    target: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(16))    # sent | failed | skipped
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    alert: Mapped[FloodAlert] = relationship(back_populates="deliveries")


class ChatMessage(Base):
    """Conversation history for the what-if assistant (full API content blocks)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))   # user | assistant
    content: Mapped[list] = mapped_column(JSON)     # list of content blocks as sent to the API
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
