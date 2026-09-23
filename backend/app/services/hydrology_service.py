"""
Village-level flood-susceptibility model.

The fusion model predicts *rainfall* (P of a heavy/extreme day). Whether a
place floods also depends on where the water goes, so this module turns a
rainfall scenario into a per-village flood probability with a transparent,
physically-motivated additive log-odds model:

    runoff    SCS Curve-Number runoff depth Q from event rainfall P, with the
              curve number set by soil type x built-up share and adjusted for
              antecedent moisture (AMC I / II / III). Runoff only counts in
              proportion to how well the terrain lets water accumulate.
    terrain   Height Above Nearest Drainage (HAND), river distance and slope.
    drainage  Storm-water / natural drainage capacity class.
    history   How often the place has flooded since 2000.
    rain_model  Fusion-model probability of heavy rain in the next 24 h.
    dam / tide  Upstream reservoir release, tidal backwater blocking outfalls.

Each term's coefficient x intensity is its contribution to the log-odds, so
the breakdown answers "which factor drives the risk here" exactly - the same
reading as a SHAP bar chart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.schemas.scenario import FactorContribution, FloodBand

# Pervious-surface curve numbers (hydrologic soil groups A..D, fair cover).
_SOIL_CN = {"sandy": 55.0, "loam": 69.0, "laterite": 72.0, "alluvial": 78.0, "clay": 84.0}
_IMPERVIOUS_CN = 98.0
_DRAINAGE = {"poor": 1.0, "moderate": 0.5, "good": 0.15}

INTERCEPT = -5.4
COEF = {
    "runoff": 3.4,
    "terrain": 2.4,
    "drainage": 1.3,
    "history": 0.8,
    "rain_model": 1.0,
    "dam_release": 1.4,
    "high_tide": 1.0,
}
LABELS = {
    "runoff": "Surface runoff",
    "terrain": "Low-lying terrain",
    "drainage": "Drainage capacity",
    "history": "Flood history",
    "rain_model": "AI rainfall signal",
    "dam_release": "Dam release upstream",
    "high_tide": "High tide / backwater",
}
BAND_ORDER: dict[str, int] = {"low": 0, "moderate": 1, "high": 2, "severe": 3}


@dataclass(frozen=True)
class RainEvent:
    total_mm: float
    duration_days: int
    antecedent: str = "normal"   # dry | normal | saturated
    rain_model_probability: float = 0.0
    dam_release: bool = False
    high_tide: bool = False


@dataclass
class Assessment:
    probability: float
    band: FloodBand
    runoff_mm: float
    depth_m: float
    landslide_risk: bool
    factors: list[FactorContribution]
    reasons: list[str]


# ---------------------------------------------------------------------------
def band_for(probability: float) -> FloodBand:
    if probability < 0.25:
        return "low"
    if probability < 0.5:
        return "moderate"
    if probability < 0.75:
        return "high"
    return "severe"


def curve_number(village: dict[str, Any], antecedent: str) -> float:
    pervious = _SOIL_CN.get(village.get("soil_type", "loam"), 70.0)
    urban = float(village.get("urban_fraction", 0.0))
    cn = urban * _IMPERVIOUS_CN + (1.0 - urban) * pervious
    if antecedent == "dry":        # AMC I
        cn = 4.2 * cn / (10.0 - 0.058 * cn)
    elif antecedent == "saturated":  # AMC III
        cn = 23.0 * cn / (10.0 + 0.13 * cn)
    return max(30.0, min(99.0, cn))


def scs_runoff(rain_mm: float, cn: float) -> float:
    """SCS-CN direct runoff depth (mm) for event rainfall `rain_mm`."""
    s = 25.4 * (1000.0 / cn - 10.0)
    ia = 0.2 * s
    if rain_mm <= ia:
        return 0.0
    return (rain_mm - ia) ** 2 / (rain_mm - ia + s)


def terrain_exposure(village: dict[str, Any]) -> float:
    hand = max(0.0, float(village.get("hand_m", 5.0)))
    dist = max(0.0, float(village.get("dist_to_river_km", 2.0)))
    slope = max(0.0, float(village.get("slope_pct", 2.0)))
    return (
        0.55 * math.exp(-hand / 3.0)
        + 0.30 * math.exp(-dist / 1.5)
        + 0.15 * (1.0 - min(slope, 15.0) / 15.0)
    )


# ---------------------------------------------------------------------------
def assess(village: dict[str, Any], event: RainEvent) -> Assessment:
    cn = curve_number(village, event.antecedent)
    runoff_mm = scs_runoff(event.total_mm, cn)
    runoff_intensity = 1.0 - math.exp(-runoff_mm / 120.0)
    terrain = terrain_exposure(village)
    drainage = _DRAINAGE.get(village.get("drainage_class", "moderate"), 0.5)
    history = min(float(village.get("flood_history_count", 0)) / 6.0, 1.0)
    dam = 1.0 if (event.dam_release and village.get("downstream_of_dam")) else 0.0
    tide = 1.0 if (event.high_tide and village.get("coastal")) else 0.0
    rain_model = max(0.0, min(1.0, event.rain_model_probability))

    # Runoff only floods a place where the terrain lets water pond.
    runoff_effective = runoff_intensity * (0.4 + 0.6 * terrain)

    values = {
        "runoff": runoff_effective,
        "terrain": terrain,
        "drainage": drainage,
        "history": history,
        "rain_model": rain_model,
        "dam_release": dam,
        "high_tide": tide,
    }
    contributions = {k: COEF[k] * v for k, v in values.items()}
    z = INTERCEPT + sum(contributions.values())
    probability = 1.0 / (1.0 + math.exp(-z))

    depth = (runoff_mm / 1000.0) * (1.0 + 10.0 * terrain)
    depth *= 1.0 + 0.3 * dam + 0.2 * tide
    depth = round(min(depth, 4.0), 2) if probability >= 0.25 else 0.0

    slope = float(village.get("slope_pct", 0.0))
    landslide_threshold = 120.0 if event.antecedent == "saturated" else 150.0
    landslide = slope >= 15.0 and event.total_mm >= landslide_threshold

    details = _factor_details(village, event, cn, runoff_mm, terrain, rain_model)
    factors = [
        FactorContribution(
            factor=k,
            label=LABELS[k],
            value=round(values[k], 3),
            contribution=round(contributions[k], 3),
            detail=details[k],
        )
        for k in COEF
    ]
    factors.sort(key=lambda f: f.contribution, reverse=True)
    reasons = [f.detail for f in factors if f.contribution >= 0.5][:4]
    if landslide:
        reasons.append(
            f"Steep slopes ({slope:.0f}%) with {event.total_mm:.0f} mm of rain: landslide / debris-flow risk "
            "even where standing floodwater is unlikely."
        )

    return Assessment(
        probability=round(probability, 4),
        band=band_for(probability),
        runoff_mm=round(runoff_mm, 1),
        depth_m=depth,
        landslide_risk=landslide,
        factors=factors,
        reasons=reasons,
    )


TIMELINE_STEPS_H = (0, 6, 12, 24, 48)
# Recession time constant after rain stops (h): poorly drained land holds water longer.
_RECESSION_H = {"poor": 36.0, "moderate": 18.0, "good": 8.0}


def river_rise_m(village: dict[str, Any], event: RainEvent) -> float:
    """MODELLED river-stage rise above normal (m), not a gauge reading.

    Runoff depth scaled by how strongly the site is coupled to its river
    (distance) plus the effect of upstream releases; capped at 6 m.
    """
    runoff = scs_runoff(event.total_mm, curve_number(village, event.antecedent))
    dist = max(0.0, float(village.get("dist_to_river_km", 2.0)))
    rise = (runoff / 1000.0) * (4.0 + 6.0 * math.exp(-dist / 2.0))
    if event.dam_release and village.get("downstream_of_dam"):
        rise *= 1.4
    return round(min(rise, 6.0), 1)


def project_timeline(
    village: dict[str, Any],
    event: RainEvent,
    steps: tuple[int, ...] = TIMELINE_STEPS_H,
    prior_mm: float | None = None,
) -> list[dict[str, Any]]:
    """Flood risk at Now, +6 h, +12 h, +24 h, +48 h (plus the end of the spell
    when that falls later, flagged `beyond_window`).

    The spell's rain falls evenly from now over `duration_days`, on top of the
    rain already fallen (`prior_mm`, default a fifth of a day's rain: the
    spell has just begun). Once it stops, the effective water depth recedes
    exponentially with a time constant set by drainage. Each step is scored
    with `assess()`, so the peak equals the alert's own assessment.
    """
    duration_h = max(event.duration_days, 1) * 24.0
    daily = event.total_mm / max(event.duration_days, 1)
    prior = 0.2 * daily if prior_mm is None else prior_mm
    tau = _RECESSION_H.get(village.get("drainage_class", "moderate"), 18.0)
    all_steps = list(steps)
    if duration_h > max(steps):
        all_steps.append(int(duration_h))
    points = []
    for t in all_steps:
        if t <= duration_h:
            effective = prior + event.total_mm * (t / duration_h)
        else:
            effective = (prior + event.total_mm) * math.exp(-(t - duration_h) / tau)
        a = assess(village, RainEvent(
            total_mm=max(effective, 0.0),
            duration_days=event.duration_days,
            antecedent=event.antecedent,
            rain_model_probability=event.rain_model_probability,
            dam_release=event.dam_release,
            high_tide=event.high_tide,
        ))
        point = {"offset_h": t, "band": a.band, "probability": a.probability}
        if t > max(steps):
            point["beyond_window"] = True
        points.append(point)
    return points


def worst_timeline(timelines: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Element-wise worst case across several villages' timelines."""
    if not timelines:
        return []
    out = []
    for step in zip(*timelines):
        worst = dict(max(step, key=lambda p: p["probability"]))
        out.append(worst)
    return out


