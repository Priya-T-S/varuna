"""Pydantic schemas for early-warning alerts, recipients and alert rules."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.schemas.prediction import GeoPoint, RiskLevel
from app.schemas.scenario import Antecedent, RecommendedAction, TimelinePoint


def _utc(dt: datetime) -> datetime:
    # SQLite hands back naive datetimes; they are stored as UTC. Mark them so
    # clients don't misread them as local time.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(_utc)]

FloodLevel = Literal["moderate", "high", "severe"]
Channel = Literal["telegram", "email", "sms", "whatsapp"]


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipient_name: str
    channel: str
    target: str | None
    status: str
    error: str | None
    attempts: int
    sent_at: UtcDatetime


class AffectedVillage(BaseModel):
    name: str
    band: str
    probability: float
    depth_m: float
    reasons: list[str] = []
    river_rise_m: float | None = None


class AlertEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage: str
    at: UtcDatetime
    actor: str
    detail: str
    data: dict | None = None


class WhyItem(BaseModel):
    icon: str = Field(..., description="rain | soil | river | terrain | dam | tide | drainage | history | ai")
    text: str
    modelled: bool = Field(False, description="True when the fact is a model estimate, not an observation")


class ModelDriver(BaseModel):
    feature: str
    label: str
    value: float | None = None
    contribution: float


class AlertResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    region_name: str
    location: GeoPoint
    risk_level: RiskLevel
    probability: float = Field(..., ge=0, le=1)
    valid_from: datetime
    valid_until: datetime
    message: str = Field(..., description="Human-readable warning text, including the AI's reasoning")
    issued_at: datetime
    is_active: bool
    # --- flood-alert details ---
    region: str
    district: str
    flood_level: FloodLevel
    title: str
    rain_probability: float | None = None
    rain_event_mm: float
    rain_duration_days: int
    top_drivers: list[str] = []
    affected_villages: list[AffectedVillage] = []
    similar_incident: dict | None = None
    source: str
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    deliveries: list[DeliveryResponse] = []
    # --- confidence, freshness, horizon ---
    confidence_pct: float | None = None
    confidence_label: str | None = Field(None, description="High | Medium | Low (AI rainfall model)")
    horizon_hours: int = Field(24, description="Horizon of the AI rainfall probability")
    data_mode: str | None = Field(None, description="observed | climatology | demo | scenario | test")
    data_as_of: datetime | None = Field(None, description="When the rainfall input was observed / entered")
    # --- explanation, projection, actions ---
    why: list[WhyItem] = []
    model_drivers: list[ModelDriver] = []
    timeline: list[TimelinePoint] = []
    actions: list[RecommendedAction] = []
    # --- lifecycle ---
    status: str = "active"
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    supersedes_id: int | None = None
    provenance: list[dict] = Field([], description="Which AI / rule components produced this alert")
    events: list[AlertEventResponse] = []


class ReviewRequest(BaseModel):
    by: str = Field(..., min_length=1, max_length=120)
    note: str = Field("", max_length=1000)


class SeverityRequest(BaseModel):
    by: str = Field(..., min_length=1, max_length=120)
    level: Literal["moderate", "high", "severe"]
    reason: str = Field(..., min_length=3, max_length=1000)


class ResolveRequest(BaseModel):
    by: str = Field(..., min_length=1, max_length=120)
    note: str = Field("", max_length=1000)


class NoteRequest(BaseModel):
    by: str = Field(..., min_length=1, max_length=120)
    text: str = Field(..., min_length=1, max_length=1000)


class RecipientIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    role: Literal["collector", "adm", "sdma", "control_room", "other"] = "collector"
    region: str
    district: str | None = Field(None, description="None = every district in the region")
    phone: str | None = Field(None, description="E.164, e.g. +919876543210")
    whatsapp: str | None = Field(None, description="E.164; defaults to phone")
    email: str | None = None
    telegram_chat_id: str | None = None
    channels: list[Channel] = []
    min_level: FloodLevel = "high"
    active: bool = True


class RecipientOut(RecipientIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: UtcDatetime


class AlertRuleIn(BaseModel):
    region: str | None = None
    district: str | None = None
    min_level: FloodLevel = "high"
    min_probability: float = Field(0.0, ge=0, le=1)
    cooldown_minutes: int = Field(180, ge=0, le=10080)
    active: bool = True


class AlertRuleOut(AlertRuleIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class EvaluateRequest(BaseModel):
    """Run the monitor for a region now. Without observations the region's
    current-month climatology is used; supply observed / forecast rainfall to
    evaluate a live situation."""

    region: str
    rain_24h_mm: float | None = Field(None, ge=0, le=2000)
    rain_event_mm: float | None = Field(None, ge=0, le=3000, description="Expected total over duration_days")
    duration_days: int = Field(3, ge=1, le=10)
    antecedent: Antecedent = "normal"
    dam_release: bool = False
    high_tide: bool = False
    dispatch: bool = True
    ignore_cooldown: bool = False
    observed_at: datetime | None = Field(None, description="When the rainfall figures were observed (default: now)")


class EvaluateResponse(BaseModel):
    region: str
    rain_event_mm: float
    rain_probability: float | None
    districts: list[dict]
    alerts_created: list[int]
    deliveries: dict[int, list[dict]] = {}


class TestAlertRequest(BaseModel):
    region: str = "Kerala"
    district: str | None = None
    level: FloodLevel = "high"
    recipient_ids: list[int] | None = Field(None, description="Default: every recipient of that district")
    channels: list[Channel] | None = Field(None, description="Default: each recipient's own channels")


class ProviderStatus(BaseModel):
    channel: str
    name: str
    enabled: bool
    cost: str
    missing_config: list[str]


class AcknowledgeRequest(BaseModel):
    by: str = Field("Dashboard user", max_length=120)
