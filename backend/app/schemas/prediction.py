"""
Pydantic schemas defining the prediction API contract.

These are the single source of truth for what the frontend sends and
receives — model implementations (Phases 3–6) must conform to them.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Rainfall impact classification, aligned with IMD-style severity tiers."""

    LOW = "low"
    MODERATE = "moderate"
    HEAVY = "heavy"
    EXTREME = "extreme"


class GeoPoint(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class WeatherFeatures(BaseModel):
    """Meteorological inputs to the tabular model.

    All fields optional: when omitted, the service fetches the latest
    observed values for the location from the database (Phase 7).
    """

    temperature_c: float | None = Field(None, description="Surface air temperature, °C")
    humidity_pct: float | None = Field(None, ge=0, le=100, description="Relative humidity, %")
    pressure_hpa: float | None = Field(None, description="Mean sea-level pressure, hPa")
    wind_speed_ms: float | None = Field(None, ge=0, description="Wind speed, m/s")
    cloud_cover_pct: float | None = Field(None, ge=0, le=100, description="Total cloud cover, %")
    wind_direction_deg: float | None = Field(None, ge=0, le=360, description="Wind direction, degrees")
    rain_sum_1d: float | None = Field(None, ge=0, description="Rainfall accumulated over the past 24 h, mm")
    rain_sum_3d: float | None = Field(None, ge=0, description="Rainfall accumulated over the past 3 days, mm")
    rain_sum_7d: float | None = Field(None, ge=0, description="Rainfall accumulated over the past 7 days, mm")
    rain_sum_30d: float | None = Field(None, ge=0, description="Rainfall accumulated over the past 30 days, mm")
    rain_trend_3d: float | None = Field(None, description="3-day rainfall trend (slope of daily totals)")


class PredictionRequest(BaseModel):
    location: GeoPoint
    region_name: str | None = Field(None, description="Human-readable place name, e.g. 'Kerala'")
    horizon_hours: int = Field(12, ge=1, le=72, description="Forecast lead time in hours")
    weather: WeatherFeatures | None = None
    include_explanation: bool = Field(True, description="Attach SHAP/Grad-CAM explanation payload")
    satellite_image_b64: str | None = Field(None, description="Optional base64-encoded satellite image (PNG/JPEG)")


class FeatureAttribution(BaseModel):
    """One SHAP feature contribution, for the explanation panel."""

    feature: str
    value: float | None = Field(None, description="The input value the model saw")
    contribution: float = Field(..., description="Signed SHAP value (log-odds or probability units)")


class ImageExplanation(BaseModel):
    """Grad-CAM output for satellite-image-based predictions."""

    satellite_image_id: str
    heatmap_url: str = Field(..., description="URL of the Grad-CAM overlay rendered by the backend")
    description: str = Field(..., description="Plain-language summary of highlighted regions")


class HistoricalMatch(BaseModel):
    event: str
    region: str
    date: str
    observed_category: int
    observed_rainfall_mm: float
    similarity: float
    similarity_pct: float


class HistoricalExplanation(BaseModel):
    reference_events: int
    closest_match: HistoricalMatch | None = None
    matches: list[HistoricalMatch] = []
    notes: list[str] = []


class ConfidenceFactors(BaseModel):
    model_agreement: float | None = None
    historical_similarity: float | None = None
    data_quality: str
    data_quality_score: float


class ConfidenceExplanation(BaseModel):
    confidence_pct: float
    confidence: str
    factors: ConfidenceFactors
    components: dict[str, Any] = {}


class Explanation(BaseModel):
    feature_attributions: list[FeatureAttribution] = []
    image_explanation: ImageExplanation | None = None
    narrative: str = Field(
        "",
        description="Human-readable sentence explaining the main drivers of the prediction",
    )
    historical_explanation: HistoricalExplanation | None = None
    confidence_explanation: ConfidenceExplanation | None = None
    caveats: list[str] = []
    provenance: list[dict[str, Any]] = Field(
        [], description="Which component produced each part: trained / tuned / algorithmic / rule-based; ran / estimated / not_run"
    )


class PredictionResponse(BaseModel):
    location: GeoPoint
    region_name: str | None
    generated_at: datetime
    horizon_hours: int
    probability: float = Field(..., ge=0, le=1, description="Probability of a high-impact rain event")
    risk_level: RiskLevel
    confidence: float = Field(..., ge=0, le=1, description="Model confidence score")
    model_version: str
    explanation: Explanation | None = None


# ---------------------------------------------------------------------------
# Grad-CAM image explanation schema (separate endpoint)
# ---------------------------------------------------------------------------

class GradCamRegion(BaseModel):
    """One named high-attention region extracted from the Grad-CAM heatmap."""
    name: str
    bbox: list[float] = Field(
        ..., description="Normalised bounding box [x0, y0, x1, y1] in scene coordinates"
    )
    area_share: float = Field(..., description="Share of the whole scene this region covers")
    intensity: float = Field(..., description="Mean normalised attribution inside the region")
    position: str = Field(..., description="Plain-language position within the scene")


class GradCamResponse(BaseModel):
    """
    Real Grad-CAM explanation from the trained satellite CNN (satellite_model_v1.pt).

    The heatmap is returned as a base64-encoded PNG data URL so the browser
    can display it without a static file server.  Nothing here is synthesised:
    if the satellite model cannot process the supplied image, the endpoint
    raises 422.
    """
    source: str = Field(
        "real",
        description="Always 'real' — distinguishes from simulator Grad-CAM"
    )
    model_name: str
    model_version: str
    target_layer: str = Field(
        ..., description="Convolutional layer used for attribution (e.g. 'features.3')"
    )
    predicted_category: int
    class_probabilities: dict[str, float]
    satellite_risk_score: float
    high_influence_coverage: float
    coverage_label: str
    regions: list[GradCamRegion]
    #: Normalised heatmap encoded as a PNG data URL (data:image/png;base64,…)
    heatmap_data_url: str
    #: Side-by-side overlay (original scene + heatmap) as a PNG data URL
    overlay_data_url: str
    notes: list[str] = []

