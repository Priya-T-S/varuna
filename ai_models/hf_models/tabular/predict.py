"""
HuggingFace tabular model prediction CLI.

Mirrors the interface of ai_models.baseline.predict — same input fields,
same output structure — so the backend can swap models without changes.

CLI:
    backend/.venv/bin/python -m ai_models.hf_models.tabular.predict \\
        --model tabpfn \\
        --input '{"latitude": 10.0, "longitude": 76.3, "temperature_c": 26,
                  "humidity_pct": 92, "pressure_hpa": 1001, "wind_speed_ms": 9,
                  "cloud_cover_pct": 95}'
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ai_models.baseline.config import BaselineConfig
from ai_models.hf_models.registry import build_tabular_model, tabular_keys
from ai_models.hf_models.tabular.hf_tabular import (
    _FEATURE_NAMES,
    _LABEL_NAMES,
    _RISK_BY_CATEGORY,
)

logger = logging.getLogger(__name__)

# ── Input validation spec (same as baseline/predict.py) ──────────────────────
_INPUT_SPEC: dict[str, tuple[float, float, bool]] = {
    "latitude": (-90.0, 90.0, True),
    "longitude": (-180.0, 180.0, True),
    "temperature_c": (-60.0, 60.0, True),
    "humidity_pct": (0.0, 100.0, True),
    "pressure_hpa": (850.0, 1100.0, True),
    "wind_speed_ms": (0.0, 120.0, True),
    "cloud_cover_pct": (0.0, 100.0, True),
    "wind_direction_deg": (0.0, 360.0, False),
    "recent_rainfall_mm_1d": (0.0, 2000.0, False),
    "recent_rainfall_mm_3d": (0.0, 5000.0, False),
    "recent_rainfall_mm_7d": (0.0, 10000.0, False),
    "recent_rainfall_mm_30d": (0.0, 30000.0, False),
}

_HISTORY_TO_FEATURE = {
    "recent_rainfall_mm_1d": "rain_sum_1d",
    "recent_rainfall_mm_3d": "rain_sum_3d",
    "recent_rainfall_mm_7d": "rain_sum_7d",
    "recent_rainfall_mm_30d": "rain_sum_30d",
}


class InvalidInputError(ValueError):
    """Raised when prediction input is missing required fields or out of range."""


class ModelNotTrainedError(RuntimeError):
    """Raised when no saved artifact exists for the chosen model key."""


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------

class HFTabularPredictor:
    """Loads a trained HF tabular artifact once and serves predictions."""

    def __init__(self, model_key: str = "tabpfn", model_path: Path | None = None) -> None:
        config = BaselineConfig()
        from ai_models.hf_models.tabular.hf_tabular import _HF_TAB_BUNDLE_TEMPLATE

        artifact_dir = (
            model_path.parent if model_path else config.saved_models_dir
        )
        self._model = build_tabular_model(model_key)
        try:
            self._model.load(artifact_dir)
        except FileNotFoundError as exc:
            raise ModelNotTrainedError(str(exc)) from exc
        self._key = model_key
        logger.info("Loaded HF tabular model '%s' v%s", model_key, self._model.version)

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        values = self._validate(payload)
        features, assumed = self._build_features(values, payload.get("date"))

        proba = self._model.predict_proba_batch(
            np.array(list(features.values()), dtype=np.float64).reshape(1, -1)
        )[0]
        category = int(np.argmax(proba))
        max_p = float(proba.max())

        return {
            "prediction": _LABEL_NAMES[category],
            "category": category,
            "risk_score": round(float(proba[1:].sum()), 4),
            "class_probabilities": {
                _LABEL_NAMES[i]: round(float(p), 4) for i, p in enumerate(proba)
            },
            "confidence": _confidence(max_p, downgraded=bool(assumed)),
            "model": f"hf-tabular-{self._key}-{self._model.version}",
            "assumed_features": assumed,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    def _validate(self, payload: dict[str, Any]) -> dict[str, float]:
        if not isinstance(payload, dict):
            raise InvalidInputError("Input must be a JSON object")
        values: dict[str, float] = {}
        for field, (lo, hi, required) in _INPUT_SPEC.items():
            if field not in payload or payload[field] is None:
                if required:
                    raise InvalidInputError(f"Missing required field: {field}")
                continue
            try:
                value = float(payload[field])
            except (TypeError, ValueError) as exc:
                raise InvalidInputError(f"{field} is not numeric: {payload[field]!r}") from exc
            if math.isnan(value) or not (lo <= value <= hi):
                raise InvalidInputError(f"{field}={value} outside valid range [{lo}, {hi}]")
            values[field] = value
        return values

    def _build_features(
        self, values: dict[str, float], date: str | None
    ) -> tuple[dict[str, float], list[str]]:
        medians = self._model._feature_medians
        assumed: list[str] = []
        row: dict[str, float] = {}
        for name in _FEATURE_NAMES:
            if name in values:
                row[name] = values[name]
            elif name in ("season_sin", "season_cos"):
                row[name] = _season(name, date)
            elif name == "rain_trend_3d":
                row[name] = _trend(values, medians, assumed)
            else:
                history_key = next(
                    (k for k, v in _HISTORY_TO_FEATURE.items() if v == name), None
                )
                if history_key and history_key in values:
                    row[name] = values[history_key]
                else:
                    row[name] = float(medians.get(name, 0.0))
                    assumed.append(name)
        return row, assumed


# ---------------------------------------------------------------------------
# Feature helpers (mirrors baseline/predict.py)
# ---------------------------------------------------------------------------

def _season(component: str, date: str | None) -> float:
    try:
        when = datetime.fromisoformat(date) if date else datetime.now(timezone.utc)
    except ValueError as exc:
        raise InvalidInputError(f"Unparseable date: {date!r}") from exc
    angle = 2 * math.pi * when.timetuple().tm_yday / 365.25
    return math.sin(angle) if component == "season_sin" else math.cos(angle)


def _trend(values: dict[str, float], medians: dict[str, float], assumed: list[str]) -> float:
    if "recent_rainfall_mm_3d" in values and "recent_rainfall_mm_7d" in values:
        prev = max(values["recent_rainfall_mm_7d"] - values["recent_rainfall_mm_3d"], 0.0)
        return values["recent_rainfall_mm_3d"] - prev * (3.0 / 4.0)
    assumed.append("rain_trend_3d")
    return float(medians.get("rain_trend_3d", 0.0))


def _confidence(max_p: float, *, downgraded: bool) -> str:
    idx = 2 if max_p >= 0.75 else 1 if max_p >= 0.5 else 0
    if downgraded and idx > 0:
        idx -= 1
    return ["Low", "Medium", "High"][idx]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="HuggingFace tabular model rainfall prediction"
    )
    parser.add_argument("--input", required=True, help="JSON object with weather conditions")
    parser.add_argument(
        "--model",
        default="tabpfn",
        choices=tabular_keys(),
        help="HF tabular model key (default: tabpfn)",
    )
    parser.add_argument("--model-path", type=Path, default=None, help="Path to artifact file")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    try:
        payload = json.loads(args.input)
        result = HFTabularPredictor(model_key=args.model, model_path=args.model_path).predict(payload)
    except (InvalidInputError, ModelNotTrainedError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
