"""
Operational transparency + demo tooling.

GET  /system/status         per-component health with honest data-mode labels and degradations
GET  /system/data-sources   where every input comes from and whether it is live / modelled / simulated
GET  /system/faults         demo failure switches
POST /system/faults         toggle a simulated failure (rainfall feed stale, AI model down, notifications down)
GET  /system/current-risk   latest village-level risk snapshot per region (map layer)
POST /demo/run              one-click demo scenario (Kerala extreme rain / Mumbai 26 July replay)
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import settings
from app.db.models import AlertDelivery
from app.db.session import session_scope
from app.schemas.alert import EvaluateRequest
from app.services import system_state
from app.services.alert_service import evaluate_and_dispatch, get_alert_service
from app.services.notifications.dispatcher import BROADCAST_CHANNELS, get_dispatcher
from app.services.prediction_service import get_prediction_service

router = APIRouter()
demo_router = APIRouter()

S = system_state.state


def _aware(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; they are stored as UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _minutes(delta: timedelta) -> int:
    return max(0, int(delta.total_seconds() // 60))


def _latest_snapshot() -> system_state.RegionSnapshot | None:
    """The most recent real (operator) or demo input; climatology only when nothing else exists."""
    snaps = S.snapshots()
    if not snaps:
        return None
    rank = {"observed": 2, "demo": 1}
    return max(snaps, key=lambda s: (rank.get(s.data_mode, 0), s.data_as_of))


# ---------------------------------------------------------------------------
@router.get("/status")
def system_status() -> dict[str, Any]:
    now = system_state.utcnow()
    components: dict[str, dict[str, Any]] = {}
    degradations: list[dict[str, str]] = []

    # --- AI model -----------------------------------------------------------
    model_loaded = get_prediction_service().model_loaded
    if S.faults["ai_model"] or not model_loaded:
        components["ai_model"] = {"state": "unavailable", "label": "Unavailable",
                                  "detail": "Flood risk falls back to a rainfall-only proxy."}
        degradations.append({
            "component": "ai_model", "severity": "critical", "title": "AI model unavailable",
            "message": "Flood risk is being estimated with the rainfall-only fallback. "
                       "Explanations and confidence scores are limited.",
        })
    else:
        components["ai_model"] = {"state": "online", "label": "Online",
                                  "detail": "Fusion rainfall model with SHAP explanations."}

    # --- Weather / rainfall data ---------------------------------------------
    snap = _latest_snapshot()
    if snap is None:
        components["weather_data"] = {"state": "none", "label": "No data yet",
                                      "detail": "No rainfall has been assessed since start-up."}
    else:
        age = S.data_age(snap)
        mode_label = {"observed": "Manual input", "demo": "Demo", "climatology": "Climatology",
                      "scenario": "Scenario", "test": "Test"}.get(snap.data_mode, snap.data_mode)
        delayed = snap.data_mode in ("observed", "demo") and age > system_state.STALE_AFTER
        if delayed:
            components["weather_data"] = {
                "state": "delayed", "label": "Delayed", "age_minutes": _minutes(age), "mode": snap.data_mode,
                "detail": f"Latest rainfall input ({mode_label.lower()}, {snap.region}) is {_minutes(age)} min old.",
            }
            degradations.append({
                "component": "weather_data", "severity": "warning", "title": "Rainfall data delayed",
                "message": f"Latest observation is {_minutes(age)} minutes old. Predictions may be less reliable.",
            })
        else:
            components["weather_data"] = {
                "state": snap.data_mode, "label": mode_label, "age_minutes": _minutes(age), "mode": snap.data_mode,
                "detail": {
                    "observed": "Rainfall entered by an operator. No automatic gauge feed is connected.",
                    "demo": "Demo scenario rainfall (simulated).",
                    "climatology": "Monthly rainfall normals. No live feed is connected.",
                }.get(snap.data_mode, "Rainfall input"),
            }

    # --- River data (always modelled) ----------------------------------------
    components["river_data"] = {"state": "simulated", "label": "Simulated",
                                "detail": "River rise is estimated from the runoff model. No gauge feed is connected."}

    # --- Notifications -------------------------------------------------------
    providers = get_dispatcher().provider_status()
    external = [p for p in providers if p["channel"] not in BROADCAST_CHANNELS]
    active = [p for p in external if p["enabled"]]
    with session_scope() as db:
        recent_failures = [
            d for d in db.scalars(select(AlertDelivery).where(AlertDelivery.status == "failed")).all()
            if d.channel not in BROADCAST_CHANNELS and _aware(d.sent_at) > now - timedelta(hours=1)
        ]
    if S.faults["notifications"] or recent_failures:
        components["notifications"] = {
            "state": "degraded", "label": "Degraded", "failures_last_hour": len(recent_failures),
            "detail": f"{len(recent_failures)} delivery failure(s) in the last hour. The dashboard feed still works.",
        }
        degradations.append({
            "component": "notifications", "severity": "warning", "title": "Notification provider failing",
            "message": "Some Telegram / e-mail / SMS / WhatsApp deliveries are failing. "
                       "Alerts still appear on the dashboard. Check Alerts → Recipients & channels.",
        })
    else:
        components["notifications"] = {
            "state": "ok" if active else "limited", "label": f"{len(active)} of {len(external)} channels",
            "detail": ", ".join(p["name"] for p in active) or "Only the dashboard feed and server log are active.",
        }

    # --- Monitor -------------------------------------------------------------
    if not settings.ALERTS_ENABLED:
        components["monitor"] = {"state": "disabled", "label": "Disabled", "detail": "ALERTS_ENABLED is false."}
    elif S.monitor_last_error:
        components["monitor"] = {"state": "error", "label": "Error", "detail": S.monitor_last_error}
        degradations.append({"component": "monitor", "severity": "warning", "title": "Automatic monitor error",
                             "message": S.monitor_last_error})
    else:
        components["monitor"] = {
            "state": "ok" if S.monitor_last_run else "starting",
            "label": "Running" if S.monitor_last_run else "Starting",
            "last_run": S.monitor_last_run.isoformat() if S.monitor_last_run else None,
            "detail": f"Re-checks every region every {settings.ALERT_SCAN_INTERVAL_MIN} min.",
        }

    return {
        "generated_at": now.isoformat(),
        # No automatic rain-gauge, IMD or river-gauge feed is connected: this is a prototype that runs the
        # AI decision pipeline on operator-provided, simulated or estimated conditions.
        "prototype_mode": True,
        "prototype_notice": "Weather and river inputs are operator-provided, simulated or estimated. "
                            "AI inference and risk analysis run on the supplied conditions.",
        "components": components,
        "degradations": degradations,
        "faults": dict(S.faults),
    }


# ---------------------------------------------------------------------------
@router.get("/data-sources")
def data_sources() -> list[dict[str, Any]]:
    snap = _latest_snapshot()
    rain_mode = snap.data_mode if snap else "none"
    rain_mode_public = {"observed": "manual", "climatology": "historical", "demo": "demo",
                        "scenario": "simulated", "test": "simulated", "none": "unavailable"}[rain_mode]
    return [
        {
            "input": "Rainfall forecast / observation",
            "source": {
                "observed": "Entered by an operator (Alerts → Evaluate now)",
                "demo": "Demo scenario preset",
                "climatology": "IMD long-period monthly normals",
                "none": "Nothing received yet",
            }.get(rain_mode, rain_mode),
            "mode": rain_mode_public,
            "last_update": S.effective_as_of(snap).isoformat() if snap else None,
            "note": "No automatic rain-gauge or IMD API feed is connected yet.",
        },
        {
            "input": "Weather inputs to the AI model",
            "source": "NASA POWER daily meteorology (training, 2004–2024); typical conditions fill live gaps",
            "mode": "historical",
            "last_update": None,
            "note": "Temperature, humidity, pressure, wind and cloud cover.",
        },
        {
            "input": "Satellite imagery",
            "source": "NASA GIBS MODIS scenes (training); INSAT images can be uploaded on Analysis",
            "mode": "historical",
            "last_update": None,
            "note": "No live satellite ingestion.",
        },
        {
            "input": "River levels",
            "source": "Estimated from the village runoff model",
            "mode": "simulated",
            "last_update": snap.assessed_at.isoformat() if snap else None,
            "note": "Not a gauge reading. Connect CWC / India-WRIS gauges for real stages.",
        },
        {
            "input": "Soil moisture",
            "source": "Derived from 30-day rainfall (antecedent moisture condition)",
            "mode": "modelled",
            "last_update": snap.assessed_at.isoformat() if snap else None,
            "note": "Not a satellite or in-situ measurement.",
        },
        {
            "input": "Historical flood records",
            "source": "Curated catalogue of 21 documented events (NDMA / SDMA reports, news)",
            "mode": "historical",
            "last_update": None,
            "note": "Figures are rounded approximations.",
        },
        {
            "input": "Terrain & elevation",
            "source": "Curated village profiles with SRTM-derived elevation and height above drainage",
            "mode": "static",
            "last_update": None,
            "note": "Approximate; replace with district GIS extracts for operations.",
        },
    ]


# ---------------------------------------------------------------------------
class FaultRequest(BaseModel):
    component: Literal["rainfall_feed", "ai_model", "notifications"]
    enabled: bool


@router.get("/faults")
def get_faults() -> dict[str, bool]:
    return dict(S.faults)


@router.post("/faults")
def set_fault(body: FaultRequest) -> dict[str, bool]:
    """Demo tool: simulate a failure to show how the system degrades."""
    S.set_fault(body.component, body.enabled)
    return dict(S.faults)


@router.get("/current-risk")
def current_risk() -> list[dict[str, Any]]:
    out = []
    for snap in S.snapshots():
        out.append({
            "region": snap.region,
            "data_mode": snap.data_mode,
            "data_as_of": S.effective_as_of(snap).isoformat(),
            "age_minutes": _minutes(S.data_age(snap)),
            "rain_event_mm": snap.rain_event_mm,
            "duration_days": snap.duration_days,
            "rain_probability": snap.rain_probability,
            "confidence_label": snap.confidence_label,
            "villages": snap.villages,
        })
    return out


# ---------------------------------------------------------------------------
DEMO_SCENARIOS: dict[str, dict[str, Any]] = {
    "kerala_extreme": {
        "title": "Extreme Kerala rainfall",
        "subtitle": "350 mm over 3 days · saturated soil",
        "request": EvaluateRequest(region="Kerala", rain_event_mm=350, duration_days=3,
                                   antecedent="saturated", ignore_cooldown=True),
    },
    "mumbai_2005": {
        "title": "Mumbai 26 July replay",
        "subtitle": "900 mm in 24 hours · high tide",
        "request": EvaluateRequest(region="Mumbai", rain_event_mm=900, duration_days=1,
                                   antecedent="normal", high_tide=True, ignore_cooldown=True),
    },
}


class DemoRequest(BaseModel):
    scenario: Literal["kerala_extreme", "mumbai_2005"] = "kerala_extreme"


@demo_router.get("/scenarios")
def demo_scenarios() -> list[dict[str, str]]:
    return [{"id": k, "title": v["title"], "subtitle": v["subtitle"]} for k, v in DEMO_SCENARIOS.items()]


@demo_router.post("/run")
async def run_demo(body: DemoRequest) -> dict[str, Any]:
    """Run a preset scenario through the real pipeline (model → hydrology → alert → dispatch)."""
    preset = DEMO_SCENARIOS.get(body.scenario)
    if preset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown scenario")
    started = time.perf_counter()
    req: EvaluateRequest = preset["request"].model_copy()
    result = await evaluate_and_dispatch(req, source="demo", data_mode="demo")
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    at_risk = [d for d in result.districts if d["level"] in ("high", "severe")]
    villages = sorted({v for d in result.districts for v in d["villages_at_risk"]})
    alerts = [get_alert_service().get(i) for i in result.alerts_created]
    alerts = [a for a in alerts if a]
    top = max(alerts, key=lambda a: a.probability) if alerts else None
    sent_rows = [r for rows in result.deliveries.values() for r in rows if r["status"] == "sent"]
    external = [r for r in sent_rows if r["channel"] not in BROADCAST_CHANNELS]
    delivered_text = (
        f"{len(external)} message(s) sent via {', '.join(sorted({r['channel'] for r in external}))}"
        if external else "shown on the dashboard and logged (no Telegram / e-mail / SMS / WhatsApp configured)"
    )
    stages = [
        {"key": "data", "label": "Data received",
         "detail": f"{result.rain_event_mm:.0f} mm over {req.duration_days} day(s) for {result.region} (demo input)"},
        {"key": "ai", "label": "AI analysing",
         "detail": (f"Fusion model: {result.rain_probability:.0%} chance of heavy rain in the next 24 h"
                    if result.rain_probability is not None else "AI model unavailable: rainfall-only fallback used")},
        {"key": "risk", "label": "Risk detected",
         "detail": f"{len(at_risk)} district(s) at high or severe flood risk"},
        {"key": "explain", "label": "Explanation generated",
         "detail": (f"Top reason: {top.why[0].text}" if top and top.why else "Factor breakdown computed")},
        {"key": "villages", "label": "Villages identified",
         "detail": f"{len(villages)} location(s) at risk" + (f", e.g. {', '.join(villages[:3])}" if villages else "")},
        {"key": "alert", "label": "Alert prepared",
         "detail": (f"{len(alerts)} alert(s) issued; {delivered_text}"
                    if alerts else "No district crossed its threshold")},
    ]
    return {
        "scenario": body.scenario,
        "title": preset["title"],
        "region": result.region,
        "stages": stages,
        "alerts_created": result.alerts_created,
        "top_alert_id": top.id if top else None,
        "elapsed_ms": elapsed_ms,
    }
