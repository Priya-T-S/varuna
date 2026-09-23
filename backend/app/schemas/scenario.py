"""Pydantic schemas for the what-if scenario simulator."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Antecedent = Literal["dry", "normal", "saturated"]
FloodBand = Literal["low", "moderate", "high", "severe"]


class ScenarioRequest(BaseModel):
    region: str = Field(..., description="Kerala | Mumbai | Chennai | Assam (a district name also resolves)")
    rainfall_change_pct: float | None = Field(
        None, ge=-90, le=500, description="Change vs. the region's reference heavy-rain spell, e.g. 20 for +20%"
    )
    rainfall_mm: float | None = Field(
        None, gt=0, le=2000, description="Absolute event rainfall over `duration_days` (overrides the % change)"
    )
    duration_days: int = Field(3, ge=1, le=10, description="Length of the rain spell")
    antecedent: Antecedent = Field("normal", description="Soil moisture before the spell")
    dam_release: bool = Field(False, description="Upstream reservoirs are releasing water")
    high_tide: bool = Field(False, description="Spring / high tide coincides with peak rain (coastal sites)")
    humidity_pct: float | None = Field(None, ge=0, le=100)
    cloud_cover_pct: float | None = Field(None, ge=0, le=100)
    district: str | None = Field(None, description="Restrict village results to one district")

    @model_validator(mode="after")
    def _default_change(self) -> "ScenarioRequest":
        if self.rainfall_change_pct is None and self.rainfall_mm is None:
            self.rainfall_change_pct = 0.0
        return self


class FactorContribution(BaseModel):
    factor: str
    label: str
    value: float = Field(..., description="Normalised factor intensity, 0-1")
    contribution: float = Field(..., description="Signed contribution to the flood log-odds")
    detail: str


class TimelinePoint(BaseModel):
    offset_h: int = Field(..., description="Hours from now: 0, 6, 12, 24, 48 (+ end of spell)")
    band: FloodBand
    probability: float
    beyond_window: bool = Field(False, description="End-of-spell point after +48 h")


class RecommendedAction(BaseModel):
    text: str
    priority: str
    owner: str


class VillageImpact(BaseModel):
    id: str
    name: str
    district: str
    region: str
    lat: float
    lon: float
    population: int
    baseline_probability: float
    flood_probability: float
    baseline_band: FloodBand
    band: FloodBand
    band_increased: bool
    runoff_mm: float
    expected_depth_m: float = Field(..., description="Indicative inundation depth for the scenario")
    landslide_risk: bool
    river_rise_m: float = Field(0.0, description="MODELLED river rise above normal (not a gauge reading)")
    factors: list[FactorContribution]
    reasons: list[str]
    timeline: list[TimelinePoint] = []


class DriverChange(BaseModel):
    feature: str
    label: str
    baseline_value: float | None
    scenario_value: float | None
    baseline_contribution: float
    scenario_contribution: float
    delta: float


class ModelRisk(BaseModel):
    probability: float = Field(..., description="Fusion-model P(heavy or extreme rain, next 24 h)")
    risk_level: str
    confidence: float
    confidence_label: str = Field("Low", description="High | Medium | Low")
    horizon_hours: int = 24
    class_probabilities: dict[str, float] = {}


class RainfallInputs(BaseModel):
    rain_1d_mm: float
    rain_3d_mm: float
    rain_7d_mm: float
    rain_30d_mm: float
    event_total_mm: float
    duration_days: int
    change_pct: float


class IncidentMatch(BaseModel):
    id: str
    name: str
    date: str
    region: str
    districts: list[str]
    villages: list[str]
    rainfall_mm: float
    rainfall_window_days: int
    deaths: int | None = None
    displaced: int | None = None
    causes: list[str]
    summary: str
    source: str
    similarity: float
    why_similar: list[str]


class ModelAnalogue(BaseModel):
    region: str
    date: str
    observed_rainfall_mm: float
    similarity_pct: float


class ScenarioSummary(BaseModel):
    villages_assessed: int
    villages_high_or_severe: int
    newly_at_risk: int
    population_at_risk: int
    districts_at_risk: list[str]
    headline: str


class ScenarioResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    region: str
    scenario: ScenarioRequest
    baseline_rain: RainfallInputs
    scenario_rain: RainfallInputs
    baseline_model: ModelRisk | None
    scenario_model: ModelRisk | None
    model_delta: float | None
    driver_changes: list[DriverChange]
    villages: list[VillageImpact]
    summary: ScenarioSummary
    timeline: list[TimelinePoint] = Field([], description="Worst village per step, Now to +48 h (hydrological projection)")
    actions: list[RecommendedAction] = []
    data_mode: str = "scenario"
    generated_at: str | None = None
    provenance: list[dict[str, Any]] = Field([], description="Which AI / rule components produced the scenario result")
    similar_incidents: list[IncidentMatch]
    model_analogues: list[ModelAnalogue]
    assumptions: list[str]
    caveats: list[str]
