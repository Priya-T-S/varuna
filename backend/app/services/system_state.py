"""
Process-wide operational state:

* RiskSnapshotStore - the latest assessment per region (what the map and
  status panels show, and how fresh it is).
* Faults - demo switches that simulate failures (stale rainfall feed, AI model
  down, notification providers down) so fallback behaviour can be shown live.
* Monitor bookkeeping - when the background monitor last ran / failed.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# How old rainfall data may get before it is reported as delayed.
STALE_AFTER = timedelta(minutes=30)
# How far a simulated "stale feed" fault pushes the data age.
STALE_FAULT_AGE = timedelta(minutes=47)


@dataclass
class RegionSnapshot:
    region: str
    data_mode: str            # observed | climatology | demo | scenario | test
    data_as_of: datetime      # when the rainfall input was observed / entered
    assessed_at: datetime
    rain_event_mm: float
    duration_days: int
    rain_probability: float | None
    confidence_label: str | None
    villages: list[dict[str, Any]] = field(default_factory=list)  # id, name, district, lat, lon, band, probability, reasons


class _State:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshots: dict[str, RegionSnapshot] = {}
        self.faults: dict[str, bool] = {"rainfall_feed": False, "ai_model": False, "notifications": False}
        self.monitor_last_run: datetime | None = None
        self.monitor_last_error: str | None = None

    # --- snapshots ---------------------------------------------------------
    def put_snapshot(self, snap: RegionSnapshot) -> None:
        with self._lock:
            self._snapshots[snap.region] = snap

    def snapshots(self) -> list[RegionSnapshot]:
        with self._lock:
            return list(self._snapshots.values())

    def snapshot(self, region: str) -> RegionSnapshot | None:
        with self._lock:
            return self._snapshots.get(region)

    def data_age(self, snap: RegionSnapshot) -> timedelta:
        age = utcnow() - snap.data_as_of
        if self.faults["rainfall_feed"]:
            age = max(age, STALE_FAULT_AGE)
        return age

    def effective_as_of(self, snap: RegionSnapshot) -> datetime:
        return utcnow() - self.data_age(snap)

    # --- faults ------------------------------------------------------------
    def set_fault(self, component: str, enabled: bool) -> None:
        if component not in self.faults:
            raise KeyError(component)
        self.faults[component] = enabled

    def reset(self) -> None:
        with self._lock:
            self._snapshots.clear()
        for key in self.faults:
            self.faults[key] = False
        self.monitor_last_run = None
        self.monitor_last_error = None


state = _State()
