"""
What-if scenario engine.

    scenario ("Kerala, +20% rain for 3 days, rivers already full")
        -> rainfall inputs for baseline and scenario (region climatology)
        -> fusion model on both + SHAP delta   (what changes in the AI's view)
        -> hydrology on every village           (who floods and why)
        -> past incidents that looked like this (has it happened before)

The baseline is the region's reference monsoon heavy-rain spell under normal
soil moisture, no dam release and no high tide; the scenario applies the
requested rainfall change and every stated aggravating condition, so the
difference isolates what the user asked about.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.schemas.scenario import (
    DriverChange,
    ModelAnalogue,
    ModelRisk,
    RainfallInputs,
    ScenarioRequest,
    ScenarioResult,
    ScenarioSummary,
    VillageImpact,
)
from app.services import actions as action_service
from app.services import geo_data, hydrology_service, incident_service, system_state
from app.services.hydrology_service import BAND_ORDER, Assessment, RainEvent
from app.services.prediction_service import (
    ModelNotAvailableError,
    PredictionService,
    build_provenance,
    feature_label,
    get_prediction_service,
)

logger = logging.getLogger(__name__)

_ANTECEDENT_30D_FACTOR = {"dry": 0.4, "normal": 1.0, "saturated": 1.7}


def action_context(
    at_risk: list[Any], *, dam_release: bool, high_tide: bool, landslide: bool
) -> action_service.ActionContext:
    """Context for recommended actions from the at-risk villages (VillageImpact or village dicts)."""
    by_id = {v["id"]: v for v in geo_data.villages()}
    profiles = [by_id.get(getattr(v, "id", None) or v.get("id"), {}) for v in at_risk]
    return action_service.ActionContext(
        dam_release=dam_release and any(p.get("downstream_of_dam") for p in profiles),
        high_tide=high_tide and any(p.get("coastal") for p in profiles),
        landslide=landslide,
        dam_names=tuple(sorted({p["downstream_of_dam"] for p in profiles if p.get("downstream_of_dam")})),
        villages=tuple(p.get("name", "") for p in profiles[:3] if p),
    )


def _action_level(villages: list[VillageImpact]) -> str:
    """Level for recommended actions: the worst band, with 'low' treated as 'moderate' (watch)."""
    worst = max((BAND_ORDER[v.band] for v in villages), default=1)
    return {3: "severe", 2: "high"}.get(worst, "moderate")


@dataclass
class RegionAssessment:
    rain: RainfallInputs
    model: ModelRisk | None
    shap: dict[str, tuple[float | None, float]]  # feature -> (value, contribution)
    analogues: list[dict[str, Any]]
    villages: list[tuple[dict[str, Any], Assessment]]
    event: RainEvent
    model_fallback: bool = False  # True when the rainfall-only proxy replaced the AI model
    provenance: list[dict[str, Any]] = field(default_factory=list)


class ScenarioService:
    def __init__(self, predictor: PredictionService | None = None) -> None:
        self._predictor = predictor

    @property
    def predictor(self) -> PredictionService:
        if self._predictor is None:
            self._predictor = get_prediction_service()
        return self._predictor

    # ------------------------------------------------------------------
    # Rainfall inputs
    # ------------------------------------------------------------------
    @staticmethod
    def rainfall_inputs(
        region: dict[str, Any],
        *,
        factor: float,
        duration_days: int,
        antecedent: str,
        month: int | None = None,
        event_total_mm: float | None = None,
    ) -> RainfallInputs:
        spell = region["heavy_spell"]
        month = month or region["peak_month"]
        clim_daily = region["monthly_rain_mm"][month - 1] / 30.0

        base_daily = spell["rain_3d"] / 3.0
        if event_total_mm is not None:
            event_total = event_total_mm
            factor = event_total / (base_daily * duration_days)
        else:
            event_total = base_daily * factor * duration_days
        daily = event_total / duration_days

        rain_1d = event_total if duration_days == 1 else max(daily, spell["rain_1d"] * factor)
        rain_3d = daily * min(duration_days, 3) + max(0, 3 - duration_days) * clim_daily
        rain_7d = daily * min(duration_days, 7) + max(0, 7 - duration_days) * clim_daily
        prior_days = max(0, 30 - duration_days)
        rain_30d = (
            _ANTECEDENT_30D_FACTOR[antecedent] * clim_daily * prior_days
            + daily * min(duration_days, 30)
        )
        return RainfallInputs(
            rain_1d_mm=round(rain_1d, 1),
            rain_3d_mm=round(rain_3d, 1),
            rain_7d_mm=round(rain_7d, 1),
            rain_30d_mm=round(rain_30d, 1),
            event_total_mm=round(event_total, 1),
            duration_days=duration_days,
            change_pct=round((factor - 1.0) * 100.0, 1),
        )

    # ------------------------------------------------------------------
    # Core assessment (shared with the alert monitor)
    # ------------------------------------------------------------------
    def assess_region(
        self,
        region_name: str,
        rain: RainfallInputs,
        *,
        antecedent: str = "normal",
        dam_release: bool = False,
        high_tide: bool = False,
        weather_overrides: dict[str, float] | None = None,
        month: int | None = None,
        district: str | None = None,
        with_shap: bool = True,
    ) -> RegionAssessment:
        region = geo_data.get_region(region_name)
        month = month or region["peak_month"]
        weather = {
            **region["typical_weather"],
            **{k: v for k, v in (weather_overrides or {}).items() if v is not None},
            "rain_sum_1d": rain.rain_1d_mm,
            "rain_sum_3d": rain.rain_3d_mm,
            "rain_sum_7d": rain.rain_7d_mm,
            "rain_sum_30d": rain.rain_30d_mm,
        }
        timestamp = datetime(datetime.now(timezone.utc).year, month, 15, 6, tzinfo=timezone.utc).isoformat()

        model: ModelRisk | None = None
        shap: dict[str, tuple[float | None, float]] = {}
        analogues: list[dict[str, Any]] = []
        result: dict[str, Any] | None = None
        try:
            if system_state.state.faults["ai_model"]:
                raise ModelNotAvailableError("AI model disabled by a simulated fault")
            result = self.predictor.predict_conditions(
                weather,
                region=region["name"],
                latitude=region["lat"],
                longitude=region["lon"],
                timestamp=timestamp,
                with_shap=with_shap,
            )
            model = ModelRisk(
                probability=float(result["risk_probability"]),
                risk_level=str(result["risk_level"]).lower(),
                confidence=float(result.get("confidence_pct", 0.0)) / 100.0,
                confidence_label=str(result.get("confidence", "Low")),
                class_probabilities=result.get("class_probabilities", {}),
            )
            shap = {c.feature: (c.value, float(c.contribution)) for c in result.get("shap", [])}
            analogues = result.get("similar_historical_events", [])
        except ModelNotAvailableError:
            logger.warning("Fusion model unavailable - hydrology uses a rainfall-only proxy")

        rain_signal = model.probability if model else 1.0 - math.exp(-rain.rain_1d_mm / 100.0)
        event = RainEvent(
            total_mm=rain.event_total_mm,
            duration_days=rain.duration_days,
            antecedent=antecedent,
            rain_model_probability=rain_signal,
            dam_release=dam_release,
            high_tide=high_tide,
        )
        villages = geo_data.villages_in(region["name"])
        if district:
            villages = [v for v in villages if v["district"].lower() == district.lower()] or villages
        assessed = [(v, hydrology_service.assess(v, event)) for v in villages]
        return RegionAssessment(
            rain=rain, model=model, shap=shap, analogues=analogues, villages=assessed,
            event=event, model_fallback=model is None,
            provenance=build_provenance(
                result if model else None, image_used=False, shap_ok=bool(shap), include_flood_rules=True
            ),
        )

    # ------------------------------------------------------------------
    def simulate(self, req: ScenarioRequest) -> ScenarioResult:
        region = geo_data.get_region(req.region)
        base_rain = self.rainfall_inputs(
            region, factor=1.0, duration_days=req.duration_days, antecedent="normal"
        )
        factor = 1.0 + (req.rainfall_change_pct or 0.0) / 100.0
        scen_rain = self.rainfall_inputs(
            region,
            factor=factor,
            duration_days=req.duration_days,
            antecedent=req.antecedent,
            event_total_mm=req.rainfall_mm,
        )
        overrides = {"humidity_pct": req.humidity_pct, "cloud_cover_pct": req.cloud_cover_pct}

        base = self.assess_region(region["name"], base_rain, district=req.district)
        scen = self.assess_region(
            region["name"],
            scen_rain,
            antecedent=req.antecedent,
            dam_release=req.dam_release,
            high_tide=req.high_tide,
            weather_overrides=overrides,
            district=req.district,
        )

        villages = self._village_impacts(base.villages, scen.villages, scen.event)
        driver_changes = self._driver_changes(base.shap, scen.shap)
        region_timeline = hydrology_service.worst_timeline([[p.model_dump() for p in v.timeline] for v in villages])
        model_delta = (
            round(scen.model.probability - base.model.probability, 4)
            if base.model and scen.model else None
        )

        at_risk = [v for v in villages if BAND_ORDER[v.band] >= BAND_ORDER["high"]]
        newly = [v for v in at_risk if v.band_increased]
        causes = incident_service.scenario_causes(
            antecedent=req.antecedent,
            dam_release=req.dam_release,
            high_tide=req.high_tide,
            daily_rain_mm=scen_rain.event_total_mm / scen_rain.duration_days,
        )
        incidents = incident_service.find_similar(
            region["name"],
            scen_rain.event_total_mm,
            scen_rain.duration_days,
            causes=causes,
            villages=[v.name for v in at_risk],
        )

        summary = ScenarioSummary(
            villages_assessed=len(villages),
            villages_high_or_severe=len(at_risk),
            newly_at_risk=len(newly),
            population_at_risk=sum(v.population for v in at_risk),
            districts_at_risk=sorted({v.district for v in at_risk}),
            headline=self._headline(region["name"], scen_rain, villages, at_risk, newly),
        )

        return ScenarioResult(
            region=region["name"],
            scenario=req,
            baseline_rain=base_rain,
            scenario_rain=scen_rain,
            baseline_model=base.model,
            scenario_model=scen.model,
            model_delta=model_delta,
            driver_changes=driver_changes,
            villages=villages,
            summary=summary,
            timeline=region_timeline,
            actions=action_service.recommend(
                _action_level(villages),
                action_context(at_risk, dam_release=req.dam_release, high_tide=req.high_tide,
                                landslide=any(v.landslide_risk for v in villages)),
            ),
            data_mode="scenario",
            generated_at=datetime.now(timezone.utc).isoformat(),
            provenance=scen.provenance,
            similar_incidents=incidents,
            model_analogues=[
                ModelAnalogue(
                    region=str(a.get("region", "")),
                    date=str(a.get("date", "")),
                    observed_rainfall_mm=float(a.get("observed_rainfall_mm", 0.0)),
                    similarity_pct=float(a.get("similarity_pct", 0.0)),
                )
                for a in scen.analogues
            ],
            assumptions=self._assumptions(region, base_rain, scen_rain, req),
            caveats=self._caveats(base, scen, scen_rain),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _village_impacts(
        base: list[tuple[dict[str, Any], Assessment]],
        scen: list[tuple[dict[str, Any], Assessment]],
        event: RainEvent,
    ) -> list[VillageImpact]:
        base_by_id = {v["id"]: a for v, a in base}
        out = []
        for v, a in scen:
            b = base_by_id[v["id"]]
            out.append(
                VillageImpact(
                    id=v["id"],
                    name=v["name"],
                    district=v["district"],
                    region=v["region"],
                    lat=v["lat"],
                    lon=v["lon"],
                    population=int(v.get("population", 0)),
                    baseline_probability=b.probability,
                    flood_probability=a.probability,
                    baseline_band=b.band,
                    band=a.band,
                    band_increased=BAND_ORDER[a.band] > BAND_ORDER[b.band],
                    runoff_mm=a.runoff_mm,
                    expected_depth_m=a.depth_m,
                    landslide_risk=a.landslide_risk,
                    river_rise_m=hydrology_service.river_rise_m(v, event),
                    factors=a.factors,
                    reasons=a.reasons,
                    timeline=hydrology_service.project_timeline(v, event),
                )
            )
        out.sort(key=lambda x: x.flood_probability, reverse=True)
        return out

    @staticmethod
    def _driver_changes(
        base: dict[str, tuple[float | None, float]],
        scen: dict[str, tuple[float | None, float]],
        top: int = 8,
    ) -> list[DriverChange]:
        changes = []
        for feature in set(base) | set(scen):
            b_val, b_c = base.get(feature, (None, 0.0))
            s_val, s_c = scen.get(feature, (None, 0.0))
            changes.append(
                DriverChange(
                    feature=feature,
                    label=feature_label(feature),
                    baseline_value=b_val,
                    scenario_value=s_val,
                    baseline_contribution=round(b_c, 4),
                    scenario_contribution=round(s_c, 4),
                    delta=round(s_c - b_c, 4),
                )
            )
        changes.sort(key=lambda c: (abs(c.delta), abs(c.scenario_contribution)), reverse=True)
        return changes[:top]

    @staticmethod
    def _headline(
        region: str,
        rain: RainfallInputs,
        villages: list[VillageImpact],
        at_risk: list[VillageImpact],
        newly: list[VillageImpact],
    ) -> str:
        change = f"{rain.change_pct:+.0f}% rain" if rain.change_pct else "Reference heavy spell"
        people = sum(v.population for v in at_risk)
        text = (
            f"{change} ({rain.event_total_mm:.0f} mm over {rain.duration_days} day"
            f"{'s' if rain.duration_days > 1 else ''}) puts {len(at_risk)} of {len(villages)} "
            f"{region} locations at high/severe flood risk"
        )
        if newly:
            text += f" ({len(newly)} newly)"
        if people:
            text += f", about {people:,} people"
        return text + "."

    @staticmethod
    def _assumptions(
        region: dict[str, Any], base: RainfallInputs, scen: RainfallInputs, req: ScenarioRequest
    ) -> list[str]:
        month = datetime(2000, region["peak_month"], 1).strftime("%B")
        items = [
            f"Baseline = {region['name']} reference monsoon heavy spell: {base.rain_1d_mm:.0f} mm in 24 h, "
            f"{base.event_total_mm:.0f} mm over {base.duration_days} day(s), normal soil moisture, no dam release, no high tide.",
            f"Scenario rainfall: {scen.event_total_mm:.0f} mm over {scen.duration_days} day(s) "
            f"({scen.change_pct:+.0f}% vs baseline); 30-day antecedent {scen.rain_30d_mm:.0f} mm ({req.antecedent} soil).",
            f"Unspecified weather (temperature, pressure, wind) uses typical {month} heavy-rain conditions for {region['name']}.",
        ]
        if req.dam_release:
            items.append("Upstream reservoirs are assumed to be releasing, which affects villages flagged as downstream of a dam.")
        if req.high_tide:
            items.append("High tide is assumed to coincide with peak rainfall, blocking coastal outfalls.")
        return items

    @staticmethod
    def _caveats(base: RegionAssessment, scen: RegionAssessment, rain: RainfallInputs) -> list[str]:
        caveats = [
            "Village flood probabilities come from a transparent SCS-runoff + terrain susceptibility model "
            "on curated, approximate terrain data. They indicate relative exposure, not a calibrated hydrodynamic forecast.",
            "The fusion AI model predicts next-day heavy-rainfall probability. It was trained on Kerala, Mumbai, "
            "Chennai and Assam (2004-2024), and the extreme class has little training support.",
        ]
        if base.model and scen.model and rain.change_pct > 0 and scen.model.probability < base.model.probability:
            caveats.append(
                "The AI rainfall probability went down even though rain went up. This scenario is outside the "
                "rainfall range the tree-based model saw in training, so its output is unreliable here. The flood "
                "estimates rely mainly on the physically-based runoff model, which scales with rainfall."
            )
        if scen.model is None:
            caveats.append("The fusion model is not loaded, so a rainfall-only proxy replaced the AI signal.")
        if any(v["region"] == "Assam" for v, _ in scen.villages):
            caveats.append(
                "Assam floods are often driven by upstream Brahmaputra flows from Arunachal, Bhutan and Tibet, "
                "not local rain alone. Treat these results as a lower bound when upstream rivers are high."
            )
        return caveats
