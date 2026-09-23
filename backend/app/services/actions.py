"""
Recommended actions for a flood warning: decision support for the
responsible officer, never automatic commands.

Base actions scale with the risk level; context-specific actions are added
for dam releases, high tide and landslide-prone terrain. The list always
ends with when to re-evaluate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REEVALUATE = {"severe": "30 minutes", "high": "1 hour", "moderate": "3 hours"}


@dataclass(frozen=True)
class ActionContext:
    dam_release: bool = False
    high_tide: bool = False
    landslide: bool = False
    dam_names: tuple[str, ...] = ()
    villages: tuple[str, ...] = ()


def _item(text: str, priority: str, owner: str) -> dict[str, Any]:
    return {"text": text, "priority": priority, "owner": owner}


def recommend(level: str, ctx: ActionContext | None = None) -> list[dict[str, Any]]:
    ctx = ctx or ActionContext()
    places = ", ".join(ctx.villages[:3])
    where = f" ({places})" if places else ""
    items: list[dict[str, Any]] = []

    if level == "severe":
        items += [
            _item("Activate the district Emergency Operations Centre", "immediate", "District Collector"),
            _item(f"Start evacuating low-lying wards{where}", "immediate", "Tahsildar / local body"),
            _item("Pre-position NDRF/SDRF teams and boats", "immediate", "District Collector"),
            _item("Open relief shelters and stock food, water and medicines", "immediate", "Revenue department"),
        ]
    elif level == "high":
        items += [
            _item(f"Alert village-level officials{where}", "immediate", "Tahsildar"),
            _item("Prepare evacuation shelters", "within 3 h", "Revenue department"),
            _item("Warn residents in low-lying areas", "within 3 h", "Local body / police"),
            _item("Clear drains and culverts at known choke points", "within 6 h", "Municipal engineering"),
        ]
    else:
        items += [
            _item(f"Inform village-level officials{where}", "within 6 h", "Tahsildar"),
            _item("Keep response teams on standby", "within 6 h", "District Disaster Management Authority"),
        ]

    items.append(_item("Monitor river gauges and rain gauges", "continuous", "Water resources department"))

    if ctx.dam_release:
        dams = ", ".join(ctx.dam_names[:2]) or "upstream reservoirs"
        items.append(_item(f"Coordinate release schedules with the {dams} dam authority", "immediate", "District Collector"))
    if ctx.high_tide:
        items.append(_item("Time evacuations and drainage pumping around the high-tide peak", "within 3 h", "Municipal engineering"))
    if ctx.landslide:
        items.append(_item("Move residents off steep, landslide-prone slopes", "immediate", "Tahsildar / geology cell"))

    items.append(_item(f"Re-evaluate the situation in {REEVALUATE.get(level, '3 hours')}", "scheduled", "Control room"))
    return items
