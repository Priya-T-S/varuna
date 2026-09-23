"""
Alert service — turns risk into district-level early warnings.

    conditions (observed / forecast rain, or current-month climatology)
      -> ScenarioService.assess_region   (fusion model + village hydrology)
      -> group villages by district      (district level = worst village band)
      -> AlertRule threshold + cooldown  (no repeats unless the level escalates)
      -> FloodAlert row + audit events   (why, timeline, actions, confidence, freshness)
      -> dispatcher                      (Telegram / e-mail / SMS / WhatsApp / dashboard)

Every alert carries an audit trail (detected -> generated -> reviewed -> sent
-> acknowledged -> resolved). Alerts are auto-approved by rule so warnings
are never delayed; operators can review, re-grade and resolve afterwards.

A background monitor re-evaluates every region every ALERT_SCAN_INTERVAL_MIN
minutes. There is no live rain-gauge feed yet, so unattended scans use
current-month climatology (data_mode "climatology"); operators push observed
rainfall via POST /alerts/evaluate (data_mode "observed").
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.models import AlertEvent, AlertRule, FloodAlert, Recipient
from app.db.session import session_scope
from app.schemas.alert import (
    AffectedVillage,
    AlertEventResponse,
    AlertResponse,
    DeliveryResponse,
    EvaluateRequest,
    EvaluateResponse,
    ModelDriver,
    TestAlertRequest,
    WhyItem,
)
from app.schemas.prediction import GeoPoint, RiskLevel
from app.schemas.scenario import RecommendedAction, TimelinePoint
from app.services import actions as action_service
from app.services import geo_data, hydrology_service, incident_service, system_state
from app.services.hydrology_service import Assessment, RainEvent
from app.services.notifications.broadcaster import broadcaster
from app.services.notifications.dispatcher import LEVELS, get_dispatcher
from app.services.scenario_service import RegionAssessment, ScenarioService, action_context

logger = logging.getLogger(__name__)

_RISK_FOR_LEVEL = {"moderate": RiskLevel.MODERATE, "high": RiskLevel.HEAVY, "severe": RiskLevel.EXTREME}
_ALERT_OPTIONS = [selectinload(FloodAlert.deliveries), selectinload(FloodAlert.events)]


class AlertNotFoundError(LookupError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; they are stored as UTC.
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _status(alert: FloodAlert) -> str:
    if alert.status:
        return alert.status
    return "acknowledged" if alert.acknowledged_at else "active"


def to_response(alert: FloodAlert, with_deliveries: bool = True) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        region_name=f"{alert.district}, {alert.region}",
        location=GeoPoint(latitude=alert.lat, longitude=alert.lon),
        risk_level=_RISK_FOR_LEVEL.get(alert.level, RiskLevel.MODERATE),
        probability=round(alert.flood_probability, 4),
        valid_from=_aware(alert.valid_from),
        valid_until=_aware(alert.valid_until),
        message=alert.message,
        issued_at=_aware(alert.issued_at),
        is_active=alert.is_active,
        region=alert.region,
        district=alert.district,
        flood_level=alert.level,
        title=alert.title,
        rain_probability=alert.rain_probability,
        rain_event_mm=alert.rain_event_mm,
        rain_duration_days=alert.rain_duration_days,
        top_drivers=list(alert.top_drivers or []),
        affected_villages=[AffectedVillage(**v) for v in (alert.affected_villages or [])],
        similar_incident=alert.similar_incident,
        source=alert.source,
        acknowledged_at=_aware(alert.acknowledged_at),
        acknowledged_by=alert.acknowledged_by,
        deliveries=[DeliveryResponse.model_validate(d) for d in alert.deliveries] if with_deliveries else [],
        confidence_pct=alert.confidence_pct,
        confidence_label=alert.confidence_label,
        horizon_hours=alert.horizon_hours or 24,
        data_mode=alert.data_mode,
        data_as_of=_aware(alert.data_as_of),
        why=[WhyItem(**w) for w in (alert.why or [])],
        model_drivers=[ModelDriver(**d) for d in (alert.model_drivers or [])],
        timeline=[TimelinePoint(**p) for p in (alert.timeline or [])],
        actions=[RecommendedAction(**a) for a in (alert.actions or [])],
        status=_status(alert),
        resolved_at=_aware(alert.resolved_at),
        resolved_by=alert.resolved_by,
        supersedes_id=alert.supersedes_id,
        provenance=list(alert.provenance or []),
        events=[AlertEventResponse.model_validate(e) for e in alert.events] if with_deliveries else [],
    )


def add_event(
    db: Session, alert: FloodAlert, stage: str, detail: str, actor: str = "system", data: dict | None = None
) -> AlertEvent:
    event = AlertEvent(alert_id=alert.id, stage=stage, actor=actor, detail=detail, data=data, at=_utcnow())
    db.add(event)
    return event


class AlertService:
    def __init__(self, scenario: ScenarioService | None = None) -> None:
        self.scenario = scenario or ScenarioService()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def list_active(self) -> list[AlertResponse]:
        self.deactivate_expired()
        with session_scope() as db:
            rows = db.scalars(
                select(FloodAlert)
                .where(FloodAlert.is_active.is_(True))
                .options(*_ALERT_OPTIONS)
                .order_by(FloodAlert.issued_at.desc())
            ).all()
            return [to_response(a) for a in rows]

    def list_recent(self, limit: int = 50) -> list[AlertResponse]:
        with session_scope() as db:
            rows = db.scalars(
                select(FloodAlert).options(*_ALERT_OPTIONS).order_by(FloodAlert.issued_at.desc()).limit(limit)
            ).all()
            return [to_response(a) for a in rows]

    def get(self, alert_id: int) -> AlertResponse | None:
        with session_scope() as db:
            alert = db.get(FloodAlert, alert_id, options=_ALERT_OPTIONS)
            return to_response(alert) if alert else None

    def events(self, alert_id: int) -> list[AlertEventResponse]:
        with session_scope() as db:
            alert = db.get(FloodAlert, alert_id, options=_ALERT_OPTIONS)
            if alert is None:
                raise AlertNotFoundError(alert_id)
            return [AlertEventResponse.model_validate(e) for e in alert.events]

    # ------------------------------------------------------------------
    # Lifecycle actions
    # ------------------------------------------------------------------
    def _mutate(self, alert_id: int, fn) -> AlertResponse:
        with session_scope() as db:
            alert = db.get(FloodAlert, alert_id, options=_ALERT_OPTIONS)
            if alert is None:
                raise AlertNotFoundError(alert_id)
            fn(db, alert)
            db.flush()
            db.refresh(alert, attribute_names=["events", "deliveries"])
            return to_response(alert)

    def acknowledge(self, alert_id: int, by: str) -> AlertResponse | None:
        def apply(db: Session, alert: FloodAlert) -> None:
            if alert.acknowledged_at is None:
                alert.acknowledged_at = _utcnow()
                alert.acknowledged_by = by
                if _status(alert) == "active":
                    alert.status = "acknowledged"
                add_event(db, alert, "acknowledged", f"Acknowledged by {by}.", actor=by)

        try:
            return self._mutate(alert_id, apply)
        except AlertNotFoundError:
            return None

    def review(self, alert_id: int, by: str, note: str = "") -> AlertResponse:
        def apply(db: Session, alert: FloodAlert) -> None:
            add_event(db, alert, "reviewed", f"Reviewed by {by}." + (f" {note}" if note else ""), actor=by)

        return self._mutate(alert_id, apply)

    def change_severity(self, alert_id: int, by: str, level: str, reason: str) -> AlertResponse:
        def apply(db: Session, alert: FloodAlert) -> None:
            old = alert.level
            if old == level:
                return
            alert.level = level
            alert.title = alert.title.replace(old.upper(), level.upper(), 1)
            alert.actions = action_service.recommend(level)
            add_event(
                db, alert, "severity_changed",
                f"Severity changed from {old.upper()} to {level.upper()} by {by}: {reason}",
                actor=by, data={"from": old, "to": level, "reason": reason},
            )

        return self._mutate(alert_id, apply)

    def resolve(self, alert_id: int, by: str, note: str = "") -> AlertResponse:
        def apply(db: Session, alert: FloodAlert) -> None:
            if _status(alert) == "resolved":
                return
            alert.status = "resolved"
            alert.is_active = False
            alert.resolved_at = _utcnow()
            alert.resolved_by = by
            add_event(db, alert, "resolved", f"Resolved by {by}." + (f" {note}" if note else ""), actor=by)

        return self._mutate(alert_id, apply)

    def add_note(self, alert_id: int, by: str, text: str) -> AlertResponse:
        return self._mutate(alert_id, lambda db, alert: add_event(db, alert, "note", text, actor=by))

    def deactivate_expired(self) -> int:
        now = _utcnow()
        with session_scope() as db:
            rows = db.scalars(select(FloodAlert).where(FloodAlert.is_active.is_(True))).all()
            expired = [a for a in rows if _aware(a.valid_until) <= now]
            for a in expired:
                a.is_active = False
                if _status(a) != "resolved":
                    a.status = "resolved"
                    a.resolved_at = now
                    a.resolved_by = "system"
                    add_event(db, a, "resolved", "Expired: validity window ended without a new warning.")
            return len(expired)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate_region(
        self, req: EvaluateRequest, source: str = "manual", data_mode: str | None = None
    ) -> EvaluateResponse:
        region = geo_data.get_region(req.region)
        month = _utcnow().month
        observed = req.rain_event_mm is not None or req.rain_24h_mm is not None
        if req.rain_event_mm is not None:
            event_total = req.rain_event_mm
        elif req.rain_24h_mm is not None:
            event_total = req.rain_24h_mm * req.duration_days
        else:
            event_total = region["monthly_rain_mm"][month - 1] / 30.0 * req.duration_days
        event_total = max(event_total, 0.1)
        data_mode = data_mode or ("observed" if observed else "climatology")
        data_as_of = _aware(req.observed_at) or _utcnow()

        rain = self.scenario.rainfall_inputs(
            region, factor=1.0, duration_days=req.duration_days, antecedent=req.antecedent,
            month=month, event_total_mm=event_total,
        )
        if req.rain_24h_mm is not None:
            rain = rain.model_copy(update={"rain_1d_mm": req.rain_24h_mm})

        assessed = self.scenario.assess_region(
            region["name"], rain, antecedent=req.antecedent, dam_release=req.dam_release,
            high_tide=req.high_tide, month=month, with_shap=True,
        )
        self._store_snapshot(region["name"], assessed, data_mode, data_as_of)
        rain_probability = assessed.model.probability if assessed.model else None
        causes = incident_service.scenario_causes(
            antecedent=req.antecedent, dam_release=req.dam_release, high_tide=req.high_tide,
            daily_rain_mm=event_total / req.duration_days,
        )

        by_district: dict[str, list[tuple[dict, Assessment]]] = defaultdict(list)
        for village, assessment in assessed.villages:
            by_district[village["district"]].append((village, assessment))

        summaries: list[dict[str, Any]] = []
        created: list[int] = []
        with session_scope() as db:
            rules = db.scalars(select(AlertRule).where(AlertRule.active.is_(True))).all()
            for district, items in sorted(by_district.items()):
                items.sort(key=lambda t: t[1].probability, reverse=True)
                worst = items[0][1]
                level = worst.band
                summary = {
                    "district": district,
                    "level": level,
                    "flood_probability": worst.probability,
                    "villages_at_risk": [v["name"] for v, a in items if LEVELS[a.band] >= LEVELS["moderate"]],
                }
                rule = _rule_for(rules, region["name"], district)
                min_level = rule.min_level if rule else settings.ALERT_DEFAULT_MIN_LEVEL
                min_prob = rule.min_probability if rule else 0.0
                cooldown = rule.cooldown_minutes if rule else settings.ALERT_COOLDOWN_MIN

                if LEVELS[level] < LEVELS[min_level] or worst.probability < min_prob:
                    summary["action"] = f"below threshold ({min_level})"
                    summaries.append(summary)
                    continue

                previous = db.scalars(
                    select(FloodAlert)
                    .where(FloodAlert.region == region["name"], FloodAlert.district == district,
                           FloodAlert.is_active.is_(True), FloodAlert.source != "test")
                    .order_by(FloodAlert.issued_at.desc())
                ).first()
                if previous and not req.ignore_cooldown:
                    recent = _aware(previous.issued_at) > _utcnow() - timedelta(minutes=cooldown)
                    if recent and LEVELS[level] <= LEVELS[previous.level]:
                        summary["action"] = f"suppressed: alert #{previous.id} already active (cooldown)"
                        summaries.append(summary)
                        continue

                alert = self._build_alert(
                    region, district, level, items, assessed, causes, source, data_mode, data_as_of
                )
                db.add(alert)
                db.flush()
                rule_label = f"rule #{rule.id}" if rule else "the default rule"
                add_event(
                    db, alert, "detected",
                    f"Flood risk in {district} reached {level.upper()} ({worst.probability:.0%}), "
                    f"crossing the {min_level} threshold of {rule_label}. Input: {_mode_label(data_mode)}.",
                    data={"rule_id": rule.id if rule else None, "data_mode": data_mode,
                          "rain_event_mm": rain.event_total_mm, "duration_days": rain.duration_days},
                )
                add_event(
                    db, alert, "generated",
                    f"Warning generated for {len(alert.affected_villages or [])} location(s) with explanation, "
                    f"48-hour projection and {len(alert.actions or [])} recommended actions.",
                )
                add_event(db, alert, "reviewed", f"Auto-approved by {rule_label} (auto-send policy).")
                if previous:
                    previous.is_active = False
                    previous.status = "resolved"
                    previous.resolved_at = _utcnow()
                    previous.resolved_by = "system"
                    if LEVELS[level] != LEVELS[previous.level]:
                        alert.supersedes_id = previous.id
                        verb = "Escalated" if LEVELS[level] > LEVELS[previous.level] else "Downgraded"
                        add_event(
                            db, alert, "severity_changed",
                            f"{verb} from {previous.level.upper()} (alert #{previous.id}) to {level.upper()}.",
                            data={"from": previous.level, "to": level, "previous_alert_id": previous.id},
                        )
                    add_event(db, previous, "resolved", f"Superseded by alert #{alert.id} ({level.upper()}).")
                created.append(alert.id)
                summary["action"] = f"alert #{alert.id} issued"
                summaries.append(summary)

        return EvaluateResponse(
            region=region["name"],
            rain_event_mm=rain.event_total_mm,
            rain_probability=rain_probability,
            districts=summaries,
            alerts_created=created,
        )

    def create_test_alert(self, req: TestAlertRequest) -> int:
        """A realistic sample alert (from a +30% saturated-soil scenario) for channel testing."""
        region = geo_data.get_region(req.region)
        district = req.district or region["districts"][0]["name"]
        rain = self.scenario.rainfall_inputs(region, factor=1.3, duration_days=3, antecedent="saturated")
        assessed = self.scenario.assess_region(
            region["name"], rain, antecedent="saturated", district=district, with_shap=False
        )
        items = sorted(assessed.villages, key=lambda t: t[1].probability, reverse=True)
        if not items:
            raise ValueError(f"No monitored villages in district '{district}'")
        with session_scope() as db:
            alert = self._build_alert(
                region, items[0][0]["district"], req.level, items, assessed,
                {"extreme_rainfall", "saturated_soil"}, "test", "test", _utcnow(),
            )
            alert.title = "[TEST] " + alert.title
            alert.message = "This is a TEST alert to verify delivery channels. " + alert.message
            alert.valid_until = _utcnow() + timedelta(hours=1)
            db.add(alert)
            db.flush()
            add_event(db, alert, "generated", "Test alert generated from a sample +30% saturated-soil scenario.")
            add_event(db, alert, "reviewed", "Auto-approved (test alert).")
            return alert.id

    # ------------------------------------------------------------------
    def _build_alert(
        self,
        region: dict[str, Any],
        district: str,
        level: str,
        items: list[tuple[dict, Assessment]],
        assessed: RegionAssessment,
        causes: set[str],
        source: str,
        data_mode: str,
        data_as_of: datetime,
    ) -> FloodAlert:
        rain = assessed.rain
        event = assessed.event
        rain_probability = assessed.model.probability if assessed.model else None
        at_risk = [(v, a) for v, a in items if LEVELS[a.band] >= LEVELS["moderate"]] or items[:1]
        villages = [
            {
                "name": v["name"],
                "band": a.band,
                "probability": round(a.probability, 3),
                "depth_m": a.depth_m,
                "reasons": a.reasons[:3],
                "river_rise_m": hydrology_service.river_rise_m(v, event),
            }
            for v, a in at_risk[:8]
        ]
        drivers: list[str] = []
        for _, a in at_risk[:3]:
            for reason in a.reasons[:2]:
                if reason not in drivers:
                    drivers.append(reason)
        model_sentence = _model_driver_sentence(assessed.shap)
        if model_sentence:
            drivers.append(model_sentence)

        matches = incident_service.find_similar(
            region["name"], rain.event_total_mm, rain.duration_days, causes=causes,
            villages=[v["name"] for v, _ in at_risk], top_k=1, include_other_regions=False,
        )
        incident = None
        if matches:
            m = matches[0]
            incident = {"id": m.id, "name": m.name, "date": m.date, "summary": m.summary,
                        "deaths": m.deaths, "similarity": m.similarity}

        timeline = hydrology_service.worst_timeline(
            [hydrology_service.project_timeline(v, event) for v, _ in items]
        )
        actions = action_service.recommend(
            level,
            action_context(
                [v for v, _ in at_risk], dam_release=event.dam_release, high_tide=event.high_tide,
                landslide=any(a.landslide_risk for _, a in items),
            ),
        )
        why = _why_bullets(at_risk, event, rain, rain_probability, incident)

        info = geo_data.district_info(region["name"], district)
        lat = info["lat"] if info else sum(v["lat"] for v, _ in items) / len(items)
        lon = info["lon"] if info else sum(v["lon"] for v, _ in items) / len(items)

        village_text = "; ".join(
            f"{v['name']} ({v['band']}, {v['probability']:.0%}, ~{v['depth_m']} m)" for v in villages[:4]
        )
        peak = max(timeline, key=lambda p: p["probability"]) if timeline else None
        message = (
            f"{rain.event_total_mm:.0f} mm of rain expected over {rain.duration_days} day(s) in {district}. "
            f"Locations at risk: {village_text}. "
            f"Main factor: {(drivers[0] if drivers else 'heavy rainfall').rstrip('.')}."
            + (f" Risk projected to peak around +{peak['offset_h']} h." if peak and peak["offset_h"] else "")
            + (f" Similar to {_incident_label(incident)}." if incident else "")
            + " Suggested first steps: " + "; ".join(a["text"] for a in actions[:2]) + "."
        )
        now = _utcnow()
        return FloodAlert(
            region=region["name"],
            district=district,
            lat=lat,
            lon=lon,
            level=level,
            flood_probability=max(a.probability for _, a in items),
            rain_probability=rain_probability,
            rain_event_mm=rain.event_total_mm,
            rain_duration_days=rain.duration_days,
            title=f"{level.upper()} flood risk: {district} ({region['name']})",
            message=message,
            top_drivers=drivers[:5],
            affected_villages=villages,
            similar_incident=incident,
            source=source,
            valid_from=now,
            valid_until=now + timedelta(hours=settings.ALERT_VALIDITY_HOURS),
            issued_at=now,
            is_active=True,
            status="active",
            why=why,
            model_drivers=_model_drivers(assessed.shap),
            timeline=timeline,
            actions=actions,
            confidence_pct=round(assessed.model.confidence * 100, 1) if assessed.model else None,
            confidence_label=assessed.model.confidence_label if assessed.model else "Low",
            horizon_hours=24,
            data_mode=data_mode,
            data_as_of=data_as_of,
            provenance=assessed.provenance,
        )

    @staticmethod
    def _store_snapshot(region: str, assessed: RegionAssessment, data_mode: str, data_as_of: datetime) -> None:
        system_state.state.put_snapshot(system_state.RegionSnapshot(
            region=region,
            data_mode=data_mode,
            data_as_of=data_as_of,
            assessed_at=_utcnow(),
            rain_event_mm=assessed.rain.event_total_mm,
            duration_days=assessed.rain.duration_days,
            rain_probability=assessed.model.probability if assessed.model else None,
            confidence_label=assessed.model.confidence_label if assessed.model else None,
            villages=[
                {
                    "id": v["id"], "name": v["name"], "district": v["district"], "lat": v["lat"], "lon": v["lon"],
                    "band": a.band, "probability": a.probability, "depth_m": a.depth_m,
                    "river_rise_m": hydrology_service.river_rise_m(v, assessed.event),
                    "landslide_risk": a.landslide_risk, "reasons": a.reasons[:3],
                }
                for v, a in assessed.villages
            ],
        ))

    # ------------------------------------------------------------------
    # Seed data
    # ------------------------------------------------------------------
    @staticmethod
    def seed_defaults() -> None:
        """Default global rule + a directory of district collectors (no contact
        details: fill them in on the Alert settings page to start receiving)."""
        with session_scope() as db:
            if db.scalars(select(AlertRule)).first() is None:
                db.add(AlertRule(min_level=settings.ALERT_DEFAULT_MIN_LEVEL,
                                 cooldown_minutes=settings.ALERT_COOLDOWN_MIN))
            if db.scalars(select(Recipient)).first() is None:
                for region in geo_data.regions():
                    title = "Deputy Commissioner" if region["name"] == "Assam" else "District Collector"
                    for d in region["districts"]:
                        db.add(Recipient(
                            name=f"{title}, {d['name']}", role="collector", region=region["name"],
                            district=d["name"], channels=[], min_level="high",
                        ))
                    db.add(Recipient(
                        name=f"{region['state']} SDMA / State EOC", role="sdma", region=region["name"],
                        district=None, channels=[], min_level="severe",
                    ))


_MODE_LABEL = {
    "observed": "rainfall entered by an operator",
    "climatology": "monthly rainfall climatology (no live feed)",
    "demo": "demo scenario (simulated)",
    "scenario": "what-if scenario (simulated)",
    "test": "test data",
}


def _mode_label(mode: str) -> str:
    return _MODE_LABEL.get(mode, mode)


def _incident_label(incident: dict[str, Any]) -> str:
    return incident_service.incident_label(incident["name"], incident["date"])


def _why_bullets(
    at_risk: list[tuple[dict, Assessment]],
    event: RainEvent,
    rain,
    rain_probability: float | None,
    incident: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Compact, scannable reasons ("Why High Risk?"), most important first."""
    bullets: list[dict[str, Any]] = [
        {"icon": "rain", "text": f"{rain.event_total_mm:.0f} mm rain expected over {rain.duration_days} day(s)"},
    ]
    if event.antecedent == "saturated":
        bullets.append({"icon": "soil", "text": "Soil already saturated from earlier rain"})
    rise = max(hydrology_service.river_rise_m(v, event) for v, _ in at_risk)
    if rise >= 0.3:
        bullets.append({"icon": "river", "text": f"River about {rise:.1f} m above normal (modelled estimate)", "modelled": True})
    lowest = min((v for v, _ in at_risk), key=lambda v: float(v.get("hand_m", 99)))
    if float(lowest.get("hand_m", 99)) <= 2.5:
        bullets.append({"icon": "terrain", "text": f"Low-lying terrain: {lowest['name']} sits {lowest['hand_m']} m above the nearest channel"})
    if event.dam_release and any(v.get("downstream_of_dam") for v, _ in at_risk):
        dam = next(v["downstream_of_dam"] for v, _ in at_risk if v.get("downstream_of_dam"))
        bullets.append({"icon": "dam", "text": f"Upstream dam releasing ({dam})"})
    if event.high_tide and any(v.get("coastal") for v, _ in at_risk):
        bullets.append({"icon": "tide", "text": "High tide blocking drainage outfalls"})
    if any(v.get("drainage_class") == "poor" for v, _ in at_risk) and len(bullets) < 5:
        bullets.append({"icon": "drainage", "text": "Poor drainage in the most exposed wards"})
    if incident:
        bullets.append({"icon": "history", "text": f"Similar conditions preceded the {_incident_label(incident)}"})
    if rain_probability is not None:
        bullets.append({"icon": "ai", "text": f"AI model: {rain_probability:.0%} chance of heavy rain in the next 24 h"})
    return bullets[:6]


