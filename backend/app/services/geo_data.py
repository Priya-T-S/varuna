"""
Curated geo / hydrology reference data (data/geo/*.json).

Loaded once and cached. Every lookup is case-insensitive so names coming
from the chatbot ("kuttanad", "CHENNAI") resolve the same as UI input.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
# Overridable so a container can mount the data outside the source tree.
GEO_DIR = Path(os.environ.get("GEO_DATA_DIR") or REPO_ROOT / "data" / "geo")


class UnknownRegionError(ValueError):
    """Raised when a region name is not one of the monitored regions."""


def _load(name: str) -> dict[str, Any]:
    with open(GEO_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache
def regions() -> list[dict[str, Any]]:
    return _load("regions.json")["regions"]


@lru_cache
def villages() -> list[dict[str, Any]]:
    return _load("villages.json")["villages"]


@lru_cache
def incidents() -> list[dict[str, Any]]:
    return _load("flood_incidents.json")["incidents"]


def region_names() -> list[str]:
    return [r["name"] for r in regions()]


def get_region(name: str) -> dict[str, Any]:
    key = (name or "").strip().lower()
    for region in regions():
        if region["name"].lower() == key or region["state"].lower() == key:
            return region
    # Allow district names ("Alappuzha") to resolve to their region.
    for region in regions():
        if any(d["name"].lower() == key for d in region["districts"]):
            return region
    raise UnknownRegionError(
        f"Unknown region '{name}'. Monitored regions: {', '.join(region_names())}."
    )


def villages_in(region: str) -> list[dict[str, Any]]:
    canonical = get_region(region)["name"]
    return [v for v in villages() if v["region"] == canonical]


def find_village(name: str) -> dict[str, Any] | None:
    key = (name or "").strip().lower()
    if not key:
        return None
    exact = [v for v in villages() if v["name"].lower() == key or v["id"].lower() == key]
    if exact:
        return exact[0]
    partial = [v for v in villages() if key in v["name"].lower()]
    return partial[0] if partial else None


def district_info(region: str, district: str) -> dict[str, Any] | None:
    for d in get_region(region)["districts"]:
        if d["name"].lower() == district.lower():
            return d
    return None
