"""
Tools the what-if assistant can call. Each wraps the deterministic engine,
returns compact JSON for the model, and records the full structured result
in a per-request collector so the UI can draw the map / cards from the same
numbers the assistant quotes.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from anthropic import beta_tool

from app.schemas.scenario import ScenarioRequest, ScenarioResult
from app.services import geo_data, incident_service
from app.services.scenario_service import ScenarioService


@dataclass
class ToolArtifacts:
    scenario: ScenarioResult | None = None
    incidents: list[dict[str, Any]] = field(default_factory=list)
    villages: list[dict[str, Any]] = field(default_factory=list)
    alert_preview: str | None = None
    tools_used: list[str] = field(default_factory=list)


_artifacts: ContextVar[ToolArtifacts | None] = ContextVar("chat_tool_artifacts", default=None)
_scenario_service: ScenarioService | None = None


def begin_collection() -> ToolArtifacts:
    artifacts = ToolArtifacts()
    _artifacts.set(artifacts)
    return artifacts


def _collector() -> ToolArtifacts:
    artifacts = _artifacts.get()
    if artifacts is None:
        artifacts = begin_collection()
    return artifacts


def _scenarios() -> ScenarioService:
    global _scenario_service
    if _scenario_service is None:
        _scenario_service = ScenarioService()
    return _scenario_service


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _error(message: str) -> str:
    return _json({"error": message, "monitored_regions": geo_data.region_names()})


# ---------------------------------------------------------------------------
@beta_tool
def simulate_flood_scenario(
    region: str,
    rainfall_change_pct: float = 0.0,
    rainfall_mm: float | None = None,
    duration_days: int = 3,
    antecedent: str = "normal",
    dam_release: bool = False,
    high_tide: bool = False,
    district: str | None = None,
) -> str:
    """Run the what-if flood simulator for a region and return which villages would flood, why, and similar past incidents.

    It compares a reference monsoon heavy-rain spell (baseline) with the scenario. It runs the VARUNA fusion
    rainfall model with SHAP explanations on both, plus a village-level runoff and terrain flood model. Call it
    whenever the user describes a rainfall situation, including again with changed parameters for follow-ups.

    Args:
        region: One of Kerala, Mumbai, Chennai, Assam. A district name in those regions also works.
        rainfall_change_pct: Rainfall change versus the reference heavy spell in percent, e.g. 20 for "+20%", -30 for "30% less".
        rainfall_mm: Absolute rainfall total in mm over duration_days, e.g. 900 for "900 mm in a day". Overrides rainfall_change_pct.
        duration_days: Length of the rain spell in days (1-10).
        antecedent: Soil moisture before the spell: "dry", "normal" or "saturated". Use "saturated" for weeks of prior rain or rivers already full.
        dam_release: True if upstream reservoirs are releasing water.
        high_tide: True if a high or spring tide coincides with the peak rain (affects coastal outfalls).
        district: Optional district to focus the village list on.
    """
    try:
        req = ScenarioRequest(
            region=region,
            rainfall_change_pct=rainfall_change_pct,
            rainfall_mm=rainfall_mm,
            duration_days=max(1, min(int(duration_days), 10)),
            antecedent=antecedent if antecedent in ("dry", "normal", "saturated") else "normal",
            dam_release=dam_release,
            high_tide=high_tide,
            district=district,
        )
        result = _scenarios().simulate(req)
    except geo_data.UnknownRegionError as exc:
        return _error(str(exc))
    except ValueError as exc:
        return _error(f"Invalid scenario: {exc}")

    artifacts = _collector()
    artifacts.scenario = result
    artifacts.tools_used.append("simulate_flood_scenario")

    return _json({
        "headline": result.summary.headline,
        "rainfall": {
            "baseline": result.baseline_rain.model_dump(),
            "scenario": result.scenario_rain.model_dump(),
        },
        "ai_rain_model": {
            "baseline_p_heavy_rain_24h": result.baseline_model.probability if result.baseline_model else None,
            "scenario_p_heavy_rain_24h": result.scenario_model.probability if result.scenario_model else None,
            "delta": result.model_delta,
            "shap_driver_changes": [
                {"feature": d.label, "baseline_value": d.baseline_value, "scenario_value": d.scenario_value,
                 "contribution_change": d.delta}
                for d in result.driver_changes[:5]
            ],
        },
        "summary": result.summary.model_dump(),
        "villages": [
            {
                "name": v.name,
                "district": v.district,
                "band": f"{v.baseline_band} -> {v.band}",
                "flood_probability": f"{v.baseline_probability:.0%} -> {v.flood_probability:.0%}",
                "expected_depth_m": v.expected_depth_m,
                "population": v.population,
                "landslide_risk": v.landslide_risk,
                "top_factors": [
                    {"factor": f.label, "contribution": f.contribution} for f in v.factors[:3]
                ],
                "reasons": v.reasons[:3],
            }
            for v in result.villages[:10]
        ],
        "similar_past_incidents": [
            {"name": i.name, "date": i.date, "rainfall_mm": i.rainfall_mm,
             "window_days": i.rainfall_window_days, "deaths": i.deaths, "displaced": i.displaced,
             "causes": i.causes, "summary": i.summary, "why_similar": i.why_similar}
            for i in result.similar_incidents
        ],
        "model_rain_day_analogues": [a.model_dump() for a in result.model_analogues],
        "assumptions": result.assumptions,
        "caveats": result.caveats,
    })


@beta_tool
def get_village_profile(village_name: str) -> str:
    """Look up the terrain and hydrology profile of a monitored village or ward, and the past floods that hit it.

    The profile covers elevation, height above the nearest drainage, river, soil, drainage, dam and coastal flags.

    Args:
        village_name: Village or ward name, e.g. "Kuttanad", "Velachery", "Kurla", "Majuli".
    """
    village = geo_data.find_village(village_name)
    if village is None:
        return _error(f"No monitored village matches '{village_name}'. Use list_monitored_places to see options.")
    history = incident_service.search(village=village["name"], limit=5)
    artifacts = _collector()
    artifacts.villages.append(village)
    artifacts.tools_used.append("get_village_profile")
    return _json({
        "village": village,
        "past_incidents": [
            {"name": i["name"], "date": i["date"], "rainfall_mm": i["rainfall_mm"], "deaths": i["deaths"],
             "causes": i["causes"], "summary": i["summary"]}
            for i in history
        ],
    })


@beta_tool
def search_past_incidents(
    region: str | None = None,
    min_rainfall_mm: float | None = None,
    cause: str | None = None,
    village: str | None = None,
) -> str:
    """Search the catalogue of documented past floods and extreme-rain disasters. All filters are optional.

    Args:
        region: Kerala, Mumbai, Chennai or Assam.
        min_rainfall_mm: Only incidents with at least this peak accumulation.
        cause: A cause tag: extreme_rainfall, saturated_soil, dam_release, high_tide, river_overflow, embankment_breach, choked_drains, encroachment, urban_runoff, landslide, cyclone, backwater.
        village: Only incidents that affected this village or ward.
    """
    try:
        results = incident_service.search(region, min_rainfall_mm, cause, village, limit=6)
    except geo_data.UnknownRegionError as exc:
        return _error(str(exc))
    artifacts = _collector()
    artifacts.incidents = results
    artifacts.tools_used.append("search_past_incidents")
    return _json({"count": len(results), "incidents": results})


@beta_tool
def list_monitored_places() -> str:
    """List the monitored regions, their districts and villages, and each region's reference heavy-rain spell."""
    _collector().tools_used.append("list_monitored_places")
    return _json([
        {
            "region": r["name"],
            "reference_heavy_spell": r["heavy_spell"],
            "districts": {
                d["name"]: [v["name"] for v in geo_data.villages_in(r["name"]) if v["district"] == d["name"]]
                for d in r["districts"]
            },
        }
        for r in geo_data.regions()
    ])