def _model_drivers(shap: dict[str, tuple[float | None, float]], top: int = 8) -> list[dict[str, Any]]:
    from app.services.prediction_service import feature_label

    ranked = sorted(shap.items(), key=lambda kv: -abs(kv[1][1]))[:top]
    return [
        {"feature": f, "label": feature_label(f), "value": None if v is None else round(float(v), 3),
         "contribution": round(float(c), 5)}
        for f, (v, c) in ranked
    ]


def _rule_for(rules: list[AlertRule], region: str, district: str) -> AlertRule | None:
    def specificity(r: AlertRule) -> int:
        if r.district and r.district.lower() == district.lower():
            return 3
        if r.region and r.region.lower() == region.lower() and not r.district:
            return 2
        if not r.region and not r.district:
            return 1
        return 0

    ranked = sorted(((specificity(r), r) for r in rules), key=lambda t: t[0], reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] > 0 else None


def _model_driver_sentence(shap: dict[str, tuple[float | None, float]]) -> str | None:
    from app.services.prediction_service import feature_label

    top = sorted(((f, c) for f, (_, c) in shap.items() if c > 0), key=lambda t: -t[1])[:2]
    if not top:
        return None
    return "AI rainfall model's main drivers: " + ", ".join(feature_label(f) for f, _ in top) + "."


