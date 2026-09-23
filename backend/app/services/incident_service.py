"""
Past-incident retrieval: "has something like this happened before?"

Ranks the curated flood catalogue (data/geo/flood_incidents.json) against a
scenario by region, rainfall intensity (compared per day so a 1-day and a
3-day event are comparable), cause overlap and village overlap. Every match
carries plain-language `why_similar` reasons.
"""

from __future__ import annotations

import math
from typing import Any

from app.schemas.scenario import IncidentMatch
from app.services import geo_data


def incident_label(name: str, date: str) -> str:
    """'Mumbai 26 July deluge (2005)', without doubling a year already in the name."""
    year = str(date)[:4]
    return name if year in name else f"{name} ({year})"


def scenario_causes(
    *, antecedent: str, dam_release: bool, high_tide: bool, daily_rain_mm: float
) -> set[str]:
    causes: set[str] = set()
    if daily_rain_mm >= 115:
        causes.add("extreme_rainfall")
    if antecedent == "saturated":
        causes.add("saturated_soil")
    if dam_release:
        causes.add("dam_release")
    if high_tide:
        causes.update({"high_tide", "backwater"})
    return causes


def find_similar(
    region: str,
    event_total_mm: float,
    duration_days: int,
    causes: set[str] | None = None,
    villages: list[str] | None = None,
    top_k: int = 3,
    include_other_regions: bool = True,
) -> list[IncidentMatch]:
    canonical = geo_data.get_region(region)["name"] if region else None
    causes = causes or set()
    village_set = {v.lower() for v in (villages or [])}
    daily = event_total_mm / max(duration_days, 1)

    scored: list[tuple[float, dict[str, Any], list[str]]] = []
    for inc in geo_data.incidents():
        same_region = inc["region"] == canonical
        if not same_region and not include_other_regions:
            continue
        why: list[str] = []

        inc_daily = inc["rainfall_mm"] / max(inc["rainfall_window_days"], 1)
        ratio = abs(math.log(max(daily, 1.0) / max(inc_daily, 1.0)))
        rain_sim = max(0.0, 1.0 - ratio / math.log(4.0))
        if rain_sim >= 0.6:
            why.append(
                f"comparable intensity (~{inc_daily:.0f} mm/day then vs ~{daily:.0f} mm/day now)"
            )

        shared = causes & set(inc["causes"])
        cause_sim = len(shared) / len(causes) if causes else 0.5
        if shared:
            why.append("same drivers: " + ", ".join(sorted(c.replace("_", " ") for c in shared)))

        overlap = village_set & {v.lower() for v in inc["villages"]}
        village_sim = min(len(overlap) / 3.0, 1.0)
        if overlap:
            names = [v for v in inc["villages"] if v.lower() in overlap][:3]
            why.append("hit the same places: " + ", ".join(names))

        if same_region:
            why.insert(0, f"same region ({inc['region']})")

        score = 0.35 * same_region + 0.35 * rain_sim + 0.15 * cause_sim + 0.15 * village_sim
        scored.append((score, inc, why))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        IncidentMatch(
            **{k: inc[k] for k in (
                "id", "name", "date", "region", "districts", "villages", "rainfall_mm",
                "rainfall_window_days", "deaths", "displaced", "causes", "summary", "source",
            )},
            similarity=round(score, 3),
            why_similar=why,
        )
        for score, inc, why in scored[:top_k]
    ]


def search(
    region: str | None = None,
    min_rainfall_mm: float | None = None,
    cause: str | None = None,
    village: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Filter-style lookup used by the chatbot's `search_past_incidents` tool."""
    canonical = geo_data.get_region(region)["name"] if region else None
    cause_key = cause.lower().replace(" ", "_") if cause else None
    out = []
    for inc in geo_data.incidents():
        if canonical and inc["region"] != canonical:
            continue
        if min_rainfall_mm and inc["rainfall_mm"] < min_rainfall_mm:
            continue
        if cause_key and not any(cause_key in c for c in inc["causes"]):
            continue
        if village and not any(village.lower() in v.lower() for v in inc["villages"]):
            continue
        out.append(inc)
    out.sort(key=lambda i: i["date"], reverse=True)
    return out[:limit]