def _factor_details(
    village: dict[str, Any], event: RainEvent, cn: float, runoff_mm: float, terrain: float, rain_model: float
) -> dict[str, str]:
    soil = village.get("soil_type", "loam")
    urban_pct = round(float(village.get("urban_fraction", 0)) * 100)
    share = (runoff_mm / event.total_mm * 100.0) if event.total_mm > 0 else 0.0
    moisture = {"dry": "dry", "normal": "normally moist", "saturated": "already saturated"}[event.antecedent]
    dam_name = village.get("downstream_of_dam")
    return {
        "runoff": (
            f"{runoff_mm:.0f} mm of the {event.total_mm:.0f} mm rain ({share:.0f}%) runs off: "
            f"{soil} soil, {urban_pct}% built-up, {moisture} ground (curve number {cn:.0f})."
        ),
        "terrain": (
            f"Only {village.get('hand_m')} m above the nearest drainage channel, "
            f"{village.get('dist_to_river_km')} km from the {village.get('river_name')}, "
            f"{village.get('slope_pct')}% slope (exposure {terrain:.2f})."
        ),
        "drainage": f"{str(village.get('drainage_class', 'moderate')).capitalize()} drainage capacity.",
        "history": f"Flooded about {village.get('flood_history_count', 0)} times since 2000.",
        "rain_model": f"VARUNA fusion model gives {rain_model:.0%} chance of heavy rain in the next 24 h.",
        "dam_release": (
            f"Downstream of {dam_name}; releases add river flow." if dam_name and event.dam_release
            else (f"Downstream of {dam_name} (no release assumed)." if dam_name else "No upstream reservoir.")
        ),
        "high_tide": (
            "High tide blocks storm-water outfalls to the sea / backwaters." if village.get("coastal") and event.high_tide
            else ("Tidal outfall (no high tide assumed)." if village.get("coastal") else "Not tidally influenced.")
        ),
    }