# ---------------------------------------------------------------------------
# Background monitor
# ---------------------------------------------------------------------------
_service: AlertService | None = None


def get_alert_service() -> AlertService:
    global _service
    if _service is None:
        _service = AlertService()
    return _service


async def evaluate_and_dispatch(
    req: EvaluateRequest, source: str = "manual", data_mode: str | None = None
) -> EvaluateResponse:
    service = get_alert_service()
    result = await asyncio.to_thread(service.evaluate_region, req, source, data_mode)
    if req.dispatch:
        dispatcher = get_dispatcher()
        for alert_id in result.alerts_created:
            result.deliveries[alert_id] = await dispatcher.dispatch(alert_id)
    broadcaster.publish({"type": "snapshot", "region": result.region})
    return result


async def monitor_loop(initial_delay: float = 20.0) -> None:
    """Re-evaluate every monitored region on a fixed interval."""
    interval = max(1, settings.ALERT_SCAN_INTERVAL_MIN) * 60
    await asyncio.sleep(initial_delay)
    while True:
        try:
            for name in geo_data.region_names():
                snap = system_state.state.snapshot(name)
                # Don't let climatology overwrite a fresher operator/demo picture of the same region.
                if snap and snap.data_mode in ("observed", "demo") and \
                        system_state.utcnow() - snap.assessed_at < timedelta(hours=6):
                    continue
                result = await evaluate_and_dispatch(EvaluateRequest(region=name), source="monitor")
                if result.alerts_created:
                    logger.info("Monitor issued %d alert(s) for %s", len(result.alerts_created), name)
            await asyncio.to_thread(get_alert_service().deactivate_expired)
            system_state.state.monitor_last_run = system_state.utcnow()
            system_state.state.monitor_last_error = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # keep the monitor alive whatever happens
            logger.exception("Alert monitor cycle failed")
            system_state.state.monitor_last_error = f"{type(exc).__name__}: {exc}"
        await asyncio.sleep(interval)