@beta_tool
def draft_alert_message(district: str) -> str:
    """Draft (without sending) the WhatsApp/SMS alert text a District Collector would get for the most recently simulated scenario.

    Call simulate_flood_scenario first.

    Args:
        district: The district to draft the alert for, e.g. "Alappuzha".
    """
    artifacts = _collector()
    result = artifacts.scenario
    if result is None:
        return _error("Run simulate_flood_scenario first, then draft the alert.")
    villages = [v for v in result.villages if v.district.lower() == district.lower()]
    if not villages:
        return _error(f"No simulated villages in district '{district}'. Districts: "
                      + ", ".join(sorted({v.district for v in result.villages})))
    worst = max(villages, key=lambda v: v.flood_probability)
    lines = [
        f"VARUNA AI - {worst.band.upper()} FLOOD ALERT (SCENARIO DRAFT)",
        f"District: {district} ({result.region})",
        f"Rain: {result.scenario_rain.event_total_mm:.0f} mm over {result.scenario_rain.duration_days} day(s)",
        "Villages at risk:",
        *[f"- {v.name}: {v.band} ({v.flood_probability:.0%}, ~{v.expected_depth_m} m)" for v in villages[:5]],
        "Why: " + (worst.reasons[0] if worst.reasons else "heavy rainfall"),
    ]
    if result.similar_incidents:
        inc = result.similar_incidents[0]
        lines.append(f"Similar past event: {incident_service.incident_label(inc.name, inc.date)}")
    text = "\n".join(lines)
    artifacts.alert_preview = text
    artifacts.tools_used.append("draft_alert_message")
    return _json({"draft": text, "note": "Not sent. Send it from the Alerts page."})


TOOLS = [
    simulate_flood_scenario,
    get_village_profile,
    search_past_incidents,
    list_monitored_places,
    draft_alert_message,
]
